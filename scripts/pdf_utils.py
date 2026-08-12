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


def _extract_images_from_page(
    doc: fitz.Document, page: fitz.Page, dpi: int
) -> list[Image.Image]:
    """페이지에서 개별 이미지를 추출한다."""
    images = []
    img_list = page.get_images(full=True)

    for img_info in img_list:
        xref = img_info[0]
        try:
            base_image = doc.extract_image(xref)
            if base_image and base_image["image"]:
                img = Image.open(io.BytesIO(base_image["image"]))
                # 너무 작은 이미지는 건너뛰기 (아이콘 등)
                if img.width >= 100 and img.height >= 100:
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    images.append(img)
        except Exception:
            continue

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
