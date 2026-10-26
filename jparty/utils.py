from functools import lru_cache
import logging
import re
import os
import sys
import json

from PyQt6.QtGui import QColor, QFontMetrics
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt, QSize, QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from jparty.paths import config_path

def get_base_path(file=None):
    if getattr(sys, "frozen", False):
        # PyInstaller creates a temp folder and stores bundled resources in _MEIPASS.
        path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    else:
        path = os.path.dirname(os.path.abspath(__file__))
    if file is None:
        return path
    return os.path.join(path, file)

_cached_theme = None


@lru_cache(maxsize=4)
def audio_assets(base_path):
    try:
        with open(os.path.join(base_path, 'data', 'audio-manifest.json')) as stream:
            return json.load(stream)['files']
    except FileNotFoundError:
        return {}


def resource_path(relative_path):
    global _cached_theme
    base_path = get_base_path()

    # Read the current theme from the configuration file (cached)
    if _cached_theme is None:
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            _cached_theme = str(config.get('theme', 'default')).lower()
        except Exception:
            _cached_theme = 'default'

    for theme in (_cached_theme, 'default'):
        # Keep direct theme overrides working, including legacy WAV recordings.
        resolved_file = os.path.join(base_path, 'data', theme, relative_path)
        if os.path.isfile(resolved_file):
            return resolved_file
        shared = audio_assets(base_path).get(f'{theme}/{relative_path}')
        if shared:
            resolved_file = os.path.join(base_path, 'data', shared)
            if os.path.isfile(resolved_file):
                return resolved_file
    return os.path.join(base_path, 'data', 'default', relative_path)


class SongPlayer(QObject):
    """Stream theme music with Qt; marshal calls from game workers to Qt's thread."""
    _play_requested = pyqtSignal(str, bool)
    _mute_requested = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._muted = False
        self._output = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._output)
        self._player.errorOccurred.connect(self._audio_error)
        self._play_requested.connect(self._play_track)
        self._mute_requested.connect(self._set_muted)

    def set_muted(self, muted):
        self._mute_requested.emit(bool(muted))

    def play(self, repeat=False):
        self._play_requested.emit('intro.wav', bool(repeat))

    def final(self, repeat=False):
        self._play_requested.emit('final.wav', bool(repeat))

    def stop(self):
        self._play_requested.emit('', False)

    @pyqtSlot(bool)
    def _set_muted(self, muted):
        self._muted = muted
        self._output.setMuted(muted)
        if muted:
            self._player.stop()

    @pyqtSlot(str, bool)
    def _play_track(self, name, repeat):
        self._player.stop()
        if not name or self._muted:
            return
        self._player.setLoops(-1 if repeat else 1)
        self._player.setSource(QUrl.fromLocalFile(resource_path(name)))
        self._player.play()

    def _audio_error(self, _error, message):
        logging.warning('Theme music playback failed: %s', message)


class CompoundObject(object):
    def __init__(self, *objs):
        self.__objs = list(objs)

    def __setattr__(self, name, value):
        if name[0] == "_":
            self.__dict__[name] = value
        else:
            for obj in self.__objs:
                setattr(obj, name, value)

    def __getattr__(self, name):
        ret = CompoundObject(*[getattr(obj, name) for obj in self.__objs])
        return ret

    def __iadd__(self, display):
        self.__objs.append(display)
        return self

    def __call__(self, *args, **kwargs):
        return CompoundObject(*[obj(*args, **kwargs) for obj in self.__objs])

    def __repr__(self):
        return "CompoundObject(" + ", ".join([repr(o) for o in self.__objs]) + ")"


"""add shadow to widget. Radius is proportion of widget height"""


def add_shadow(widget, radius=None, offset=3):
    shadow = QGraphicsDropShadowEffect(widget)
    if radius is not None:
        shadow.setBlurRadius(radius)
    else:
        shadow.setBlurRadius(widget.height())
    shadow.setColor(QColor("black"))
    shadow.setOffset(offset)
    widget.setGraphicsEffect(shadow)


class AutosizeWidget(object):
    """This class is a mixin which must be inherited with a QWidget with a `text()` method."""

    def __init__(self, *args, **kwargs):
        self.autosize_margins = (0.0, 0.0, 0.0, 0.0)  # as percentage of size
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.autoresize()

    def sizeHint(self):
        return QSize()

    def minimumSizeHint(self):
        return QSize()

    def heightForWidth(self, w):
        return -1

    def resizeEvent(self, event):
        self.autoresize()

    def autoresize(self):
        if self.size().height() <= 0 or self.text() == "":
            return None

        fontsize = self.autofitsize()
        if fontsize <= 0:
            return None
            
        font = self.font()
        font.setPixelSize(fontsize)
        self.setFont(font)

    def plaintext(self):
        text = self.text()
        text = re.sub("<br>", "\n", text)
        text = re.sub("<[^>]*>", "", text)
        return text

    def setAutosizeMargins(self, *args):
        """
        set the dynamic sizing margins.
        ---
        if 1 arg, set all margins,
        if 2 args, set width and height margins
        if 4 args, set left, top, right and bottom margins
        """
        if len(args) == 1:
            self.autosize_margins = (args[0], args[0], args[0], args[0])
        elif len(args) == 2:
            self.autosize_margins = (args[0], args[1], args[0], args[1])
        elif len(args) == 4:
            self.autosize_margins = (args[0], args[1], args[2], args[3])
        else:
            raise Exception("Need 1, 2, or 4 arguments")

    def autofitsize(self, stepsize=1):

        font = self.font()

        ml, mt, mr, md = self.autosize_margins
        rect = self.rect().adjusted(
            int(self.width() * ml),
            int(self.height() * mt),
            int(-self.width() * mr),
            int(-self.height() * mt),
        )

        text = self.plaintext()

        initial_size = int(self.initialSize())
        if initial_size <= 0:
            return 0
            
        font.setPixelSize(initial_size)
        size = font.pixelSize()

        def fullrect(font):
            fm = QFontMetrics(font)
            return fm.boundingRect(rect, self.flags(), text)

        newrect = fullrect(font)
        if not rect.contains(newrect):
            while size > 2:
                size -= stepsize
                font.setPixelSize(size)
                newrect = fullrect(font)
                if rect.contains(newrect):
                    return font.pixelSize()

        return size


class DynamicLabel(QLabel, AutosizeWidget):
    def __init__(self, text, initialSize, parent=None):
        self.__initialSize = initialSize
        super().__init__(text, parent)

    def flags(self):
        flags = 0
        if self.wordWrap():
            flags |= Qt.TextFlag.TextWordWrap

        flags |= self.alignment()

        return flags

    def resizeEvent(self, event):
        AutosizeWidget.resizeEvent(self, event)

    def setText(self, text):
        super().setText(text)
        self.autoresize()

    def initialSize(self):
        if callable(self.__initialSize):
            return self.__initialSize()
        else:
            return self.__initialSize


class DynamicButton(QPushButton, AutosizeWidget):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)

    def resizeEvent(self, event):
        AutosizeWidget.resizeEvent(self, event)

    def setText(self, text):
        super().setText(text)
        self.autoresize()

    def initialSize(self):
        return self.height() * 0.5

    def flags(self):
        return 0
