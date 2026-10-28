"""Team settings and live roster controls for the host."""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)
from jparty.teams import member_name
from jparty.settings_widgets import settings_card


TEAM_COLORS = ['#4361ee', '#0d9488', '#c24163', '#b87916',
               '#8055c7', '#247ca5', '#ca6636', '#568231']
TEAM_TINTS = ['#eef1ff', '#e8f7f3', '#fceef2', '#fff5df',
              '#f3edfc', '#eaf5fc', '#fff1e8', '#f0f6e8']


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def card(name='teamCard'):
    widget = QFrame()
    widget.setObjectName(name)
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return widget, layout


TEAM_STYLE = """
    QWidget#TeamSettingsPanel, QDialog#TeamRoster { color: #243047; font-size: 13px; }
    QFrame#teamHero { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #172c59, stop:1 #294b91); border: none; border-radius: 14px; }
    QLabel#heroEyebrow { color: #a8c3ff; font-size: 10px; font-weight: 700; }
    QLabel#heroTitle { color: white; font-size: 28px; font-weight: 700; }
    QLabel#heroDescription { color: #d6e3ff; font-size: 13px; }
    QLabel#heroChip { background: #35558c; color: white; padding: 5px 10px;
        border-radius: 11px; font-size: 11px; font-weight: 600; }
    QFrame#teamCard { background: white; border: 1px solid #dce3ef; border-radius: 12px; }
    QLabel#sectionTitle { font-size: 15px; font-weight: 700; color: #182b4d; }
    QLabel#teamMuted { color: #6b7890; font-size: 12px; }
    QLabel#teamStatus { color: #3561ba; font-size: 12px; font-weight: 600; }
    QLineEdit { background: #f8faff; border: 1px solid #dce3ef; border-radius: 7px;
        padding: 8px 10px; color: #182b4d; font-size: 14px; }
    QLineEdit:focus { border-color: #4361ee; background: white; }
    QLineEdit:disabled { background: #f3f5f9; color: #8994a7; }
    QSpinBox { background: #f4f7fd; border: none; border-radius: 7px;
        color: #182b4d; font-size: 15px; font-weight: 700; padding: 5px; }
    QPushButton#teamStep { padding: 0; background: white; border: 1px solid #dce3ef;
        border-radius: 8px; color: #3657b3; font-size: 20px; }
    QPushButton#teamStep:hover { background: #eef2ff; border-color: #9caeee; }
    QPushButton#teamAction { background: #edf2ff; color: #2854bb; border: 1px solid #dce6ff;
        border-radius: 8px; padding: 9px 13px; font-weight: 600; }
    QPushButton#teamAction:hover { background: #e1eaff; }
    QPushButton#teamRemove { background: white; color: #9e4051; border: 1px solid #efdce0;
        border-radius: 7px; padding: 7px 12px; }
    QPushButton#teamRemove:hover { background: #fff0f2; }
    QPushButton#teamAction:disabled, QPushButton#teamRemove:disabled, QPushButton#teamStep:disabled {
        color: #9ca6b8; background: #f1f3f7; border-color: #e5e9f0; }
    QFrame#memberRow { background: #f7f9fd; border: none; border-radius: 8px; }
    QLabel#memberBadge { color: #315bbb; background: #e8efff; border-radius: 9px;
        padding: 3px 8px; font-size: 10px; font-weight: 600; }
    QDialog#TeamRoster { background: #f3f5fa; }
    QDialog#TeamRoster QScrollArea, QDialog#TeamRoster QScrollArea > QWidget > QWidget {
        background: #f3f5fa; border: none; }
"""


class TeamToggle(QCheckBox):
    """A keyboard-accessible checkbox painted as a switch."""
    def sizeHint(self):
        return QSize(46, 28)

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = '#4361ee' if self.isChecked() else '#bdc7d8'
        if not self.isEnabled():
            color = '#dce2ed'
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(2, 3, 42, 24, 12, 12)
        painter.setBrush(QColor('white'))
        painter.drawEllipse(24 if self.isChecked() else 5, 6, 18, 18)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor('#7997fa'))
            painter.drawRoundedRect(0, 1, 45, 26, 13, 13)


