"""영수증 폴더를 스캔해 Claude가 읽을 수 있는 이미지/텍스트 매니페스트를 만든다.

이미지 파일은 그대로 참조하고, PDF/PPTX는 페이지·슬라이드의 이미지를
임시 PNG로 변환한다 (엑셀 삽입과 Claude 비전 판독 모두 raster 이미지가 필요).
"""
import argparse
import json
import os
import tempfile
import uuid

from PIL import Image

from pdf_utils import process_pdf, is_pdf
from pptx_utils import pptx_to_images, is_pptx

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}


def is_image(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in IMAGE_EXTS


def _save_temp_image(img: Image.Image, temp_dir: str) -> str:
    filename = f"{uuid.uuid4().hex}.png"
    path = os.path.join(temp_dir, filename)
    img.convert("RGB").save(path, "PNG")
    return path


def scan_folder(folder_path: str, temp_dir: str) -> list[dict]:
    """폴더(하위폴더 포함)를 스캔해 판독 대상 항목 리스트를 만든다.

    각 항목: {"image_path": 비전으로 볼 raster 이미지 경로 (엑셀 삽입용이기도 함),
              "source_file": 원본 파일 경로,
              "embedded_text": PDF에서 직접 추출한 텍스트 (없으면 None),
              "error": 처리 실패 시 에러 메시지 (정상 처리되면 이 키 자체가 없음)}

    파일 하나가 손상되어 있어도 나머지 폴더 스캔은 계속 진행한다 — 잘못된 파일
    하나 때문에 이미 정상 처리된 다른 영수증까지 통째로 날아가면 안 된다.
    """
    items = []
    for root, _dirs, files in os.walk(folder_path):
        for filename in sorted(files):
            file_path = os.path.join(root, filename)

            if is_image(file_path):
                items.append({
                    "image_path": file_path,
                    "source_file": file_path,
                    "embedded_text": None,
                })
            elif is_pdf(file_path):
                try:
                    pages = process_pdf(file_path)
                except Exception as e:
                    items.append({
                        "image_path": None,
                        "source_file": file_path,
                        "embedded_text": None,
                        "error": str(e),
                    })
                    continue
                for page in pages:
                    if page.images:
                        for img in page.images:
                            items.append({
                                "image_path": _save_temp_image(img, temp_dir),
                                "source_file": file_path,
                                "embedded_text": page.text,
                            })
            elif is_pptx(file_path):
                try:
                    images = pptx_to_images(file_path)
                except Exception as e:
                    items.append({
                        "image_path": None,
                        "source_file": file_path,
                        "embedded_text": None,
                        "error": str(e),
                    })
                    continue
                for img in images:
                    items.append({
                        "image_path": _save_temp_image(img, temp_dir),
                        "source_file": file_path,
                        "embedded_text": None,
                    })
    return items


def main():
    parser = argparse.ArgumentParser(description="영수증 폴더 스캔 → 매니페스트 JSON 생성")
    parser.add_argument("folder", help="영수증이 들어있는 폴더 경로")
    parser.add_argument("--output", required=True, help="매니페스트 JSON 출력 경로")
    args = parser.parse_args()

    temp_dir = tempfile.mkdtemp(prefix="sikdae_")
    items = scan_folder(args.folder, temp_dir)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"{len(items)}건 발견, temp_dir={temp_dir}")
    print(args.output)


if __name__ == "__main__":
    main()
