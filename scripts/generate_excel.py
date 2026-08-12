"""Claude 가 판독한 영수증 데이터 → 정산 대장 xlsx.

입력 JSON 형식:
    [{"date": "YYYY-MM-DD" | null,
      "merchant": str,
      "amount": int | null,
      "image_path": str}, ...]

date 나 amount 를 판독하지 못했으면 반드시 null 로 둔다. 추측한 값을 넣으면
'확인 필요' 분류가 무력화되어 잘못된 정산이 그대로 제출된다.

한도 우선순위:
    --daily-limit-from-chat  (대화 지시)   > --daily-limit (실행 인자)
    > config.json 의 날짜 구간 이력 > config.json 기본값 > 내장 기본값
"""

import argparse
import json
import sys
from datetime import date

from config_store import load_config
from models import ReceiptData
from expense_processor import process_receipts, ProcessResult
from excel_writer import create_expense_excel
from limit_policy import load_policy, LimitPolicy


def _parse_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        # 형식이 깨진 날짜는 지어내지 않고 '미판독'으로 떨군다.
        return None


def _parse_amount(value):
    if value in (None, ""):
        return None
    try:
        parsed = int(str(value).replace(",", "").replace("원", "").strip())
    except (ValueError, TypeError):
        return None
    return parsed if parsed >= 0 else None


