"""전체 테스트 실행기.

    uv run python tests/run_all.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = [
    "test_models.py",
    "test_image_utils.py",
    "test_limit_policy.py",
    "test_expense_processor.py",
    "test_prepare_receipts.py",
    "test_generate_excel_cli.py",
]


def main():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    failed = []
    for suite in SUITES:
        print(f"\n{'=' * 60}\n{suite}\n{'=' * 60}")
        proc = subprocess.run([sys.executable, os.path.join(HERE, suite)], env=env)
        if proc.returncode != 0:
            failed.append(suite)

    print(f"\n{'=' * 60}")
    if failed:
        print(f"실패한 스위트: {', '.join(failed)}")
        sys.exit(1)
    print(f"전체 {len(SUITES)}개 스위트 통과")


if __name__ == "__main__":
    main()
