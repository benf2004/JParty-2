from PyQt6.QtGui import (
    QPainter,
    QPixmap,
    QImage,
    QPalette,
    QColor,
    QIcon,
    QFont,
    QFontDatabase
)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QPushButton
from PyQt6.QtCore import Qt, QSize, QPoint, QTimer

import time
from threading import Thread
from base64 import urlsafe_b64decode
from functools import partial

from jparty.style import MyLabel
from jparty.utils import resource_path, add_shadow
from jparty.constants import DEFAULT_CONFIG
from jparty.teams import Team, member_name


class NameLabel(MyLabel):
    name_aspect_ratio = 1.3422

    def __init__(self, name, parent, height=None):
        self.signature = None
        super().__init__("", self.startNameFontSize, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self._name = None
        self.set_name(name)
        self.setGraphicsEffect(None)
        self.setAutosizeMargins(0.05)
        if height is not None:
            self.setFixedHeight(height)

    def set_name(self, name):
        if name == self._name:
            return
        self._name = name
        self.signature = None
        self.clear()
        if name.startswith("data:image/png;base64,"):
            i = QImage()
            i.loadFromData(urlsafe_b64decode(name[22:]), "PNG")
            self.signature = QPixmap.fromImage(i)
            self.resizeEvent(None)
        else:
            self.setText(name)

    def startNameFontSize(self):
        return self.height() * 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.signature is not None and not self.signature.isNull():
            self.setPixmap(
                self.signature.scaled(
                    self.width(), self.height(),
                    aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                    transformMode=Qt.TransformationMode.SmoothTransformation,
                )
            )


class PlayerWidget(QWidget):
    aspect_ratio = 0.732
    margin = 0.05

    def __init__(self, game, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.game = game
        self.__buzz_hint_thread = None
        self.__flash_thread = None
        self.__light_thread = None
        self.__timeout_thread = None
        self.buzz_delay = None # Holds stats for buzz delay

        self.name_label = NameLabel(player.name, self)
        self.team_caption = MyLabel(player.name, lambda: self.height() * 0.045, self)
        self.team_caption.setTextFormat(Qt.TextFormat.PlainText)
        self.team_caption.setVisible(isinstance(player, Team) and bool(player.signature))
        self.member_signature = NameLabel('', self)
        self.member_signature.setVisible(isinstance(player, Team))
        self.member_label = MyLabel("", lambda: self.height() * 0.06, self)
        self.member_label.setWordWrap(True)
        self.member_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.member_label.setVisible(isinstance(player, Team))
        self.score_label = MyLabel("$0", self.startScoreFontSize, self)
        self.score_label.setFont(QFont(QFontDatabase.applicationFontFamilies(0)))
        self.stats_label = MyLabel("", self.height() * 0.8, self)
        self.dummy_stats_label = MyLabel("", self.height() * 0.8, self)

        if self.parent().parent().parent().host():
            self.dummy_stats_label.setVisible(False)
        else:
            self.stats_label.setVisible(False)

        add_shadow(self.stats_label, 10, 0)

        # self.resizeEvent(None)
        self.update_score()

        self.setMouseTracking(True)

        self.main_background = QPixmap(resource_path("player.png"))
        self.active_background = QPixmap(resource_path("player_active.png"))
        self.timeout_background = QPixmap(resource_path("player_timed_out.png"))
        self.lights_backgrounds = [
            QPixmap(resource_path(f"player_lights{i}.png")) for i in range(1, 6)
        ]
        self.background = self.main_background

        self.highlighted = False

        layout = QVBoxLayout()
        layout.addStretch(6)
        layout.addWidget(self.score_label, 10)
        layout.addStretch(15)
        if isinstance(player, Team):
            layout.addWidget(self.team_caption, 6)
            layout.addWidget(self.name_label, 24)
            layout.addWidget(self.member_label, 7)
            layout.addWidget(self.member_signature, 15)
            self.refresh_team_label()
        else:
            layout.addWidget(self.name_label, 40)
        layout.addWidget(self.stats_label, 10)
        layout.addWidget(self.dummy_stats_label, 10)
        layout.addStretch(2)

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Expanding)
        self.setLayout(layout)

        self.show()

    def sizeHint(self):
        h = self.height()
        return QSize(int(h * PlayerWidget.aspect_ratio), h)

    def minimumSizeHint(self):
        return QSize()

    def startScoreFontSize(self):
        return self.height() * 0.2

    def resizeEvent(self, event):
        m = int(PlayerWidget.margin * self.width())
        self.setContentsMargins(m, 0, m, 0)

    def set_lights(self, val):
        self.background = self.active_background if val else self.main_background
        self.update()

    def __buzz_hint(self):
        self.set_lights(True)
        time.sleep(0.25)
        self.set_lights(False)

    def buzz_hint(self):
        self.__buzz_hint_thread = Thread(target=self.__buzz_hint, name="buzz_hint")
        self.__buzz_hint_thread.start()

    def update_score(self):
        score = self.player.score
        palette = self.score_label.palette()
        if score < 0:
            palette.setColor(QPalette.ColorRole.WindowText, QColor("red"))
        else:
            palette.setColor(QPalette.ColorRole.WindowText, QColor("white"))
        self.score_label.setPalette(palette)

        self.score_label.setText(f"{'-$' if score < 0 else '$'}{abs(score):,}")

    def refresh_team_label(self):
        if not isinstance(self.player, Team):
            return
        self.name_label.set_name(self.player.signature or self.player.name)
        self.team_caption.setText(self.player.name)
        answering = self.game.answering_player
        if answering in self.player.members:
            text = "Answering: " + member_name(answering)
            self.member_signature.set_name(answering.name)
        else:
            text = "Representative: " + member_name(self.player.representative)
            self.member_signature.set_name('')
        self.member_label.setText(text)
        self.update_score()

    def update_stats(self, delay, timing="early", player=None):
        player = player or self.player
        if getattr(player, "_display_buzz_delay", None) is not None or not self.parent().parent().parent().host():
            return
        player._display_buzz_delay = delay
        self.buzz_delay = delay
        if timing == "early":
            self.stats_label.setText('{0:.2f}s early'.format(self.buzz_delay))
        elif timing == "late":
            self.stats_label.setText('{0:.2f}s late'.format(self.buzz_delay))
        else:
            self.stats_label.setText('{0:.2f}s first buzz'.format(self.buzz_delay))
        
        # Log stats for aggregation
        player.buzz_delays.append({
            "delay": self.buzz_delay,
            "timing": timing
        })
    
    def clear_stats(self):
        self.buzz_delay = None
        members = self.player.members if isinstance(self.player, Team) else [self.player]
        for player in members:
            player.buzz_time = None
            player._display_buzz_delay = None
        self.stats_label.setText('')

    def run_lights(self):
        self.__light_thread = Thread(target=self.__lights, name="lights")
        self.__light_thread.start()

    def stop_lights(self):
        self.__light_thread = None
        self.set_lights(False)
        self.update()

    def __lights(self):
        for img in self.lights_backgrounds:
            self.background = img
            self.update()
            time.sleep(1.0)
            if self.__light_thread is None:  # provide stopability
                return None

        self.set_lights(True)
        self.update()
    
    def run_timeout_lights(self, player=None):
        player = player or self.player
        player.istimedout = True
        self.__timeout_thread = Thread(target=self.__timeout_lights, args=(player,), name="timeout_lights")
        self.__timeout_thread.start()
    
    def __timeout_lights(self, player):
        if not isinstance(self.player, Team):
            self.background = self.timeout_background
            self.update()
        time.sleep(self.game.config.get('earlybuzztimeout', DEFAULT_CONFIG['earlybuzztimeout']) / 1000)
        player.istimedout = False
        if not isinstance(self.player, Team):
            self.set_lights(False)
            self.update()

    def mousePressEvent(self, event):
        if self.game.soliciting_player:
            self.game.get_dd_wager(self.player)
            return None

        self.game.adjust_score(self.player)

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.drawPixmap(self.rect(), self.background)
        qp.end()

    def leaveEvent(self, event):
        if self.game.soliciting_player:
            self.set_lights(False)

    def enterEvent(self, event):
        if self.game.soliciting_player:
            self.set_lights(True)


class HostPlayerWidget(PlayerWidget):
    def __init__(self, game, player, parent=None):
        self.remove_button = None
        super().__init__(game, player, parent)
        self.remove_button = QPushButton("", self)
        # self.remove_button.setStyleSheet("color: red")
        if isinstance(player, Team):
            self.remove_button.clicked.connect(self.show_roster)
            self.remove_button.setToolTip("Manage team members")
        else:
            self.remove_button.clicked.connect(partial(self.game.remove_player, player))
        if isinstance(player, Team):
            self.remove_button.setText("…")
        else:
            self.remove_button.setIcon(QIcon(resource_path("close-icon.png")))
        self.remove_button.show()

    def show_roster(self):
        from jparty.team_widgets import TeamRosterDialog
        TeamRosterDialog(self.game, self).exec()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.remove_button is not None:
            self.remove_button.move(QPoint(0, 0))
            xbutton_size = int(self.width() * 0.2)
            self.remove_button.resize(QSize(xbutton_size, xbutton_size))
            self.remove_button.setIconSize(self.size())


class ScoreBoard(QWidget):
    def __init__(self, game, parent=None):
        super().__init__(parent)

        self.game = game

        self.player_widgets = []

        self.player_layout = QHBoxLayout()
        self.player_layout.addStretch()
        self.setLayout(self.player_layout)
        self.__podium_pixmap = QPixmap(resource_path("podium.png"))
        self.show()

    def minimumHeight(self):
        return 0.2 * self.width()

    def refresh_players(self):
        for pw in list(self.player_widgets):  # copy list so we can remove elements
            if pw.player not in self.game.contestants():
                i = self.player_layout.indexOf(pw)
                self.player_layout.takeAt(i + 1)  # remove stretch
                self.player_layout.takeAt(i)
                self.player_widgets.remove(pw)
                pw.deleteLater()

        for (i, p) in enumerate(self.game.contestants()):
            if not any(pw.player is p for pw in self.player_widgets):
                pw = self.create_player_widget(p)
                self.player_layout.insertWidget(2 * i + 1, pw)
                self.player_layout.insertStretch(2 * i + 2)
                self.player_widgets.append(pw)

        for pw in self.player_widgets:
            pw.refresh_team_label()
        self.size_team_podiums()
        QTimer.singleShot(0, self.size_team_podiums)
        self.update()

    def size_team_podiums(self):
        teams = [pw for pw in self.player_widgets if isinstance(pw.player, Team)]
        if not teams:
            return
        margins = self.player_layout.contentsMargins()
        height = max(1, self.height() - margins.top() - margins.bottom())
        available = max(1, self.width() - margins.left() - margins.right()
                        - max(0, self.player_layout.spacing()) * 2 * len(teams))
        width = max(1, int(min(height * PlayerWidget.aspect_ratio, available / len(teams))))
        for pw in teams:
            pw.setFixedWidth(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.size_team_podiums()

    def create_player_widget(self, player):
        return PlayerWidget(self.game, player, self)

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.drawPixmap(self.rect(), self.__podium_pixmap)
        qp.end()


class HostScoreBoard(ScoreBoard):
    def create_player_widget(self, player):
        return HostPlayerWidget(self.game, player, self)

    def hide_close_buttons(self):
        for pw in self.player_widgets:
            pw.remove_button.setVisible(isinstance(pw.player, Team))
            pw.remove_button.setEnabled(isinstance(pw.player, Team))
    
    def show_close_buttons(self):
        for pw in self.player_widgets:
            pw.remove_button.setVisible(True)
            pw.remove_button.setEnabled(True)
