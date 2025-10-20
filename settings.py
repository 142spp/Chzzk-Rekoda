"""
이 스크립트는 Chzzk Rekoda 애플리케이션 설정을 위한 명령줄 인터페이스를 제공합니다.

사용자는 이 인터페이스를 통해 채널 설정(추가, 삭제, 녹화 토글),
녹화 매개변수(스레드, 재검색 간격) 조정, 인증 쿠키 설정,
로깅 토글 등을 관리할 수 있습니다. 모든 설정은 단일 `config.json` 파일에 저장됩니다.
"""
from typing import Dict, Any
from config import load_config, save_config

# 전역 설정 변수
config: Dict[str, Any] = {}

def try_again():
    """사용자에게 다시 시도하라는 메시지를 출력합니다."""
    print("다시 시도해주세요.\n")

# --- 핵심 기능 ---

def add_channel():
    """새 채널 추가를 위한 사용자 프롬프트를 처리하고 저장합니다."""
    ch_id = input("추가할 스트리머 채널의 고유 ID를 입력하세요: ")
    name = input("스트리머 이름을 입력하세요: ")
    output_dir = input("저장 경로를 지정하세요 (기본값 './recordings'는 비워두세요): ") or "./recordings"

    while True:
        answer = input(f"ID: {ch_id}, 이름: {name}, 저장 경로: {output_dir}. 맞습니까? (Y/N): ").upper()
        if answer == 'Y':
            channel_count = len(config['channels'])
            identifier = f"ch{channel_count + 1}"

            config['channels'].append({
                "id": ch_id,
                "name": name,
                "output_dir": output_dir,
                "identifier": identifier,
                "active": "on",
            })
            config['delays'][identifier] = channel_count

            save_config(config)
            print("채널이 추가되었습니다.")
            break
        elif answer == 'N':
            print("채널 추가가 취소되었습니다.")
            break
        else:
            try_again()

def delete_channel():
    """기존 채널 삭제를 위한 사용자 프롬프트를 처리합니다."""
    if not config['channels']:
        print("삭제할 채널이 없습니다.")
        return

    print("현재 채널 목록:")
    for idx, channel in enumerate(config['channels'], 1):
        print(f"{idx}. ID: {channel['id']}, 이름: {channel['name']}")

    try:
        choice = int(input("삭제할 채널의 번호를 입력하세요: ")) - 1
        if 0 <= choice < len(config['channels']):
            deleted_channel = config['channels'].pop(choice)
            print(f"삭제된 채널: ID: {deleted_channel['id']}, 이름: {deleted_channel['name']}")

            # 식별자 및 지연 시간 재정렬
            new_delays = {}
            for i, channel in enumerate(config['channels']):
                new_id = f"ch{i + 1}"
                channel["identifier"] = new_id
                new_delays[new_id] = i
            config['delays'] = new_delays

            save_config(config)
            print("채널이 삭제되었습니다.")
        else:
            print("잘못된 채널 번호입니다.")
    except ValueError:
        print("잘못된 입력입니다. 유효한 번호를 입력해주세요.")

def toggle_channel_recording():
    """채널의 녹화 상태를 'on'과 'off' 사이에서 토글합니다."""
    if not config['channels']:
        print("토글할 채널이 없습니다.")
        return

    print("현재 채널 목록:")
    for idx, channel in enumerate(config['channels'], 1):
        status = '켜짐' if channel.get('active', 'on') == 'on' else '꺼짐'
        print(f"{idx}. ID: {channel['id']}, 이름: {channel['name']}, 녹화 상태: {status}")

    try:
        choice = int(input("녹화 상태를 토글할 채널의 번호를 입력하세요: ")) - 1
        if 0 <= choice < len(config['channels']):
            channel = config['channels'][choice]
            current_state = channel.get("active", "on")
            new_state = "off" if current_state == "on" else "on"
            channel["active"] = new_state

            save_config(config)
            print(f"{channel['name']} 채널의 녹화 상태가 {'꺼짐' if new_state == 'off' else '켜짐'}(으)로 변경되었습니다.")
        else:
            print("잘못된 채널 번호입니다.")
    except ValueError:
        print("잘못된 입력입니다. 유효한 번호를 입력해주세요.")