def load_receipts(json_path: str) -> list[ReceiptData]:
    """Claude 가 확정한 영수증 데이터 JSON 을 읽어온다.

    prepare_receipts.py 의 매니페스트를 그대로 넘기면 안 된다 — 매니페스트에는
    판독 결과(date/merchant/amount)가 없고, 변환 실패 항목도 섞여 있다.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise ValueError("입력 JSON 의 최상위는 영수증 객체의 배열이어야 합니다.")

    receipts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        receipts.append(
            ReceiptData(
                date=_parse_date(item.get("date")),
                merchant=(item.get("merchant") or "").strip(),
                amount=_parse_amount(item.get("amount")),
                source_file=item.get("image_path") or "",
            )
        )
    return receipts


def build_receipt_images(receipts: list[ReceiptData]) -> list[tuple[str, str]]:
    return [
        (r.source_file, r.merchant or f"영수증 {i + 1}")
        for i, r in enumerate(receipts)
        if r.source_file
    ]


def build_limit_summary(result: ProcessResult, policy: LimitPolicy) -> list[str]:
    """적용된 한도와 그 출처를 사람이 읽을 문장 목록으로 만든다.

    이 목록은 표준출력과 엑셀 하단 양쪽에 동일하게 기록된다 — 나중에
    "이 대장은 한도 얼마로 계산된 거냐"는 질문에 파일만 보고 답할 수 있어야 한다.
    """
    lines = []
    if policy.has_override:
        # 회차 전체에 일괄 적용된 경우 — 한 줄이면 충분하다.
        decision = policy.for_date(None)
        lines.append(f"적용 한도: {decision.amount:,}원")
        lines.append(f"출처: {decision.detail}")
        lines.append("(config.json 의 날짜 구간 이력보다 우선 적용되었습니다)")
        return lines

    if not result.limits_applied:
        decision = policy.for_date(None)
        lines.append(f"적용 한도: {decision.amount:,}원")
        lines.append(f"출처: {decision.detail}")
        return lines

    # 날짜 구간별로 다른 한도가 적용될 수 있으므로 구간 단위로 묶어서 보여준다.
    by_detail: dict[tuple[int, str], list] = {}
    for day, decision in sorted(result.limits_applied.items()):
        by_detail.setdefault((decision.amount, decision.detail), []).append(day)

    if len(by_detail) == 1:
        (amount, detail), days = next(iter(by_detail.items()))
        lines.append(f"적용 한도: {amount:,}원")
        lines.append(f"출처: {detail}")
    else:
        lines.append("적용 한도: 사용일자 구간에 따라 다름")
        for (amount, detail), days in sorted(by_detail.items()):
            span = f"{min(days).isoformat()} ~ {max(days).isoformat()}"
            lines.append(f"  - {span}: {amount:,}원  (출처: {detail})")
    return lines


def main():
    parser = argparse.ArgumentParser(
        description="영수증 판독 JSON → 개인경비 사용내역서 엑셀 생성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("receipts_json", help="Claude 가 판독한 영수증 데이터 JSON 경로")
    parser.add_argument("--output", default=None, help="출력 엑셀 경로 (생략시 ~/Downloads 에 자동 생성)")
    parser.add_argument(
        "--daily-limit",
        type=int,
        default=None,
        metavar="원",
        help="이번 회차에만 적용할 일 한도. config.json 의 값보다 우선한다.",
    )
    parser.add_argument(
        "--daily-limit-from-chat",
        type=int,
        default=None,
        metavar="원",
        help=(
            "사용자가 대화로 지시한 일 한도. 최우선으로 적용되며 출처가 '대화 지시'로 "
            "기록된다. Claude 전용 — 사람이 터미널에서 쓸 일은 없다."
        ),
    )
    parser.add_argument("--config", default=None, help="한도 config.json 경로 (기본: 스킬 폴더의 config.json)")
    parser.add_argument("--name", default=None, help="제출자 성명 (저장된 설정 대신 사용)")
    parser.add_argument("--position", default=None, help="직책")
    parser.add_argument("--department", default=None, help="부서")
    args = parser.parse_args()

    for label, value in (("--daily-limit", args.daily_limit),
                         ("--daily-limit-from-chat", args.daily_limit_from_chat)):
        if value is not None and value <= 0:
            print(f"ERROR: {label} 은 0보다 커야 합니다.", file=sys.stderr)
            sys.exit(1)

    saved = load_config()
    user_name = args.name or (saved.user_name if saved else "")
    position = args.position if args.position is not None else (saved.position if saved else "")
    department = args.department if args.department is not None else (saved.department if saved else "")
    if not user_name:
        print(
            "ERROR: 제출자 성명이 없습니다. --name 으로 넘기거나 "
            "manage_config.py save 로 먼저 저장하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    policy = load_policy(
        chat_limit=args.daily_limit_from_chat,
        arg_limit=args.daily_limit,
        config_path=args.config,
    )
    if policy.config_error:
        print(f"경고: {policy.config_error}", file=sys.stderr)

    try:
        receipts = load_receipts(args.receipts_json)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"ERROR: 영수증 JSON 을 읽지 못했습니다 ({e})", file=sys.stderr)
        sys.exit(1)

    if not receipts:
        print("ERROR: 영수증 데이터가 비어 있습니다.", file=sys.stderr)
        sys.exit(1)

    result = process_receipts(receipts, policy=policy, user_name=user_name)
    limit_summary = build_limit_summary(result, policy)

    # ---- 적용된 한도와 출처는 반드시 출력한다 ----
    print("=" * 56)
    for line in limit_summary:
        print(line)
    print("=" * 56)

    print(f"영수증 {len(receipts)}건 처리")
    print(f"  결제금액 합계 : {result.total_original:,}원")
    print(f"  인정금액 합계 : {result.total_claimed:,}원   ← 실제 청구액")
    print(f"  초과금액 합계 : {result.total_excess:,}원")

    review = result.review_rows
    if review:
        print(f"  확인 필요     : {len(review)}건 (한도 계산에서 제외됨)")
        for row in review:
            label = row.merchant or "(상호 미판독)"
            print(f"      - {label}: {row.note}")

    receipt_images = build_receipt_images(receipts)
    skipped = len(receipts) - len(receipt_images)
    if skipped:
        print(f"  참고: 이미지 경로가 없는 {skipped}건은 영수증 시트에 첨부되지 않았습니다.")

    try:
        output_path = create_expense_excel(
            result,
            user_name=user_name,
            department=department,
            position=position,
            receipt_images=receipt_images,
            output_path=args.output,
            limit_summary=limit_summary,
        )
    except OSError as e:
        print(
            f"ERROR: 엑셀 저장 실패 — 경로가 올바른지, 같은 이름의 파일이 이미 "
            f"열려있지는 않은지 확인하세요. ({e})",
            file=sys.stderr,
        )
        sys.exit(1)

    print(output_path)


if __name__ == "__main__":
    main()
