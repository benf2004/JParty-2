from PyQt6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QFont,
    QPixmap,
    QFontDatabase
)
import requests
import re
import logging
import json
import sys, os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import Qt

from jparty.style import MyLabel, CARDPAL, board_text_color
from jparty.constants import DEFAULT_CONFIG, VIDEO_PLAY_TIME
from jparty.utils import get_base_path
from jparty.paths import config_path
import threading
import time
from urllib.parse import urlparse, parse_qs
from html import escape

class QuestionWidget(QWidget):
    def __init__(self, question, parent=None):
        super().__init__(parent)
        self.question = question
        self.setAutoFillBackground(True)
        self.main_layout = QVBoxLayout()

        # Read the config.json file
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Question text
        self.question_label = MyLabel(question.text.upper(), self.startFontSize, self)
        self.question_label.setFont(QFont(QFontDatabase.applicationFontFamilies(1)))
        self.main_layout.addWidget(self.question_label)
        self.main_layout.setContentsMargins(0, 50, 0, 50)
        self.corner_category_label = MyLabel(
            f"{question.category} - {question.value}".upper(),
            lambda: self.height() * 0.032,
            self,
        )
        self.corner_category_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        self.corner_category_label.setWordWrap(False)
        self.corner_category_label.setStyleSheet(f"color: {board_text_color.name()}")
        self.position_category_label()

        if question.video_link is not None:
            logging.info(f"Question has video, loading video: {question.video_link}")
            self.load_video(parent, question)

        else:
            if question.image_link is not None:
                logging.info(f"Question has image: {question.image_link}")
                if question.image_content is None:
                    self.load_image_content(question)
                
                logging.info(f"Question has image content: {question.image_content}")
                if question.image_content is not None and b"html" in question.image_content.lower():
                    question.image_content = None

                disable_images = self.config.get('showtextwithimages', DEFAULT_CONFIG['showtextwithimages']) == 'Only show text'

                if not disable_images and question.image_content is not None and b"Not Found" not in question.image_content:
                    self.image = QPixmap()
                    self.image.loadFromData(question.image_content)
                    
                    if self.config.get('showtextwithimages', DEFAULT_CONFIG['showtextwithimages']) == 'Show both':
                        # Show both text and image
                        self.image = self.image.scaledToHeight(self.height() * 12)

                        # Create a QLabel for the image
                        self.image_label = MyLabel("", self.startFontSize, self)
                        self.image_label.setPixmap(self.image)
                        self.main_layout.addWidget(self.image_label)
                    elif self.config.get('showtextwithimages', DEFAULT_CONFIG['showtextwithimages']) == 'Only show image':
                        # Show image only
                        self.image = self.image.scaledToWidth(self.width() * 12)
                        self.question_label.setPixmap(self.image)

            if question.audio_link is not None and parent and hasattr(parent, "host") and parent.host():
                logging.info(f"Question has audio, loading audio: {question.audio_link}")
                self.load_audio(parent, question)

        self.setLayout(self.main_layout)

        self.setPalette(CARDPAL)
        self.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_category_label()

    def position_category_label(self):
        if not hasattr(self, "corner_category_label") or self.corner_category_label is None:
            return
        margin = max(12, int(self.width() * 0.018))
        label_width = max(180, int(self.width() * 0.38))
        label_height = max(28, int(self.height() * 0.07))
        self.corner_category_label.setGeometry(
            self.width() - label_width - margin,
            self.height() - label_height - margin,
            label_width,
            label_height,
        )
        self.corner_category_label.raise_()

    def is_remote_link(self, link):
        return isinstance(link, str) and link.lower().startswith(("http://", "https://"))

    def load_image_content(self, question):
        try:
            if self.is_remote_link(question.image_link):
                request = requests.get(question.image_link, timeout=1)
                question.image_content = request.content
            else:
                with open(question.image_link, "rb") as image_file:
                    question.image_content = image_file.read()
            logging.info(f"Loaded image: {question.image_link}")
        except (OSError, requests.exceptions.RequestException):
            logging.info(f"Failed to load image: {question.image_link}", exc_info=True)

    def local_or_remote_media_url(self, link):
        if self.is_remote_link(link):
            return link
        return QUrl.fromLocalFile(os.path.abspath(link)).toString()

    def load_direct_media(self, parent, question, link, media_type, audio_only=False):
        try:
            self.web_view = QWebEngineView()
            media_url = self.local_or_remote_media_url(link)
            if media_type == "audio":
                media_element = f'<audio id="local-media" src="{escape(media_url)}" controls></audio>'
            else:
                media_element = f'<video id="local-media" src="{escape(media_url)}" controls autoplay muted></video>'

            html = f"""
            <!doctype html>
            <html>
              <head>
                <style>
                  html, body {{
                    width: 100%;
                    height: 100%;
                    margin: 0;
                    overflow: hidden;
                    background: #000;
                  }}
                  body {{
                    display: flex;
                    align-items: center;
                    justify-content: center;
                  }}
                  video, audio {{
                    width: 100%;
                    max-height: 100%;
                  }}
                </style>
              </head>
              <body>
                {media_element}
                <script>
                  function startVideo() {{
                    const media = document.getElementById("local-media");
                    if (media) {{
                      media.muted = false;
                      media.play();
                    }}
                  }}
                </script>
              </body>
            </html>
            """
            self.web_view.setHtml(html, QUrl.fromLocalFile(os.path.dirname(os.path.abspath(link)) if not self.is_remote_link(link) else os.getcwd()))
            self.web_view.page().settings().setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            self.web_view.page().settings().setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
            )

            is_host = bool(parent and hasattr(parent, "host") and parent.host())
            if audio_only or is_host:
                self.web_view.setFixedHeight(self.height() * 5)
                self.web_view.setFixedWidth(self.width() * 3)
            else:
                self.web_view.setFixedHeight(self.height() * 12)
                self.web_view.setFixedWidth(self.width() * 7)

            self.main_layout.addSpacing(self.main_layout.contentsMargins().top())
            self.main_layout.addWidget(self.web_view, alignment=Qt.AlignmentFlag.AlignCenter)
        except Exception:
            logging.info(f"Failed to load direct {media_type}: {link}", exc_info=True)

    def load_audio(self, parent, question):
        question.includes_audio = True
        self.load_direct_media(parent, question, question.audio_link, "audio", audio_only=True)

    def load_video(self, parent, question):
        try:
            # --- Parse YouTube URL variants robustly ---
            video_url = None
            video_length = VIDEO_PLAY_TIME
            audio_only = False

            u = urlparse(question.video_link)
            host = (u.hostname or "").lower()
            qs = parse_qs(u.query or "")

            yt_id = None
            # youtu.be/VIDEOID
            if "youtu.be" in host and u.path:
                yt_id = u.path.strip("/")

            # youtube.com/watch?v=VIDEOID
            if (yt_id is None) and ("youtube.com" in host):
                yt_id = (qs.get("v") or [None])[0]

            # Build video.html URL if we have an ID
            if yt_id:
                parts = [f"video.html?v={yt_id}"]

                # start time (?t=123) — only accept pure digits
                t_val = (qs.get("t") or [None])[0]
                if t_val and t_val.isdigit():
                    parts.append(f"t={t_val}")

                # configured play length (?l=123)
                l_val = (qs.get("l") or [None])[0]
                if l_val and l_val.isdigit():
                    video_length = int(l_val)

                # audio-only flag (?a=1)
                a_val = (qs.get("a") or [None])[0]
                if a_val == "1":
                    audio_only = True
                    question.includes_audio = True
                    parts.append("a=1")

                video_url = "&".join(parts)

            if video_url:
                is_host = bool(parent and hasattr(parent, "host") and parent.host())
                if not audio_only or (audio_only and is_host):
                    # Embed youtube clip video
                    self.web_view = QWebEngineView()
                    url = f"http://localhost:8081/{video_url}"
                    logging.info(f"loading url: {url}")
                    self.web_view.load(QUrl(url))
                    self.web_view.page().settings().setAttribute(
                        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
                    )
                    self.web_view.page().settings().setAttribute(
                        QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
                    )

                    if audio_only or is_host:
                        self.web_view.setFixedHeight(self.height() * 5)
                        self.web_view.setFixedWidth(self.width() * 3)
                    else:
                        self.web_view.setFixedHeight(self.height() * 12)
                        self.web_view.setFixedWidth(self.width() * 7)

                    self.main_layout.addSpacing(self.main_layout.contentsMargins().top())
                    self.main_layout.addWidget(self.web_view, alignment=Qt.AlignmentFlag.AlignCenter)

                    if not audio_only:
                        def end_video(main_layout, web_view, video_length):
                            time.sleep(video_length)
                            self.hide_video()

                        thread = threading.Thread(target=end_video, args=(self.main_layout, self.web_view, video_length,))
                        thread.start()
            else:
                self.load_direct_media(parent, question, question.video_link, "video")
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logging.info(f"error: {exc_type}, {fname}:{exc_tb.tb_lineno}")
    
    def play_video(self):
        if hasattr(self, 'web_view'):
            self.web_view.page().runJavaScript("startVideo();")
            print("Starting video via JavaScript")

    def hide_video(self):
        if hasattr(self, 'web_view'):
            self.main_layout.removeWidget(self.web_view)
            self.web_view.deleteLater()
            del self.web_view

    def startFontSize(self):
        return self.width() * 0.05


