"""영수증 데이터 모델.

OCR/정규식 파싱 로직은 없다 — Claude 가 영수증을 직접 보고 판독한 값만 담는다.
`date` 와 `amount` 가 `None` 일 수 있다는 점이 중요하다: 판독에 실패했을 때
0 이나 오늘 날짜 같은 값으로 채우면 사람이 오류를 발견할 수 없게 된다.
못 읽은 건 못 읽은 채로 두고 '확인 필요'로 분류한다.
"""

from dataclasses import dataclass
from datetime import date


@dataclass
class ReceiptData:
    """영수증 한 건에서 얻은 데이터."""

    date: date | None = None
    merchant: str = ""
    amount: int | None = None
    source_file: str = ""

    @property
    def is_readable(self) -> bool:
        """한도 계산에 넣을 수 있는가? 날짜와 금액이 모두 있어야 한다."""
        return self.date is not None and self.amount is not None

    def review_reasons(self) -> list[str]:
        """'확인 필요'로 분류되는 이유들. 읽을 수 있는 영수증이면 빈 리스트.

        상호 미판독은 여기 포함하지 않는다 — 상호를 몰라도 금액과 날짜가 있으면
        한도 계산 자체는 정확하기 때문이다. 상호는 비고에 별도로 표시한다.
        """
        reasons = []
        if self.date is None:
            reasons.append("사용일자 미판독")
        if self.amount is None:
            reasons.append("금액 미판독")
        return reasons
