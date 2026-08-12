"""제출자 인적사항 조회/저장 CLI, 그리고 현재 한도 정책 확인 CLI.

한도 **변경**은 이 CLI 가 아니라 config.json 을 직접 고쳐서 한다 (규정 이력이
파일에 남아야 하기 때문). 여기서는 현재 어떤 한도가 적용되는지 확인만 한다.
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date

from config_store import UserConfig, load_config, save_config
from limit_policy import load_policy


def main():
    parser = argparse.ArgumentParser(description="식대 정산 설정 관리")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="저장된 인적사항을 JSON 으로 출력 (없으면 NOT_FOUND)")

    save_parser = sub.add_parser("save", help="성명/직책/부서 저장")
    save_parser.add_argument("--name", required=True)
    save_parser.add_argument("--position", default="")
    save_parser.add_argument("--department", default="")

    limit_parser = sub.add_parser(
        "show-limit", help="현재 한도 정책 확인 (특정 날짜에 적용될 한도를 조회)"
    )
    limit_parser.add_argument(
        "--on", default=None, metavar="YYYY-MM-DD",
        help="이 날짜의 영수증에 적용될 한도를 조회 (생략시 오늘)",
    )
    limit_parser.add_argument("--config", default=None, help="config.json 경로")

    args = parser.parse_args()

    if args.command == "show":
        config = load_config()
        print("NOT_FOUND" if config is None else json.dumps(asdict(config), ensure_ascii=False))
        return

    if args.command == "save":
        save_config(
            UserConfig(
                user_name=args.name,
                position=args.position,
                department=args.department,
            )
        )
        print("SAVED")
        return

    if args.command == "show-limit":
        if args.on:
            try:
                target = date.fromisoformat(args.on)
            except ValueError:
                print(f"ERROR: --on 은 YYYY-MM-DD 형식이어야 합니다 ({args.on})", file=sys.stderr)
                sys.exit(1)
        else:
            target = date.today()

        policy = load_policy(config_path=args.config)
        if policy.config_error:
            print(f"경고: {policy.config_error}", file=sys.stderr)
        decision = policy.for_date(target)
        print(f"{target.isoformat()} 적용 한도: {decision.describe()}")
        if policy.config_path:
            print(f"config: {policy.config_path}")
        else:
            print("config: (없음 — 내장 기본값 사용)")


if __name__ == "__main__":
    main()
