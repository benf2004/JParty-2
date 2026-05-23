from PyQt6.QtGui import (
    QPainter,
    QBrush,
    QImage,
    QFont,
    QPalette,
    QPixmap,
    QColor, 
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QMessageBox,
    QLabel,
    QDialog,
    QComboBox,
    QPushButton,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal

import qrcode
import time
import datetime
from threading import Thread
import logging
import json
import os
import sys
import webbrowser

from jparty.version import version
from jparty.retrieve import get_game, get_random_game, get_game_from_file
from jparty.utils import resource_path, add_shadow, DynamicLabel, DynamicButton
from jparty.helpmsg import helpmsg
from jparty.style import WINDOWPAL
from jparty.constants import DEFAULT_CONFIG, DESIGNER_URL
from jparty.paths import config_path, history_path

AUTO_HOST_VOICE_OPTIONS = [
    ("alloy", "Neutral, balanced"),
    ("ash", "Masculine, crisp"),
    ("ballad", "Masculine, expressive"),
    ("coral", "Feminine, bright"),
    ("echo", "Masculine, warm"),
    ("fable", "Neutral, animated"),
    ("nova", "Feminine, energetic"),
    ("onyx", "Masculine, deep"),
    ("sage", "Neutral, calm"),
    ("shimmer", "Feminine, warm"),
    ("verse", "Neutral, smooth"),
    ("marin", "Neutral, best quality"),
    ("cedar", "Masculine, best quality"),
]

KOKORO_VOICE_OPTIONS = [
    ("af_heart", "Feminine, warm and expressive"),
    ("af_alloy", "Feminine, balanced and clear"),
    ("af_aoede", "Feminine, bright and polished"),
    ("af_bella", "Feminine, lively and upbeat"),
    ("af_jessica", "Feminine, friendly and crisp"),
    ("af_kore", "Feminine, calm and steady"),
    ("af_nicole", "Feminine, soft and composed"),
    ("af_nova", "Feminine, energetic and modern"),
    ("af_river", "Feminine, smooth and conversational"),
    ("af_sarah", "Feminine, natural and clear"),
    ("af_sky", "Feminine, light and casual"),
    ("am_adam", "Masculine, deep and direct"),
    ("am_echo", "Masculine, warm and clear"),
    ("am_eric", "Masculine, neutral and steady"),
    ("am_fenrir", "Masculine, bold and animated"),
    ("am_liam", "Masculine, relaxed and friendly"),
    ("am_michael", "Masculine, polished and confident"),
    ("am_onyx", "Masculine, low and resonant"),
    ("am_puck", "Masculine, playful and lively"),
    ("am_santa", "Masculine, character voice"),
    ("bf_emma", "British feminine, clear and refined"),
    ("bf_isabella", "British feminine, warm and elegant"),
    ("bm_george", "British masculine, classic and clear"),
    ("bm_lewis", "British masculine, smooth and composed"),
]

LOCAL_TTS_PRESET_OPTIONS = [
    ("kokoro", "Kokoro voice"),
    ("kokoclone_clone", "KokoClone cloned voice"),
    ("custom", "Custom local endpoint"),
]


class Image(qrcode.image.base.BaseImage):
    """QR code image widget"""

    def __init__(self, border, width, box_size):
        self.border = border
        self.width = width
        self.box_size = box_size
        size = (width + border * 2) * box_size
        self._image = QImage(size, size, QImage.Format.Format_RGB16)
        self._image.fill(WINDOWPAL.color(QPalette.ColorRole.Window))

    def pixmap(self):
        return QPixmap.fromImage(self._image)

    def drawrect(self, row, col):
        painter = QPainter(self._image)
        painter.fillRect(
            (col + self.border) * self.box_size,
            (row + self.border) * self.box_size,
            self.box_size,
            self.box_size,
            Qt.GlobalColor.black,
        )

    def save(self, stream, kind=None):
        pass


class StartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon = QPixmap(resource_path("icon.png"))
        self.icon_label = DynamicLabel("", 0, self)

        add_shadow(self, radius=0.2)
        self.setPalette(WINDOWPAL)

        self.icon_layout = QHBoxLayout()
        self.icon_layout.addStretch()
        self.icon_layout.addWidget(self.icon_label)
        self.icon_layout.addStretch()

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.setBrush(QBrush(WINDOWPAL.color(QPalette.ColorRole.Window)))
        qp.drawRect(self.rect())

    def resizeEvent(self, event):
        icon_size = self.icon_label.height()
        self.icon_label.setPixmap(
            self.icon.scaled(
                icon_size,
                icon_size,
                transformMode=Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.icon_label.setMaximumWidth(icon_size)


class Welcome(StartWidget):
    gameid_trigger = pyqtSignal(str)
    summary_trigger = pyqtSignal(str)

    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.title_font = QFont()
        self.title_font.setBold(True)

        self.title_label = DynamicLabel("JParty!", lambda: self.height() * 0.1, self)
        self.title_label.setFont(self.title_font)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.version_label = DynamicLabel(
            f"version {version}", lambda: self.height() * 0.03
        )
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setStyleSheet("QLabel { color : grey}")

        select_layout = QHBoxLayout()

        gameid_text = f'Game ID (from J-Archive URL)<br>or <a href="{DESIGNER_URL}">Custom Game ZIP</a>'
        self.gameid_label = DynamicLabel(gameid_text, lambda: self.height() * 0.1, self)
        self.gameid_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.gameid_label.setOpenExternalLinks(True)

        self.textbox = QLineEdit(self)
        self.textbox.textChanged.connect(self.show_summary)
        f = self.textbox.font()
        self.textbox.setFont(f)

        button_layout = QVBoxLayout()
        self.start_button = DynamicButton("Start!", self)
        self.start_button.clicked.connect(self.on_start)
        self.start_button.setEnabled(False)

        self.rand_button = DynamicButton("Random", self)
        self.rand_button.clicked.connect(self.random)

        self.load_button = DynamicButton("Load custom game", self)
        self.load_button.clicked.connect(self.load_game_file)

        button_layout.addWidget(self.start_button, 12)
        button_layout.addStretch(1)
        button_layout.addWidget(self.rand_button, 12)
        button_layout.addStretch(1)
        button_layout.addWidget(self.load_button, 12)

        select_layout.addStretch(5)
        select_layout.addWidget(self.gameid_label, 40)
        select_layout.addStretch(2)
        select_layout.addWidget(self.textbox, 40)
        select_layout.addStretch(2)
        select_layout.addLayout(button_layout, 20)
        select_layout.addStretch(5)

        self.summary_label = DynamicLabel("", lambda: self.height() * 0.04, self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.quit_button = DynamicButton("Quit", self)
        self.quit_button.clicked.connect(self.game.close)

        self.help_button = DynamicButton("Show help", self)
        self.help_button.clicked.connect(self.show_help)

        self.settings_button = DynamicButton("Settings", self)
        self.settings_button.clicked.connect(self.show_settings)

        self.mute_button = DynamicButton("", self)
        self.mute_button.clicked.connect(self.toggle_mute)
        self.update_mute_button()

        footer_layout = QHBoxLayout()
        footer_layout.addStretch(5)
        footer_layout.addWidget(self.quit_button, 3)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.help_button, 3)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.settings_button, 3)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.mute_button, 3)
        footer_layout.addStretch(5)

        main_layout.addStretch(3)
        main_layout.addLayout(self.icon_layout, 6)
        main_layout.addWidget(self.title_label, 3)
        main_layout.addWidget(self.version_label, 1)
        main_layout.addStretch(1)
        main_layout.addLayout(select_layout, 5)
        main_layout.addStretch(1)
        main_layout.addWidget(self.summary_label, 5)
        main_layout.addLayout(footer_layout, 3)
        main_layout.addStretch(3)

        self.gameid_trigger.connect(self.set_gameid)
        self.summary_trigger.connect(self.set_summary)

        self.setLayout(main_layout)

        self.show()

    def show_help(self):
        logging.info("Showing help")
        msgbox = QMessageBox(
            QMessageBox.Icon.NoIcon,
            "JParty Help",
            helpmsg,
            QMessageBox.StandardButton.Ok,
            self,
        )
        msgbox.exec()

    def update_mute_button(self):
        self.mute_button.setText("Unmute music" if self.game.muted else "Mute music")

    def toggle_mute(self):
        muted = not self.game.muted
        self.game.set_muted(muted)
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except Exception:
            config = {}
        config['mute_sound'] = muted
        with open(config_path, 'w') as f:
            json.dump(config, f)
        self.update_mute_button()

    def show_settings(self):
        logging.info("Showing settings")
        settings_menu = SettingsMenu(self)
        settings_menu.exec()

    def open_designer(self):
        logging.info("Opening game designer in external browser")
        webbrowser.open_new_tab(DESIGNER_URL)

    def load_game_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load custom game file",
            os.path.expanduser("~"),
            "Game files (*.json *.zip);;All files (*)",
        )
        if not file_path:
            return

        try:
            self.game.data = get_game_from_file(file_path)
            if self.game.valid_game():
                self.summary_trigger.emit(self.game.data.date + "\n" + self.game.data.comments)
                self.check_start()
            else:
                QMessageBox.warning(self, "Invalid game", "The selected file does not contain a valid game.")
        except Exception as exc:
            logging.exception("Failed to load custom game file")
            QMessageBox.warning(self, "Load failed", f"Could not load game file:\n{exc}")

    def resizeEvent(self, event):
        super().resizeEvent(event)

        textbox_height = int(self.gameid_label.height() * 0.95)
        self.textbox.setMinimumSize(QSize(0, textbox_height))
        f = self.textbox.font()
        f.setPixelSize(int(textbox_height * 0.8))
        self.textbox.setFont(f)

    def __random(self):
        while True:
            game_id = get_random_game()
            logging.info(f"GAMEID {game_id}")
            self.game.data = get_game(game_id)
            if self.game.valid_game():
                break
            else:
                time.sleep(0.25)

        self.gameid_trigger.emit(str(game_id))
        self.summary_trigger.emit(self.game.data.date + "\n" + self.game.data.comments)

    def random(self, checked):
        self.summary_trigger.emit("Loading...")
        t = Thread(target=self.__random)
        t.start()

    def __show_summary(self):
        game_id = self.textbox.text()
        try:
            self.game.data = get_game(game_id)
            if self.game.valid_game():
                summary = self.game.data.date + "\n" + self.game.data.comments
                warning = self.played_warning(game_id)
                if warning:
                    summary = warning + "\n\n" + summary
                self.summary_trigger.emit(summary)
            else:
                self.summary_trigger.emit("Game has blank questions")

        except Exception:
            self.summary_trigger.emit("Cannot get game")

        self.check_start()

    def set_summary(self, text):
        self.summary_label.setText(text)

    def set_gameid(self, text):
        self.textbox.setText(text)

    def show_summary(self, text=None):
        self.summary_trigger.emit("Loading...")
        t = Thread(target=self.__show_summary)
        t.start()

        self.check_start()

    def check_start(self):
        if self.game.startable():
            self.start_button.setEnabled(True)
        else:
            self.start_button.setEnabled(False)

    def on_start(self):
        self.game.start_game()
        self.save_history()

    def load_history(self):
        if not os.path.exists(history_path):
            return {}
        try:
            with open(history_path, "r") as f:
                return json.load(f)
        except Exception:
            logging.exception("Failed to load game history")
            return {}

    def save_history(self):
        game_id = self.textbox.text().strip()
        if not game_id:
            return

        history = self.load_history()
        history[game_id] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with open(history_path, "w") as f:
                json.dump(history, f, indent=2)
        except Exception:
            logging.exception("Failed to save game history")

    def played_warning(self, game_id):
        game_id = str(game_id).strip()
        if not game_id:
            return ""

        history = self.load_history()
        played_date = history.get(game_id)
        if played_date:
            return f"Warning: you already played this game on {played_date}"
        return ""

    def restart(self):
        self.show_summary(self)


