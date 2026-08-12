"""제출자 인적사항(성명/직책/부서) 저장소.

한도는 여기서 다루지 않는다 — 한도는 전적으로 `limit_policy.py` + `config.json` 소관이다.
(한도가 두 군데에 흩어져 있으면 규정이 바뀔 때 한쪽만 고치는 사고가 난다.)

기본 경로는 ~/.sikdae_config.json.
테스트에서는 SIKDAE_CONFIG_PATH 환경변수로 경로를 오버라이드한다.
"""

import json
import os
from dataclasses import dataclass, asdict


def _config_path() -> str:
    override = os.environ.get("SIKDAE_CONFIG_PATH")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".sikdae_config.json")


@dataclass
class UserConfig:
    user_name: str
    position: str = ""
    department: str = ""


def load_config() -> UserConfig | None:
    path = _config_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None

    # 구버전은 성명을 "name" 키로 저장했다.
    user_name = data.get("user_name") or data.get("name") or ""
    if not user_name:
        return None

    return UserConfig(
        user_name=user_name,
        position=data.get("position", ""),
        department=data.get("department", ""),
    )


def save_config(config: UserConfig) -> None:
    path = _config_path()
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                existing = loaded
        except (json.JSONDecodeError, OSError):
            existing = {}

    # 다른 도구가 같은 파일에 써 둔 키(예: 구버전 exe 의 daily_cap)를 지우지 않는다.
    existing.update(asdict(config))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
