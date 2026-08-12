"""판정 로직 테스트 — 일자별 합산/한도, 초과분 분리, 확인 필요 분류."""

import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from models import ReceiptData  # noqa: E402
from expense_processor import process_receipts  # noqa: E402
from limit_policy import load_policy  # noqa: E402
from test_support import run_test_classes  # noqa: E402


def _policy(default=15000, history=None, chat=None, arg=None):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"daily_limit": {"default": default, "history": history or []}}, f)
    return load_policy(chat_limit=chat, arg_limit=arg, config_path=path)


def R(day, merchant, amount, src="x.png"):
    return ReceiptData(
        date=date.fromisoformat(day) if day else None,
        merchant=merchant,
        amount=amount,
        source_file=src,
    )


class TestDailyLimit:
    def test_single_receipt_under_limit_fully_claimed(self):
        result = process_receipts([R("2026-07-02", "행복분식", 9000)], _policy())
        row = result.rows[0]
        assert row.claimed == 9000, row.claimed
        assert row.excess == 0, row.excess
        assert row.amount == 9000, row.amount

    def test_single_receipt_over_limit_splits_excess(self):
        result = process_receipts([R("2026-07-02", "행복분식", 22000)], _policy(default=15000))
        row = result.rows[0]
        assert row.claimed == 15000, row.claimed
        assert row.excess == 7000, row.excess
        assert row.amount == 22000, "원 결제금액은 절대 덮어쓰지 않는다"

    def test_same_day_receipts_are_summed_then_capped(self):
        result = process_receipts(
            [R("2026-07-02", "A", 10000), R("2026-07-02", "B", 9000)],
            _policy(default=15000),
        )
        assert result.total_claimed == 15000, result.total_claimed
        assert result.total_excess == 4000, result.total_excess
        assert result.total_original == 19000, result.total_original

    def test_same_day_third_receipt_fully_excess(self):
        result = process_receipts(
            [R("2026-07-02", "A", 15000), R("2026-07-02", "B", 5000)],
            _policy(default=15000),
        )
        rows = result.rows
        assert rows[0].claimed == 15000, rows[0].claimed
        assert rows[1].claimed == 0, rows[1].claimed
        assert rows[1].excess == 5000, rows[1].excess

    def test_unused_limit_does_not_carry_over(self):
        result = process_receipts(
            [R("2026-07-02", "A", 5000), R("2026-07-03", "B", 20000)],
            _policy(default=15000),
        )
        by_date = {r.date: r for r in result.rows}
        assert by_date[date(2026, 7, 3)].claimed == 15000, "전날 미사용분이 이월되면 안 된다"
        assert by_date[date(2026, 7, 3)].excess == 5000

    def test_different_days_are_independent(self):
        result = process_receipts(
            [R("2026-07-02", "A", 15000), R("2026-07-03", "B", 15000)],
            _policy(default=15000),
        )
        assert result.total_claimed == 30000, result.total_claimed
        assert result.total_excess == 0, result.total_excess

    def test_excess_noted_in_remarks(self):
        result = process_receipts([R("2026-07-02", "A", 20000)], _policy(default=15000))
        assert "한도 초과" in result.rows[0].note, result.rows[0].note


class TestDateBracketApplied:
    """날짜 구간별로 다른 한도가 실제 판정에 반영되는지."""

    HISTORY = [
        {"from": "2025-01-01", "amount": 15000},
        {"from": "2026-07-01", "amount": 20000},
    ]

    def test_receipts_across_rule_change_use_own_bracket(self):
        result = process_receipts(
            [R("2026-06-20", "구규정", 20000), R("2026-07-20", "신규정", 20000)],
            _policy(history=self.HISTORY),
        )
        by_date = {r.date: r for r in result.rows}
        assert by_date[date(2026, 6, 20)].claimed == 15000, "과거분은 옛 한도"
        assert by_date[date(2026, 6, 20)].excess == 5000
        assert by_date[date(2026, 7, 20)].claimed == 20000, "이후분은 새 한도"
        assert by_date[date(2026, 7, 20)].excess == 0

    def test_limits_applied_records_each_date(self):
        result = process_receipts(
            [R("2026-06-20", "A", 5000), R("2026-07-20", "B", 5000)],
            _policy(history=self.HISTORY),
        )
        assert result.limits_applied[date(2026, 6, 20)].amount == 15000
        assert result.limits_applied[date(2026, 7, 20)].amount == 20000

    def test_row_carries_its_limit_and_source(self):
        result = process_receipts([R("2026-07-20", "A", 5000)], _policy(history=self.HISTORY))
        row = result.rows[0]
        assert row.daily_limit == 20000, row.daily_limit
        assert "2026-07-01" in row.limit_source, row.limit_source

    def test_chat_override_wins_over_bracket(self):
        result = process_receipts(
            [R("2026-06-20", "A", 25000)],
            _policy(history=self.HISTORY, chat=20000),
        )
        assert result.rows[0].claimed == 20000, result.rows[0].claimed