class QRWidget(StartWidget):
    def __init__(self, url, parent=None):
        super().__init__(parent)

        self.font = QFont()
        self.font.setPointSize(30)

        main_layout = QVBoxLayout()

        self.hint_label = DynamicLabel("Scan for Buzzer:", self.start_fontsize, self)
        self.hint_label.setFont(self.font)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.qrlabel = QLabel(self)
        self.qrlabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.url = url
        self.url_label = DynamicLabel(self.url, self.start_fontsize, self)
        self.url_label.setFont(self.font)
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addStretch(1)
        main_layout.addLayout(self.icon_layout, 5)
        main_layout.addWidget(self.hint_label, 2)
        main_layout.addWidget(self.qrlabel, 5)
        main_layout.addWidget(self.url_label, 2)
        main_layout.addStretch(1)

        self.setLayout(main_layout)

        self.show()

    def start_fontsize(self):
        return 0.1 * self.width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.qrlabel.setPixmap(
            qrcode.make(
                self.url, image_factory=Image, box_size=max(self.height() / 50, 1)
            ).pixmap()
        )

    def set_url(self, url):
        self.url = url
        self.url_label.setText(url)
        self.resizeEvent(None)

    def restart(self):
        pass

class SettingsMenu(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Read the current theme from the configuration file
        with open(config_path, 'r') as f:
            config = json.load(f)

        current_theme = config.get('theme', DEFAULT_CONFIG['theme'])
        current_showtextwithimages = config.get('showtextwithimages', DEFAULT_CONFIG['showtextwithimages'])
        current_earlybuzztimeout = config.get('earlybuzztimeout', DEFAULT_CONFIG['earlybuzztimeout'])
        current_allownegative = config.get('allownegative', DEFAULT_CONFIG['allownegative'])
        current_allownegativeinfinal = config.get('allownegativeinfinal', DEFAULT_CONFIG['allownegativeinfinal'])
        current_use_wayback_first = config.get('use_wayback_first', DEFAULT_CONFIG['use_wayback_first'])
        current_auto_host = DEFAULT_CONFIG['auto_host'].copy()
        current_auto_host.update(config.get('auto_host', {}) or {})

        self.setWindowTitle("Settings")
        self.setFixedSize(560, 700)
        layout = QVBoxLayout()

        # Add info about theme change auto-restarting the game
        settings_info = QLabel("Theme change auto-restarts the game.", self)
        settings_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        settings_info.setFixedWidth(self.width())
        palette = settings_info.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(128, 128, 128))
        settings_info.setPalette(palette)
        settings_info_layout = QHBoxLayout()

        # Add a label for the "Theme" section
        theme_label = QLabel("Theme:", self)

        # Add a combo box for theme selection
        self.theme_combobox = QComboBox(self)
        self.theme_combobox.addItem("Default")
        self.theme_combobox.addItem("Christmas")
        self.theme_combobox.addItem("Halloween")
        self.theme_combobox.addItem("EightiesSynthwave")
        self.theme_combobox.addItem("Birthday")
        self.theme_combobox.addItem("BibleBonkers")
        self.theme_combobox.setCurrentText(current_theme)

        # Set the font to bold and text color to white
        font = self.theme_combobox.font()
        font.setBold(True)
        self.theme_combobox.setFont(font)
        palette = self.theme_combobox.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        self.theme_combobox.setPalette(palette)

        # Add a white border around the dropdown menu
        self.theme_combobox.setStyleSheet("QComboBox { border: 2px solid white; }")

        # Create a horizontal layout for the label and combo box
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combobox)

        # Add a label for the "showtextwithimages" section
        showtextwithimages_label = QLabel("Question display mode:", self)

        # Add a combo box for showtextwithimages selection
        self.showtextwithimages_combobox = QComboBox(self)
        self.showtextwithimages_combobox.addItem("Only show text")
        self.showtextwithimages_combobox.addItem("Only show image")
        self.showtextwithimages_combobox.addItem("Show both")
        self.showtextwithimages_combobox.setCurrentText(current_showtextwithimages)

        # Set the font to bold and text color to white
        font = self.showtextwithimages_combobox.font()
        font.setBold(True)
        self.showtextwithimages_combobox.setFont(font)
        palette = self.showtextwithimages_combobox.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        self.showtextwithimages_combobox.setPalette(palette)

        # Add a white border around the dropdown menu
        self.showtextwithimages_combobox.setStyleSheet("QComboBox { border: 2px solid white; }")

        # Create a horizontal layout for the label and combo box
        showtextwithimages_layout = QHBoxLayout()
        showtextwithimages_layout.addWidget(showtextwithimages_label)
        showtextwithimages_layout.addWidget(self.showtextwithimages_combobox)

        # Add a label for the "earlybuzztimeout" section
        earlybuzztimeout_label = QLabel("Early buzz timeout (ms):", self)

        # Add a combo box for earlybuzztimeout selection
        self.earlybuzztimeout_combobox = QLineEdit(self)
        self.earlybuzztimeout_combobox.setText(str(current_earlybuzztimeout))

        # Set the font to bold and text color to white
        font = self.earlybuzztimeout_combobox.font()
        font.setBold(True)
        self.earlybuzztimeout_combobox.setFont(font)
        palette = self.earlybuzztimeout_combobox.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        self.earlybuzztimeout_combobox.setPalette(palette)

        # Add a white border around the dropdown menu
        self.earlybuzztimeout_combobox.setStyleSheet("QComboBox { border: 2px solid white; }")

        # Create a horizontal layout for the label and combo box
        earlybuzztimeout_layout = QHBoxLayout()
        earlybuzztimeout_layout.addWidget(earlybuzztimeout_label)
        earlybuzztimeout_layout.addWidget(self.earlybuzztimeout_combobox)

        # Add a label for the "use_wayback_first" section
        wayback_label = QLabel("Use Wayback Machine first:", self)

        # Add a combo box for use_wayback_first selection
        self.wayback_combobox = QComboBox(self)
        self.wayback_combobox.addItem("True")
        self.wayback_combobox.addItem("False")
        self.wayback_combobox.setCurrentText("True" if current_use_wayback_first else "False")

        # Set the font to bold and text color to white
        font = self.wayback_combobox.font()
        font.setBold(True)
        self.wayback_combobox.setFont(font)
        palette = self.wayback_combobox.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        self.wayback_combobox.setPalette(palette)

        # Add a white border around the dropdown menu
        self.wayback_combobox.setStyleSheet("QComboBox { border: 2px solid white; }")

        # Create a horizontal layout for the label and combo box
        wayback_layout = QHBoxLayout()
        wayback_layout.addWidget(wayback_label)
        wayback_layout.addWidget(self.wayback_combobox)
        layout.addLayout(wayback_layout)

        # Add a label for the "allownegative" section
        allownegative_label = QLabel("Allow Negatives:", self)

        # Add a combo box for allownegative selection
        self.allownegative_combobox = QComboBox(self)
        self.allownegative_combobox.addItem("True")
        self.allownegative_combobox.addItem("False")
        self.allownegative_combobox.setCurrentText(current_allownegative)

        # Set the font to bold and text color to white
        font = self.allownegative_combobox.font()
        font.setBold(True)
        self.allownegative_combobox.setFont(font)
        palette = self.allownegative_combobox.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        self.allownegative_combobox.setPalette(palette)

        # Add a white border around the dropdown menu
        self.allownegative_combobox.setStyleSheet("QComboBox { border: 2px solid white; }")

        # Create a horizontal layout for the label and combo box
        allownegative_layout = QHBoxLayout()
        allownegative_layout.addWidget(allownegative_label)
        allownegative_layout.addWidget(self.allownegative_combobox)

        # Add a label for the "allownegativeinfinal" section
        allownegativeinfinal_label = QLabel("Allow Negative Score In Final Jeopardy:", self)

        # Add a combo box for allownegativeinfinal selection
        self.allownegativeinfinal_combobox = QComboBox(self)
        self.allownegativeinfinal_combobox.addItem("True")
        self.allownegativeinfinal_combobox.addItem("False")
        self.allownegativeinfinal_combobox.setCurrentText(current_allownegativeinfinal)

        # Set the font to bold and text color to white
        font = self.allownegativeinfinal_combobox.font()
        font.setBold(True)
        self.allownegativeinfinal_combobox.setFont(font)
        palette = self.allownegativeinfinal_combobox.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        self.allownegativeinfinal_combobox.setPalette(palette)

        # Add a white border around the dropdown menu
        self.allownegativeinfinal_combobox.setStyleSheet("QComboBox { border: 2px solid white; }")

        # Create a horizontal layout for the label and combo box
        allownegativeinfinal_layout = QHBoxLayout()
        allownegativeinfinal_layout.addWidget(allownegativeinfinal_label)
        allownegativeinfinal_layout.addWidget(self.allownegativeinfinal_combobox)

        auto_host_label = QLabel("Auto Host:", self)
        self.auto_host_combobox = QComboBox(self)
        self.auto_host_combobox.addItem("False")
        self.auto_host_combobox.addItem("True")
        self.auto_host_combobox.setCurrentText("True" if current_auto_host.get('enabled') else "False")

        ai_provider_label = QLabel("Auto Host AI provider:", self)
        self.auto_host_provider_combobox = QComboBox(self)
        self.auto_host_provider_combobox.addItem("openai")
        self.auto_host_provider_combobox.addItem("local")
        self.auto_host_provider_combobox.setCurrentText(current_auto_host.get('ai_provider', 'openai'))

        leniency_label = QLabel("Auto Host leniency:", self)
        self.auto_host_leniency_combobox = QComboBox(self)
        self.auto_host_leniency_combobox.addItem("strict")
        self.auto_host_leniency_combobox.addItem("normal")
        self.auto_host_leniency_combobox.addItem("generous")
        self.auto_host_leniency_combobox.setCurrentText(current_auto_host.get('leniency', 'normal'))

        auto_host_layout = QHBoxLayout()
        auto_host_layout.addWidget(auto_host_label)
        auto_host_layout.addWidget(self.auto_host_combobox)

        auto_host_provider_layout = QHBoxLayout()
        auto_host_provider_layout.addWidget(ai_provider_label)
        auto_host_provider_layout.addWidget(self.auto_host_provider_combobox)

        auto_host_leniency_layout = QHBoxLayout()
        auto_host_leniency_layout.addWidget(leniency_label)
        auto_host_leniency_layout.addWidget(self.auto_host_leniency_combobox)

        voice_label = QLabel("Auto Host voice:", self)
        self.auto_host_voice_combobox = QComboBox(self)
        for voice, description in AUTO_HOST_VOICE_OPTIONS:
            self.auto_host_voice_combobox.addItem(f"{voice} - {description}", voice)
        current_voice_index = self.auto_host_voice_combobox.findData(current_auto_host.get('tts_voice', 'coral'))
        self.auto_host_voice_combobox.setCurrentIndex(max(0, current_voice_index))

        auto_host_voice_layout = QHBoxLayout()
        auto_host_voice_layout.addWidget(voice_label)
        auto_host_voice_layout.addWidget(self.auto_host_voice_combobox)

        openai_key_label = QLabel("OpenAI API Key:", self)
        self.openai_api_key_input = QLineEdit(self)
        self.openai_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_api_key_input.setPlaceholderText("sk-...")
        self.openai_api_key_input.setText(current_auto_host.get('openai_api_key', ''))

        openai_key_hint = QLabel("Stored locally on this computer. Leave blank to use OPENAI_API_KEY.", self)
        openai_key_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        openai_key_hint.setWordWrap(True)
        hint_palette = openai_key_hint.palette()
        hint_palette.setColor(QPalette.ColorRole.WindowText, QColor(128, 128, 128))
        openai_key_hint.setPalette(hint_palette)

        openai_key_layout = QHBoxLayout()
        openai_key_layout.addWidget(openai_key_label)
        openai_key_layout.addWidget(self.openai_api_key_input)

        self.local_auto_host_widgets = []

        local_llm_url_label = QLabel("Local LLM URL:", self)
        self.local_llm_url_input = QLineEdit(self)
        self.local_llm_url_input.setText(current_auto_host.get('local_llm_base_url', DEFAULT_CONFIG['auto_host']['local_llm_base_url']))
        self.local_llm_url_input.setPlaceholderText("http://localhost:11434/v1")
        local_llm_url_layout = QHBoxLayout()
        local_llm_url_layout.addWidget(local_llm_url_label)
        local_llm_url_layout.addWidget(self.local_llm_url_input)

        local_llm_model_label = QLabel("Local LLM model:", self)
        self.local_llm_model_input = QLineEdit(self)
        self.local_llm_model_input.setText(current_auto_host.get('local_llm_model', DEFAULT_CONFIG['auto_host']['local_llm_model']))
        self.local_llm_model_input.setPlaceholderText("qwen2.5:7b")
        local_llm_model_layout = QHBoxLayout()
        local_llm_model_layout.addWidget(local_llm_model_label)
        local_llm_model_layout.addWidget(self.local_llm_model_input)

        local_stt_url_label = QLabel("Local STT URL:", self)
        self.local_stt_url_input = QLineEdit(self)
        self.local_stt_url_input.setText(current_auto_host.get('local_stt_base_url', DEFAULT_CONFIG['auto_host']['local_stt_base_url']))
        self.local_stt_url_input.setPlaceholderText("http://localhost:8082/v1")
        local_stt_url_layout = QHBoxLayout()
        local_stt_url_layout.addWidget(local_stt_url_label)
        local_stt_url_layout.addWidget(self.local_stt_url_input)

        local_stt_model_label = QLabel("Local STT model:", self)
        self.local_stt_model_input = QLineEdit(self)
        self.local_stt_model_input.setText(current_auto_host.get('local_stt_model', DEFAULT_CONFIG['auto_host']['local_stt_model']))
        self.local_stt_model_input.setPlaceholderText("whisper")
        local_stt_model_layout = QHBoxLayout()
        local_stt_model_layout.addWidget(local_stt_model_label)
        local_stt_model_layout.addWidget(self.local_stt_model_input)

        local_tts_url_label = QLabel("Local TTS URL:", self)
        self.local_tts_url_input = QLineEdit(self)
        self.local_tts_url_input.setText(current_auto_host.get('local_tts_base_url', DEFAULT_CONFIG['auto_host']['local_tts_base_url']))
        self.local_tts_url_input.setPlaceholderText("http://localhost:8880/v1")
        local_tts_url_layout = QHBoxLayout()
        local_tts_url_layout.addWidget(local_tts_url_label)
        local_tts_url_layout.addWidget(self.local_tts_url_input)

        local_tts_preset_label = QLabel("Local TTS:", self)
        self.local_tts_preset_combobox = QComboBox(self)
        for preset, description in LOCAL_TTS_PRESET_OPTIONS:
            self.local_tts_preset_combobox.addItem(description, preset)
        current_tts_preset = current_auto_host.get('local_tts_preset')
        if not current_tts_preset:
            current_tts_model = current_auto_host.get('local_tts_model', DEFAULT_CONFIG['auto_host']['local_tts_model'])
            current_tts_url = current_auto_host.get('local_tts_base_url', DEFAULT_CONFIG['auto_host']['local_tts_base_url'])
            if current_tts_model == 'kokoclone' or current_tts_url.startswith('http://localhost:8892'):
                current_tts_preset = 'kokoclone_clone'
            elif current_tts_model != DEFAULT_CONFIG['auto_host']['local_tts_model'] or current_tts_url != DEFAULT_CONFIG['auto_host']['local_tts_base_url']:
                current_tts_preset = 'custom'
            else:
                current_tts_preset = DEFAULT_CONFIG['auto_host'].get('local_tts_preset', 'kokoro')
        current_tts_preset_index = self.local_tts_preset_combobox.findData(current_tts_preset)
        self.local_tts_preset_combobox.setCurrentIndex(max(0, current_tts_preset_index))
        local_tts_preset_layout = QHBoxLayout()
        local_tts_preset_layout.addWidget(local_tts_preset_label)
        local_tts_preset_layout.addWidget(self.local_tts_preset_combobox)

        local_tts_model_label = QLabel("Local TTS model:", self)
        self.local_tts_model_input = QLineEdit(self)
        self.local_tts_model_input.setText(current_auto_host.get('local_tts_model', DEFAULT_CONFIG['auto_host']['local_tts_model']))
        self.local_tts_model_input.setPlaceholderText("kokoro")
        local_tts_model_layout = QHBoxLayout()
        local_tts_model_layout.addWidget(local_tts_model_label)
        local_tts_model_layout.addWidget(self.local_tts_model_input)

        local_tts_voice_label = QLabel("Local TTS voice:", self)
        self.local_tts_voice_combobox = QComboBox(self)
        self.local_tts_voice_combobox.setEditable(False)
        self.local_tts_voice_combobox.setMinimumWidth(360)
        for voice, description in KOKORO_VOICE_OPTIONS:
            self.local_tts_voice_combobox.addItem(f"{description} ({voice})", voice)
        current_local_voice = current_auto_host.get('local_tts_voice', DEFAULT_CONFIG['auto_host']['local_tts_voice'])
        current_local_voice_index = self.local_tts_voice_combobox.findData(current_local_voice)
        if current_local_voice_index < 0:
            self.local_tts_voice_combobox.addItem(f"Custom configured voice ({current_local_voice})", current_local_voice)
            current_local_voice_index = self.local_tts_voice_combobox.findData(current_local_voice)
        self.local_tts_voice_combobox.setCurrentIndex(max(0, current_local_voice_index))
        local_tts_voice_layout = QHBoxLayout()
        local_tts_voice_layout.addWidget(local_tts_voice_label)
        local_tts_voice_layout.addWidget(self.local_tts_voice_combobox)

        local_tts_clone_voice_label = QLabel("Cloned voice name:", self)
        self.local_tts_clone_voice_input = QLineEdit(self)
        self.local_tts_clone_voice_input.setText(current_auto_host.get('local_tts_clone_voice', DEFAULT_CONFIG['auto_host'].get('local_tts_clone_voice', 'my_voice')))
        self.local_tts_clone_voice_input.setPlaceholderText("my_voice")
        local_tts_clone_voice_layout = QHBoxLayout()
        local_tts_clone_voice_layout.addWidget(local_tts_clone_voice_label)
        local_tts_clone_voice_layout.addWidget(self.local_tts_clone_voice_input)

        local_hint = QLabel("Local mode expects already-running OpenAI-compatible services. Use AUTOHOST.md or scripts/setup_local_auto_host_macos.sh to get started.", self)
        local_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        local_hint.setWordWrap(True)
        local_hint.setPalette(hint_palette)

        self.local_auto_host_widgets.extend([
            local_llm_url_label,
            self.local_llm_url_input,
            local_llm_model_label,
            self.local_llm_model_input,
            local_stt_url_label,
            self.local_stt_url_input,
            local_stt_model_label,
            self.local_stt_model_input,
            local_tts_preset_label,
            self.local_tts_preset_combobox,
            local_tts_url_label,
            self.local_tts_url_input,
            local_tts_model_label,
            self.local_tts_model_input,
            local_tts_voice_label,
            self.local_tts_voice_combobox,
            local_tts_clone_voice_label,
            self.local_tts_clone_voice_input,
            local_hint,
        ])

        self.local_tts_advanced_widgets = [
            local_tts_url_label,
            self.local_tts_url_input,
            local_tts_model_label,
            self.local_tts_model_input,
        ]
        self.local_tts_kokoro_widgets = [
            local_tts_voice_label,
            self.local_tts_voice_combobox,
        ]
        self.local_tts_clone_widgets = [
            local_tts_clone_voice_label,
            self.local_tts_clone_voice_input,
        ]

        # Add the horizontal layouts to the main layout
        layout.addLayout(settings_info_layout)
        layout.addSpacing(20)
        layout.addLayout(theme_layout)
        layout.addLayout(showtextwithimages_layout)
        layout.addLayout(earlybuzztimeout_layout)
        layout.addLayout(allownegative_layout)
        layout.addLayout(allownegativeinfinal_layout)
        layout.addLayout(auto_host_layout)
        layout.addLayout(auto_host_provider_layout)
        layout.addLayout(auto_host_leniency_layout)
        layout.addLayout(auto_host_voice_layout)
        layout.addLayout(openai_key_layout)
        layout.addWidget(openai_key_hint)
        layout.addLayout(local_llm_url_layout)
        layout.addLayout(local_llm_model_layout)
        layout.addLayout(local_stt_url_layout)
        layout.addLayout(local_stt_model_layout)
        layout.addLayout(local_tts_preset_layout)
        layout.addLayout(local_tts_url_layout)
        layout.addLayout(local_tts_model_layout)
        layout.addLayout(local_tts_voice_layout)
        layout.addLayout(local_tts_clone_voice_layout)
        layout.addWidget(local_hint)
        self.auto_host_provider_combobox.currentTextChanged.connect(self.update_auto_host_provider_fields)
        self.local_tts_preset_combobox.currentTextChanged.connect(lambda _text: self.update_local_tts_fields())
        self.update_auto_host_provider_fields(self.auto_host_provider_combobox.currentText())

        # Add space before the Apply button
        layout.addSpacing(10)

        # Add an "Apply" button
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.save_settings)  # Connect the button's clicked signal to the save_settings method
        self.apply_button.setStyleSheet("QPushButton { border: 2px solid black; }")
        self.apply_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.apply_button.setMinimumSize(100, 30)
        layout.addWidget(self.apply_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Add space after the Apply button
        layout.addSpacing(10)

        # Set the font to bold for all widgets in the layout
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget is not None:
                font = widget.font()
                font.setBold(True)
                widget.setFont(font)

        self.setLayout(layout)

    def update_auto_host_provider_fields(self, provider):
        is_local = provider == "local"
        for widget in getattr(self, "local_auto_host_widgets", []):
            widget.setVisible(is_local)
        self.update_local_tts_fields()

    def update_local_tts_fields(self):
        is_local = self.auto_host_provider_combobox.currentText() == "local"
        preset = self.local_tts_preset_combobox.currentData() or "kokoro"
        for widget in getattr(self, "local_tts_advanced_widgets", []):
            widget.setVisible(is_local and preset == "custom")
        for widget in getattr(self, "local_tts_kokoro_widgets", []):
            widget.setVisible(is_local and preset in ("kokoro", "custom"))
        for widget in getattr(self, "local_tts_clone_widgets", []):
            widget.setVisible(is_local and preset == "kokoclone_clone")

    def save_settings(self):
        logging.info("save_settings method called")  # Debugging line
        new_settings = {}
        requires_restart = False

        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Theme setting
        old_theme = config.get('theme', 'default')
        theme = self.theme_combobox.currentText()
        logging.info("theme: " + theme)
        if theme != old_theme:
            requires_restart = True

        # Show text with images setting
        showtextwithimages = self.showtextwithimages_combobox.currentText()

        # Early buzz timeout setting
        earlybuzztimeout = int(self.earlybuzztimeout_combobox.text())

        # Show allow negative setting
        allownegative = self.allownegative_combobox.currentText()

        # Show allow negative in final setting
        allownegativeinfinal = self.allownegativeinfinal_combobox.currentText()

        # Use Wayback Machine first setting
        use_wayback_first = self.wayback_combobox.currentText() == "True"

        auto_host = config.get('auto_host', DEFAULT_CONFIG['auto_host']).copy()
        auto_host['enabled'] = self.auto_host_combobox.currentText() == "True"
        auto_host['ai_provider'] = self.auto_host_provider_combobox.currentText()
        auto_host['openai_api_key'] = self.openai_api_key_input.text().strip()
        auto_host['tts_voice'] = self.auto_host_voice_combobox.currentData() or 'coral'
        auto_host['local_llm_base_url'] = self.local_llm_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_llm_base_url']
        auto_host['local_llm_model'] = self.local_llm_model_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_llm_model']
        auto_host['local_stt_base_url'] = self.local_stt_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_stt_base_url']
        auto_host['local_stt_model'] = self.local_stt_model_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_stt_model']
        tts_preset = self.local_tts_preset_combobox.currentData() or 'kokoro'
        auto_host['local_tts_preset'] = tts_preset
        auto_host['local_tts_clone_voice'] = self.local_tts_clone_voice_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_tts_clone_voice']
        if tts_preset == 'kokoclone_clone':
            auto_host['local_tts_base_url'] = 'http://localhost:8892/v1'
            auto_host['local_tts_model'] = 'kokoclone'
            auto_host['local_tts_voice'] = auto_host['local_tts_clone_voice']
        elif tts_preset == 'kokoro':
            auto_host['local_tts_base_url'] = DEFAULT_CONFIG['auto_host']['local_tts_base_url']
            auto_host['local_tts_model'] = DEFAULT_CONFIG['auto_host']['local_tts_model']
            auto_host['local_tts_voice'] = (
                self.local_tts_voice_combobox.currentData()
                or DEFAULT_CONFIG['auto_host']['local_tts_voice']
            )
        else:
            auto_host['local_tts_base_url'] = self.local_tts_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_tts_base_url']
            auto_host['local_tts_model'] = self.local_tts_model_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_tts_model']
            auto_host['local_tts_voice'] = (
                self.local_tts_voice_combobox.currentData()
                or DEFAULT_CONFIG['auto_host']['local_tts_voice']
            )
        auto_host['selection_mode'] = 'voice_with_gui_fallback'
        auto_host['answer_judging'] = 'auto_with_challenge'
        auto_host['leniency'] = self.auto_host_leniency_combobox.currentText()

        # Save config
        logging.info("Saving settings...")
        with open(config_path, 'w') as f:
            json.dump({
                'theme': theme,
                'showtextwithimages': showtextwithimages,
                'earlybuzztimeout': earlybuzztimeout,
                'allownegative': allownegative,
                'allownegativeinfinal': allownegativeinfinal,
                'use_wayback_first': use_wayback_first,
                'mute_sound': config.get('mute_sound', DEFAULT_CONFIG['mute_sound']),
                'auto_host': auto_host,
            }, f)

        try:
            self.parent().game.config = config
            self.parent().game.config.update({
                'theme': theme,
                'showtextwithimages': showtextwithimages,
                'earlybuzztimeout': earlybuzztimeout,
                'allownegative': allownegative,
                'allownegativeinfinal': allownegativeinfinal,
                'use_wayback_first': use_wayback_first,
                'mute_sound': config.get('mute_sound', DEFAULT_CONFIG['mute_sound']),
                'auto_host': auto_host,
            })
            self.parent().game.auto_host.refresh_config()
            url = self.parent().game.buzzer_controller.player_url(prefer_https=True)
            self.parent().game.main_display.welcome_widget.set_url(url)
        except Exception:
            logging.exception("Failed to refresh buzzer URL after settings save")

        if requires_restart:
            # Restart the application
            # Use sys.executable as both the path and the first argument
            os.execv(sys.executable, [sys.executable] + sys.argv)
        self.accept()  # Close the dialog
