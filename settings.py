"""
This script provides a command-line interface for configuring the Chzzk Rekoda application.

It allows users to manage channel settings (add, delete, toggle recording),
adjust recording parameters (threads, rescan interval), set authentication cookies,
and toggle logging. All settings are persisted to JSON or text files in the
application's root directory.
"""
import os
import json
from typing import List, Dict, Any

# --- File Path Settings ---
script_directory = os.path.dirname(os.path.abspath(__name__))
channel_count_file_path = os.path.join(script_directory, "channel_count.txt")
channels_file_path = os.path.join(script_directory, "channels.json")
delays_file_path = os.path.join(script_directory, "delays.json")
log_enabled_file_path = os.path.join(script_directory, "log_enabled.txt")

# --- Global Variables ---
channels: List[Dict[str, Any]] = []
delays: Dict[str, int] = {}
channel_count: int = 0
log_enabled: bool = True

# --- Utility Functions ---

def try_again():
    """Prints a message asking the user to try again."""
    print("Please try again.\n")

# --- Data Loading and Saving ---

def load_data():
    """Loads all necessary data from files into global variables."""
    global channels, delays, channel_count, log_enabled

    if os.path.exists(channels_file_path):
        with open(channels_file_path, "r") as f:
            channels = json.load(f)
        channel_count = len(channels)
    else:
        channels = []
        channel_count = 0

    if os.path.exists(delays_file_path):
        with open(delays_file_path, "r") as f:
            delays = json.load(f)
    else:
        delays = {}

    if os.path.exists(log_enabled_file_path):
        with open(log_enabled_file_path, "r") as f:
            log_enabled = f.readline().strip().lower() == "true"
    else:
        log_enabled = True

def save_channels():
    """Saves the current state of the channels list to channels.json."""
    with open(channels_file_path, "w") as f:
        json.dump(channels, f, indent=2)
    print("The channels.json file has been modified.")

def save_delays():
    """Saves the current state of the delays dictionary to delays.json."""
    with open(delays_file_path, "w") as f:
        json.dump(delays, f, indent=2)
    print("The delays.json file has been modified.")

def save_channel_count():
    """Saves the current channel count to channel_count.txt."""
    with open(channel_count_file_path, "w") as f:
        f.write(str(channel_count))

# --- Core Functionality ---

def add_channel():
    """Handles the user prompts for adding a new channel and saves it."""
    global channel_count
    ch_id = input("Enter the unique ID of the streamer channel you want to add: ")
    name = input("Enter the streamer name: ")
    output_dir = input("Specify the storage path (leave empty for default './recordings'): ") or "./recordings"

    while True:
        answer = input(f"id: {ch_id}, name: {name}, storage path: {output_dir}. Is this correct? (Y/N): ").upper()
        if answer == "Y":
            channel_count += 1
            identifier = f"ch{channel_count}"
            channels.append({
                "id": ch_id,
                "name": name,
                "output_dir": output_dir,
                "identifier": identifier,
                "active": "on",
            })
            delays[identifier] = channel_count - 1
            save_channels()
            save_delays()
            save_channel_count()
            break
        elif answer == "N":
            print("Then please enter it again.")
            break
        else:
            try_again()

def delete_channel():
    """Handles the user prompts for deleting an existing channel."""
    global channel_count
    if not channels:
        print("No channels to delete.")
        return

    print("Current channel list:")
    for idx, channel in enumerate(channels, 1):
        print(f"{idx}. id: {channel['id']}, name: {channel['name']}")

    try:
        choice = int(input("Enter the number of the channel to delete: ")) - 1
        if 0 <= choice < len(channels):
            deleted_channel = channels.pop(choice)
            print(f"Deleted channel: id: {deleted_channel['id']}, name: {deleted_channel['name']}")

            # Update channel count and identifiers
            channel_count -= 1
            save_channel_count()

            delays.pop(deleted_channel["identifier"], None)
            # Re-generate identifiers and delays
            new_delays = {}
            for i, channel in enumerate(channels):
                new_id = f"ch{i + 1}"
                channel["identifier"] = new_id
                new_delays[new_id] = i

            global delays
            delays = new_delays

            save_channels()
            save_delays()
        else:
            print("Invalid channel number.")
    except ValueError:
        print("Invalid input. Please enter a valid number.")