def set_recording_threads():
    """사용자가 녹화 스레드 수를 설정할 수 있도록 합니다."""
    current_threads = config['recorder_settings']['threads']
    print(f"현재 녹화 스레드 수는 {current_threads}개입니다.")
    print("권장: 저사양 시스템은 2, 고사양 시스템은 4.")

    new_threads = input("변경할 스레드 수를 입력하세요: ")
    if new_threads.isdigit():
        config['recorder_settings']['threads'] = int(new_threads)
        save_config(config)
        print("스레드 수가 변경되었습니다.")
    else:
        print("잘못된 입력입니다. 숫자를 입력해주세요.")

def set_rescan_interval():
    """사용자가 방송 재검색 간격을 설정할 수 있도록 합니다."""
    current_interval = config['recorder_settings']['rescan_interval']
    print(f"현재 방송 재검색 간격은 {current_interval}초입니다.")

    new_interval = input("변경할 재검색 간격을 초 단위로 입력하세요: ")
    if new_interval.isdigit():
        config['recorder_settings']['rescan_interval'] = int(new_interval)
        save_config(config)
        print("방송 재검색 간격이 변경되었습니다.")
    else:
        print("잘못된 입력입니다. 숫자를 입력해주세요.")

def set_cookie_info():
    """사용자에게 쿠키 값을 입력받아 저장합니다."""
    ses = input("NID_SES 값을 입력하세요: ")
    aut = input("NID_AUT 값을 입력하세요: ")
    config['cookies'] = {"NID_SES": ses, "NID_AUT": aut}
    save_config(config)
    print("쿠키 정보가 성공적으로 저장되었습니다.")

def toggle_logging():
    """로깅 설정을 켜거나 끕니다."""
    is_enabled = config['recorder_settings']['logging_enabled']
    config['recorder_settings']['logging_enabled'] = not is_enabled
    save_config(config)
    print(f"로깅이 {'비활성화' if is_enabled else '활성화'}되었습니다.")

# --- 메뉴 함수 ---

def manage_channel_settings():
    """채널 설정 하위 메뉴를 표시하고 사용자 입력을 처리합니다."""
    while True:
        print("\n--- 채널 설정 ---")
        print("1. 채널 추가")
        print("2. 채널 삭제")
        print("3. 채널 녹화 토글")
        print("4. 뒤로 가기")
        choice = input("원하는 작업을 선택하세요: ")

        actions = {"1": add_channel, "2": delete_channel, "3": toggle_channel_recording}
        if choice in actions:
            actions[choice]()
        elif choice == "4":
            break
        else:
            try_again()

def manage_recording_settings():
    """녹화 설정 하위 메뉴를 표시하고 사용자 입력을 처리합니다."""
    while True:
        print("\n--- 녹화 설정 ---")
        print("1. 녹화 스레드 설정")
        print("2. 방송 재검색 간격 설정")
        print("3. 뒤로 가기")
        choice = input("원하는 작업을 선택하세요: ")

        actions = {"1": set_recording_threads, "2": set_rescan_interval}
        if choice in actions:
            actions[choice]()
        elif choice == "3":
            break
        else:
            try_again()

def main_menu():
    """메인 메뉴를 표시하고 사용자 상호 작용 루프를 조정합니다."""
    global config
    config = load_config()

    while True:
        print("\n--- Chzzk 자동 녹화 설정 ---")
        print("1. 채널 설정")
        print("2. 녹화 설정")
        print("3. 쿠키 설정 (성인 인증용)")

        log_status = "활성화" if config['recorder_settings']['logging_enabled'] else "비활성화"
        print(f"4. 로깅 토글 (현재: {log_status})")
        print("5. 종료")

        choice = input("원하는 작업을 선택하세요: ")

        menu_actions = {
            "1": manage_channel_settings,
            "2": manage_recording_settings,
            "3": set_cookie_info,
            "4": toggle_logging
        }

        if choice in menu_actions:
            menu_actions[choice]()
        elif choice == "5":
            print("설정을 종료합니다.")
            break
        else:
            try_again()

if __name__ == "__main__":
    main_menu()
