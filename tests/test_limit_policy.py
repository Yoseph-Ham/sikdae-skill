"""한도 결정 로직 테스트 — 우선순위, 날짜 구간, 출처 추적."""

import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from limit_policy import (  # noqa: E402
    load_policy,
    BUILTIN_DEFAULT_LIMIT,
    SOURCE_CHAT,
    SOURCE_ARG,
    SOURCE_CONFIG_HISTORY,
    SOURCE_CONFIG_DEFAULT,
    SOURCE_BUILTIN,
)
from test_support import run_test_classes  # noqa: E402


def _write_config(payload) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


HISTORY_CONFIG = {
    "daily_limit": {
        "default": 15000,
        "history": [
            {"from": "2025-01-01", "amount": 15000, "note": "2025년 규정"},
            {"from": "2026-07-01", "amount": 20000, "note": "2026-07 인상"},
        ],
    }
}


class TestDateBrackets:
    """영수증 사용일자가 속한 구간의 한도가 적용되어야 한다."""

    def test_date_before_any_bracket_uses_default(self):
        path = _write_config(HISTORY_CONFIG)
        policy = load_policy(config_path=path)
        d = policy.for_date(date(2024, 6, 1))
        assert d.amount == 15000, d.amount
        assert d.source == SOURCE_CONFIG_DEFAULT, d.source

    def test_date_in_first_bracket(self):
        path = _write_config(HISTORY_CONFIG)
        d = load_policy(config_path=path).for_date(date(2026, 6, 30))
        assert d.amount == 15000, d.amount
        assert d.source == SOURCE_CONFIG_HISTORY, d.source
        assert "2025-01-01" in d.detail, d.detail

    def test_bracket_boundary_is_inclusive(self):
        """from 당일부터 새 한도가 적용된다."""
        path = _write_config(HISTORY_CONFIG)
        d = load_policy(config_path=path).for_date(date(2026, 7, 1))
        assert d.amount == 20000, d.amount

    def test_date_in_latest_bracket(self):
        path = _write_config(HISTORY_CONFIG)
        d = load_policy(config_path=path).for_date(date(2026, 8, 15))
        assert d.amount == 20000, d.amount
        assert "2026-07-01" in d.detail, d.detail

    def test_past_receipts_not_retroactively_recalculated(self):
        """규정 인상 후에도 과거 영수증은 과거 한도로 계산된다 (핵심 요구사항)."""
        path = _write_config(HISTORY_CONFIG)
        policy = load_policy(config_path=path)
        old = policy.for_date(date(2026, 6, 15))
        new = policy.for_date(date(2026, 7, 15))
        assert old.amount == 15000, old.amount
        assert new.amount == 20000, new.amount

    def test_unreadable_date_falls_back_to_default(self):
        path = _write_config(HISTORY_CONFIG)
        d = load_policy(config_path=path).for_date(None)
        assert d.amount == 15000, d.amount
        assert d.source == SOURCE_CONFIG_DEFAULT, d.source
        assert "미판독" in d.detail, d.detail

    def test_unsorted_history_is_sorted(self):
        path = _write_config({
            "daily_limit": {
                "default": 10000,
                "history": [
                    {"from": "2026-07-01", "amount": 20000},
                    {"from": "2025-01-01", "amount": 15000},
                ],
            }
        })
        policy = load_policy(config_path=path)
        assert policy.for_date(date(2026, 3, 1)).amount == 15000
        assert policy.for_date(date(2026, 9, 1)).amount == 20000

    def test_broken_history_entry_is_skipped_not_fatal(self):
        path = _write_config({
            "daily_limit": {
                "default": 15000,
                "history": [
                    {"from": "not-a-date", "amount": 99999},
                    {"from": "2026-07-01", "amount": 20000},
                ],
            }
        })
        policy = load_policy(config_path=path)
        assert policy.for_date(date(2026, 8, 1)).amount == 20000


