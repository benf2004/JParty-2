from PyQt6.QtGui import (
    QPainter,
    QBrush,
    QImage,
    QFont,
    QPalette,
    QPixmap,
    QColor,
    QIntValidator,
    QPolygonF,
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
    QCheckBox,
    QPushButton,
    QFileDialog,
    QScrollArea,
    QTabWidget,
    QGroupBox,
    QApplication,
    QStyleFactory,
)
from PyQt6.QtCore import Qt, QSize, QPointF, pyqtSignal

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
from jparty.local_services import LocalServiceManager
from jparty.service_widgets import LocalServicesPanel

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

MACOS_SAY_VOICE_OPTIONS = [
    ("__custom__", "Custom / Personal Voice"),
    ("", "Use macOS default voice"),
    ("Agnes", "English US"),
    ("Albert", "English US"),
    ("Alex", "English US"),
    ("Alice", "Italian"),
    ("Alva", "Swedish"),
    ("Amelie", "Canadian French"),
    ("Anna", "German"),
    ("Bad News", "English US"),
    ("Bahh", "English US"),
    ("Bells", "English US"),
    ("Boing", "English US"),
    ("Bruce", "English US"),
    ("Bubbles", "English US"),
    ("Carmit", "Hebrew"),
    ("Cellos", "English US"),
    ("Damayanti", "Indonesian"),
    ("Daniel", "British English"),
    ("Deranged", "English US"),
    ("Diego", "Argentinian Spanish"),
    ("Ellen", "Belgian Dutch"),
    ("Fiona", "Scottish English"),
    ("Fred", "English US"),
    ("Good News", "English US"),
    ("Hysterical", "English US"),
    ("Ioana", "Romanian"),
    ("Joana", "Portuguese"),
    ("Junior", "English US"),
    ("Kanya", "Thai"),
    ("Karen", "Australian English"),
    ("Kathy", "English US"),
    ("Kyoko", "Japanese"),
    ("Laura", "Slovak"),
    ("Lekha", "Hindi"),
    ("Luciana", "Brazilian Portuguese"),
    ("Mariska", "Hungarian"),
    ("Mei-Jia", "Taiwan Mandarin"),
    ("Melina", "Greek"),
    ("Milena", "Russian"),
    ("Moira", "Irish English"),
    ("Monica", "Spanish"),
    ("Nora", "Norwegian"),
    ("Paulina", "Mexican Spanish"),
    ("Pipe Organ", "English US"),
    ("Princess", "English US"),
    ("Ralph", "English US"),
    ("Samantha", "English US"),
    ("Sara", "Danish"),
    ("Satu", "Finnish"),
    ("Sin-ji", "Hong Kong Cantonese"),
    ("Tarik", "Arabic"),
    ("Tessa", "South African English"),
    ("Thomas", "French"),
    ("Ting-Ting", "Mainland Mandarin"),
    ("Trinoids", "English US"),
    ("Veena", "Indian English"),
    ("Vicki", "English US"),
    ("Victoria", "English US"),
    ("Whisper", "English US"),
    ("Xander", "Dutch"),
    ("Yelda", "Turkish"),
    ("Yuna", "Korean"),
    ("Zarvox", "English US"),
    ("Zosia", "Polish"),
    ("Zuzana", "Czech"),
]