class HostQuestionWidget(QuestionWidget):
    def __init__(self, question, parent=None):
        super().__init__(question, parent)

        self.question_label.setText(question.text)
        self.main_layout.setStretchFactor(self.question_label, 6)
        self.main_layout.addSpacing(self.main_layout.contentsMargins().top())
        self.answer_label = MyLabel(question.answer, self.startFontSize, self)
        self.answer_label.setFont(QFont(QFontDatabase.applicationFontFamilies(1)))
        self.main_layout.addWidget(self.answer_label, 1)

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.setPen(QPen(QColor("white")))
        line_y = self.main_layout.itemAt(1).geometry().top()
        qp.drawLine(0, line_y, self.width(), line_y)


class DailyDoubleWidget(QuestionWidget):
    def __init__(self, question, parent=None):
        super().__init__(question, parent)
        self.question_label.setVisible(False)
        if hasattr(self, 'image_label'):
            self.image_label.setVisible(False)

        self.dd_label = MyLabel("DAILY<br/>DOUBLE!", self.startDDFontSize, self)
        self.main_layout.replaceWidget(self.question_label, self.dd_label)

    def startDDFontSize(self):
        return self.width() * 0.2

    def show_question(self):
        self.main_layout.replaceWidget(self.dd_label, self.question_label)
        self.dd_label.deleteLater()
        self.dd_label = None
        self.question_label.setVisible(True)
        if hasattr(self, 'image_label'):
            self.image_label.setVisible(True)


