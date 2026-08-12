"""일 한도 결정 로직.

한도는 코드에 하드코딩하지 않는다. 아래 우선순위로 결정되며,
결정된 값과 **그 값이 어디서 왔는지(출처)** 를 항상 함께 돌려준다.

    1. 대화 지시      — 사용자가 대화로 "이번엔 2만원" 이라고 지시한 경우
    2. 실행 인자      — --daily-limit
    3. config history — 영수증 사용일자가 속한 날짜 구간의 한도
    4. config default — 구간에 안 걸리는 날짜 / 사용일자 미판독 건
    5. 내장 기본값    — config.json 이 아예 없거나 읽을 수 없을 때

1·2번은 회차 전체에 일괄 적용되고, 3번은 영수증마다 사용일자에 따라 달라진다.
그래서 한도는 "회차 단위 상수"가 아니라 `LimitPolicy.for_date(d)` 로 조회한다.
"""

import json
import os
from dataclasses import dataclass
from datetime import date

# config.json 이 없을 때만 쓰이는 최후의 폴백. config.json 의 default 가 있으면 그쪽이 이긴다.
BUILTIN_DEFAULT_LIMIT = 15_000

# 출처 식별자 — 화면 출력 문구와 프로그램 판별용 값을 분리해 둔다.
SOURCE_CHAT = "chat"
SOURCE_ARG = "arg"
SOURCE_CONFIG_HISTORY = "config-history"
SOURCE_CONFIG_DEFAULT = "config-default"
SOURCE_BUILTIN = "builtin-default"


def _config_path(explicit: str | None = None) -> str:
    """config.json 경로. 환경변수 > 스킬 폴더 기본 위치 순."""
    if explicit:
        return explicit
    override = os.environ.get("SIKDAE_LIMIT_CONFIG")
    if override:
        return override
    # scripts/limit_policy.py 기준 한 단계 위 = 스킬 루트
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


@dataclass(frozen=True)
class LimitDecision:
    """한 건(또는 한 회차)에 적용된 한도와 그 근거."""

    amount: int
    source: str
    detail: str  # 사람이 읽을 출처 설명

    def describe(self) -> str:
        return f"{self.amount:,}원 (출처: {self.detail})"


@dataclass(frozen=True)
class _Bracket:
    start: date
    amount: int
    note: str


class LimitPolicy:
    """한도 조회기. `for_date()` 로 영수증 날짜별 한도를 얻는다."""

    def __init__(
        self,
        default_limit: int,
        brackets: list[_Bracket],
        default_source: str,
        override: int | None = None,
        override_source: str | None = None,
        config_path: str | None = None,
        config_error: str | None = None,
    ):
        self._default_limit = default_limit
        self._brackets = sorted(brackets, key=lambda b: b.start)
        self._default_source = default_source
        self._override = override
        self._override_source = override_source
        self.config_path = config_path
        self.config_error = config_error

    @property
    def has_override(self) -> bool:
        return self._override is not None

    def for_date(self, receipt_date: date | None) -> LimitDecision:
        """해당 사용일자에 적용할 한도를 결정한다.

        사용일자가 없으면(판독 실패) 구간을 특정할 수 없으므로 기본값을 쓴다.
        """
        # 1·2순위: 회차 전체에 일괄 적용되는 오버라이드
        if self._override is not None:
            label = "대화 지시" if self._override_source == SOURCE_CHAT else "실행 인자 --daily-limit"
            return LimitDecision(self._override, self._override_source, label)

        # 3순위: 날짜 구간
        if receipt_date is not None:
            matched = None
            for bracket in self._brackets:
                if bracket.start <= receipt_date:
                    matched = bracket
                else:
                    break  # 정렬돼 있으므로 더 볼 필요 없음
            if matched is not None:
                detail = f"config.json 구간 {matched.start.isoformat()}~"
                if matched.note:
                    detail += f" ({matched.note})"
                return LimitDecision(matched.amount, SOURCE_CONFIG_HISTORY, detail)

        # 4·5순위: 기본값
        detail = (
            "config.json 기본값"
            if self._default_source == SOURCE_CONFIG_DEFAULT
            else "내장 기본값 (config.json 없음)"
        )
        if receipt_date is None:
            detail += " — 사용일자 미판독이라 구간 적용 불가"
        return LimitDecision(self._default_limit, self._default_source, detail)


def _parse_brackets(raw_history) -> list[_Bracket]:
    brackets = []
    if not isinstance(raw_history, list):
        return brackets
    for entry in raw_history:
        if not isinstance(entry, dict):
            continue
        try:
            start = date.fromisoformat(str(entry["from"]))
            amount = int(entry["amount"])
        except (KeyError, ValueError, TypeError):
            # 항목 하나가 깨졌다고 나머지 구간까지 버리지 않는다.
            continue
        if amount < 0:
            continue
        brackets.append(_Bracket(start=start, amount=amount, note=str(entry.get("note", ""))))
    return brackets


def load_policy(
    chat_limit: int | None = None,
    arg_limit: int | None = None,
    config_path: str | None = None,
) -> LimitPolicy:
    """config 를 읽고 오버라이드를 얹어 한도 조회기를 만든다.

    chat_limit 이 주어지면 arg_limit 보다 우선한다 (대화 지시 > 실행 인자).
    """
    override = None
    override_source = None
    if chat_limit is not None:
        override, override_source = chat_limit, SOURCE_CHAT
    elif arg_limit is not None:
        override, override_source = arg_limit, SOURCE_ARG

    path = _config_path(config_path)
    default_limit = BUILTIN_DEFAULT_LIMIT
    default_source = SOURCE_BUILTIN
    brackets: list[_Bracket] = []
    config_error = None

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            section = data.get("daily_limit") or {}
            raw_default = section.get("default")
            if raw_default is not None:
                default_limit = int(raw_default)
                default_source = SOURCE_CONFIG_DEFAULT
            brackets = _parse_brackets(section.get("history"))
        except (json.JSONDecodeError, OSError, ValueError, TypeError, AttributeError) as e:
            # config 가 깨졌다고 실행을 막지는 않되, 조용히 넘어가지도 않는다.
            config_error = f"{path} 를 읽지 못해 내장 기본값을 사용합니다 ({e})"
            default_limit = BUILTIN_DEFAULT_LIMIT
            default_source = SOURCE_BUILTIN
            brackets = []

    return LimitPolicy(
        default_limit=default_limit,
        brackets=brackets,
        default_source=default_source,
        override=override,
        override_source=override_source,
        config_path=path if os.path.exists(path) else None,
        config_error=config_error,
    )