class TestPriority:
    """대화 지시 > 실행 인자 > config."""

    def test_arg_beats_config(self):
        path = _write_config(HISTORY_CONFIG)
        d = load_policy(arg_limit=18000, config_path=path).for_date(date(2026, 7, 15))
        assert d.amount == 18000, d.amount
        assert d.source == SOURCE_ARG, d.source

    def test_chat_beats_arg(self):
        path = _write_config(HISTORY_CONFIG)
        d = load_policy(chat_limit=20000, arg_limit=18000, config_path=path).for_date(date(2026, 7, 15))
        assert d.amount == 20000, d.amount
        assert d.source == SOURCE_CHAT, d.source
        assert "대화" in d.detail, d.detail

    def test_chat_beats_config_history(self):
        path = _write_config(HISTORY_CONFIG)
        d = load_policy(chat_limit=20000, config_path=path).for_date(date(2026, 1, 5))
        assert d.amount == 20000, d.amount

    def test_override_applies_to_every_date(self):
        """오버라이드는 회차 전체에 일괄 적용된다 — 날짜별로 갈리지 않는다."""
        path = _write_config(HISTORY_CONFIG)
        policy = load_policy(chat_limit=20000, config_path=path)
        assert policy.has_override
        for day in [date(2025, 3, 1), date(2026, 6, 30), date(2026, 7, 1), None]:
            assert policy.for_date(day).amount == 20000, day

    def test_no_override_flag(self):
        path = _write_config(HISTORY_CONFIG)
        assert not load_policy(config_path=path).has_override


class TestConfigFallback:
    """config 가 없거나 깨져도 동작해야 한다."""

    def test_missing_config_uses_builtin_default(self):
        policy = load_policy(config_path=os.path.join(tempfile.gettempdir(), "no_such_config_12345.json"))
        d = policy.for_date(date(2026, 7, 1))
        assert d.amount == BUILTIN_DEFAULT_LIMIT, d.amount
        assert d.source == SOURCE_BUILTIN, d.source
        assert policy.config_path is None

    def test_corrupt_config_reports_error_and_falls_back(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        policy = load_policy(config_path=path)
        assert policy.config_error is not None, "깨진 config 를 조용히 넘기면 안 된다"
        assert policy.for_date(date(2026, 7, 1)).amount == BUILTIN_DEFAULT_LIMIT

    def test_corrupt_config_not_described_as_missing(self):
        """파일이 '깨진' 것과 '없는' 것은 구분해서 알려야 한다.

        깨진 config 를 '없음'이라고 하면 사용자가 있지도 않은 파일을 찾으러 다닌다.
        """
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ broken")
        detail = load_policy(config_path=path).for_date(date(2026, 7, 1)).detail
        assert "없음" not in detail, detail
        assert "읽지 못함" in detail, detail

    def test_missing_config_described_as_missing(self):
        missing = os.path.join(tempfile.gettempdir(), "definitely_not_here_98765.json")
        detail = load_policy(config_path=missing).for_date(date(2026, 7, 1)).detail
        assert "없음" in detail, detail

    def test_config_without_history_uses_default(self):
        path = _write_config({"daily_limit": {"default": 17000}})
        d = load_policy(config_path=path).for_date(date(2026, 7, 1))
        assert d.amount == 17000, d.amount
        assert d.source == SOURCE_CONFIG_DEFAULT, d.source

    def test_env_var_override_of_config_path(self):
        path = _write_config({"daily_limit": {"default": 21000}})
        os.environ["SIKDAE_LIMIT_CONFIG"] = path
        try:
            assert load_policy().for_date(date(2026, 7, 1)).amount == 21000
        finally:
            del os.environ["SIKDAE_LIMIT_CONFIG"]


class TestDescribe:
    def test_describe_includes_amount_and_source(self):
        path = _write_config(HISTORY_CONFIG)
        text = load_policy(config_path=path).for_date(date(2026, 7, 15)).describe()
        assert "20,000원" in text, text
        assert "출처" in text, text


if __name__ == "__main__":
    ok = run_test_classes(TestDateBrackets, TestPriority, TestConfigFallback, TestDescribe)
    sys.exit(0 if ok else 1)
