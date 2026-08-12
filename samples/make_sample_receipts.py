"""데모용 가상 영수증 이미지를 생성한다.

이 레포에는 실제 영수증이 단 한 장도 들어있지 않다. 데모를 돌려보려면
이 스크립트로 가짜 영수증을 만들어서 쓴다.

    uv run python samples/make_sample_receipts.py --output samples/receipts

여기 등장하는 상호·금액·카드번호·사업자번호·사람 이름은 전부 지어낸 것이다.
"""

import argparse
import os

from PIL import Image, ImageDraw, ImageFont

# 전부 가상의 데이터. 실존 상호/인물과 무관하다.
SAMPLE_RECEIPTS = [
    # (파일명, 상호, 사업자번호, 날짜, 항목, 금액)
    ("01_happy_bunsik.png", "행복분식 테스트점", "000-00-00001", "2026-07-02", "김치찌개 2인", 18000),
    ("02_cafe_haru.png", "카페 하루 (가상)", "000-00-00002", "2026-07-02", "아메리카노 2잔", 9000),
    ("03_mirae_sikdang.png", "미래식당 3호점", "000-00-00003", "2026-07-03", "제육정식", 11000),
    ("04_noodle_lab.png", "면류연구소 (샘플)", "000-00-00004", "2026-07-06", "우동 세트", 13500),
    ("05_green_salad.png", "그린샐러드 데모점", "000-00-00005", "2026-07-06", "샐러드볼", 12000),
    ("06_old_rice.png", "옛날국밥 예시점", "000-00-00006", "2026-05-28", "돼지국밥", 14000),
    # 일부러 흐리게 만들어 '확인 필요' 흐름을 보여주는 건
    ("07_unreadable.png", "??? (판독 불가 데모)", "000-00-00007", None, "?????", None),
]

WIDTH, HEIGHT = 460, 620
BG = (252, 252, 250)
INK = (28, 28, 30)
FAINT = (150, 150, 155)


def _font(size: int, bold: bool = False):
    """맑은 고딕 → 없으면 기본 폰트. 한글이 깨져도 데모 목적에는 지장 없다."""
    candidates = [
        "C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_receipt(merchant, biz_no, day, item, amount, blurred=False) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)

    f_title = _font(26, bold=True)
    f_body = _font(17)
    f_small = _font(14)
    f_total = _font(24, bold=True)

    y = 34
    d.text((WIDTH // 2, y), "신 용 카 드 매 출 전 표", font=f_title, fill=INK, anchor="ma")
    y += 46
    d.text((WIDTH // 2, y), "* 이 영수증은 데모용 가상 데이터입니다 *",
           font=f_small, fill=FAINT, anchor="ma")
    y += 34
    d.line([(30, y), (WIDTH - 30, y)], fill=INK, width=2)
    y += 22

    def row(label, value, gap=30):
        nonlocal y
        d.text((36, y), label, font=f_body, fill=FAINT)
        d.text((WIDTH - 36, y), value, font=f_body, fill=INK, anchor="ra")
        y += gap

    row("가맹점명", merchant)
    row("가맹점번호", biz_no)
    row("거래일시", f"{day.replace('-', '.')} 12:41:07" if day else "??.??.?? ??:??")
    y += 8
    d.line([(30, y), (WIDTH - 30, y)], fill=FAINT, width=1)
    y += 22

    row("품목", item)
    supply = int(round(amount / 1.1)) if amount else None
    vat = amount - supply if amount else None
    row("공급가액", f"{supply:,}" if supply else "?????")
    row("부가세", f"{vat:,}" if vat else "?????")
    y += 10
    d.line([(30, y), (WIDTH - 30, y)], fill=INK, width=2)
    y += 20

    d.text((36, y), "합계", font=f_total, fill=INK)
    d.text((WIDTH - 36, y), f"{amount:,}원" if amount else "?????",
           font=f_total, fill=INK, anchor="ra")
    y += 52

    d.line([(30, y), (WIDTH - 30, y)], fill=FAINT, width=1)
    y += 20
    row("카드번호", "1234-****-****-5678", gap=26)
    row("승인번호", "00000000", gap=26)
    row("결제구분", "일시불", gap=26)

    d.text((WIDTH // 2, HEIGHT - 46), "SAMPLE / NOT A REAL RECEIPT",
           font=f_small, fill=FAINT, anchor="ma")

    if blurred:
        from PIL import ImageFilter
        img = img.filter(ImageFilter.GaussianBlur(radius=3.2))
    return img


def main():
    parser = argparse.ArgumentParser(description="가상 영수증 이미지 생성")
    parser.add_argument("--output", default="samples/receipts", help="이미지를 저장할 폴더")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    for filename, merchant, biz_no, day, item, amount in SAMPLE_RECEIPTS:
        blurred = amount is None  # 판독 불가 케이스는 일부러 흐리게
        img = draw_receipt(merchant, biz_no, day, item, amount, blurred=blurred)
        path = os.path.join(args.output, filename)
        img.save(path, "PNG")
        print(path)

    print(f"\n가상 영수증 {len(SAMPLE_RECEIPTS)}장 생성 완료: {args.output}")


if __name__ == "__main__":
    main()