class HostDailyDoubleWidget(HostQuestionWidget, DailyDoubleWidget):
    def __init__(self, question, parent=None):
        super().__init__(question, parent)
        self.answer_label.setVisible(False)

        self.main_layout.setStretchFactor(self.dd_label, 6)
        self.hint_label = MyLabel(
            "Click the player below who found the Daily Double",
            self.startFontSize,
            self,
        )
        self.main_layout.replaceWidget(self.answer_label, self.hint_label)
        self.main_layout.setStretchFactor(self.hint_label, 1)

    def show_question(self):
        super().show_question()
        self.main_layout.replaceWidget(self.hint_label, self.answer_label)
        self.hint_label.deleteLater()
        self.hint_label = None
        self.answer_label.setVisible(True)


class FinalJeopardyWidget(QuestionWidget):
    def __init__(self, question, parent=None):
        super().__init__(question, parent)
        self.question_label.setVisible(False)
        if hasattr(self, "corner_category_label"):
            self.corner_category_label.setVisible(False)

        self.category_label = MyLabel(
            question.category, self.startCategoryFontSize, self
        )
        self.main_layout.replaceWidget(self.question_label, self.category_label)

    def startCategoryFontSize(self):
        return self.width() * 0.1

    def show_question(self):
        self.main_layout.replaceWidget(self.category_label, self.question_label)
        self.category_label.deleteLater()
        self.category_label = None
        self.question_label.setVisible(True)


class HostFinalJeopardyWidget(FinalJeopardyWidget, HostQuestionWidget):
    def __init__(self, question, parent):
        super().__init__(question, parent)
        self.answer_label.setVisible(False)

        self.main_layout.setStretchFactor(self.question_label, 6)
        self.hint_label = MyLabel(
            "Waiting for all players to wager...", self.startFontSize, self
        )
        self.main_layout.replaceWidget(self.answer_label, self.hint_label)
        self.main_layout.setStretchFactor(self.hint_label, 1)

    def hide_hint(self):
        self.hint_label.setVisible(True)

    def show_question(self):
        super().show_question()
        self.main_layout.replaceWidget(self.hint_label, self.answer_label)
        self.hint_label.deleteLater()
        self.hint_label = None
        self.answer_label.setVisible(True)