LOCAL_TTS_PRESET_OPTIONS = [
    ("macos_say", "macOS Say / Personal Voice"),
    ("kokoro", "Kokoro"),
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
        self.game.start_countdown_changed.connect(self.update_start_countdown)

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
        self.auto_host_status_label = QLabel()
        self.auto_host_status_label.setWordWrap(True)
        self.auto_host_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.auto_host_status_label.setContentsMargins(24, 12, 24, 18)
        self.auto_host_status_label.setStyleSheet('color: #64748b; font-size: 13px;')
        main_layout.addWidget(self.auto_host_status_label)
        main_layout.addLayout(footer_layout, 3)
        main_layout.addStretch(3)

        self.gameid_trigger.connect(self.set_gameid)
        self.summary_trigger.connect(self.set_summary)
        self.game.local_services.changed.connect(self.update_auto_host_status)
        self.update_auto_host_status()

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

    def update_auto_host_status(self):
        enabled = self.game.auto_host.enabled
        self.auto_host_status_label.setVisible(enabled)
        self.auto_host_status_label.setText('Auto Host · ' + self.game.local_services.message)
        self.check_start()

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
        if self.game.auto_host.enabled and not self.game.auto_host_ready():
            self.start_button.setToolTip('Auto Host is not ready. Open Settings → Local Services to start or set up its services.')
        else:
            self.start_button.setToolTip('')

    def update_start_countdown(self, state):
        seconds = state["seconds_remaining"]
        if state.get('checking_services'):
            self.start_button.setText("Checking Auto Host… Cancel")
        else:
            self.start_button.setText(f"Starting in {seconds}… Cancel" if seconds else "Start!")
        self.check_start()

    def on_start(self):
        if self.game.start_countdown_deadline is not None or getattr(self.game, '_start_check_pending', False):
            self.game.cancel_start_game()
        else:
            self.game.request_start_game()

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

class SettingsComboBox(QComboBox):
    """Keep the dropdown affordance visible with the settings stylesheet."""
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#637089'))
        x, y = self.width() - 17, self.height() / 2
        painter.drawPolygon(QPolygonF([QPointF(x - 4, y - 2), QPointF(x + 4, y - 2), QPointF(x, y + 3)]))


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
        current_image_fallback = DEFAULT_CONFIG['image_fallback'].copy()
        current_image_fallback.update(config.get('image_fallback', {}) or {})
        current_auto_host = DEFAULT_CONFIG['auto_host'].copy()
        current_auto_host.update(config.get('auto_host', {}) or {})

        self.setWindowTitle("Settings")
        self.setObjectName("SettingsMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.settings_style = QStyleFactory.create("Fusion")
        self.setStyle(self.settings_style)
        self.resize(880, 780)
        self.setMinimumSize(720, 570)
        self._saved_auto_host = current_auto_host.copy()
        game = getattr(parent, 'game', None)
        self.service_manager = getattr(game, 'local_services', None)
        if self.service_manager is None:
            self.service_manager = LocalServiceManager(current_auto_host, self)

        def section_heading(text):
            label = QLabel(text, self)
            heading_font = label.font()
            heading_font.setBold(True)
            heading_font.setPointSize(max(heading_font.pointSize() + 2, 14))
            label.setFont(heading_font)
            return label

        general_heading = section_heading("General")
        images_heading = section_heading("Images")
        auto_host_heading = section_heading("Auto Host")

        # Add a label for the "Theme" section
        theme_label = QLabel("Theme:", self)

        # Add a combo box for theme selection
        self.theme_combobox = SettingsComboBox(self)
        self.theme_combobox.addItem("Default")
        self.theme_combobox.addItem("Christmas")
        self.theme_combobox.addItem("Halloween")
        self.theme_combobox.addItem("EightiesSynthwave")
        self.theme_combobox.addItem("Birthday")
        self.theme_combobox.addItem("BibleBonkers")
        self.theme_combobox.setCurrentText(current_theme)

        # Create a horizontal layout for the label and combo box
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combobox)

        # Add a label for the "showtextwithimages" section
        showtextwithimages_label = QLabel("Question display mode:", self)

        # Add a combo box for showtextwithimages selection
        self.showtextwithimages_combobox = SettingsComboBox(self)
        self.showtextwithimages_combobox.addItem("Only show text")
        self.showtextwithimages_combobox.addItem("Only show image")
        self.showtextwithimages_combobox.addItem("Show both")
        self.showtextwithimages_combobox.setCurrentText(current_showtextwithimages)

        # Create a horizontal layout for the label and combo box
        showtextwithimages_layout = QHBoxLayout()
        showtextwithimages_layout.addWidget(showtextwithimages_label)
        showtextwithimages_layout.addWidget(self.showtextwithimages_combobox)

        # Add a label for the "earlybuzztimeout" section
        earlybuzztimeout_label = QLabel("Early buzz timeout (ms):", self)

        # Add a combo box for earlybuzztimeout selection
        self.earlybuzztimeout_combobox = QLineEdit(self)
        self.earlybuzztimeout_combobox.setText(str(current_earlybuzztimeout))
        self.earlybuzztimeout_combobox.setValidator(QIntValidator(0, 10000, self))

        # Create a horizontal layout for the label and combo box
        earlybuzztimeout_layout = QHBoxLayout()
        earlybuzztimeout_layout.addWidget(earlybuzztimeout_label)
        earlybuzztimeout_layout.addWidget(self.earlybuzztimeout_combobox)

        # Add a label for the "use_wayback_first" section
        wayback_label = QLabel("Use Wayback Machine first:", self)

        # Add a combo box for use_wayback_first selection
        self.wayback_combobox = SettingsComboBox(self)
        self.wayback_combobox.addItem("Try archived images first", True)
        self.wayback_combobox.addItem("Try live images first", False)
        self.wayback_combobox.setCurrentIndex(0 if current_use_wayback_first else 1)

        # Create a horizontal layout for the label and combo box
        wayback_layout = QHBoxLayout()
        wayback_layout.addWidget(wayback_label)
        wayback_layout.addWidget(self.wayback_combobox)

        self.use_pexels_checkbox = QCheckBox("USE PEXELS API (requires OpenAI key or local LLM)", self)
        self.use_pexels_checkbox.setChecked(bool(current_image_fallback.get('use_pexels', False)))
        self.use_pexels_checkbox.setToolTip("Only replaces missing J-Archive media images.")

        pexels_key_label = QLabel("Pexels API Key:", self)
        self.pexels_api_key_input = QLineEdit(self)
        self.pexels_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pexels_api_key_input.setPlaceholderText("Pexels API key")
        self.pexels_api_key_input.setText(current_image_fallback.get('pexels_api_key', ''))

        pexels_key_layout = QHBoxLayout()
        pexels_key_layout.addWidget(pexels_key_label)
        pexels_key_layout.addWidget(self.pexels_api_key_input)

        self.pexels_status_label = QLabel("", self)
        self.pexels_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pexels_status_label.setWordWrap(True)
        pexels_status_palette = self.pexels_status_label.palette()
        pexels_status_palette.setColor(QPalette.ColorRole.WindowText, QColor(128, 128, 128))
        self.pexels_status_label.setPalette(pexels_status_palette)

        # Add a label for the "allownegative" section
        allownegative_label = QLabel("Negative scores:", self)

        # Add a combo box for allownegative selection
        self.allownegative_combobox = SettingsComboBox(self)
        self.allownegative_combobox.addItem("Allowed", "True")
        self.allownegative_combobox.addItem("Not allowed", "False")
        self.allownegative_combobox.setCurrentIndex(max(0, self.allownegative_combobox.findData(current_allownegative)))

        # Create a horizontal layout for the label and combo box
        allownegative_layout = QHBoxLayout()
        allownegative_layout.addWidget(allownegative_label)
        allownegative_layout.addWidget(self.allownegative_combobox)

        # Add a label for the "allownegativeinfinal" section
        allownegativeinfinal_label = QLabel("Negative scores in Final Jeopardy:", self)

        # Add a combo box for allownegativeinfinal selection
        self.allownegativeinfinal_combobox = SettingsComboBox(self)
        self.allownegativeinfinal_combobox.addItem("Allowed", "True")
        self.allownegativeinfinal_combobox.addItem("Not allowed", "False")
        self.allownegativeinfinal_combobox.setCurrentIndex(max(0, self.allownegativeinfinal_combobox.findData(current_allownegativeinfinal)))

        # Create a horizontal layout for the label and combo box
        allownegativeinfinal_layout = QHBoxLayout()
        allownegativeinfinal_layout.addWidget(allownegativeinfinal_label)
        allownegativeinfinal_layout.addWidget(self.allownegativeinfinal_combobox)

        auto_host_label = QLabel("Use Auto Host:", self)
        self.auto_host_combobox = SettingsComboBox(self)
        self.auto_host_combobox.addItem("Manual host", False)
        self.auto_host_combobox.addItem("Auto Host enabled", True)
        self.auto_host_combobox.setCurrentIndex(1 if current_auto_host.get('enabled') else 0)

        ai_provider_label = QLabel("Auto Host AI provider:", self)
        self.auto_host_provider_combobox = SettingsComboBox(self)
        self.auto_host_provider_combobox.addItem("OpenAI · cloud", "openai")
        self.auto_host_provider_combobox.addItem("Local · on this Mac", "local")
        self.auto_host_provider_combobox.setCurrentIndex(max(0, self.auto_host_provider_combobox.findData(current_auto_host.get('ai_provider', 'openai'))))

        leniency_label = QLabel("Auto Host leniency:", self)
        self.auto_host_leniency_combobox = SettingsComboBox(self)
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

        judge_provider_layout = QHBoxLayout()
        judge_provider_layout.addWidget(QLabel("Answer judge:", self))
        self.judge_provider_combobox = SettingsComboBox(self)
        self.judge_provider_combobox.addItem("Local LLM · fast true/false (recommended)", "local_binary")
        self.judge_provider_combobox.addItem("Use Auto Host AI provider", "default")
        self.judge_provider_combobox.addItem("Kev (local decision model)", "kev")
        judge_index = self.judge_provider_combobox.findData(current_auto_host.get('judge_provider', 'local_binary'))
        self.judge_provider_combobox.setCurrentIndex(max(0, judge_index))
        judge_provider_layout.addWidget(self.judge_provider_combobox)

        kev_url_label = QLabel("Kev URL:", self)
        self.kev_url_input = QLineEdit(self)
        self.kev_url_input.setText(current_auto_host.get('kev_base_url', DEFAULT_CONFIG['auto_host']['kev_base_url']))
        kev_url_layout = QHBoxLayout()
        kev_url_layout.addWidget(kev_url_label)
        kev_url_layout.addWidget(self.kev_url_input)
        kev_model_label = QLabel("Kev served model:", self)
        self.kev_model_input = QLineEdit(self)
        self.kev_model_input.setText(current_auto_host.get('kev_model', DEFAULT_CONFIG['auto_host']['kev_model']))
        kev_model_layout = QHBoxLayout()
        kev_model_layout.addWidget(kev_model_label)
        kev_model_layout.addWidget(self.kev_model_input)
        kev_hint = QLabel("Kev-0.8B judges unresolved answers. Fast checks run first. Use Local Services to set up and start Kev.", self)
        kev_hint.setWordWrap(True)
        self.kev_judge_widgets = [kev_url_label, self.kev_url_input, kev_model_label, self.kev_model_input, kev_hint]

        auto_host_leniency_layout = QHBoxLayout()
        auto_host_leniency_layout.addWidget(leniency_label)
        auto_host_leniency_layout.addWidget(self.auto_host_leniency_combobox)

        voice_label = QLabel("Auto Host voice:", self)
        self.auto_host_voice_combobox = SettingsComboBox(self)
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

        self.openai_auto_host_widgets = [
            voice_label,
            self.auto_host_voice_combobox,
            openai_key_label,
            self.openai_api_key_input,
            openai_key_hint,
        ]

        self._pexels_local_llm_available = any(
            row['name'] == 'Text generation' and row['ready'] for row in self.service_manager.results
        )

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
        self.local_tts_preset_combobox = SettingsComboBox(self)
        for preset, description in LOCAL_TTS_PRESET_OPTIONS:
            self.local_tts_preset_combobox.addItem(description, preset)
        current_tts_preset = current_auto_host.get('local_tts_preset')
        if current_tts_preset == 'macos_personal_voice':
            current_tts_preset = 'macos_say'
        if not current_tts_preset:
            current_tts_model = current_auto_host.get('local_tts_model', DEFAULT_CONFIG['auto_host']['local_tts_model'])
            current_tts_url = current_auto_host.get('local_tts_base_url', DEFAULT_CONFIG['auto_host']['local_tts_base_url'])
            if current_tts_model == 'macos-say':
                current_tts_preset = 'macos_say'
            elif current_tts_model != DEFAULT_CONFIG['auto_host']['local_tts_model'] or current_tts_url != DEFAULT_CONFIG['auto_host']['local_tts_base_url']:
                current_tts_preset = 'custom'
            else:
                current_tts_preset = DEFAULT_CONFIG['auto_host'].get('local_tts_preset', 'macos_say')
                if current_tts_preset == 'macos_personal_voice':
                    current_tts_preset = 'macos_say'
        current_tts_preset_index = self.local_tts_preset_combobox.findData(current_tts_preset)
        self.local_tts_preset_combobox.setCurrentIndex(max(0, current_tts_preset_index))
        local_tts_preset_layout = QHBoxLayout()
        local_tts_preset_layout.addWidget(local_tts_preset_label)
        local_tts_preset_layout.addWidget(self.local_tts_preset_combobox)

        local_tts_model_label = QLabel("Local TTS model:", self)
        self.local_tts_model_input = QLineEdit(self)
        self.local_tts_model_input.setText(current_auto_host.get('local_tts_model', DEFAULT_CONFIG['auto_host']['local_tts_model']))
        self.local_tts_model_input.setPlaceholderText("macos-say")
        local_tts_model_layout = QHBoxLayout()
        local_tts_model_layout.addWidget(local_tts_model_label)
        local_tts_model_layout.addWidget(self.local_tts_model_input)

        current_local_voice = current_auto_host.get('local_tts_voice', DEFAULT_CONFIG['auto_host']['local_tts_voice'])

        macos_tts_voice_label = QLabel("macOS Say voice:", self)
        self.macos_tts_voice_combobox = SettingsComboBox(self)
        self.macos_tts_voice_combobox.setMinimumWidth(360)
        for voice, description in MACOS_SAY_VOICE_OPTIONS:
            if voice == "__custom__":
                label = description
            elif not voice:
                label = "Use macOS default voice"
            else:
                label = f"{voice} - {description}"
            self.macos_tts_voice_combobox.addItem(label, voice)
        current_macos_voice_index = self.macos_tts_voice_combobox.findData(current_local_voice)
        if current_macos_voice_index < 0:
            current_macos_voice_index = self.macos_tts_voice_combobox.findData("__custom__")
        self.macos_tts_voice_combobox.setCurrentIndex(max(0, current_macos_voice_index))
        macos_tts_voice_layout = QHBoxLayout()
        macos_tts_voice_layout.addWidget(macos_tts_voice_label)
        macos_tts_voice_layout.addWidget(self.macos_tts_voice_combobox)

        macos_tts_custom_voice_label = QLabel("Custom voice name:", self)
        self.macos_tts_custom_voice_input = QLineEdit(self)
        if current_macos_voice_index == self.macos_tts_voice_combobox.findData("__custom__"):
            self.macos_tts_custom_voice_input.setText(current_local_voice)
        self.macos_tts_custom_voice_input.setPlaceholderText("Exact Personal Voice name from say -v ?")
        macos_tts_custom_voice_layout = QHBoxLayout()
        macos_tts_custom_voice_layout.addWidget(macos_tts_custom_voice_label)
        macos_tts_custom_voice_layout.addWidget(self.macos_tts_custom_voice_input)

        kokoro_tts_voice_label = QLabel("Kokoro voice:", self)
        self.kokoro_tts_voice_combobox = SettingsComboBox(self)
        self.kokoro_tts_voice_combobox.setMinimumWidth(360)
        for voice, description in KOKORO_VOICE_OPTIONS:
            self.kokoro_tts_voice_combobox.addItem(f"{description} ({voice})", voice)
        current_kokoro_voice = current_local_voice or 'af_heart'
        current_kokoro_voice_index = self.kokoro_tts_voice_combobox.findData(current_kokoro_voice)
        self.kokoro_tts_voice_combobox.setCurrentIndex(max(0, current_kokoro_voice_index))
        kokoro_tts_voice_layout = QHBoxLayout()
        kokoro_tts_voice_layout.addWidget(kokoro_tts_voice_label)
        kokoro_tts_voice_layout.addWidget(self.kokoro_tts_voice_combobox)

        local_hint = QLabel("For Personal Voice, create it in macOS Accessibility, allow applications to use it, then use the exact voice name shown by say -v ?. Use Set up in Local Services to install the voice bridge.", self)
        local_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        local_hint.setWordWrap(True)
        local_hint.setPalette(hint_palette)

        self.local_llm_widgets = [local_llm_url_label, self.local_llm_url_input,
                                  local_llm_model_label, self.local_llm_model_input]
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
            macos_tts_voice_label,
            self.macos_tts_voice_combobox,
            macos_tts_custom_voice_label,
            self.macos_tts_custom_voice_input,
            kokoro_tts_voice_label,
            self.kokoro_tts_voice_combobox,
            local_hint,
        ])

        self.local_tts_custom_endpoint_widgets = [
            local_tts_url_label,
            self.local_tts_url_input,
            local_tts_model_label,
            self.local_tts_model_input,
        ]
        self.local_tts_macos_widgets = [
            macos_tts_voice_label,
            self.macos_tts_voice_combobox,
        ]
        self.local_tts_macos_custom_widgets = [
            macos_tts_custom_voice_label,
            self.macos_tts_custom_voice_input,
        ]
        self.local_tts_kokoro_widgets = [
            kokoro_tts_voice_label,
            self.kokoro_tts_voice_combobox,
        ]

        # Each settings page scrolls independently; actions stay in the footer.
        for widget in self.findChildren(QWidget):
            widget.setStyleSheet("")
            widget.setPalette(QApplication.palette())
            widget.setFont(QFont("Helvetica Neue", 12))
            if isinstance(widget, QComboBox):
                widget.setMinimumWidth(180)
                widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                widget.setMinimumContentsLength(16)
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        def page(title, heading, description):
            content = QWidget()
            body = QVBoxLayout(content)
            body.setContentsMargins(22, 22, 22, 22)
            body.setSpacing(16)
            heading.setObjectName('pageTitle')
            body.addWidget(heading)
            subtitle = QLabel(description)
            subtitle.setProperty('muted', True)
            subtitle.setWordWrap(True)
            body.addWidget(subtitle)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, title)
            return body
        def group(body, title, rows):
            box = QGroupBox(title)
            inner = QVBoxLayout(box)
            inner.setContentsMargins(16, 24, 16, 16)
            inner.setSpacing(12)
            for row in rows:
                if isinstance(row, QWidget):
                    inner.addWidget(row)
                else:
                    row.setSpacing(12)
                    first = row.itemAt(0).widget() if row.count() else None
                    if isinstance(first, QLabel):
                        first.setFixedWidth(265)
                    inner.addLayout(row)
            body.addWidget(box)
            return box

        game_body = page('Game', general_heading, 'Set the look, pacing, and scoring rules for your game.')
        group(game_body, 'Appearance', [theme_layout, showtextwithimages_layout])
        group(game_body, 'Rules and timing', [earlybuzztimeout_layout, allownegative_layout,
                                           allownegativeinfinal_layout, wayback_layout])
        game_body.addStretch()

        from jparty.teams import TeamMode
        from jparty.team_widgets import TeamSettingsPanel
        self.team_panel = TeamSettingsPanel(game if isinstance(game, TeamMode) else None, self)
        team_scroll = QScrollArea()
        team_scroll.setWidgetResizable(True)
        team_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        team_scroll.setWidget(self.team_panel)
        self.team_tab_index = self.tabs.addTab(team_scroll, 'Team mode')

        host_body = page('Auto Host', auto_host_heading, 'Choose who hosts, how answers are judged, and which voice players hear.')
        group(host_body, 'Hosting', [auto_host_layout, auto_host_provider_layout])
        restart_hint = QLabel('Turning Auto Host on or off restarts JParty to update phone microphone access. Save changes before starting services.')
        restart_hint.setWordWrap(True)
        restart_hint.setProperty('muted', True)
        host_body.addWidget(restart_hint)
        group(host_body, 'Answer judging', [judge_provider_layout, auto_host_leniency_layout])
        self.cloud_group = group(host_body, 'OpenAI', [openai_key_layout, auto_host_voice_layout, openai_key_hint])
        local_shortcut = QPushButton('Manage local services →')
        local_shortcut.clicked.connect(lambda: self.tabs.setCurrentIndex(self.services_tab_index))
        host_body.addWidget(local_shortcut)
        host_body.addStretch()

        self.services_tab_index = self.tabs.count()
        services_body = page('Local Services', QLabel('Local Auto Host'), 'Your game-night stack, in one place.')
        self.services_panel = LocalServicesPanel(self.service_manager, self.service_action_config, self)
        group(services_body, 'Service status', [self.services_panel])
        self.llm_group = group(services_body, 'Local LLM · text generation and answer judging', [local_llm_url_layout, local_llm_model_layout])
        self.stt_group = group(services_body, 'Speech recognition · Whisper', [local_stt_url_layout, local_stt_model_layout])
        self.voice_group = group(services_body, 'Host voice', [local_tts_preset_layout, local_tts_url_layout,
            local_tts_model_layout, macos_tts_voice_layout, macos_tts_custom_voice_layout,
            kokoro_tts_voice_layout, local_hint])
        self.kev_group = group(services_body, 'Answer judging · Kev', [kev_url_layout, kev_model_layout, kev_hint])
        services_body.addStretch()

        images_body = page('Images', images_heading, 'Replace missing clue images with photos from Pexels.')
        self.use_pexels_checkbox.setText('Find replacement images with Pexels')
        group(images_body, 'Image fallback', [self.use_pexels_checkbox, pexels_key_layout, self.pexels_status_label])
        images_body.addStretch()

        self.auto_host_provider_combobox.currentTextChanged.connect(self.update_auto_host_provider_fields)
        self.judge_provider_combobox.currentIndexChanged.connect(self.update_judge_provider_fields)
        self.openai_api_key_input.textChanged.connect(lambda _text: self.update_pexels_fields())
        self.local_tts_preset_combobox.currentTextChanged.connect(lambda _text: self.update_local_tts_fields())
        self.macos_tts_voice_combobox.currentTextChanged.connect(lambda _text: self.update_local_tts_fields())
        self.update_auto_host_provider_fields(self.auto_host_provider_combobox.currentData())
        self.update_judge_provider_fields()
        self.update_pexels_fields()

        footer = QHBoxLayout()
        self.settings_feedback = QLabel('Changes apply when you save.')
        self.settings_feedback.setWordWrap(True)
        self.settings_feedback.setMinimumWidth(0)
        self.settings_feedback.setProperty('muted', True)
        footer.addWidget(self.settings_feedback, 1)
        self.cancel_button = QPushButton('Close')
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        self.apply_button = QPushButton('Save changes')
        self.apply_button.setObjectName('primaryButton')
        self.apply_button.clicked.connect(lambda: self.save_settings(close=False))
        footer.addWidget(self.apply_button)
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(18, 14, 18, 16)
        dialog_layout.setSpacing(14)
        dialog_layout.addWidget(self.tabs, 1)
        dialog_layout.addLayout(footer)
        self.service_manager.changed.connect(self.update_service_controls)
        self.update_service_controls()
        self.setStyleSheet("""
            QDialog#SettingsMenu { background: #f3f5fa; }
            QWidget { color: #243047; font-size: 13px; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: #f3f5fa; }
            QTabWidget::pane { border: 0; }
            QTabBar::tab { padding: 11px 20px; margin-right: 5px; border-radius: 7px; color: #637089; }
            QTabBar::tab:selected { color: #1d4ed8; background: #e3ebff; font-weight: 600; }
            QGroupBox { background: white; border: 1px solid #dce2ed; border-radius: 10px;
                        margin-top: 10px; padding-top: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 5px; }
            QLabel#pageTitle { font-size: 25px; font-weight: 700; color: #14213a; }
            QLabel[muted="true"] { color: #66748b; font-size: 12px; }
            QLabel#serviceSummary { font-weight: 600; font-size: 15px; }
            QLabel#serviceRow[state="ready"] { border-left: 3px solid #24946b; }
            QLabel#serviceRow[state="offline"] { border-left: 3px solid #d29029; }
            QLabel#serviceRow { background: #f7f9fc; border-radius: 6px; padding: 10px; font-size: 12px; }
            QLineEdit, QComboBox { background: white; border: 1px solid #cbd4e2;
                                  border-radius: 6px; padding: 7px 10px; min-height: 18px; }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #4777eb; }
            QComboBox::drop-down { border: 0; width: 24px; }
            QComboBox::down-arrow { image: none; }
            QComboBox QAbstractItemView { background: white; color: #243047; selection-background-color: #e3ebff; }
            QPushButton { background: white; border: 1px solid #cbd4e2; border-radius: 7px;
                          padding: 9px 15px; font-weight: 600; }
            QPushButton:hover { background: #edf2fc; border-color: #8da6da; }
            QPushButton#primaryButton { background: #285ee8; color: white; border: 1px solid #285ee8; }
            QPushButton#primaryButton:hover { background: #1e4dcc; }
            QPushButton:disabled { background: #e8ecf3; color: #8994a7; border-color: #dce2ed; }
            QPlainTextEdit { background: #172238; color: #dce7fb; border: none; border-radius: 8px;
                             padding: 10px; font-family: Menlo; font-size: 11px; }
            QScrollBar:vertical { width: 9px; background: transparent; }
            QScrollBar::handle:vertical { background: #bec8d9; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

    def update_service_controls(self):
        self.apply_button.setEnabled(not self.service_manager.busy)
        self._pexels_local_llm_available = any(
            row['name'] == 'Text generation' and row['ready'] for row in self.service_manager.results
        )
        self.update_pexels_fields()

    def service_action_config(self):
        draft = self.auto_host_settings()
        if any(draft.get(key) != self._saved_auto_host.get(key) for key in (
            'enabled', 'ai_provider', 'judge_provider', 'local_llm_base_url', 'local_llm_model',
            'local_stt_base_url', 'local_stt_model', 'local_tts_base_url', 'local_tts_model',
            'local_tts_preset', 'local_tts_voice', 'kev_base_url', 'kev_model',
        )):
            raise ValueError('Save your Auto Host changes first, then set up or start services.')
        return self._saved_auto_host

    def update_judge_provider_fields(self, *_args):
        is_kev = self.judge_provider_combobox.currentData() == "kev"
        for widget in self.kev_judge_widgets:
            widget.setVisible(is_kev)
        self.kev_group.setVisible(is_kev)
        self.update_auto_host_provider_fields(None)

    def update_auto_host_provider_fields(self, provider):
        is_local = self.auto_host_provider_combobox.currentData() == "local"
        for widget in getattr(self, "openai_auto_host_widgets", []):
            widget.setVisible(not is_local)
        needs_local_judge = self.judge_provider_combobox.currentData() == "local_binary"
        for widget in getattr(self, "local_auto_host_widgets", []):
            widget.setVisible(is_local or (needs_local_judge and widget in self.local_llm_widgets))
        self.cloud_group.setVisible(not is_local)
        self.llm_group.setVisible(is_local or needs_local_judge)
        for group in (self.stt_group, self.voice_group):
            group.setVisible(is_local)
        self.update_local_tts_fields()

    def update_pexels_fields(self):
        has_llm = bool(
            os.environ.get("OPENAI_API_KEY")
            or self.openai_api_key_input.text().strip()
            or self._pexels_local_llm_available
        )
        self.use_pexels_checkbox.setEnabled(has_llm)
        if has_llm:
            self.pexels_status_label.setText("Stored locally on this computer. Leave blank to use PEXELS_API_KEY.")
        else:
            self.pexels_status_label.setText("Add an OpenAI API key or start your local LLM, then click Check status in Local Services to enable Pexels.")

    def update_local_tts_fields(self):
        is_local = self.auto_host_provider_combobox.currentData() == "local"
        preset = self.local_tts_preset_combobox.currentData() or "macos_say"
        if preset == "macos_personal_voice":
            preset = "macos_say"
        macos_custom = self.macos_tts_voice_combobox.currentData() == "__custom__"
        for widget in getattr(self, "local_tts_custom_endpoint_widgets", []):
            widget.setVisible(is_local and preset == "custom")
        for widget in getattr(self, "local_tts_macos_widgets", []):
            widget.setVisible(is_local and preset == "macos_say")
        for widget in getattr(self, "local_tts_macos_custom_widgets", []):
            widget.setVisible(is_local and ((preset == "macos_say" and macos_custom) or preset == "custom"))
        for widget in getattr(self, "local_tts_kokoro_widgets", []):
            widget.setVisible(is_local and preset == "kokoro")

    def selected_macos_tts_voice(self):
        voice = self.macos_tts_voice_combobox.currentData()
        if voice == "__custom__":
            return self.macos_tts_custom_voice_input.text().strip()
        return voice or ""

    def selected_kokoro_tts_voice(self):
        return self.kokoro_tts_voice_combobox.currentData() or "af_heart"

    def auto_host_settings(self):
        auto_host = self._saved_auto_host.copy()
        auto_host['enabled'] = bool(self.auto_host_combobox.currentData())
        auto_host['ai_provider'] = self.auto_host_provider_combobox.currentData()
        auto_host['judge_provider'] = self.judge_provider_combobox.currentData() or 'local_binary'
        auto_host['kev_base_url'] = self.kev_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['kev_base_url']
        auto_host['kev_model'] = self.kev_model_input.text().strip() or DEFAULT_CONFIG['auto_host']['kev_model']
        auto_host['openai_api_key'] = self.openai_api_key_input.text().strip()
        auto_host['tts_voice'] = self.auto_host_voice_combobox.currentData() or 'coral'
        auto_host['local_llm_base_url'] = self.local_llm_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_llm_base_url']
        auto_host['local_llm_model'] = self.local_llm_model_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_llm_model']
        auto_host['local_stt_base_url'] = self.local_stt_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_stt_base_url']
        auto_host['local_stt_model'] = self.local_stt_model_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_stt_model']
        tts_preset = self.local_tts_preset_combobox.currentData() or 'macos_say'
        if tts_preset == 'macos_personal_voice':
            tts_preset = 'macos_say'
        auto_host['local_tts_preset'] = tts_preset
        if tts_preset == 'macos_say':
            auto_host['local_tts_base_url'] = self.local_tts_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_tts_base_url']
            auto_host['local_tts_model'] = 'macos-say'
            auto_host['local_tts_voice'] = self.selected_macos_tts_voice()
        elif tts_preset == 'kokoro':
            auto_host['local_tts_base_url'] = self.local_tts_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_tts_base_url']
            auto_host['local_tts_model'] = 'kokoro'
            auto_host['local_tts_voice'] = self.selected_kokoro_tts_voice()
        else:
            auto_host['local_tts_base_url'] = self.local_tts_url_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_tts_base_url']
            auto_host['local_tts_model'] = self.local_tts_model_input.text().strip() or DEFAULT_CONFIG['auto_host']['local_tts_model']
            auto_host['local_tts_voice'] = self.macos_tts_custom_voice_input.text().strip()
        auto_host['selection_mode'] = 'voice_with_gui_fallback'
        auto_host['answer_judging'] = 'auto_with_challenge'
        auto_host['leniency'] = self.auto_host_leniency_combobox.currentText()

        return auto_host

    def save_settings(self, close=True):
        logging.info("save_settings method called")  # Debugging line
        if self.service_manager.busy:
            self.settings_feedback.setText("Wait for the service command to finish before saving.")
            return
        if not self.earlybuzztimeout_combobox.hasAcceptableInput():
            self.settings_feedback.setText("Buzzer timeout must be a number from 0 to 10000 ms.")
            self.tabs.setCurrentIndex(0)
            self.earlybuzztimeout_combobox.setFocus()
            return
        team_error = self.team_panel.validation_error()
        if team_error:
            self.settings_feedback.setText(team_error)
            self.tabs.setCurrentIndex(self.team_tab_index)
            return
        requires_restart = False
        team_mode = self.team_panel.enabled.isChecked()
        if team_mode != self.team_panel._saved:
            requires_restart = True

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
        allownegative = self.allownegative_combobox.currentData()

        # Show allow negative in final setting
        allownegativeinfinal = self.allownegativeinfinal_combobox.currentData()

        # Use Wayback Machine first setting
        use_wayback_first = bool(self.wayback_combobox.currentData())

        auto_host = self.auto_host_settings()
        if auto_host['enabled'] != bool(config.get('auto_host', {}).get('enabled')):
            requires_restart = True

        image_fallback = config.get('image_fallback', DEFAULT_CONFIG['image_fallback']).copy()
        image_fallback['use_pexels'] = self.use_pexels_checkbox.isChecked()
        image_fallback['pexels_api_key'] = self.pexels_api_key_input.text().strip()

        if not self.team_panel.apply():
            self.settings_feedback.setText('Could not save team setup. Check your teams and try again.')
            self.tabs.setCurrentIndex(self.team_tab_index)
            return

        # Save config
        logging.info("Saving settings...")
        config.update({
                'team_mode': team_mode,
                'theme': theme,
                'showtextwithimages': showtextwithimages,
                'earlybuzztimeout': earlybuzztimeout,
                'allownegative': allownegative,
                'allownegativeinfinal': allownegativeinfinal,
                'use_wayback_first': use_wayback_first,
                'mute_sound': config.get('mute_sound', DEFAULT_CONFIG['mute_sound']),
                'image_fallback': image_fallback,
                'auto_host': auto_host,
            })
        with open(config_path, 'w') as f:
            json.dump(config, f)

        try:
            self.parent().game.config = config
            self.parent().game.config.update({
                'team_mode': team_mode,
                'theme': theme,
                'showtextwithimages': showtextwithimages,
                'earlybuzztimeout': earlybuzztimeout,
                'allownegative': allownegative,
                'allownegativeinfinal': allownegativeinfinal,
                'use_wayback_first': use_wayback_first,
                'mute_sound': config.get('mute_sound', DEFAULT_CONFIG['mute_sound']),
                'image_fallback': image_fallback,
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
            arguments = sys.argv[1:] if getattr(sys, 'frozen', False) else sys.argv
            os.execv(sys.executable, [sys.executable] + arguments)
        self._saved_auto_host = auto_host.copy()
        self.service_manager.configure(auto_host)
        self.settings_feedback.setText("Settings saved.")
        if close:
            self.accept()
