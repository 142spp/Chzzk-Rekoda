"""
이 스크립트는 Chzzk Rekoda의 메인 진입점으로, Chzzk 스트리밍 플랫폼을 위한 자동 녹화 도구입니다.

이 스크립트는 동시 스트림 녹화를 위해 asyncio를, 비동기 HTTP 요청을 위해 aiohttp를,
그리고 터미널에 실시간 진행 상황 대시보드를 표시하기 위해 Rich 라이브러리를 사용합니다.
스크립트는 여러 녹화 작업을 관리하고, 정상적인 종료를 처리하며, 상세한 로깅을 제공합니다.
"""
import asyncio
import hashlib
import logging
import os
import platform
import re
import signal
import sys
import time
import collections
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import aiohttp
import orjson

if platform.system() != "Windows":
    import uvloop

    uvloop.install()

# Rich 라이브러리 구성 요소 가져오기
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

# Rich를 위한 전역 콘솔 인스턴스
console = Console()

# 채널 진행 상황을 위한 공유 데이터 구조
channel_progress: Dict[str, Dict[str, Any]] = {}
channel_progress_lock = asyncio.Lock()

# 로그 메시지를 위한 큐 생성
log_queue: asyncio.Queue = asyncio.Queue()


# log_enabled 로드를 위한 헬퍼 함수
def get_log_enabled() -> bool:
    """'log_enabled.txt'에서 읽어 로깅 활성화 여부를 확인합니다.

    반환값:
        bool: 로깅이 활성화된 경우 True, 그렇지 않은 경우 False.
    """
    script_directory = os.path.dirname(os.path.abspath(__file__))
    log_enabled_file_path = os.path.join(script_directory, "log_enabled.txt")
    if os.path.exists(log_enabled_file_path):
        with open(log_enabled_file_path, "r") as f:
            return f.readline().strip().lower() == "true"
    return True


# log_enabled 토글 함수
def toggle_log_enabled():
    """로깅 상태를 활성화와 비활성화 사이에서 토글합니다.

    이 함수는 'log_enabled.txt'에서 현재 상태를 읽어와 반전시킨 후,
    새로운 상태를 파일에 다시 씁니다.
    """
    script_directory = os.path.dirname(os.path.abspath(__file__))
    log_enabled_file_path = os.path.join(script_directory, "log_enabled.txt")
    current_state = get_log_enabled()
    new_state = not current_state
    with open(log_enabled_file_path, "w") as f:
        f.write("true" if new_state else "false")
    print(f"로깅이 {'활성화' if new_state else '비활성화'}되었습니다.")


# 로그 메시지를 큐에 넣는 사용자 정의 로깅 핸들러
class QueueHandler(logging.Handler):
    """로그 레코드를 asyncio 큐에 넣는 로깅 핸들러입니다."""

    def __init__(self, queue: asyncio.Queue):
        """주어진 큐로 핸들러를 초기화합니다.

        Args:
            queue: 로그 메시지가 전송될 asyncio.Queue.
        """
        super().__init__()
        self.queue = queue

    def emit(self, record):
        """로그 레코드를 포맷하고 큐에 넣습니다.

        큐가 가득 차면 메시지는 삭제됩니다.

        Args:
            record: 내보낼 로그 레코드.
        """
        msg = self.format(record)
        try:
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # 큐가 가득 찬 경우 처리


# 로거 설정
class FfmpegStderrFilter(logging.Filter):
    """특정 ffmpeg stderr 메시지를 제외하기 위한 로깅 필터입니다."""

    def filter(self, record):
        """ffmpeg stderr에서 'Invalid DTS' 메시지를 필터링합니다.

        Args:
            record: 확인할 로그 레코드.

        반환값:
            bool: 메시지를 필터링해야 하는 경우 False, 그렇지 않은 경우 True.
        """
        msg = record.getMessage()
        if "ffmpeg stderr" in msg and "Invalid DTS" in msg:
            return False
        return True


