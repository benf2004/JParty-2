from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication, QMessageBox

import sys
import requests
import logging
import subprocess
import os
import signal
from simpleaudio._simpleaudio import SimpleaudioError


from jparty.game import Game
from jparty.controller import BuzzerController
from jparty.main_display import DisplayWindow, HostDisplayWindow
from jparty.style import JPartyStyle
from jparty.utils import resource_path
from jparty.logger import qt_exception_hook
from jparty.constants import PORT


def check_internet():
    """check internet connection"""
    try:
        requests.get("http://www.j-archive.com/", timeout=5)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        logging.error("Connection Error")
        QMessageBox.critical(
            None,
            "Cannot connect!",
            "JParty cannot connect to the J-Archive. Please check your internet connection.",
            buttons=QMessageBox.StandardButton.Abort,
            defaultButton=QMessageBox.StandardButton.Abort,
        )
        exit(1)


def permission_error():
    logging.error(f"Cannot access port {PORT}")
    QMessageBox.critical(
        None,
        "Permission Error",
        f"JParty encountered a permissions error when trying to listen on port {PORT}.",
        buttons=QMessageBox.StandardButton.Abort,
        defaultButton=QMessageBox.StandardButton.Abort,
    )

def audio_error():
    logging.error(f"Cannot access audio device")
    QMessageBox.critical(
        None,
        "Audio error Error",
        f"JParty cannot access an audio device.",
        buttons=QMessageBox.StandardButton.Abort,
        defaultButton=QMessageBox.StandardButton.Abort,
    )

def check_second_monitor():
    if len(QApplication.instance().screens()) < 2:
        logging.warning("Only one monitor detected. JParty will open in dual-window mode on a single display.")


def main():

    QApplication.setStyle(JPartyStyle())
    app = QApplication(sys.argv)

    # Start the buzzer process after QApplication is initialized to ensure 
    # the main app registers correctly with the OS first.
    buzzer_process = None
    try:
        if getattr(sys, 'frozen', False):
            # In PyInstaller bundled app, use sys.executable with --buzzers flag
            # Set environment to hide pygame support prompt and ensure it doesn't try to be a GUI app
            env = os.environ.copy()
            env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
            buzzer_process = subprocess.Popen([sys.executable, "--buzzers"], env=env)
            logging.info("Started buzzer subprocess")
        else:
            base_path = os.path.abspath(".")
            buzzer_script = os.path.join(base_path, "physicalbuzzers", "physicalbuzzers.py")
            if os.path.exists(buzzer_script):
                buzzer_process = subprocess.Popen([sys.executable, buzzer_script])
                logging.info("Started buzzer subprocess (dev)")
    except Exception as e:
        logging.error(f"Could not start buzzer subprocess: {e}")

    check_second_monitor()
    check_internet()
    app.setFont(QFont("Verdana"))

    i_board = QFontDatabase.addApplicationFont(
        resource_path("board_font.ttf")
    )
    i_question = QFontDatabase.addApplicationFont(
        resource_path("question_font.ttf")
    )

    font_families = QFontDatabase.applicationFontFamilies(i_board)
    if font_families:
        font_family_name = font_families[0]
        print(f"Loaded board font family name: {font_family_name}")
    else:
        print("Could not retrieve board font family name.")
    
    font_families = QFontDatabase.applicationFontFamilies(i_question)
    if font_families:
        font_family_name = font_families[0]
        print(f"Loaded question font family name: {font_family_name}")
    else:
        print("Could not retrieve question font family name.")

    game = Game()

    socket_controller = BuzzerController(game)

    game.setBuzzerController(socket_controller)

    try:
        socket_controller.start()
    except PermissionError as e:
        permission_error()
        exit(1)

    main_window = DisplayWindow(game)
    host_window = HostDisplayWindow(game)
    game.setDisplays(host_window, main_window)
    
    try:
        game.begin()
    except SimpleaudioError as e:
        audio_error()
        exit(1)

    song_player = game.song_player



    r=1 # fail by default
    try:
        r = app.exec()
    finally:
        logging.info("terminated")
        if buzzer_process:
            buzzer_process.terminate()
            try:
                buzzer_process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                os.kill(buzzer_process.pid, signal.SIGKILL)
        
        if song_player:
            song_player.stop()

        sys.exit(r)
