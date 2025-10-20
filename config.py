"""
이 모듈은 Chzzk Rekoda 애플리케이션의 설정을 관리합니다.

- 이전 버전의 여러 설정 파일(`channels.json`, `cookie.json` 등)을 단일 `config.json`으로 마이그레이션합니다.
- `config.json` 파일에서 설정을 로드하고 저장하는 기능을 제공합니다.
"""
import os
import json
import shutil
from typing import Dict, Any

# --- 상수 정의 ---
CONFIG_FILE_PATH = "config.json"

# 이전 설정 파일 경로
OLD_FILES = {
    "channels": "channels.json",
    "delays": "delays.json",
    "cookies": "cookie.json",
    "threads": "thread.txt",
    "rescan_interval": "time_sleep.txt",
    "logging_enabled": "log_enabled.txt",
    "channel_count": "channel_count.txt"
}

def _read_old_json(file_path: str, default: Any = None) -> Any:
    """이전 JSON 파일을 읽습니다. 파일이 없으면 기본값을 반환합니다."""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding='utf-8') as f:
            return json.load(f)
    return default

def _read_old_text(file_path: str, default: Any = None) -> Any:
    """이전 텍스트 파일을 읽습니다. 파일이 없으면 기본값을 반환합니다."""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding='utf-8') as f:
            return f.read().strip()
    return default

def _create_default_config() -> Dict[str, Any]:
    """기본 설정 딕셔너리를 생성합니다."""
    return {
        "channels": [],
        "delays": {},
        "cookies": {"NID_SES": "", "NID_AUT": ""},
        "recorder_settings": {
            "threads": 2,
            "rescan_interval": 60,
            "logging_enabled": True
        }
    }

def _migrate_old_config():
    """이전 설정 파일들을 새로운 config.json으로 마이그레이션합니다."""
    print("기존 설정 파일들을 새로운 config.json으로 마이그레이션합니다...")

    config = _create_default_config()

    # 데이터 읽기
    channels_data = _read_old_json(OLD_FILES["channels"], [])
    delays_data = _read_old_json(OLD_FILES["delays"], {})
    cookies_data = _read_old_json(OLD_FILES["cookies"], {"NID_SES": "", "NID_AUT": ""})

    threads = _read_old_text(OLD_FILES["threads"], "2")
    rescan_interval = _read_old_text(OLD_FILES["rescan_interval"], "60")
    logging_enabled_str = _read_old_text(OLD_FILES["logging_enabled"], "true")

    # 새 설정 구조에 데이터 할당
    config["channels"] = channels_data
    config["delays"] = delays_data
    config["cookies"] = cookies_data
    config["recorder_settings"]["threads"] = int(threads) if threads.isdigit() else 2
    config["recorder_settings"]["rescan_interval"] = int(rescan_interval) if rescan_interval.isdigit() else 60
    config["recorder_settings"]["logging_enabled"] = logging_enabled_str.lower() == "true"

    # 새 설정 파일 저장
    save_config(config)
    print("config.json 파일이 성공적으로 생성되었습니다.")

    # 이전 파일 백업
    for key, file_path in OLD_FILES.items():
        if os.path.exists(file_path):
            shutil.move(file_path, f"{file_path}.bak")
    print("기존 설정 파일들은 .bak 확장자로 백업되었습니다.")

def load_config() -> Dict[str, Any]:
    """
    설정을 로드합니다. config.json이 없으면 마이그레이션을 시도하거나 기본 설정을 생성합니다.
    """
    is_old_config_present = any(os.path.exists(p) for p in OLD_FILES.values())

    if not os.path.exists(CONFIG_FILE_PATH):
        if is_old_config_present:
            _migrate_old_config()
        else:
            print("설정 파일이 없어 새로 생성합니다.")
            default_config = _create_default_config()
            save_config(default_config)

    # 설정 파일 읽기
    with open(CONFIG_FILE_PATH, "r", encoding='utf-8') as f:
        return json.load(f)

def save_config(config: Dict[str, Any]):
    """주어진 설정 딕셔너리를 config.json 파일에 저장합니다."""
    with open(CONFIG_FILE_PATH, "w", encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