def toggle_channel_recording():
    """Handles toggling a channel's recording status between 'on' and 'off'."""
    if not channels:
        print("No channels available to toggle.")
        return

    print("Current channel list:")
    for idx, channel in enumerate(channels, 1):
        status = 'On' if channel.get('active', 'on') == 'on' else 'Off'
        print(f"{idx}. id: {channel['id']}, name: {channel['name']}, recording status: {status}")

    try:
        choice = int(input("Enter the number of the channel to toggle recording status: ")) - 1
        if 0 <= choice < len(channels):
            channel = channels[choice]
            current_state = channel.get("active", "on")
            new_state = "off" if current_state == "on" else "on"
            channel["active"] = new_state
            print(f"The recording status of {channel['name']} has been changed to {'Off' if new_state == 'off' else 'On'}.")
            save_channels()
        else:
            print("Invalid channel number.")
    except ValueError:
        print("Invalid input. Please enter a valid number.")

def set_recording_threads():
    """Allows the user to set the number of recording threads."""
    thread_file_path = os.path.join(script_directory, "thread.txt")
    try:
        with open(thread_file_path, "r") as f:
            threads = f.readline().strip()
        print(f"The current number of recording threads is {threads}.")
    except FileNotFoundError:
        print("Thread setting file not found. A new one will be created.")

    print("Recommended: 2 for low-end systems, 4 for high-end systems.")
    new_threads = input("Enter the number of threads to change: ")
    if new_threads.isdigit():
        with open(thread_file_path, "w") as f:
            f.write(new_threads)
        print("The number of threads has been changed.")
    else:
        print("Invalid input. Please enter a number.")

def set_rescan_interval():
    """Allows the user to set the broadcast rescan interval."""
    rescan_file_path = os.path.join(script_directory, "time_sleep.txt")
    try:
        with open(rescan_file_path, "r") as f:
            interval = f.readline().strip()
        print(f"The current broadcast rescan interval is {interval} seconds.")
    except FileNotFoundError:
        print("Rescan interval file not found. A new one will be created.")

    new_interval = input("Enter the rescan interval to change (in seconds): ")
    if new_interval.isdigit():
        with open(rescan_file_path, "w") as f:
            f.write(new_interval)
        print("The broadcast rescan interval has been changed.")
    else:
        print("Invalid input. Please enter a number.")

def save_cookie_info():
    """Prompts the user for cookie values and saves them to cookie.json."""
    ses = input("Enter SES: ")
    aut = input("Enter AUT: ")
    cookie_data = {"NID_SES": ses, "NID_AUT": aut}
    with open("cookie.json", "w") as f:
        json.dump(cookie_data, f, indent=2)
    print("Cookie information has been successfully saved.")

def toggle_logging():
    """Toggles the logging setting on or off."""
    global log_enabled
    log_enabled = not log_enabled
    with open(log_enabled_file_path, "w") as f:
        f.write("true" if log_enabled else "false")
    print(f"Logging has been {'enabled' if log_enabled else 'disabled'}.")

# --- Menu Functions ---

def manage_channel_settings():
    """Displays the channel settings sub-menu and handles user input."""
    while True:
        print("\n--- Channel Settings ---")
        print("1. Add Channel")
        print("2. Delete Channel")
        print("3. Toggle Channel Recording")
        print("4. Go Back")
        choice = input("Enter your choice: ")

        if choice == "1":
            add_channel()
        elif choice == "2":
            delete_channel()
        elif choice == "3":
            toggle_channel_recording()
        elif choice == "4":
            break
        else:
            try_again()

def manage_recording_settings():
    """Displays the recording settings sub-menu and handles user input."""
    while True:
        print("\n--- Recording Settings ---")
        print("1. Set Recording Threads")
        print("2. Set Broadcast Rescan Interval")
        print("3. Go Back")
        choice = input("Enter your choice: ")

        if choice == "1":
            set_recording_threads()
        elif choice == "2":
            set_rescan_interval()
        elif choice == "3":
            break
        else:
            try_again()

def main_menu():
    """Displays the main menu and orchestrates the user interaction loop."""
    load_data()
    while True:
        print("\n--- Chzzk Auto-Recording Settings ---")
        print("1. Channel Settings")
        print("2. Recording Settings")
        print("3. Cookie Settings (for adult verification)")
        print(f"4. Toggle Logging ({'Enabled' if log_enabled else 'Disabled'})")
        print("5. Quit")
        choice = input("Enter your choice: ")

        if choice == "1":
            manage_channel_settings()
        elif choice == "2":
            manage_recording_settings()
        elif choice == "3":
            save_cookie_info()
        elif choice == "4":
            toggle_logging()
        elif choice == "5":
            print("Exiting the settings.")
            break
        else:
            try_again()

if __name__ == "__main__":
    main_menu()