class TeamSettingsPanel(QWidget):
    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game
        self.setObjectName('TeamSettingsPanel')
        self._saved = bool(game and game.team_mode)
        body = QVBoxLayout(self)
        body.setContentsMargins(22, 22, 22, 22)
        body.setSpacing(16)
        body.addWidget(label('Team mode', 'pageTitle'))
        subtitle = label('Everyone gets a buzzer. Your team shares the score.')
        subtitle.setProperty('muted', True)
        body.addWidget(subtitle)

        mode, layout = settings_card('Play as teams')
        row = QHBoxLayout()
        copy = QVBoxLayout()
        copy.addWidget(label('Players choose a team or create their own when they join.', 'settingsMuted'))
        row.addLayout(copy, 1)
        self.mode_status = label('', 'settingsStatus')
        row.addWidget(self.mode_status)
        self.enabled = TeamToggle()
        self.enabled.setFixedSize(self.enabled.sizeHint())
        self.enabled.setAccessibleName('Enable team mode')
        self.enabled.setChecked(self._saved)
        row.addWidget(self.enabled)
        layout.addLayout(row)
        self.lock_notice = label('', 'settingsMuted')
        layout.addWidget(self.lock_notice)
        body.addWidget(mode)

        flow, layout = settings_card('Made by your players')
        layout.addWidget(label('1. Everyone types their own name and signs in on their phone.\n'
                               '2. A team’s first player types and draws its name. Teammates choose it from the list.\n'
                               '3. When someone buzzes, their own signature appears below the team name.', 'settingsMuted'))
        layout.addWidget(label('2–8 teams can play. At least two teams need players before starting.', 'settingsMuted'))
        body.addWidget(flow)

        roster, layout = settings_card('Your players')
        row = QHBoxLayout()
        copy = QVBoxLayout()
        self.roster_summary = label('', 'settingsMuted')
        copy.addWidget(self.roster_summary)
        row.addLayout(copy, 1)
        self.roster_button = QPushButton('Manage players  →')
        self.roster_button.setObjectName('teamAction')
        self.roster_button.clicked.connect(self.show_roster)
        row.addWidget(self.roster_button)
        layout.addLayout(row)
        layout.addWidget(label('Manage members and recover team controls here. Team names are created on phones.', 'settingsMuted'))
        body.addWidget(roster)
        body.addStretch()
        self.enabled.toggled.connect(self.refresh_controls)
        if game:
            game.teams_changed.connect(self.refresh_controls)
        self.refresh_controls()

    def validation_error(self):
        if self.enabled.isChecked() == self._saved:
            return ''
        if not self.game or self.game.current_round is not None:
            return 'Team mode is locked during play. Return to the lobby to change it.'
        return ''

    def apply(self):
        if self.validation_error():
            return False
        if self.game and self.enabled.isChecked() != self.game.team_mode:
            if not self.game.configure_teams(self.enabled.isChecked()):
                return False
        self._saved = self.enabled.isChecked()
        self.refresh_controls()
        return True

    def refresh_controls(self):
        available = self.game is not None and self.game.current_round is None
        self.enabled.setEnabled(available)
        self.mode_status.setText('Enabled' if self.enabled.isChecked() else 'Off')
        self.roster_button.setEnabled(self.game is not None)
        players = len(self.game.players) if self.game else 0
        teams = len(self.game.contestants()) if self.game and self.game.team_mode else 0
        self.roster_summary.setText(f'{players} players joined · {teams} teams with members')
        self.lock_notice.setText('Saving a mode change restarts JParty. Players will need to join again.'
                                 if available else 'Team mode is locked during play. You can still manage your players.')

    def show_roster(self):
        if self.game:
            TeamRosterDialog(self.game, self).exec()


class TeamRosterDialog(QDialog):
    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game
        self.setObjectName('TeamRoster')
        self.setWindowTitle('Team roster')
        self.resize(640, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(TEAM_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(12)
        heading = label('Your players', 'heroTitle')
        heading.setStyleSheet('color: #182b4d; font-size: 24px; font-weight: 700;')
        layout.addWidget(heading)
        layout.addWidget(label('The latest correct answer decides who acts for each team.\nUse “Act for team” if that person is unavailable.', 'teamMuted'))
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        close = QPushButton('Done')
        close.setObjectName('teamAction')
        close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(close)
        layout.addLayout(footer)
        game.teams_changed.connect(self.refresh)
        self.finished.connect(self.disconnect_updates)
        self.refresh()

    def disconnect_updates(self):
        self.game.teams_changed.disconnect(self.refresh)

    def refresh(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(12)
        groups = [(t.name, t.members) for t in self.game.teams]
        unassigned = [p for p in self.game.players if p.team is None]
        if unassigned:
            groups.append(('Unassigned', unassigned))
        for i, (name, members) in enumerate(groups):
            group, inner = card()
            title = label(f'{name}  ·  {len(members)} {"member" if len(members) == 1 else "members"}', 'sectionTitle')
            title.setStyleSheet(f'color: {TEAM_COLORS[i % len(TEAM_COLORS)]};')
            inner.addWidget(title)
            if not members:
                inner.addWidget(label('Waiting for players to join.', 'teamMuted'))
            for player in members:
                member, _ = card('memberRow')
                row = member.layout()
                row.setContentsMargins(10, 8, 10, 8)
                line = QHBoxLayout()
                line.addWidget(label(member_name(player)), 1)
                if player.team and player.team.representative is player:
                    line.addWidget(label('ACTING', 'memberBadge'))
                if not player.connected:
                    line.addWidget(label('Offline', 'teamMuted'))
                act = QPushButton('Act for team')
                act.setObjectName('teamAction')
                act.setEnabled(player.team is not None and player.connected
                               and player.team.representative is not player)
                act.clicked.connect(lambda checked=False, p=player: self.game.transfer_representative(p))
                line.addWidget(act)
                remove = QPushButton('Remove')
                remove.setObjectName('teamRemove')
                remove.setEnabled(not self.game.team_mode or self.game.can_remove_team_member(player))
                remove.setToolTip('Finish the active answer or Final Jeopardy review before removing its participants.')
                remove.clicked.connect(lambda checked=False, p=player: self.game.remove_player(p))
                line.addWidget(remove)
                row.addLayout(line)
                inner.addWidget(member)
            layout.addWidget(group)
        layout.addStretch()
        old = self.scroll.takeWidget()
        self.scroll.setWidget(content)
        if old:
            old.deleteLater()
