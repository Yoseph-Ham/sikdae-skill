"""여백 잘라내기 테스트.

카드사 PDF 전표는 A4 한가운데 영수증이 작게 박혀 있어, 그대로 엑셀에 넣으면
셀 대부분이 흰 여백이 된다. 그 여백을 제거하되 내용은 절대 자르지 않아야 한다.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from PIL import Image, ImageDraw  # noqa: E402

from image_utils import trim_margins, add_border  # noqa: E402
from test_support import run_test_classes  # noqa: E402


def _page_with_content(page=(800, 1000), box=(300, 400, 500, 600), bg=255, fg=0):
    """가운데에만 내용이 있는 페이지를 만든다."""
    img = Image.new("RGB", page, (bg, bg, bg))
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=(fg, fg, fg))
    return img


class TestTrimMargins:
    def test_removes_surrounding_whitespace(self):
        img = _page_with_content()
        out = trim_margins(img, padding=0)
        assert out.width < img.width, (out.width, img.width)
        assert out.height < img.height, (out.height, img.height)

    def test_keeps_all_content(self):
        """내용 영역(200x200)은 한 픽셀도 잘리면 안 된다."""
        img = _page_with_content(box=(300, 400, 500, 600))
        out = trim_margins(img, padding=0)
        assert out.width >= 200, out.width
        assert out.height >= 200, out.height

    def test_padding_is_applied(self):
        img = _page_with_content(box=(300, 400, 500, 600))
        no_pad = trim_margins(img, padding=0)
        padded = trim_margins(img, padding=20)
        assert padded.width == no_pad.width + 40, (padded.width, no_pad.width)

    def test_padding_clamped_at_page_edge(self):
        """내용이 가장자리에 붙어 있어도 패딩 때문에 밖으로 나가지 않는다."""
        img = _page_with_content(page=(400, 400), box=(0, 0, 100, 100))
        out = trim_margins(img, padding=50)
        assert out.width <= 400 and out.height <= 400, out.size

    def test_blank_image_returned_unchanged(self):
        """전부 배경이면 자를 것이 없으므로 원본 크기를 유지한다."""
        img = Image.new("RGB", (500, 500), (255, 255, 255))
        out = trim_margins(img)
        assert out.size == (500, 500), out.size

    def test_full_bleed_image_barely_trimmed(self):
        """내용이 페이지를 꽉 채우면 거의 잘리지 않는다."""
        img = Image.new("RGB", (400, 400), (10, 10, 10))
        out = trim_margins(img)
        assert out.size == (400, 400), out.size

    def test_dark_background_is_trimmed_too(self):
        """다크모드 영수증(어두운 배경)도 여백이 잘려야 한다."""
        img = _page_with_content(bg=15, fg=240)
        out = trim_margins(img, padding=0)
        assert out.width < img.width, out.size

    def test_tiny_image_is_safe(self):
        img = Image.new("RGB", (2, 2), (255, 255, 255))
        assert trim_margins(img).size == (2, 2)

    def test_non_rgb_input_handled(self):
        img = _page_with_content().convert("L")
        out = trim_margins(img, padding=0)
        assert out.mode == "RGB", out.mode
        assert out.width < 800, out.size

    def test_noisy_corner_does_not_break_detection(self):
        """모서리 한 곳에 얼룩이 있어도 배경 추정이 무너지지 않는다."""
        img = _page_with_content()
        img.putpixel((0, 0), (0, 0, 0))  # 좌상단 얼룩
        out = trim_margins(img, padding=0)
        # 얼룩 때문에 bbox 가 좌상단까지 늘어나더라도 오른쪽/아래 여백은 잘린다
        assert out.width < img.width or out.height < img.height, out.size


class TestAddBorder:
    def test_border_increases_size(self):
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        out = add_border(img, width=3)
        assert out.size == (106, 106), out.size


if __name__ == "__main__":
    sys.exit(0 if run_test_classes(TestTrimMargins, TestAddBorder) else 1)
