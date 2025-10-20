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
import time
import collections
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import orjson
from config import load_config  # 설정 모듈 가져오기

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

# --- 로깅 설정 ---

class QueueHandler(logging.Handler):
    """로그 레코드를 asyncio 큐에 넣는 로깅 핸들러입니다."""
    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        msg = self.format(record)
        try:
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass

class FfmpegStderrFilter(logging.Filter):
    """특정 ffmpeg stderr 메시지를 제외하기 위한 로깅 필터입니다."""
    def filter(self, record):
        msg = record.getMessage()
        return not ("ffmpeg stderr" in msg and "Invalid DTS" in msg)

def setup_logger(config: Dict[str, Any]) -> logging.Logger:
    """애플리케이션의 메인 로거를 구성하고 반환합니다."""
    logger = logging.getLogger("Recorder")
    logger.setLevel(logging.DEBUG)

    # 이전 핸들러 제거
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    if config.get("recorder_settings", {}).get("logging_enabled", True):
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler = logging.FileHandler("log.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(FfmpegStderrFilter())
        logger.addHandler(file_handler)

    queue_handler = QueueHandler(log_queue)
    queue_handler.setLevel(logging.INFO)
    queue_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(queue_handler)

    logger.propagate = False
    return logger

# 초기 설정 로드 및 로거 설정
config = load_config()
logger = setup_logger(config)

print(
    "Chzzk Rekoda made by munsy0227\n"
    "If you encounter any bugs or errors, please report them on GitHub Issues!\n"
    "버그나 에러가 발생하면 깃허브 이슈에 제보해 주세요!"
)

# --- 상수 및 전역 변수 ---
LIVE_DETAIL_API = "https://api.chzzk.naver.com/service/v3/channels/{channel_id}/live-detail"
PLUGIN_DIR_PATH = Path("plugin")
SPECIAL_CHARS_REMOVER = re.compile(r'[\\/:*?"<>|]')
MAX_FILENAME_BYTES = 255
MAX_HASH_LENGTH = 8
shutdown_event = asyncio.Event()
time_pattern = re.compile(r"(\d+):(\d+):(\d+)\.(\d+)")
speed_samples = collections.deque(maxlen=5)

# --- 헬퍼 함수 ---

async def setup_paths() -> Optional[Path]:
    """ffmpeg 실행 파일의 경로를 결정합니다."""
    base_dir = Path(__file__).parent
    os_name = platform.system()
    if os_name == "Windows":
        return base_dir / "ffmpeg/bin/ffmpeg.exe"

    try:
        process = await asyncio.create_subprocess_exec(
            "which", "ffmpeg",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        if process.returncode == 0:
            ffmpeg_path = Path(stdout.decode().strip())
            logger.info(f"{os_name}에서 실행 중입니다. ffmpeg 경로: {ffmpeg_path}")
            return ffmpeg_path
        else:
            logger.error("시스템 PATH에서 ffmpeg를 찾을 수 없습니다.")
            return None
    except Exception as e:
        logger.error(f"{os_name}에서 ffmpeg를 찾는 중 오류 발생: {e}")
        return None

def get_auth_headers(cookies: Dict[str, str]) -> Dict[str, str]:
    """쿠키 값으로 인증 헤더를 구성합니다."""
    return {
        "User-Agent": "Mozilla/5.0 (X11; Unix x86_64)",
        "Cookie": f"NID_AUT={cookies.get('NID_AUT', '')}; NID_SES={cookies.get('NID_SES', '')}",
        "Origin": "https://chzzk.naver.com",
        "Referer": "https://chzzk.naver.com",
    }

async def get_live_info(channel: Dict[str, Any], headers: Dict[str, str], session: aiohttp.ClientSession) -> Tuple[str, Dict[str, Any]]:
    """주어진 채널의 라이브 스트림 정보를 가져옵니다."""
    url = LIVE_DETAIL_API.format(channel_id=channel["id"])
    try:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            data = await response.json()
            content = data.get("content", {})
            status = content.get("status", "CLOSE")

            if status == "BLOCK":
                logger.info(f"채널 '{channel.get('name', 'Unknown')}'이(가) 차단되었습니다.")

            return status, content
    except aiohttp.ClientError as e:
        logger.error(f"{channel.get('name', 'Unknown')}의 라이브 정보를 가져오는 중 HTTP 오류 발생: {e}")
    except Exception as e:
        logger.error(f"{channel.get('name', 'Unknown')}의 라이브 정보를 가져오는 데 실패했습니다: {e}")
    return "CLOSE", {}

def shorten_filename(filename: str) -> str:
    """파일 이름이 너무 길 경우 줄입니다."""
    if len(filename.encode('utf-8')) > MAX_FILENAME_BYTES:
        base, ext = os.path.splitext(filename)
        hash_value = hashlib.sha256(filename.encode('utf-8')).hexdigest()[:MAX_HASH_LENGTH]
        max_base_len = MAX_FILENAME_BYTES - len(ext.encode('utf-8')) - 1 - MAX_HASH_LENGTH
        shortened_base = base.encode('utf-8')[:max_base_len].decode('utf-8', 'ignore')
        short_filename = f"{shortened_base}_{hash_value}{ext}"
        logger.warning(f"파일 이름이 너무 깁니다: '{filename}' -> '{short_filename}'")
        return short_filename
    return filename

def format_size(size_bytes: float) -> str:
    """바이트를 사람이 읽기 쉬운 형식으로 변환합니다."""
    if size_bytes <= 0: return "0 B"
    size_names = ("B", "KB", "MB", "GB", "TB")
    i = int(size_bytes.bit_length() / 10)
    p = 1024 ** i
    s = size_bytes / p
    return f"{s:.2f} {size_names[i]}"

def parse_time(time_str: str) -> float:
    """ffmpeg 시간 문자열을 초로 변환합니다."""
    match = time_pattern.match(time_str)
    if not match: return 0.0
    h, m, s, ms = map(int, match.groups())
    return h * 3600 + m * 60 + s + ms / 100

async def read_stream(stream: asyncio.StreamReader, channel_id: str):
    """ffmpeg의 stderr 스트림에서 진행 상황을 읽고 파싱합니다."""
    summary = {}
    while not stream.at_eof():
        line = await stream.readline()
        if not line: break
        line_str = line.decode(errors="ignore").strip()

        if "=" in line_str:
            key, value = map(str.strip, line_str.split("=", 1))
            summary[key] = value

        if summary.get("progress") == "end":
            total_size = int(summary.get("total_size", 0))
            out_time_seconds = parse_time(summary.get("out_time", "00:00:00.00"))

            bitrate_kbps = (total_size * 8 / out_time_seconds / 1000) if out_time_seconds > 0 else 0

            async with channel_progress_lock:
                if channel_id in channel_progress:
                    channel_progress[channel_id].update({
                        "bitrate": f"{bitrate_kbps:.2f} kbps",
                        "total_size": format_size(total_size),
                        "out_time": summary.get("out_time", "N/A"),
                        "download_speed": "완료"
                    })
            summary.clear()

# --- 녹화 로직 ---

async def record_stream(channel: Dict[str, Any], headers: Dict[str, str], session: aiohttp.ClientSession, ffmpeg_path: Path):
    """단일 채널의 라이브 스트림을 녹화합니다."""
    global config
    channel_name = channel.get("name", "Unknown")
    channel_id = str(channel.get("id", "Unknown"))
    delay = config.get("delays", {}).get(channel.get("identifier", ""), 0)
    timeout = config["recorder_settings"]["rescan_interval"]
    threads = config["recorder_settings"]["threads"]

    logger.info(f"채널 스트림 녹화 시도: {channel_name} (딜레이: {delay}초)")
    await asyncio.sleep(delay)

    while not shutdown_event.is_set():
        if channel.get("active", "on") == "off":
            logger.info(f"{channel_name} 채널이 비활성 상태입니다. 녹화를 건너뜁니다.")
            return

        status, live_info = await get_live_info(channel, headers, session)
        if status != "OPEN":
            logger.info(f"'{channel_name}' 채널이 라이브 상태가 아닙니다. {timeout}초 후 다시 확인합니다.")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                continue
            continue

        cookies = config.get("cookies", {})
        current_time = time.strftime("%Y-%m-%d_%H-%M-%S")
        live_title = SPECIAL_CHARS_REMOVER.sub("", live_info.get("liveTitle", "live"))
        output_dir = Path(channel.get("output_dir", "./recordings")).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"[{current_time}] {channel_name} - {live_title}.ts"
        temp_path = output_dir / f"{filename}.part"
        final_path = output_dir / filename

        stream_url = f"https://chzzk.naver.com/live/{channel_id}"

        streamlink_cmd = [
            "streamlink", "--stdout", stream_url, "best",
            "--hls-live-restart", "--plugin-dirs", str(PLUGIN_DIR_PATH),
            "--stream-segment-threads", str(threads),
            "--http-header", f'Cookie=NID_AUT={cookies.get("NID_AUT", "")}; NID_SES={cookies.get("NID_SES", "")}',
            "--http-header", "User-Agent=Mozilla/5.0 (X11; Unix x86_64)",
            "--ffmpeg-ffmpeg", str(ffmpeg_path)
        ]

        ffmpeg_cmd = [
            str(ffmpeg_path), "-i", "pipe:0", "-c", "copy", "-progress", "pipe:2",
            "-y", str(temp_path)
        ]

        logger.info(f"'{channel_name}' 녹화를 시작합니다: {filename}")

        process = await asyncio.create_subprocess_exec(
            *streamlink_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        ffmpeg_process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdin=process.stdout,
            stderr=asyncio.subprocess.PIPE
        )

        async with channel_progress_lock:
            channel_progress[channel_id] = {
                "channel_name": channel_name, "bitrate": "N/A", "download_speed": "N/A",
                "total_size": "N/A", "out_time": "N/A",
                "recording_start_time": time.strftime("%Y-%m-%d %H:%M:%S")
            }

        stderr_task = asyncio.create_task(read_stream(ffmpeg_process.stderr, channel_id))

        await ffmpeg_process.wait()
        stderr_task.cancel()

        if temp_path.exists():
            final_path_short = shorten_filename(str(final_path))
            temp_path.rename(final_path_short)
            logger.info(f"녹화가 저장되었습니다: {final_path_short}")
        else:
            logger.warning(f"'{channel_name}' 녹화 파일이 생성되지 않았습니다.")

        async with channel_progress_lock:
            channel_progress.pop(channel_id, None)

async def manage_recording_tasks():
    """현재 설정에 따라 모든 활성 녹화 작업을 관리합니다."""
    global config
    active_tasks: Dict[str, asyncio.Task] = {}
    ffmpeg_path = await setup_paths()

    if not ffmpeg_path or not ffmpeg_path.exists():
        logger.error("ffmpeg 실행 파일을 찾을 수 없습니다. 종료합니다.")
        return

    async with aiohttp.ClientSession() as session:
        while not shutdown_event.is_set():
            config = load_config()  # 설정 동적 리로드
            setup_logger(config) # 로거 재설정

            headers = get_auth_headers(config.get("cookies", {}))
            active_channels = [ch for ch in config.get("channels", []) if ch.get("active", "on") == "on"]
            current_ids = {str(ch["id"]) for ch in active_channels}

            # 종료된 작업 정리
            for channel_id in list(active_tasks.keys()):
                if channel_id not in current_ids:
                    task = active_tasks.pop(channel_id)
                    task.cancel()
                    logger.info(f"채널 {channel_id}의 녹화 작업이 비활성화되어 취소되었습니다.")
                    async with channel_progress_lock:
                        channel_progress.pop(channel_id, None)

            # 새 작업 시작
            for channel in active_channels:
                channel_id = str(channel["id"])
                if channel_id not in active_tasks:
                    task = asyncio.create_task(record_stream(channel, headers, session, ffmpeg_path))
                    active_tasks[channel_id] = task
                    logger.info(f"'{channel.get('name', 'Unknown')}' 채널에 대한 녹화 작업을 시작합니다.")

            if not active_tasks:
                logger.info("활성 녹화 채널이 없습니다.")

            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                continue

    # 종료 시 모든 작업 취소
    for task in active_tasks.values():
        task.cancel()
    await asyncio.gather(*active_tasks.values(), return_exceptions=True)

# --- UI 및 메인 로직 ---

def handle_shutdown():
    """애플리케이션의 정상적인 종료를 시작합니다."""
    logger.info("종료 신호를 받았습니다. 종료 중...")
    shutdown_event.set()

async def display_progress():
    """터미널에 실시간 진행 상황 대시보드를 표시합니다."""
    layout = Layout(name="root")
    layout.split(Layout(name="upper", ratio=1), Layout(name="lower", ratio=3))

    with Live(layout, console=console, refresh_per_second=4, screen=True) as live:
        while not shutdown_event.is_set() or not log_queue.empty():
            log_panel_content = []
            while not log_queue.empty():
                log_panel_content.append(log_queue.get_nowait())

            layout["upper"].update(Panel(Text("\n".join(log_panel_content)), title="로그"))

            channel_panels = []
            async with channel_progress_lock:
                if not channel_progress:
                    channel_panels.append(Panel("활성 녹화 없음.", title="녹화 진행 상황"))
                else:
                    for data in channel_progress.values():
                        table = Table(show_header=True, header_style="bold magenta")
                        for col in ["채널", "비트레이트", "다운로드 속도", "총 크기", "경과 시간", "시작 시간"]:
                            table.add_column(col)
                        table.add_row(
                            data.get("channel_name", "N/A"), data.get("bitrate", "N/A"),
                            data.get("download_speed", "N/A"), data.get("total_size", "N/A"),
                            data.get("out_time", "N/A"), data.get("recording_start_time", "N/A")
                        )
                        channel_panels.append(Panel(table, title=data.get("channel_name", "Unknown")))

            layout["lower"].update(Group(*channel_panels))
            await asyncio.sleep(0.25)

async def main():
    """애플리케이션의 메인 진입점."""
    if platform.system() != "Windows":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_shutdown)

    display_task = asyncio.create_task(display_progress())

    try:
        await manage_recording_tasks()
    except (KeyboardInterrupt, asyncio.CancelledError):
        handle_shutdown()
    finally:
        await display_task

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("프로그램이 종료되었습니다.")
