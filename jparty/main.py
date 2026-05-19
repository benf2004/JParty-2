from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtWidgets import QApplication, QMessageBox

import sys
import requests
import logging
import subprocess
import time
import os
import signal
from threading import Thread
try:
    import fcntl
except ImportError:
    fcntl = None
from simpleaudio._simpleaudio import SimpleaudioError


from jparty.game import Game
from jparty.controller import BuzzerController
from jparty.main_display import DisplayWindow, HostDisplayWindow
from jparty.style import JPartyStyle
from jparty.utils import resource_path
from jparty.logger import log
from jparty.constants import PORT
from jparty.paths import user_data_dir

_instance_lock_file = None

def check_single_instance():
    """Ensure only one instance of the main app is running."""
    if fcntl is None:
        return True # Cannot check on this platform
    
    global _instance_lock_file
    lock_path = os.path.join(user_data_dir, "app.lock")
    try:
        logging.info(f"Attempting to acquire lock at {lock_path}")
        _instance_lock_file = open(lock_path, "w")
        # LOCK_EX: exclusive lock, LOCK_NB: non-blocking
        fcntl.lockf(_instance_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        logging.info("Lock acquired successfully.")
        return True
    except (IOError, ImportError) as e:
        logging.warning(f"Could not acquire lock: {e}")
        # If we can't get the lock, another instance is probably running
        return False


def check_internet():
    """check internet connection in a background thread"""
    def _check():
        try:
            # Reduced timeout to 5 seconds for background check
            requests.get("http://www.j-archive.com/", timeout=5)
            logging.info("Internet connection verified.")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            logging.warning("Internet connection check failed. J-Archive features may be unavailable.")
            # We don't show a blocking critical box here anymore to avoid hanging startup.
            # The app will still work for local games.
    
    thread = Thread(target=_check, daemon=True)
    thread.start()


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
    start_time = time.time()
    logging.info("Application main() started")
    
    # Perform single instance check immediately
    if not check_single_instance():
        logging.info("Another instance of JParty is already running. Exiting.")
        sys.exit(0)

    # Initialize QApplication first
    QApplication.setStyle(JPartyStyle())
    app = QApplication(sys.argv)
    logging.info(f"QApplication created in {time.time() - start_time:.2f}s")
    
    # Initialize the exception hook after QApplication
    from jparty.logger import UncaughtHook
    qt_exception_hook = UncaughtHook()
    
    app.setFont(QFont("Verdana"))

    logging.info(f"Loading fonts...")
    i_board = QFontDatabase.addApplicationFont(
        resource_path("board_font.ttf")
    )
    i_question = QFontDatabase.addApplicationFont(
        resource_path("question_font.ttf")
    )
    logging.info(f"Fonts loaded in {time.time() - start_time:.2f}s")

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
    logging.info(f"Game core initialized in {time.time() - start_time:.2f}s")

    socket_controller = BuzzerController(game)
    game.setBuzzerController(socket_controller)

    try:
        socket_controller.start()
        logging.info(f"Socket controller started in {time.time() - start_time:.2f}s")
    except PermissionError as e:
        permission_error()
        exit(1)

    main_window = DisplayWindow(game)
    host_window = HostDisplayWindow(game)
    game.setDisplays(host_window, main_window)
    
    logging.info(f"GUI initialized and windows created in {time.time() - start_time:.2f}s")
    
    # Start the buzzer process after a short delay once the main GUI is visible.
    # This avoids interfering with the initial application launch and dock icon behavior.
    from PyQt6.QtCore import QTimer
    def start_buzzers():
        try:
            if getattr(sys, 'frozen', False):
                env = os.environ.copy()
                env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
                # Use subprocess.Popen but don't wait for it.
                # We store it in the app instance to prevent it from being garbage collected if needed,
                # though Popen objects usually persist.
                app.buzzer_process = subprocess.Popen([sys.executable, "--buzzers"], env=env)
                logging.info("Started buzzer subprocess")
            else:
                base_path = os.path.abspath(".")
                buzzer_script = os.path.join(base_path, "physicalbuzzers", "physicalbuzzers.py")
                if os.path.exists(buzzer_script):
                    app.buzzer_process = subprocess.Popen([sys.executable, buzzer_script])
                    logging.info("Started buzzer subprocess (dev)")
        except Exception as e:
            logging.error(f"Could not start buzzer subprocess: {e}")
    
    QTimer.singleShot(2000, start_buzzers)

    try:
        game.begin()
        check_second_monitor()
        # Non-blocking internet check
        check_internet()
    except SimpleaudioError as e:
        audio_error()
        exit(1)

    song_player = game.song_player



    r=1 # fail by default
    try:
        r = app.exec()
    finally:
        logging.info("terminated")
        if hasattr(app, 'buzzer_process') and app.buzzer_process:
            app.buzzer_process.terminate()
            try:
                app.buzzer_process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                os.kill(app.buzzer_process.pid, signal.SIGKILL)
        
        if song_player:
            song_player.stop()

        sys.exit(r)
