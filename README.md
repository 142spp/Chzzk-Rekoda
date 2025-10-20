# Chzzk-Rekoda

An automatic recording program for Chzzk, supporting Windows, macOS, and Linux, built using Streamlink and ffmpeg.

**Korean:** [README in Korean (README.ko.md)](README.ko.md)

**Tutorials:**
- [How to Install Chzzk-Rekoda on Android Systems](https://github.com/munsy0227/Chzzk-Rekoda/discussions/18)

## Features

- **Automatic Recording**: Monitors specified Chzzk channels and starts recording automatically when they go live.
- **Cross-Platform**: Supports Windows, macOS, and Linux.
- **Real-Time Dashboard**: A terminal-based dashboard displays the status of active recordings, including bitrate, download speed, and file size.
- **Configuration via CLI**: A simple command-line interface allows you to add/remove channels, configure recording settings, and more.
- **Adult Content Support**: Can be configured with authentication cookies to record age-restricted streams.

## Installation

### Windows

1.  **Download**:
    - If you have Git installed, clone the repository:
      ```bash
      git clone https://github.com/munsy0227/Chzzk-Rekoda.git
      ```
    - Otherwise, [download the ZIP file](https://github.com/munsy0227/Chzzk-Rekoda/archive/refs/heads/main.zip).

2.  **Install**:
    - Run the `install.bat` script to set up the environment.
      ```bash
      install.bat
      ```

### macOS/Linux

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/munsy0227/Chzzk-Rekoda.git
    cd Chzzk-Rekoda
    ```

2.  **Install ffmpeg**:
    - **macOS**: `brew install ffmpeg`
    - **Ubuntu/Debian**: `sudo apt install ffmpeg`
    - **Arch Linux**: `sudo pacman -S ffmpeg uv`

3.  **Install**:
    - Run the `install` script.
      ```bash
      ./install
      ```

## Usage

-   **Start Recording**:
    -   **Windows**: `chzzk_record.bat`
    -   **macOS/Linux**: `./chzzk_record`

-   **Configure Settings**:
    -   **Windows**: `settings.bat`
    -   **macOS/Linux**: `./settings`

---

## For Developers

### Project Structure

```
.
├── plugin/
│   └── chzzk.py       # Custom Streamlink plugin for Chzzk
├── .python-version    # Specifies the Python version
├── chzzk_record.py    # Main application script for recording
├── settings.py        # Script for configuring the application
├── install            # Installation script for macOS/Linux
├── install.bat        # Installation script for Windows
├── pyproject.toml     # Project metadata and dependencies
└── README.md          # This file
```

### Key Components

-   **`chzzk_record.py`**: The core of the application. It uses `asyncio` to manage concurrent recording tasks. A `rich`-based terminal UI displays real-time progress. It spawns `streamlink` and `ffmpeg` as subprocesses to handle the actual recording.
-   **`settings.py`**: A command-line interface for managing the application's configuration. It allows users to add or remove channels, set recording threads, and configure authentication cookies.
-   **`plugin/chzzk.py`**: A custom plugin for `streamlink` that handles the specifics of the Chzzk platform. It includes logic for refreshing HLS stream URLs with new authentication tokens to prevent interruptions.

### Configuration Files

The application's behavior is controlled by several files in the root directory:

-   **`channels.json`**: A JSON array of channel objects to be recorded. Each object contains the channel `id`, `name`, `output_dir`, and an `active` status.
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
-   **`cookie.json`**: Stores authentication cookies (`NID_SES` and `NID_AUT`) required for recording age-restricted streams.
    ```json
    {
      "NID_SES": "...",
      "NID_AUT": "..."
    }
    ```
-   **`delays.json`**: A dictionary mapping channel identifiers to recording start delays.
-   **`thread.txt`**: A plain text file containing the number of threads `streamlink` should use for downloading stream segments.
-   **`time_sleep.txt`**: A plain text file specifying the interval (in seconds) at which the application checks if a channel has gone live.
-   **`log_enabled.txt`**: A plain text file containing `true` or `false` to enable or disable logging to `log.log`.

### How It Works

1.  **Configuration**: The user runs `settings.py` to define which channels to record and to set other parameters.
2.  **Initialization**: `chzzk_record.py` starts and loads the settings from the various configuration files.
3.  **Task Management**: The `manage_recording_tasks` function creates an `asyncio` task for each active channel.
4.  **Recording**: Each `record_stream` task:
    -   Periodically calls the Chzzk API to check if the channel is live.
    -   When the stream is live, it launches a `streamlink` subprocess.
    -   The output of `streamlink` is piped to an `ffmpeg` subprocess, which writes the stream to a file.
    -   The `chzzk.py` plugin ensures that the HLS stream token is refreshed as needed.
5.  **UI**: The `display_progress` function runs concurrently, showing a live dashboard of all recording activities.

### Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue on the GitHub repository. If you'd like to contribute code, please follow these steps:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix.
3.  Make your changes and commit them with a descriptive message.
4.  Push your changes to your fork.
5.  Open a pull request to the main repository.
