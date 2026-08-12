"""PDF 임베드 이미지 병합 판정 테스트.

실제 사고 사례에서 나온 로직이다. 카드사 앱 스크린샷 한 장이 PDF 안에 가로 띠
3조각으로 잘려 들어간 경우가 있었는데, 조각을 따로 뽑으니 '거래 후 잔액'만 보이는
조각이 생겨 **잔액을 결제금액으로 읽을 뻔했다.**

반대로 서로 다른 영수증 여러 장을 한 페이지에 빈틈없이 가로로 나열한 PDF 도 있어서,
'붙어 있으면 무조건 합치기'로 하면 서로 다른 영수증이 뭉쳐 건수가 줄어든다.
두 경우를 가르는 신호는 **좌우 범위가 같은 채로 위아래로 붙어 있는가** 이다.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import fitz  # noqa: E402

from pdf_utils import _merge_adjacent, _is_vertical_slice_pair  # noqa: E402
from test_support import run_test_classes  # noqa: E402

# 실제 PDF 에서 관측된 배치값
SLICED_PAGE = [  # 스크린샷 1장이 가로 띠 3조각으로 잘림 (x범위 동일, 세로 적층)
    fitz.Rect(0.0, 103.4, 841.8, 268.1),
    fitz.Rect(0.0, 268.1, 841.8, 432.7),
    fitz.Rect(0.0, 432.7, 841.8, 491.8),
]
TILED_PAGE = [  # 서로 다른 영수증 5장을 가로로 나열 (y범위 동일, 일부는 딱 붙어 있음)
    fitz.Rect(44.9, 40.7, 288.9, 769.3),
    fitz.Rect(288.9, 40.7, 533.0, 769.3),
    fitz.Rect(607.9, 40.7, 832.1, 769.3),
    fitz.Rect(907.0, 40.7, 1151.1, 769.3),
    fitz.Rect(1151.1, 40.7, 1395.1, 769.3),
]


class TestSlicedScreenshot:
    def test_vertical_slices_merge_into_one(self):
        assert len(_merge_adjacent(SLICED_PAGE)) == 1, _merge_adjacent(SLICED_PAGE)

    def test_merged_rect_covers_all_slices(self):
        # PDF 좌표는 float 이라 정확한 비교는 하지 않는다 (841.8 이 841.79998... 로 온다)
        eps = 0.01
        box = _merge_adjacent(SLICED_PAGE)[0]
        assert box.y0 <= 103.4 + eps and box.y1 >= 491.8 - eps, box
        assert box.x0 <= 0.0 + eps and box.x1 >= 841.8 - eps, box

    def test_pair_is_recognized_as_slices(self):
        assert _is_vertical_slice_pair(SLICED_PAGE[0], SLICED_PAGE[1]) is True

    def test_slices_with_small_gap_still_merge(self):
        a = fitz.Rect(0, 0, 800, 100)
        b = fitz.Rect(0, 102, 800, 200)  # 2pt 틈
        assert _is_vertical_slice_pair(a, b) is True

    def test_overlapping_slices_merge(self):
        a = fitz.Rect(0, 0, 800, 105)
        b = fitz.Rect(0, 100, 800, 200)  # 겹침
        assert _is_vertical_slice_pair(a, b) is True


class TestTiledReceipts:
    def test_side_by_side_receipts_are_not_merged(self):
        """가로로 딱 붙어 있어도 서로 다른 영수증이면 합치면 안 된다."""
        assert len(_merge_adjacent(TILED_PAGE)) == 5, _merge_adjacent(TILED_PAGE)

    def test_touching_horizontally_is_not_a_slice_pair(self):
        # 288.9 에서 정확히 맞닿아 있지만 좌우 범위가 다르다
        assert _is_vertical_slice_pair(TILED_PAGE[0], TILED_PAGE[1]) is False

    def test_different_x_range_never_merges(self):
        a = fitz.Rect(0, 0, 400, 100)
        b = fitz.Rect(0, 100, 800, 200)  # 세로로 붙었지만 폭이 다름
        assert _is_vertical_slice_pair(a, b) is False

    def test_far_apart_not_merged(self):
        a = fitz.Rect(0, 0, 800, 100)
        b = fitz.Rect(0, 400, 800, 500)
        assert _is_vertical_slice_pair(a, b) is False


class TestMergeGeneral:
    def test_empty_input(self):
        assert _merge_adjacent([]) == []

    def test_single_rect_unchanged(self):
        out = _merge_adjacent([fitz.Rect(10, 10, 110, 210)])
        assert len(out) == 1 and out[0].width == 100

    def test_mixed_page_merges_only_slices(self):
        """한 페이지에 '잘린 한 장' + '따로 있는 한 장'이 섞인 경우."""
        rects = [
            fitz.Rect(0, 0, 400, 100),    # 조각 1
            fitz.Rect(0, 100, 400, 200),  # 조각 2 → 위와 합쳐져야 함
            fitz.Rect(500, 0, 900, 200),  # 별개 영수증
        ]
        out = _merge_adjacent(rects)
        assert len(out) == 2, out

    def test_three_slices_collapse_transitively(self):
        rects = [
            fitz.Rect(0, 0, 400, 100),
            fitz.Rect(0, 100, 400, 200),
            fitz.Rect(0, 200, 400, 300),
        ]
        out = _merge_adjacent(rects)
        assert len(out) == 1, out
        assert out[0].y1 >= 300, out[0]


if __name__ == "__main__":
    sys.exit(0 if run_test_classes(TestSlicedScreenshot, TestTiledReceipts, TestMergeGeneral) else 1)
