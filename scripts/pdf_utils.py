"""PDF 파일을 이미지 또는 텍스트로 처리하는 유틸리티."""

import fitz  # PyMuPDF
from PIL import Image
import io
from dataclasses import dataclass


@dataclass
class PDFPageResult:
    """PDF 페이지 처리 결과. 텍스트 또는 이미지 중 하나."""
    text: str | None = None  # 텍스트가 내장된 경우
    images: list[Image.Image] | None = None  # 이미지인 경우


def process_pdf(pdf_path: str, dpi: int = 300) -> list[PDFPageResult]:
    """PDF를 페이지별로 처리한다.

    텍스트가 내장된 페이지 → 텍스트 직접 추출 (OCR 불필요)
    이미지만 있는 페이지 → 개별 이미지 추출 (OCR 필요)
    """
    doc = fitz.open(pdf_path)
    results = []
    try:
        for page in doc:
            text = page.get_text().strip()

            if len(text) > 50:
                # 텍스트가 충분히 있으면 직접 사용 + 페이지 이미지도 함께 저장
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                results.append(PDFPageResult(text=text, images=[page_img]))
            else:
                # 이미지 추출 시도
                page_images = _extract_images_from_page(doc, page, dpi)
                if page_images:
                    results.append(PDFPageResult(images=page_images))
                else:
                    # 이미지 추출 실패 시 페이지 전체를 이미지로 렌더링
                    mat = fitz.Matrix(dpi / 72, dpi / 72)
                    pix = page.get_pixmap(matrix=mat)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    results.append(PDFPageResult(images=[img]))
    finally:
        doc.close()
    return results


ADJACENCY_TOLERANCE = 4  # 이 정도(pt) 이하로 떨어져 있으면 '붙어 있다'고 본다


def _is_vertical_slice_pair(a, b, tolerance: float = ADJACENCY_TOLERANCE) -> bool:
    """a 와 b 가 '스크린샷 한 장을 가로로 자른 조각' 관계인지 판단한다.

    조각의 신호는 **좌우 범위가 같은 채로 위아래로 딱 붙어 있는 것**이다.
    단순히 '붙어 있다'만 보면 안 된다 — 서로 다른 영수증을 한 페이지에 가로로
    빈틈없이 나열한 경우도 붙어 있기 때문이다. 그 경우는 좌우 범위가 서로 다르다.

        조각 (합쳐야 함)          별개 영수증 (합치면 안 됨)
        ┌──────────────┐          ┌────┐┌────┐┌────┐
        ├──────────────┤          │    ││    ││    │
        └──────────────┘          └────┘└────┘└────┘
        x범위 동일, 세로로 인접     y범위 동일, 가로로 인접
    """
    same_left = abs(a.x0 - b.x0) <= tolerance
    same_right = abs(a.x1 - b.x1) <= tolerance
    if not (same_left and same_right):
        return False
    # 위아래로 맞닿아 있는가 (겹침 포함)
    gap = max(a.y0, b.y0) - min(a.y1, b.y1)
    return gap <= tolerance


def _merge_adjacent(rects: list, tolerance: float = ADJACENCY_TOLERANCE) -> list:
    """잘린 조각으로 판단되는 사각형들만 하나로 합친다.

    조각을 따로 뽑으면 결제금액과 잔액이 서로 다른 조각에 흩어져
    **엉뚱한 숫자를 결제금액으로 읽는 사고**가 난다.
    """
    boxes = [fitz.Rect(r) for r in rects]
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if _is_vertical_slice_pair(boxes[i], boxes[j], tolerance):
                    boxes[i] = fitz.Rect(boxes[i]) | boxes[j]  # 합집합
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    return boxes


def _extract_images_from_page(
    doc: fitz.Document, page: fitz.Page, dpi: int
) -> list[Image.Image]:
    """페이지에서 영수증 단위로 이미지를 추출한다.

    임베드된 비트맵을 그대로 꺼내지 않고, **페이지 위에 놓인 위치를 기준으로**
    붙어 있는 것끼리 묶은 뒤 그 영역을 렌더링한다. 이렇게 하면
      - 한 장이 여러 조각으로 잘려 들어간 경우 → 다시 한 장으로 합쳐지고
      - 여러 장이 한 페이지에 나열된 경우 → 각각 따로 나오며
      - 페이지에 걸린 회전·변형도 렌더링에 그대로 반영된다.
    """
    rects = []
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            for r in page.get_image_rects(xref):
                rects.append(r)
        except Exception:
            continue

    if not rects:
        return []

    images = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for box in _merge_adjacent(rects):
        clip = box & page.rect  # 페이지 밖으로 나간 부분은 잘라낸다
        if clip.is_empty or clip.width <= 0 or clip.height <= 0:
            continue
        try:
            pix = page.get_pixmap(matrix=mat, clip=clip)
        except Exception:
            continue
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # 너무 작은 것은 아이콘·로고로 보고 건너뛴다
        if img.width >= 100 and img.height >= 100:
            images.append(img)

    return images


def pdf_to_images(pdf_path: str, dpi: int = 300) -> list[Image.Image]:
    """PDF 파일의 각 페이지를 PIL Image로 변환한다 (호환용)."""
    doc = fitz.open(pdf_path)
    images = []
    try:
        for page in doc:
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
    finally:
        doc.close()
    return images


def is_pdf(file_path: str) -> bool:
    return file_path.lower().endswith(".pdf")