class TestNeedsReview:
    """읽지 못한 값을 임의로 채우지 않고 '확인 필요'로 분리한다."""

    def test_missing_date_is_review(self):
        result = process_receipts([R(None, "행복분식", 9000)], _policy())
        row = result.rows[0]
        assert row.needs_review is True
        assert "사용일자 미판독" in row.note, row.note

    def test_missing_amount_is_review(self):
        result = process_receipts([R("2026-07-02", "행복분식", None)], _policy())
        row = result.rows[0]
        assert row.needs_review is True
        assert "금액 미판독" in row.note, row.note

    def test_missing_amount_is_not_zero(self):
        result = process_receipts([R("2026-07-02", "행복분식", None)], _policy())
        assert result.rows[0].amount is None, "금액 미판독을 0으로 채우면 안 된다"

    def test_review_rows_excluded_from_limit_math(self):
        result = process_receipts(
            [R("2026-07-02", "A", 9000), R("2026-07-02", "B", None), R(None, "C", 9000)],
            _policy(default=15000),
        )
        assert result.total_claimed == 9000, "확인 필요 건은 합계에 들어가면 안 된다"
        assert len(result.review_rows) == 2, len(result.review_rows)
        assert len(result.claimed_rows) == 1

    def test_review_row_does_not_consume_daily_limit(self):
        """같은 날 확인필요 건이 있어도 정상 건의 한도를 갉아먹지 않는다."""
        result = process_receipts(
            [R("2026-07-02", "A", None), R("2026-07-02", "B", 15000)],
            _policy(default=15000),
        )
        good = [r for r in result.rows if not r.needs_review][0]
        assert good.claimed == 15000, good.claimed
        assert good.excess == 0, good.excess

    def test_review_rows_placed_last(self):
        result = process_receipts(
            [R(None, "미상", 9000), R("2026-07-02", "A", 9000)],
            _policy(),
        )
        assert result.rows[-1].needs_review is True
        assert result.rows[0].needs_review is False

    def test_both_missing_lists_both_reasons(self):
        result = process_receipts([R(None, "A", None)], _policy())
        note = result.rows[0].note
        assert "사용일자 미판독" in note and "금액 미판독" in note, note


class TestOrderingAndMisc:
    def test_sorted_by_date_ascending(self):
        result = process_receipts(
            [R("2026-07-05", "C", 1000), R("2026-07-01", "A", 1000), R("2026-07-03", "B", 1000)],
            _policy(),
        )
        dates = [r.date for r in result.rows]
        assert dates == sorted(dates), dates

    def test_seq_numbers_are_sequential(self):
        result = process_receipts(
            [R("2026-07-02", "A", 1000), R("2026-07-03", "B", 1000), R(None, "C", 1000)],
            _policy(),
        )
        assert [r.seq_num for r in result.rows] == [1, 2, 3]

    def test_larger_amount_claimed_first_same_day(self):
        result = process_receipts(
            [R("2026-07-02", "small", 3000), R("2026-07-02", "big", 14000)],
            _policy(default=15000),
        )
        assert result.rows[0].merchant == "big", "같은 날은 큰 건부터 한도를 채운다"

    def test_missing_merchant_gets_placeholder_but_still_counted(self):
        result = process_receipts([R("2026-07-02", "", 9000)], _policy())
        row = result.rows[0]
        assert row.needs_review is False, "상호를 몰라도 금액/날짜가 있으면 정산은 정확하다"
        assert "미판독" in row.merchant, row.merchant
        assert "상호 확인 필요" in row.note, row.note

    def test_attendees_filled_with_user_name(self):
        result = process_receipts([R("2026-07-02", "A", 9000)], _policy(), user_name="홍길동")
        assert result.rows[0].attendees == "홍길동"

    def test_empty_input(self):
        result = process_receipts([], _policy())
        assert result.rows == []
        assert result.total_claimed == 0


if __name__ == "__main__":
    ok = run_test_classes(TestDailyLimit, TestDateBracketApplied, TestNeedsReview, TestOrderingAndMisc)
    sys.exit(0 if ok else 1)
