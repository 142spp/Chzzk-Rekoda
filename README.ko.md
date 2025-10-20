# Chzzk-Rekoda

Streamlink와 ffmpeg를 활용하여 만들어진 Windows, macOS, Linux를 지원하는 치지직 자동 녹화 프로그램입니다.

**영어:** [README in English](README.md)

**튜토리얼:**
- [안드로이드 휴대폰에 프로그램 설치하기](https://github.com/munsy0227/Chzzk-Rekoda/discussions/17)

## 주요 기능

- **자동 녹화**: 지정된 치지직 채널을 모니터링하고 라이브가 시작되면 자동으로 녹화를 시작합니다.
- **크로스 플랫폼**: Windows, macOS, Linux를 지원합니다.
- **실시간 대시보드**: 터미널 기반 대시보드에서 비트레이트, 다운로드 속도, 파일 크기 등 활성 녹화 상태를 표시합니다.
- **CLI를 통한 설정**: 간단한 명령줄 인터페이스를 통해 채널 추가/제거, 녹화 설정 구성 등이 가능합니다.
- **성인 콘텐츠 지원**: 인증 쿠키를 설정하여 연령 제한이 있는 스트림을 녹화할 수 있습니다.

## 설치 방법

### Windows

1.  **다운로드**:
    -   Git이 설치된 경우, 리포지토리를 클론하세요:
        ```bash
        git clone https://github.com/munsy0227/Chzzk-Rekoda.git
        ```
    -   그렇지 않은 경우, [ZIP 파일 다운로드](https://github.com/munsy0227/Chzzk-Rekoda/archive/refs/heads/main.zip).

2.  **설치**:
    -   `install.bat` 스크립트를 실행하여 환경을 설정합니다.
        ```bash
        install.bat
        ```

### macOS/Linux

1.  **리포지토리 클론**:
    ```bash
    git clone https://github.com/munsy0227/Chzzk-Rekoda.git
    cd Chzzk-Rekoda
    ```

2.  **ffmpeg 설치**:
    -   **macOS**: `brew install ffmpeg`
    -   **Ubuntu/Debian**: `sudo apt install ffmpeg`
    -   **Arch Linux**: `sudo pacman -S ffmpeg uv`

3.  **설치**:
    -   `install` 스크립트를 실행합니다.
        ```bash
        ./install
        ```

## 사용 방법

-   **녹화 시작**:
    -   **Windows**: `chzzk_record.bat`
    -   **macOS/Linux**: `./chzzk_record`

-   **설정 구성**:
    -   **Windows**: `settings.bat`
    -   **macOS/Linux**: `./settings`

---

## 개발자 정보

### 프로젝트 구조

```
.
├── plugin/
│   └── chzzk.py       # Chzzk용 사용자 정의 Streamlink 플러그인
├── .python-version    # Python 버전 지정
├── chzzk_record.py    # 녹화를 위한 메인 애플리케이션 스크립트
├── settings.py        # 애플리케이션 설정 스크립트
├── install            # macOS/Linux용 설치 스크립트
├── install.bat        # Windows용 설치 스크립트
├── pyproject.toml     # 프로젝트 메타데이터 및 의존성
└── README.md          # 이 파일
```

### 주요 구성 요소

-   **`chzzk_record.py`**: 애플리케이션의 핵심입니다. `asyncio`를 사용하여 동시 녹화 작업을 관리합니다. `rich` 기반의 터미널 UI는 실시간 진행 상황을 표시합니다. 실제 녹화를 처리하기 위해 `streamlink`와 `ffmpeg`를 하위 프로세스로 생성합니다.
-   **`settings.py`**: 애플리케이션의 설정을 관리하기 위한 명령줄 인터페이스입니다. 사용자가 채널을 추가 또는 제거하고, 녹화 스레드를 설정하고, 인증 쿠키를 구성할 수 있습니다.
-   **`plugin/chzzk.py`**: Chzzk 플랫폼의 특수성을 처리하는 `streamlink`용 사용자 정의 플러그인입니다. 중단을 방지하기 위해 새 인증 토큰으로 HLS 스트림 URL을 새로 고치는 로직을 포함합니다.

### 설정 파일

애플리케이션의 동작은 루트 디렉토리의 여러 파일에 의해 제어됩니다:

-   **`channels.json`**: 녹화할 채널 객체의 JSON 배열입니다. 각 객체는 채널 `id`, `name`, `output_dir` 및 `active` 상태를 포함합니다.
    ```json
    [
      {
        "id": "...",
        "name": "...",
        "output_dir": "...",
        "identifier": "ch1",
        "active": "on"
      }
    ]
    ```
-   **`cookie.json`**: 연령 제한 스트림을 녹화하는 데 필요한 인증 쿠키(`NID_SES` 및 `NID_AUT`)를 저장합니다.
    ```json
    {
      "NID_SES": "...",
      "NID_AUT": "..."
    }
    ```
-   **`delays.json`**: 채널 식별자를 녹화 시작 지연에 매핑하는 딕셔너리입니다.
-   **`thread.txt`**: `streamlink`가 스트림 세그먼트를 다운로드하는 데 사용해야 하는 스레드 수를 포함하는 일반 텍스트 파일입니다.
-   **`time_sleep.txt`**: 채널이 라이브 상태인지 확인하는 간격(초)을 지정하는 일반 텍스트 파일입니다.
-   **`log_enabled.txt`**: `log.log`에 로깅을 활성화하거나 비활성화하기 위해 `true` 또는 `false`를 포함하는 일반 텍스트 파일입니다.

### 작동 방식

1.  **설정**: 사용자가 `settings.py`를 실행하여 녹화할 채널을 정의하고 다른 매개변수를 설정합니다.
2.  **초기화**: `chzzk_record.py`가 시작되고 다양한 설정 파일에서 설정을 로드합니다.
3.  **작업 관리**: `manage_recording_tasks` 함수는 각 활성 채널에 대해 `asyncio` 작업을 생성합니다.
4.  **녹화**: 각 `record_stream` 작업:
    -   주기적으로 Chzzk API를 호출하여 채널이 라이브 상태인지 확인합니다.
    -   스트림이 라이브 상태이면 `streamlink` 하위 프로세스를 시작합니다.
    -   `streamlink`의 출력은 `ffmpeg` 하위 프로세스로 파이프되어 스트림을 파일에 씁니다.
    -   `chzzk.py` 플러그인은 필요에 따라 HLS 스트림 토큰이 새로 고쳐지도록 보장합니다.
5.  **UI**: `display_progress` 함수가 동시에 실행되어 모든 녹화 활동의 라이브 대시보드를 표시합니다.

### 기여하기

기여를 환영합니다! 버그를 발견하거나 기능 요청이 있는 경우 GitHub 리포지토리에서 이슈를 열어주세요. 코드에 기여하고 싶다면 다음 단계를 따르세요:

1.  리포지토리를 포크하세요.
2.  기능 또는 버그 수정을 위한 새 브랜치를 만드세요.
3.  변경 사항을 만들고 설명적인 메시지와 함께 커밋하세요.
4.  변경 사항을 포크로 푸시하세요.
5.  메인 리포지토리로 풀 리퀘스트를 여세요.
