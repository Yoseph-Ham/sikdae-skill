"""정산 판정 로직: 일자별 합산 → 한도 적용 → 인정/초과 분리 → 확인필요 분류.

핵심 규칙
  - 같은 날짜의 영수증은 **합산한 뒤** 그 날짜의 한도까지만 인정한다.
  - 한도를 넘는 금액은 인정금액에서 깎되 **버리지 않고 `excess` 로 따로 들고 간다**
    (엑셀에서 '초과금액' 컬럼으로 나간다). 원 결제금액은 항상 그대로 보존된다.
  - 미사용 한도는 다음 날로 이월되지 않는다.
  - 사용일자나 금액을 판독하지 못한 건은 **한도 합산에 넣지 않고** '확인 필요'로 분리한다.
    임의의 값으로 채우면 사람이 잘못된 정산을 그대로 제출하게 된다.
"""

from dataclasses import dataclass, field
from datetime import date
from itertools import groupby

from models import ReceiptData
from limit_policy import LimitPolicy, LimitDecision


@dataclass
class ExpenseRow:
    """엑셀에 출력할 한 행."""

    seq_num: int
    date: date | None
    merchant: str
    category: str  # 항목 구분 (기본: "식대")
    description: str  # 사용내역 (기본: "점심식대")
    amount: int | None  # 영수증 원 결제금액 (판독 실패 시 None)
    claimed: int  # 인정금액 (한도 적용 후 실제 청구액)
    excess: int  # 초과금액 (한도 초과로 인정되지 않은 금액)
    attendees: str  # 참석자
    note: str  # 비고
    needs_review: bool = False  # '확인 필요' — 사람이 직접 채워야 하는 행
    daily_limit: int | None = None  # 이 행에 적용된 한도
    limit_source: str = ""  # 그 한도의 출처 설명
    source_file: str = ""


@dataclass
class ProcessResult:
    """판정 결과 전체. CLI 가 이 값을 그대로 요약 출력한다."""

    rows: list[ExpenseRow] = field(default_factory=list)
    limits_applied: dict = field(default_factory=dict)  # {date|None: LimitDecision}

    @property
    def claimed_rows(self) -> list[ExpenseRow]:
        return [r for r in self.rows if not r.needs_review]

    @property
    def review_rows(self) -> list[ExpenseRow]:
        return [r for r in self.rows if r.needs_review]

    @property
    def total_claimed(self) -> int:
        return sum(r.claimed for r in self.rows if not r.needs_review)

    @property
    def total_excess(self) -> int:
        return sum(r.excess for r in self.rows if not r.needs_review)

    @property
    def total_original(self) -> int:
        return sum(r.amount or 0 for r in self.rows if not r.needs_review)


def _merchant_or_placeholder(receipt: ReceiptData) -> tuple[str, str]:
    """(표시할 상호, 상호 관련 비고)."""
    if receipt.merchant:
        return receipt.merchant, ""
    return "(상호 미판독)", "상호 확인 필요"


def process_receipts(
    receipts: list[ReceiptData],
    policy: LimitPolicy,
    user_name: str = "",
) -> ProcessResult:
    """영수증 목록에 일자별 한도를 적용해 정산 행을 만든다."""
    readable = [r for r in receipts if r.is_readable]
    unreadable = [r for r in receipts if not r.is_readable]

    # 날짜 오름차순, 같은 날은 금액 내림차순 (큰 건부터 한도를 채운다)
    readable.sort(key=lambda r: (r.date, -(r.amount or 0)))

    result = ProcessResult()
    seq = 1

    for day, group in groupby(readable, key=lambda r: r.date):
        decision: LimitDecision = policy.for_date(day)
        result.limits_applied[day] = decision

        remaining = decision.amount
        for receipt in group:
            original = receipt.amount or 0
            claimed = max(0, min(original, remaining))
            excess = original - claimed
            remaining -= claimed

            merchant, merchant_note = _merchant_or_placeholder(receipt)
            notes = [n for n in [merchant_note] if n]
            if excess > 0:
                notes.append(f"한도 초과 {excess:,}원 (일 한도 {decision.amount:,}원)")

            result.rows.append(
                ExpenseRow(
                    seq_num=seq,
                    date=day,
                    merchant=merchant,
                    category="식대",
                    description="점심식대",
                    amount=original,
                    claimed=claimed,
                    excess=excess,
                    attendees=user_name,
                    note=" / ".join(notes),
                    needs_review=False,
                    daily_limit=decision.amount,
                    limit_source=decision.detail,
                    source_file=receipt.source_file,
                )
            )
            seq += 1

    # 판독 실패 건 — 한도 계산에 넣지 않고 맨 뒤에 '확인 필요'로 붙인다.
    for receipt in unreadable:
        merchant, merchant_note = _merchant_or_placeholder(receipt)
        reasons = receipt.review_reasons()
        if merchant_note:
            reasons.append("상호 미판독")
        decision = policy.for_date(receipt.date)
        result.rows.append(
            ExpenseRow(
                seq_num=seq,
                date=receipt.date,
                merchant=merchant,
                category="식대",
                description="점심식대",
                amount=receipt.amount,
                claimed=0,
                excess=0,
                attendees=user_name,
                note="확인 필요: " + ", ".join(reasons) + " — 원본 영수증을 보고 직접 입력",
                needs_review=True,
                daily_limit=decision.amount,
                limit_source=decision.detail,
                source_file=receipt.source_file,
            )
        )
        seq += 1

    return result
