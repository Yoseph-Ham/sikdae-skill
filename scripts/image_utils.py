"""이미지 후처리 유틸 — 여백 잘라내기.

카드사에서 받은 PDF 전표는 A4 페이지 한가운데에 영수증이 작게 박혀 있는 경우가 많다.
그대로 엑셀에 넣으면 셀 대부분이 흰 여백이고 영수증은 깨알만하게 보인다.
실제 내용이 있는 영역만 남기고 잘라낸다.
"""

from PIL import Image, ImageChops, ImageOps

# 이 비율보다 많이 잘라내야 하면 뭔가 잘못된 것으로 보고 원본을 유지한다.
MIN_KEEP_RATIO = 0.02


def trim_margins(img: Image.Image, tolerance: int = 12, padding: int = 24) -> Image.Image:
    """이미지 가장자리의 균일한 여백(흰 배경/검은 배경 모두)을 잘라낸다.

    Args:
        img: 원본 이미지
        tolerance: 배경으로 간주할 밝기 차이 허용치. 스캔 노이즈를 흡수한다.
        padding: 잘라낸 뒤 남길 여유 여백(px)

    Returns:
        잘린 이미지. 잘라낼 여백이 없거나 결과가 비정상이면 원본을 그대로 돌려준다.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    gray = img.convert("L")

    # 네 모서리에서 배경색을 추정한다.
    # 평균이 아니라 중앙값을 쓴다 — 모서리 한 곳에 얼룩/스캔 노이즈가 있으면
    # 평균은 그쪽으로 끌려가 배경색을 엉뚱하게 잡고, 그러면 흰 여백까지
    # '내용'으로 판정해 아무것도 잘리지 않는다. 중앙값은 이상치 하나를 무시한다.
    w, h = gray.size
    if w < 4 or h < 4:
        return img
    corners = sorted([
        gray.getpixel((0, 0)),
        gray.getpixel((w - 1, 0)),
        gray.getpixel((0, h - 1)),
        gray.getpixel((w - 1, h - 1)),
    ])
    bg = (corners[1] + corners[2]) // 2

    background = Image.new("L", gray.size, bg)
    diff = ImageChops.difference(gray, background)
    # tolerance 이하 차이는 배경으로 뭉갠다
    mask = diff.point(lambda p: 255 if p > tolerance else 0)

    bbox = mask.getbbox()
    if not bbox:
        return img  # 전부 배경 — 자를 것이 없다

    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(img.width, right + padding)
    bottom = min(img.height, bottom + padding)

    if right <= left or bottom <= top:
        return img

    cropped = img.crop((left, top, right, bottom))

    # 내용을 거의 다 날려버렸다면(예: 배경 추정 실패) 원본을 유지한다.
    area_ratio = (cropped.width * cropped.height) / float(img.width * img.height)
    if area_ratio < MIN_KEEP_RATIO:
        return img

    return cropped


def add_border(img: Image.Image, width: int = 2, color=(200, 200, 200)) -> Image.Image:
    """엑셀에 넣었을 때 영수증 경계가 보이도록 얇은 테두리를 두른다."""
    return ImageOps.expand(img, border=width, fill=color)
