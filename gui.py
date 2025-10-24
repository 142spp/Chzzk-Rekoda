import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QListWidget, QPushButton, QLabel, QLineEdit,
    QCheckBox, QMessageBox, QInputDialog, QScrollArea, QFrame, QGridLayout
)
from PyQt6.QtCore import QTimer, Qt
from config import load_config, save_config
from typing import Dict, Any

class RekodaGUI(QMainWindow):
    """Chzzk Rekoda를 위한 GUI 애플리케이션 (PyQt6 버전)"""
    def __init__(self):
        super().__init__()
        self.config: Dict[str, Any] = load_config()

        self.setWindowTitle("Chzzk Rekoda 컨트롤 패널")
        self.setGeometry(100, 100, 700, 500)
        self.setMinimumSize(600, 400)

        self.create_widgets()
        self.load_settings_to_ui()

        # 주기적으로 파일 변경 감지
        self.config_check_timer = QTimer(self)
        self.config_check_timer.timeout.connect(self.check_for_config_changes)
        self.config_check_timer.start(2000)

    def create_widgets(self):
        """GUI 위젯들을 생성합니다."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Notebook (탭) 위젯 생성
        notebook = QTabWidget()
        main_layout.addWidget(notebook)

        # 탭 생성
        channel_tab = QWidget()
        settings_tab = QWidget()

        notebook.addTab(channel_tab, "채널 관리")
        notebook.addTab(settings_tab, "상세 설정")

        # 각 탭에 위젯 배치
        self.create_channel_tab(channel_tab)
        self.create_settings_tab(settings_tab)

    def create_channel_tab(self, parent_widget: QWidget):
        """'채널 관리' 탭의 위젯들을 생성합니다."""
        layout = QVBoxLayout(parent_widget)

        # 채널 목록
        channel_frame = QFrame()
        channel_frame.setLayout(QVBoxLayout())
        layout.addWidget(channel_frame)
        
        channel_list_layout = QHBoxLayout()
        
        self.channel_listbox = QListWidget()
        channel_list_layout.addWidget(self.channel_listbox)

        channel_frame.layout().addLayout(channel_list_layout)
        
        # 버튼
        button_layout = QHBoxLayout()
        layout.addLayout(button_layout)

        add_button = QPushButton("채널 추가")
        add_button.clicked.connect(self.add_channel)
        button_layout.addWidget(add_button)

        delete_button = QPushButton("채널 삭제")
        delete_button.clicked.connect(self.delete_channel)
        button_layout.addWidget(delete_button)

        toggle_button = QPushButton("녹화 토글")
        toggle_button.clicked.connect(self.toggle_channel)
        button_layout.addWidget(toggle_button)
        
        button_layout.addStretch(1)

    def create_settings_tab(self, parent_widget: QWidget):
        """'상세 설정' 탭의 위젯들을 생성합니다."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        parent_widget.setLayout(QVBoxLayout())
        parent_widget.layout().addWidget(scroll_area)

        settings_container = QWidget()
        scroll_area.setWidget(settings_container)
        layout = QVBoxLayout(settings_container)

        # --- 녹화 설정 ---
        recorder_frame = QFrame()
        recorder_frame.setFrameShape(QFrame.Shape.StyledPanel)
        recorder_layout = QGridLayout(recorder_frame)
        
        recorder_layout.addWidget(QLabel("스레드 수:"), 0, 0)
        self.threads_var = QLineEdit()
        recorder_layout.addWidget(self.threads_var, 0, 1)

        recorder_layout.addWidget(QLabel("재검색 간격(초):"), 1, 0)
        self.rescan_interval_var = QLineEdit()
        recorder_layout.addWidget(self.rescan_interval_var, 1, 1)

        self.logging_var = QCheckBox("로그 파일 생성 활성화")
        recorder_layout.addWidget(self.logging_var, 2, 0, 1, 2)
        
        layout.addWidget(recorder_frame)

        # --- 쿠키 설정 ---
        cookie_frame = QFrame()
        cookie_frame.setFrameShape(QFrame.Shape.StyledPanel)
        cookie_layout = QGridLayout(cookie_frame)

        cookie_layout.addWidget(QLabel("NID_SES:"), 0, 0)
        self.nid_ses_var = QLineEdit()
        cookie_layout.addWidget(self.nid_ses_var, 0, 1)

        cookie_layout.addWidget(QLabel("NID_AUT:"), 1, 0)
        self.nid_aut_var = QLineEdit()
        cookie_layout.addWidget(self.nid_aut_var, 1, 1)
        
        layout.addWidget(cookie_frame)

        # --- 저장 버튼 ---
        save_button = QPushButton("상세 설정 저장")
        save_button.clicked.connect(self.save_settings)
        layout.addWidget(save_button)

        layout.addStretch(1)

    def load_settings_to_ui(self):
        """config 파일의 내용을 UI 위젯에 로드합니다."""
        self.update_channel_list()

        recorder_settings = self.config.get("recorder_settings", {})
        cookies = self.config.get("cookies", {})

        self.threads_var.setText(str(recorder_settings.get("threads", 2)))
        self.rescan_interval_var.setText(str(recorder_settings.get("rescan_interval", 60)))
        self.logging_var.setChecked(recorder_settings.get("logging_enabled", True))
        self.nid_ses_var.setText(cookies.get("NID_SES", ""))
        self.nid_aut_var.setText(cookies.get("NID_AUT", ""))

    def save_settings(self):
        """UI의 상세 설정 내용을 config에 저장합니다."""
        try:
            self.config["recorder_settings"]["threads"] = int(self.threads_var.text())
            self.config["recorder_settings"]["rescan_interval"] = int(self.rescan_interval_var.text())
            self.config["recorder_settings"]["logging_enabled"] = self.logging_var.isChecked()
            self.config["cookies"]["NID_SES"] = self.nid_ses_var.text()
            self.config["cookies"]["NID_AUT"] = self.nid_aut_var.text()

            save_config(self.config)
            QMessageBox.information(self, "저장 완료", "상세 설정이 성공적으로 저장되었습니다.")
        except ValueError:
            QMessageBox.critical(self, "입력 오류", "스레드 수와 재검색 간격은 숫자로 입력해야 합니다.")

    def update_channel_list(self):
        """리스트 위젯에 현재 채널 목록을 표시합니다."""
        self.channel_listbox.clear()
        for channel in self.config.get('channels', []):
            status = "ON" if channel.get('active', 'on') == 'on' else "OFF"
            self.channel_listbox.addItem(f"[{status}] {channel['name']} ({channel['id']})")

    def add_channel(self):
        """새 채널을 config에 추가하고 저장합니다."""
        ch_id, ok = QInputDialog.getText(self, "채널 추가", "스트리머 채널의 고유 ID를 입력하세요:")
        if not (ok and ch_id):
            return

        name, ok = QInputDialog.getText(self, "채널 추가", "스트리머 이름을 입력하세요:")
        if not (ok and name):
            return

        reply = QMessageBox.question(self, "확인", f"ID: {ch_id}\n이름: {name}\n\n추가하시겠습니까?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            channel_count = len(self.config['channels'])
            identifier = f"ch{channel_count + 1}"
            self.config['channels'].append({ "id": ch_id, "name": name, "output_dir": name, "identifier": identifier, "active": "on" })
            self.config['delays'][identifier] = channel_count

            save_config(self.config)
            self.update_channel_list()
            QMessageBox.information(self, "완료", "채널이 추가되었습니다. 녹화 프로그램에 잠시 후 반영됩니다.")

    def delete_channel(self):
        """선택된 채널을 config에서 삭제하고 저장합니다."""
        selected_items = self.channel_listbox.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "선택 필요", "삭제할 채널을 목록에서 선택하세요.")
            return

        choice = self.channel_listbox.row(selected_items[0])
        channel = self.config['channels'][choice]

        reply = QMessageBox.question(self, "삭제 확인", f"'{channel['name']}' 채널을 정말로 삭제하시겠습니까?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.config['channels'].pop(choice)
            
            new_delays = {}
            for i, ch in enumerate(self.config['channels']):
                new_id = f"ch{i + 1}"
                ch["identifier"] = new_id
                new_delays[new_id] = i
            self.config['delays'] = new_delays

            save_config(self.config)
            self.update_channel_list()
            QMessageBox.information(self, "완료", "채널이 삭제되었습니다. 녹화 프로그램에 잠시 후 반영됩니다.")

    def toggle_channel(self):
        """선택된 채널의 녹화 상태를 토글하고 저장합니다."""
        selected_items = self.channel_listbox.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "선택 필요", "상태를 변경할 채널을 목록에서 선택하세요.")
            return

        choice = self.channel_listbox.row(selected_items[0])
        channel = self.config['channels'][choice]
        current_state = channel.get("active", "on")
        new_state = "off" if current_state == "on" else "on"
        channel["active"] = new_state

        save_config(self.config)
        self.update_channel_list()
        QMessageBox.information(self, "완료", f"채널 상태가 변경되었습니다. 녹화 프로그램에 잠시 후 반영됩니다.")

    def check_for_config_changes(self):
        """config.json 파일이 외부에서 변경되었는지 확인하고 UI를 새로고침합니다."""
        current_config_on_disk = load_config()
        if current_config_on_disk != self.config:
            self.config = current_config_on_disk
            self.load_settings_to_ui()

def start_gui():
    """GUI를 시작하고 실행합니다."""
    app = QApplication(sys.argv)
    main_win = RekodaGUI()
    main_win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    start_gui()
