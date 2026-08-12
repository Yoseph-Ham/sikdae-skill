"""ReceiptData 모델 테스트 — 판독 실패를 임의 값으로 채우지 않는지."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from models import ReceiptData  # noqa: E402
from test_support import run_test_classes  # noqa: E402


class TestReceiptData:
    def test_defaults_are_none_not_zero(self):
        r = ReceiptData()
        assert r.date is None
        assert r.amount is None, "기본 금액이 0이면 판독 실패와 0원 결제를 구분할 수 없다"
        assert r.merchant == ""

    def test_readable_requires_date_and_amount(self):
        assert ReceiptData(date=date(2026, 7, 1), amount=9000).is_readable is True
        assert ReceiptData(date=None, amount=9000).is_readable is False
        assert ReceiptData(date=date(2026, 7, 1), amount=None).is_readable is False

    def test_zero_amount_is_readable(self):
        """0원 결제는 판독 실패가 아니다."""
        assert ReceiptData(date=date(2026, 7, 1), amount=0).is_readable is True

    def test_review_reasons_lists_missing_fields(self):
        assert ReceiptData(date=None, amount=None).review_reasons() == [
            "사용일자 미판독",
            "금액 미판독",
        ]

    def test_review_reasons_empty_when_readable(self):
        assert ReceiptData(date=date(2026, 7, 1), amount=9000).review_reasons() == []

    def test_missing_merchant_is_not_a_review_reason(self):
        r = ReceiptData(date=date(2026, 7, 1), amount=9000, merchant="")
        assert r.review_reasons() == [], "상호를 몰라도 한도 계산은 정확하다"
        assert r.is_readable is True


if __name__ == "__main__":
    sys.exit(0 if run_test_classes(TestReceiptData) else 1)