def setup_logger() -> logging.Logger:
    """애플리케이션의 메인 로거를 구성하고 반환합니다.

    로거는 파일 핸들러(로깅이 활성화된 경우)와 UI에 로그를 표시하기 위한
    큐 핸들러로 구성됩니다.

    반환값:
        logging.Logger: 구성된 로거 인스턴스.
    """
    logger = logging.getLogger("Recorder")
    logger.setLevel(logging.DEBUG)

    # 로깅 활성화 여부 확인
    log_enabled = get_log_enabled()

    if log_enabled:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler = logging.FileHandler("log.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(FfmpegStderrFilter())
        logger.addHandler(file_handler)

    # QueueHandler는 항상 활성 상태 (UI 표시용)
    queue_handler = QueueHandler(log_queue)
    queue_handler.setLevel(logging.INFO)
    queue_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(queue_handler)

    logger.propagate = False

    return logger


logger = setup_logger()

print(
    "Chzzk Rekoda made by munsy0227\n"
    "If you encounter any bugs or errors, please report them on GitHub Issues!\n"
    "버그나 에러가 발생하면 깃허브 이슈에 제보해 주세요!"
)

# 상수
LIVE_DETAIL_API = (
    "https://api.chzzk.naver.com/service/v3/channels/{channel_id}/live-detail"
)
TIME_FILE_PATH = Path("time_sleep.txt")
THREAD_FILE_PATH = Path("thread.txt")
CHANNELS_FILE_PATH = Path("channels.json")
DELAYS_FILE_PATH = Path("delays.json")
COOKIE_FILE_PATH = Path("cookie.json")
PLUGIN_DIR_PATH = Path("plugin")
SPECIAL_CHARS_REMOVER = re.compile(r'[\\/:*?"<>|]')

# 최대 파일 이름 길이 상수
MAX_FILENAME_BYTES = 255
MAX_HASH_LENGTH = 8
RESERVED_BYTES = MAX_HASH_LENGTH + 1  # 해시 길이와 밑줄 하나

# 정상적인 종료를 위한 전역 변수
shutdown_event = asyncio.Event()


# 헬퍼 함수
async def setup_paths() -> Optional[Path]:
    """ffmpeg 실행 파일의 경로를 결정합니다.

    Windows에서는 로컬 'ffmpeg/bin' 디렉토리에서 ffmpeg를 확인하고,
    다른 운영 체제에서는 시스템의 PATH에서 확인합니다.

    반환값:
        Optional[Path]: ffmpeg 실행 파일의 경로. 찾을 수 없는 경우 None.
    """
    base_dir = Path(__file__).parent
    os_name = platform.system()
    ffmpeg_path: Optional[Path] = None

    if os_name == "Windows":
        ffmpeg_path = base_dir / "ffmpeg/bin/ffmpeg.exe"
        logger.info("Windows에서 실행 중입니다.")
    else:
        try:
            process = await asyncio.create_subprocess_exec(
                "which",
                "ffmpeg",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                ffmpeg_path = Path(stdout.decode().strip())
                logger.info(f"{os_name}에서 실행 중입니다. ffmpeg 경로: {ffmpeg_path}")
            else:
                logger.error("시스템 PATH에서 ffmpeg를 찾을 수 없습니다.")
        except Exception as e:
            logger.error(f"{os_name}에서 ffmpeg를 찾는 중 오류 발생: {e}")

    return ffmpeg_path


async def load_json_async(file_path: Path) -> Any:
    """JSON 파일을 비동기적으로 로드합니다.

    Args:
        file_path: JSON 파일의 경로.

    반환값:
        Any: 파싱된 JSON 내용. 오류 발생 시 None.
    """
    if not file_path.exists():
        logger.error(f"파일을 찾을 수 없습니다: {file_path}")
        return None
    try:
        async with aiofiles.open(file_path, "rb") as file:
            content = await file.read()
            return orjson.loads(content)
    except orjson.JSONDecodeError as e:
        logger.error(f"{file_path}에서 JSON 디코드 오류: {e}")
        return None
    except Exception as e:
        logger.error(f"{file_path}에서 JSON을 로드하는 중 오류 발생: {e}")
        return None


async def load_settings() -> Tuple[int, int, List[Dict[str, Any]], Dict[str, int]]:
    """각각의 파일에서 다양한 설정을 로드합니다.

    이 함수는 타임아웃, 스트림 세그먼트 스레드, 채널 목록 및
    지연 설정을 동시에 로드합니다.

    반환값:
        Tuple[int, int, List[Dict[str, Any]], Dict[str, int]]: 타임아웃,
        스트림 세그먼트 스레드, 채널 목록, 지연 딕셔너리를 포함하는 튜플.
    """
    settings = await asyncio.gather(
        load_json_async(TIME_FILE_PATH),
        load_json_async(THREAD_FILE_PATH),
        load_json_async(CHANNELS_FILE_PATH),
        load_json_async(DELAYS_FILE_PATH),
    )

    # 기본값 검증 및 설정
    timeout = settings[0] if isinstance(settings[0], int) else 60
    stream_segment_threads = settings[1] if isinstance(settings[1], int) else 2
    channels = settings[2] if isinstance(settings[2], list) else []
    delays = settings[3] if isinstance(settings[3], dict) else {}

    return timeout, stream_segment_threads, channels, delays


def get_auth_headers(cookies: Dict[str, str]) -> Dict[str, str]:
    """쿠키 값으로 인증 헤더를 구성합니다.

    Args:
        cookies: 'NID_AUT'와 'NID_SES' 쿠키를 포함하는 딕셔너리.

    반환값:
        Dict[str, str]: 인증된 요청을 위한 헤더 딕셔너리.
    """
    nid_aut = cookies.get("NID_AUT", "")
    nid_ses = cookies.get("NID_SES", "")
    return {
        "User-Agent": "Mozilla/5.0 (X11; Unix x86_64)",
        "Cookie": f"NID_AUT={nid_aut}; NID_SES={nid_ses}",
        "Origin": "https://chzzk.naver.com",
        "DNT": "1",
        "Sec-GPC": "1",
        "Connection": "keep-alive",
        "Referer": "",
    }


async def get_session_cookies() -> Dict[str, str]:
    """'cookie.json'에서 세션 쿠키를 로드합니다.

    반환값:
        Dict[str, str]: 세션 쿠키 딕셔너리. 찾을 수 없는 경우 빈 딕셔너리.
    """
    cookies = await load_json_async(COOKIE_FILE_PATH)
    if not cookies:
        logger.error(
            "'cookie.json'을 찾을 수 없습니다. 파일이 유효한지 확인하세요."
        )
        return {}
    return cookies


async def get_live_info(
    channel: Dict[str, Any], headers: Dict[str, str], session: aiohttp.ClientSession
) -> Tuple[str, Dict[str, Any]]:
    """주어진 채널의 라이브 스트림 정보를 가져옵니다.

    Args:
        channel: 채널 정보(예: id, name)를 포함하는 딕셔너리.
        headers: 요청에 사용할 헤더 딕셔너리.
        session: 요청에 사용할 aiohttp.ClientSession.

    반환값:
        Tuple[str, Dict[str, Any]]: 스트림 상태('OPEN', 'CLOSE', 'BLOCK')와
        라이브 상세 API 응답 내용을 포함하는 튜플. 실패 시 빈 문자열과 딕셔너리 반환.
    """
    logger.debug(f"채널 라이브 정보 가져오기: {channel.get('name', 'Unknown')}")
    try:
        async with session.get(
            LIVE_DETAIL_API.format(channel_id=channel["id"]), headers=headers
        ) as response:
            response.raise_for_status()
            data = await response.json()
            logger.debug(
                f"채널 라이브 정보 가져오기 성공: {channel.get('name', 'Unknown')}, 데이터: {data}"
            )

            content = data.get("content", {})
            status = content.get("status", "")
            if status == "CLOSE":
                logger.info(
                    f"채널 '{channel.get('name', 'Unknown')}'이(가) 현재 라이브 상태가 아닙니다."
                )
            if status == "BLOCK":
                logger.info(
                    f"채널 '{channel.get('name', 'Unknown')}'이(가) 차단되었습니다."
                )
                return status, {}
            return status, content
    except aiohttp.ClientError as e:
        logger.error(
            f"{channel.get('name', 'Unknown')}의 라이브 정보를 가져오는 중 HTTP 오류 발생: {e}"
        )
    except Exception as e:
        logger.error(
            f"{channel.get('name', 'Unknown')}의 라이브 정보를 가져오는 데 실패했습니다: {e}"
        )
    return "", {}


def shorten_filename(filename: str) -> str:
    """최대 허용 길이를 초과하는 경우 파일 이름을 줄입니다.

    파일 이름이 너무 길면 잘리고 파일 시스템 제한을 존중하면서
    고유성을 보장하기 위해 해시가 추가됩니다.

    Args:
        filename: 원본 파일 이름.

    반환값:
        str: 필요한 경우 줄인 파일 이름, 그렇지 않으면 원본 파일 이름.
    """
    compound_ext = ""
    if filename.endswith(".ts.part"):
        compound_ext = ".ts.part"
        name = filename[: -len(compound_ext)]
    else:
        name, compound_ext = os.path.splitext(filename)

    filename_bytes = filename.encode("utf-8")
    if len(filename_bytes) > MAX_FILENAME_BYTES:
        hash_value = hashlib.sha256(filename_bytes).hexdigest()[:MAX_HASH_LENGTH]
        max_name_length = MAX_FILENAME_BYTES - (
            len(compound_ext.encode("utf-8")) + MAX_HASH_LENGTH + 1
        )
        shortened_name_bytes = name.encode("utf-8")[:max_name_length]
        shortened_name = shortened_name_bytes.decode("utf-8", "ignore")
        shortened_filename = f"{shortened_name}_{hash_value}{compound_ext}"
        logger.warning(
            f"파일 이름 '{filename}'이(가) 너무 깁니다. '{shortened_filename}'(으)로 줄입니다."
        )
        return shortened_filename

    return filename


def format_size(size_bytes: float) -> str:
    """바이트 단위 크기를 사람이 읽을 수 있는 문자열로 포맷합니다.

    Args:
        size_bytes: 바이트 단위 크기.

    반환값:
        str: 사람이 읽을 수 있는 크기 문자열 표현 (예: "1.23 MB").
    """
    if size_bytes <= 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"


time_pattern = re.compile(r"(\d+):(\d+):(\d+)\.(\d+)")


def parse_time(time_str: str) -> float:
    """ffmpeg 출력의 시간 문자열을 초 단위로 파싱합니다.

    Args:
        time_str: 'HH:MM:SS.ms' 형식의 시간 문자열.

    반환값:
        float: 총 초 수.
    """
    logger.debug(f"out_time 파싱: {time_str}")
    match = time_pattern.match(time_str)
    if not match:
        return 0
    hours, minutes, seconds, fractions = map(int, match.groups())
    total_seconds = (
        hours * 3600 + minutes * 60 + seconds + fractions / (10 ** len(str(fractions)))
    )
    return total_seconds


speed_samples = collections.deque(maxlen=5)


async def read_stream(
    stream: asyncio.StreamReader, channel_id: str, stream_type: str
) -> None:
    """ffmpeg의 stderr 스트림에서 진행 상황을 읽고 파싱합니다.

    이 함수는 스트림에서 라인을 읽고, 키-값 쌍을 파싱하고,
    비트레이트와 다운로드 속도를 계산하고, 전역 `channel_progress`
    딕셔너리를 업데이트합니다.

    Args:
        stream: ffmpeg의 stderr를 위한 asyncio.StreamReader.
        channel_id: 녹화 중인 채널의 ID.
        stream_type: 스트림 유형을 나타내는 문자열 (예: 'stderr').
    """
    summary: Dict[str, str] = {}
    last_log_time = time.time()

    prev_total_size = None
    prev_time = None

    while not stream.at_eof():
        try:
            line = await stream.readline()
            if not line:
                break
            line_str = line.decode(errors="ignore").strip()

            # 로그 추가
            logger.debug(f"ffmpeg {stream_type} [{channel_id}]: {line_str}")

            if "=" not in line_str:
                continue

            key, value = line_str.split("=", 1)
            summary[key.strip()] = value.strip()

            if key.strip() == "progress":
                total_size_str = summary.get("total_size", "0")
                out_time_str = summary.get("out_time", "0")

                try:
                    total_size = int(total_size_str)
                except ValueError:
                    total_size = 0

                total_size_formatted = format_size(total_size)

                # out_time을 초로 변환
                out_time_seconds = parse_time(out_time_str)

                # 비트레이트 계산
                if out_time_seconds > 0:
                    bitrate = (total_size * 8) / out_time_seconds  # 초당 비트
                    bitrate_kbps = bitrate / 1000  # kbps로 변환
                    bitrate_formatted = f"{bitrate_kbps:.2f} kbps"
                else:
                    bitrate_formatted = "N/A"

                # 다운로드 속도 계산
                current_time = time.time()
                if prev_total_size is not None and prev_time is not None:
                    bytes_diff = total_size - prev_total_size
                    time_diff = current_time - prev_time
                    if time_diff > 0:
                        instant_speed = bytes_diff / time_diff  # 초당 바이트
                        speed_samples.append(instant_speed)
                        average_speed = sum(speed_samples) / len(speed_samples)
                        download_speed_formatted = format_size(average_speed) + "/s"
                    else:
                        download_speed_formatted = "N/A"
                    prev_total_size = total_size
                    prev_time = current_time
                else:
                    download_speed_formatted = "N/A"
                    prev_total_size = total_size
                    prev_time = current_time

                # 진행 데이터 업데이트
                async with channel_progress_lock:
                    if channel_id in channel_progress:
                        channel_progress[channel_id].update(
                            {
                                "bitrate": bitrate_formatted,
                                "download_speed": download_speed_formatted,
                                "total_size": total_size_formatted,
                                "out_time": out_time_str,
                            }
                        )

                last_log_time = current_time
                summary.clear()
        except Exception as e:
            logger.error(f"{channel_id}의 스트림을 읽는 중 오류 발생: {e}")
            break


async def record_stream(
    channel: Dict[str, Any],
    headers: Dict[str, str],
    session: aiohttp.ClientSession,
    delay: int,
    timeout: int,
    ffmpeg_path: Path,
    stream_segment_threads: int,
) -> None:
    """단일 채널의 라이브 스트림을 녹화합니다.

    이 함수는 채널의 전체 녹화 생명주기를 처리합니다:
    - 채널이 라이브 상태가 될 때까지 기다립니다.
    - `streamlink`와 `ffmpeg` 하위 프로세스를 구성하고 관리합니다.
    - `streamlink`의 출력을 `ffmpeg`로 파이프합니다.
    - 스트림을 모니터링하고 스트림이 끊기면 프로세스를 다시 시작합니다.
    - 정상적인 종료 및 파일 이름 변경을 처리합니다.

    Args:
        channel: 채널 정보를 포함하는 딕셔너리.
        headers: 인증된 요청을 위한 헤더.
        session: API 호출을 위한 aiohttp.ClientSession.
        delay: 녹화를 시작하기 전의 지연 시간(초).
        timeout: 라이브 스트림을 다시 확인하기 전 대기할 간격(초).
        ffmpeg_path: ffmpeg 실행 파일의 경로.
        stream_segment_threads: streamlink가 사용할 스레드 수.
    """
    channel_name = channel.get("name", "Unknown")
    channel_id = str(channel.get("id", "Unknown"))
    logger.info(f"채널 스트림 녹화 시도: {channel_name}")
    await asyncio.sleep(delay)

    if channel.get("active", "on") == "off":
        logger.info(f"{channel_name} 채널이 비활성 상태입니다. 녹화를 건너뜁니다.")
        return

    recording_started = False
    stream_process: Optional[asyncio.subprocess.Process] = None
    ffmpeg_process: Optional[asyncio.subprocess.Process] = None

    try:
        while not shutdown_event.is_set():
            stream_url = f"https://chzzk.naver.com/live/{channel['id']}"
            if stream_url:
                logger.debug(f"채널 스트림 URL 찾음: {channel_name}")
                try:
                    cookies = await get_session_cookies()
                    while not shutdown_event.is_set():
                        status, live_info = await get_live_info(
                            channel, headers, session
                        )
                        if status == "OPEN":
                            break

                        logger.info(
                            f"채널 '{channel_name}'이(가) 라이브 상태가 될 때까지 대기 중..."
                        )
                        try:
                            await asyncio.wait_for(
                                shutdown_event.wait(), timeout=timeout
                            )
                        except asyncio.TimeoutError:
                            continue

                    if shutdown_event.is_set():
                        break

                    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                    live_title = SPECIAL_CHARS_REMOVER.sub(
                        "", live_info.get("liveTitle", "").rstrip()
                    )
                    output_dir = Path(
                        channel.get("output_dir", "./recordings")
                    ).expanduser()
                    temp_output_file = shorten_filename(
                        f"[{current_time.replace(':', '_')}] {channel_name} {live_title}.ts.part"
                    )
                    final_output_file = temp_output_file[:-5]  # '.part' 제거
                    temp_output_path = output_dir / temp_output_file
                    final_output_path = output_dir / final_output_file

                    output_dir.mkdir(parents=True, exist_ok=True)

                    if not recording_started:
                        logger.info(
                            f"{channel_name}의 녹화가 {current_time}에 시작되었습니다."
                        )
                        recording_started = True
                        recording_start_time = current_time

                    if stream_process and stream_process.returncode is None:
                        stream_process.kill()
                        await stream_process.wait()
                        logger.info("기존 스트림 프로세스가 성공적으로 종료되었습니다.")

                    if ffmpeg_process and ffmpeg_process.returncode is None:
                        ffmpeg_process.kill()
                        await ffmpeg_process.wait()
                        logger.info("기존 ffmpeg 프로세스가 성공적으로 종료되었습니다.")

                    # 파이프 안전하게 생성
                    read_pipe, write_pipe = os.pipe()
                    try:
                        # streamlink 프로세스 시작
                        streamlink_cmd = [
                            "streamlink",
                            "--stdout",
                            stream_url,
                            "best",
                            "--hls-live-restart",
                            "--plugin-dirs",
                            str(PLUGIN_DIR_PATH),
                            "--stream-segment-threads",
                            str(stream_segment_threads),
                            "--http-header",
                            f'Cookie=NID_AUT={cookies.get("NID_AUT", "")}; NID_SES={cookies.get("NID_SES", "")}',
                            "--http-header",
                            "User-Agent=Mozilla/5.0 (X11; Unix x86_64)",
                            "--http-header",
                            "Origin=https://chzzk.naver.com",
                            "--http-header",
                            "DNT=1",
                            "--http-header",
                            "Sec-GPC=1",
                            "--http-header",
                            "Connection=keep-alive",
                            "--http-header",
                            "Referer=",
                            "--ffmpeg-ffmpeg",
                            str(ffmpeg_path),
                            "--ffmpeg-copyts",
                            "--hls-segment-stream-data",
                        ]

                        stream_process = await asyncio.create_subprocess_exec(
                            *streamlink_cmd,
                            stdout=write_pipe,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        os.close(write_pipe)  # 부모에서 쓰기 끝 닫기

                        # ffmpeg 프로세스 시작
                        ffmpeg_cmd = [
                            str(ffmpeg_path),
                            "-i",
                            "pipe:0",
                            "-c",
                            "copy",
                            "-progress",
                            "pipe:2",
                            "-copy_unknown",
                            "-map_metadata:s:a",
                            "0:s:a",
                            "-map_metadata:s:v",
                            "0:s:v",
                            "-bsf:v",
                            "h264_mp4toannexb",
                            "-bsf:a",
                            "aac_adtstoasc",
                            "-f",
                            "mpegts",
                            "-mpegts_flags",
                            "resend_headers",
                            "-bsf",
                            "setts=pts=PTS-STARTPTS",
                            "-fflags",
                            "+genpts+discardcorrupt+nobuffer",
                            "-avioflags",
                            "direct",
                            "-y",
                            str(temp_output_path),
                        ]

                        ffmpeg_process = await asyncio.create_subprocess_exec(
                            *ffmpeg_cmd,
                            stdin=read_pipe,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        os.close(read_pipe)  # 부모에서 읽기 끝 닫기

                        # 채널 진행 데이터 초기화
                        async with channel_progress_lock:
                            channel_progress[channel_id] = {
                                "channel_name": channel_name,
                                "bitrate": "N/A",
                                "download_speed": "N/A",
                                "total_size": "N/A",
                                "out_time": "N/A",
                                "recording_start_time": recording_start_time,
                            }

                        stderr_task = asyncio.create_task(
                            read_stream(ffmpeg_process.stderr, channel_id, "stderr")
                        )
                        ffmpeg_wait_task = asyncio.create_task(ffmpeg_process.wait())

                        await asyncio.wait(
                            [stderr_task, ffmpeg_wait_task],
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        # 종료 이벤트가 설정되면 프로세스 종료
                        if shutdown_event.is_set():
                            if ffmpeg_process.returncode is None:
                                ffmpeg_process.kill()
                                await ffmpeg_process.wait()
                            if stream_process.returncode is None:
                                stream_process.kill()
                                await stream_process.wait()
                            break

                        logger.info(
                            f"{channel_name}의 ffmpeg 프로세스가 반환 코드 {ffmpeg_process.returncode}(으)로 종료되었습니다."
                        )
                        if recording_started:
                            logger.info(f"{channel_name}의 녹화가 중지되었습니다.")
                            recording_started = False

                        await stream_process.wait()
                        logger.info(
                            f"{channel_name}의 스트림 녹화 프로세스가 반환 코드 {stream_process.returncode}(으)로 종료되었습니다."
                        )

                        # 임시 파일의 이름을 최종 출력으로 원자적으로 변경
                        if temp_output_path.exists():
                            temp_output_path.rename(final_output_path)
                            logger.info(f"녹화가 {final_output_path}에 저장되었습니다.")

                        # 진행 데이터 제거
                        async with channel_progress_lock:
                            channel_progress.pop(channel_id, None)

                    finally:
                        # 파이프가 닫혔는지 확인
                        for fd in (read_pipe, write_pipe):
                            try:
                                os.close(fd)
                            except OSError:
                                pass

                except asyncio.CancelledError:
                    logger.info(f"{channel_name}의 녹화 작업이 취소되었습니다.")
                    break
                except Exception as e:
                    logger.exception(
                        f"{channel_name}을(를) 녹화하는 중 오류 발생: {e}"
                    )
                    if recording_started:
                        logger.info(f"{channel_name}의 녹화가 중지되었습니다.")
                        recording_started = False
            else:
                logger.error(f"{channel_name}에 사용할 수 있는 스트림 URL이 없습니다.")
                if recording_started:
                    logger.info(f"{channel_name}의 녹화가 중지되었습니다.")
                    recording_started = False

            # 종료 이벤트 또는 타임아웃 대기
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                continue

    finally:
        if stream_process and stream_process.returncode is None:
            stream_process.kill()
            await stream_process.wait()
        if ffmpeg_process and ffmpeg_process.returncode is None:
            ffmpeg_process.kill()
            await ffmpeg_process.wait()
        # 남은 임시 파일 이름 변경 시도
        if recording_started and temp_output_path.exists():
            temp_output_path.rename(final_output_path)
            logger.info(f"녹화가 {final_output_path}에 저장되었습니다.")
        # 진행 데이터 제거
        async with channel_progress_lock:
            channel_progress.pop(channel_id, None)


async def manage_recording_tasks():
    """현재 설정에 따라 모든 활성 녹화 작업을 관리합니다.

    이 함수는 메인 작업 관리자 역할을 합니다:
    - 파일에서 주기적으로 설정을 다시 로드합니다.
    - 새로 추가되거나 활성화된 채널에 대해 새 녹화 작업을 시작합니다.
    - 제거되거나 비활성화된 채널의 작업을 취소합니다.
    - 종료 신호를 받을 때까지 애플리케이션이 계속 실행되도록 합니다.
    """
    active_tasks: Dict[str, asyncio.Task] = {}
    timeout, stream_segment_threads, channels, delays = await load_settings()
    cookies = await get_session_cookies()
    headers = get_auth_headers(cookies)
    ffmpeg_path = await setup_paths()

    if not ffmpeg_path or not ffmpeg_path.exists():
        logger.error("ffmpeg 실행 파일을 찾을 수 없습니다. 종료합니다.")
        return

    async with aiohttp.ClientSession() as session:
        try:
            while not shutdown_event.is_set():
                (
                    new_timeout,
                    new_stream_segment_threads,
                    new_channels,
                    new_delays,
                ) = await load_settings()
                active_channels = 0

                current_channel_ids = {
                    str(channel.get("id")) for channel in new_channels
                }

                # 제거되거나 비활성화된 채널의 작업 취소
                for channel_id in list(active_tasks.keys()):
                    if channel_id not in current_channel_ids:
                        task = active_tasks.pop(channel_id)
                        task.cancel()
                        logger.info(
                            f"비활성화된 채널의 녹화 작업 취소됨: {channel_id}"
                        )
                        # 진행 데이터 제거
                        async with channel_progress_lock:
                            channel_progress.pop(channel_id, None)

                for channel in new_channels:
                    channel_id = str(channel.get("id"))
                    if not channel_id:
                        logger.warning("구성에서 채널 ID가 누락되었습니다.")
                        continue
                    if channel_id not in active_tasks:
                        if channel.get("active", "on") == "on":
                            task = asyncio.create_task(
                                record_stream(
                                    channel,
                                    headers,
                                    session,
                                    new_delays.get(channel.get("identifier"), 0),
                                    new_timeout,
                                    ffmpeg_path,
                                    new_stream_segment_threads,
                                )
                            )
                            active_tasks[channel_id] = task
                            active_channels += 1
                            logger.info(
                                f"새 활성 채널에 대한 녹화 작업 시작됨: {channel.get('name', 'Unknown')}"
                            )
                    else:
                        if channel.get("active", "on") == "off":
                            task = active_tasks.pop(channel_id)
                            task.cancel()
                            logger.info(
                                f"비활성화된 채널의 녹화 작업 취소됨: {channel.get('name', 'Unknown')}"
                            )
                            # 진행 데이터 제거
                            async with channel_progress_lock:
                                channel_progress.pop(channel_id, None)
                        else:
                            active_channels += 1

                if active_channels == 0:
                    logger.info("모든 채널이 비활성 상태입니다. 활성 녹화가 없습니다.")

                # 종료 이벤트 또는 10초 대기
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=10)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.info("녹화 관리 작업이 취소되었습니다.")
        finally:
            # 모든 활성 녹화 작업 취소
            for task in active_tasks.values():
                task.cancel()
            await asyncio.gather(*active_tasks.values(), return_exceptions=True)


def handle_shutdown():
    """애플리케이션의 정상적인 종료를 시작합니다."""
    logger.info("종료 신호를 받았습니다. 종료 중...")
    shutdown_event.set()


async def display_progress():
    """터미널에 실시간 진행 상황 대시보드를 표시합니다.

    이 함수는 Rich 라이브러리를 사용하여 다음을 표시하는 레이아웃을 만듭니다:
    - 최신 로그 메시지가 있는 패널.
    - 각 활성 녹화에 대한 테이블이 있는 패널, 비트레이트, 다운로드 속도,
      총 크기 및 기간을 표시합니다.
    """
    layout = Layout()

    # 레이아웃을 위쪽과 아래쪽 섹션으로 분할
    layout.split(
        Layout(name="upper", ratio=1),
        Layout(name="lower", ratio=3),
    )

    log_messages = []  # 로그 메시지 목록

    with Live(layout, console=console, refresh_per_second=5, screen=False):
        while not shutdown_event.is_set() or not log_queue.empty():
            # 채널 진행 상황 표시 업데이트
            channel_panels = []

            async with channel_progress_lock:
                if channel_progress:
                    for progress_data in channel_progress.values():
                        # 각 채널에 대한 테이블 생성
                        table = Table(show_header=True, header_style="bold magenta")
                        table.add_column("채널", style="cyan", no_wrap=True)
                        table.add_column("비트레이트")
                        table.add_column("다운로드 속도")
                        table.add_column("총 크기")
                        table.add_column("경과 시간")
                        table.add_column("시작 시간")

                        table.add_row(
                            progress_data.get("channel_name", "Unknown"),
                            progress_data.get("bitrate", "N/A"),
                            progress_data.get("download_speed", "N/A"),
                            progress_data.get("total_size", "N/A"),
                            progress_data.get("out_time", "N/A"),
                            progress_data.get("recording_start_time", "N/A"),
                        )

                        # 각 채널의 테이블을 패널로 래핑
                        panel = Panel(
                            table, title=progress_data.get("channel_name", "Unknown")
                        )
                        channel_panels.append(panel)
                else:
                    # 녹화 중인 채널이 없으면 메시지 표시
                    channel_panels.append(
                        Panel("활성 녹화 없음.", title="녹화 진행 상황")
                    )

            # 모든 채널 패널을 함께 그룹화
            progress_display = Group(*channel_panels)

            layout["lower"].update(progress_display)

            # 로그 메시지 업데이트
            try:
                while True:
                    msg = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                    log_messages.append(msg)
                    # 마지막 15개의 로그 메시지만 유지
                    log_messages = log_messages[-15:]
            except (asyncio.QueueEmpty, asyncio.TimeoutError):
                pass

            # 로그 패널 업데이트
            log_text = Text("\n".join(log_messages))
            layout["upper"].update(Panel(log_text, title="로그"))

            await asyncio.sleep(0.1)


async def main() -> None:
    """애플리케이션의 메인 진입점.

    - 정상적인 종료를 위한 신호 핸들러를 설정합니다.
    - `display_progress` 및 `manage_recording_tasks` 작업을 시작합니다.
    - 작업이 완료될 때까지 기다리고 종료 절차를 처리합니다.
    """
    # 정상적인 종료를 위한 신호 핸들러 등록
    loop = asyncio.get_running_loop()
    if platform.system() != "Windows":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_shutdown)
    else:
        # Windows에서는 이벤트 루프에서 신호가 지원되지 않습니다.
        # 대신 KeyboardInterrupt 예외를 처리합니다.
        pass

    display_task = asyncio.create_task(display_progress())

    try:
        await manage_recording_tasks()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt를 받았습니다. 종료 중...")
        handle_shutdown()
        # 작업이 정리될 시간을 잠시 줍니다.
        await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        logger.info("메인 작업이 취소되었습니다.")
    except Exception as e:
        logger.exception(f"오류 발생: {e}")
    finally:
        # 남은 로그를 처리하기 위해 display_progress를 기다립니다.
        shutdown_event.set()
        await display_task
        logger.info("녹화기가 종료되었습니다.")


if __name__ == "__main__":
    asyncio.run(main())
