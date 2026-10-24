"""Team settings and live roster controls for the host."""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)
from jparty.teams import member_name


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
        self.setStyleSheet(TEAM_STYLE)
        self._saved = self.current_settings()
        body = QVBoxLayout(self)
        body.setContentsMargins(22, 22, 22, 22)
        body.setSpacing(18)

        hero, hero_layout = card('teamHero')
        hero_layout.setContentsMargins(24, 20, 24, 22)
        hero_layout.setSpacing(8)
        hero_layout.addWidget(label('PLAY TOGETHER', 'heroEyebrow'))
        hero_layout.addWidget(label('Team mode', 'heroTitle'))
        hero_layout.addWidget(label('Everyone gets a buzzer. Your team shares the score.', 'heroDescription'))
        chips = QHBoxLayout()
        chips.setSpacing(8)
        for text in ['2–8 teams', 'Up to 32 players', 'Individual phones']:
            chip = label(text, 'heroChip')
            chips.addWidget(chip)
        chips.addStretch()
        hero_layout.addLayout(chips)
        body.addWidget(hero)

        mode, mode_layout = card()
        row = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(5)
        copy.addWidget(label('Play as teams', 'sectionTitle'))
        copy.addWidget(label('Turn on shared scoring and let players choose a team on their phones.', 'teamMuted'))
        row.addLayout(copy, 1)
        self.mode_status = label('', 'teamStatus')
        row.addWidget(self.mode_status)
        self.enabled = TeamToggle()
        self.enabled.setFixedSize(self.enabled.sizeHint())
        self.enabled.setAccessibleName('Enable team mode')
        self.enabled.setChecked(self._saved[0])
        row.addWidget(self.enabled)
        mode_layout.addLayout(row)
        self.lock_notice = label('', 'teamMuted')
        mode_layout.addWidget(self.lock_notice)
        body.addWidget(mode)

        self.editor, editor_layout = card()
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        titles.addWidget(label('Make it your team', 'sectionTitle'))
        titles.addWidget(label('Choose how many teams will play, then give each one a name.', 'teamMuted'))
        header.addLayout(titles, 1)
        self.minus = QPushButton('−')
        self.plus = QPushButton('+')
        for button, name in [(self.minus, 'Remove a team'), (self.plus, 'Add a team')]:
            button.setObjectName('teamStep')
            button.setAccessibleName(name)
            button.setFixedSize(34, 34)
        self.count = QSpinBox()
        self.count.setRange(2, 8)
        self.count.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count.setFixedWidth(44)
        self.count.setAccessibleName('Number of teams')
        self.count.setValue(len(self._saved[1]))
        self.minus.clicked.connect(self.count.stepDown)
        self.plus.clicked.connect(self.count.stepUp)
        header.addWidget(self.minus)
        header.addWidget(self.count)
        header.addWidget(self.plus)
        editor_layout.addLayout(header)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(14)
        self.names, self.team_rows = [], []
        for i in range(8):
            field = QWidget()
            field_layout = QHBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            badge = label(f'{i+1:02}')
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(34, 36)
            badge.setStyleSheet(f'background: {TEAM_TINTS[i]}; color: {TEAM_COLORS[i]}; border-radius: 8px; font-weight: 700; font-size: 12px;')
            field_layout.addWidget(badge)
            name = QLineEdit(self._saved[1][i] if i < len(self._saved[1]) else f'Team {i+1}')
            name.setMaxLength(40)
            name.setAccessibleName(f'Team {i+1} name')
            name.setPlaceholderText(f'Team {i+1}')
            field_layout.addWidget(name, 1)
            self.grid.addWidget(field, i // 2, i % 2)
            self.names.append(name)
            self.team_rows.append(field)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        editor_layout.addLayout(self.grid)
        body.addWidget(self.editor)

        roster, roster_layout = card()
        roster_row = QHBoxLayout()
        roster_copy = QVBoxLayout()
        roster_copy.setSpacing(5)
        roster_copy.addWidget(label('Your players', 'sectionTitle'))
        self.roster_summary = label('', 'teamMuted')
        roster_copy.addWidget(self.roster_summary)
        roster_row.addLayout(roster_copy, 1)
        self.roster_button = QPushButton('Manage players  →')
        self.roster_button.setObjectName('teamAction')
        self.roster_button.clicked.connect(self.show_roster)
        roster_row.addWidget(self.roster_button)
        roster_layout.addLayout(roster_row)
        self.roster_hint = label('Players join from the game’s QR code and choose their team before play begins.', 'teamMuted')
        roster_layout.addWidget(self.roster_hint)
        body.addWidget(roster)

        rules = label('HOW IT PLAYS\nOne attempt per team, per clue. The last teammate to answer correctly acts for the team. One team wager and answer in Final Jeopardy.', 'teamMuted')
        rules.setContentsMargins(4, 0, 4, 0)
        body.addWidget(rules)
        body.addStretch()
        self.enabled.toggled.connect(self.refresh_controls)
        self.count.valueChanged.connect(self.refresh_controls)
        if game:
            game.teams_changed.connect(self.refresh_controls)
        self.refresh_controls()

    def current_settings(self):
        if self.game:
            return self.game.team_mode, [t.name for t in self.game.teams]
        return False, ['Team 1', 'Team 2']

    def draft(self):
        return self.enabled.isChecked(), [n.text().strip() for n in self.names[:self.count.value()]]

    def validation_error(self):
        if self.draft() == self.current_settings():
            return ''
        if not self.game or self.game.current_round is not None:
            return 'Team setup is locked during play. Return to the lobby to make changes.'
        enabled, names = self.draft()
        if any(not name for name in names):
            return 'Give every team a name before saving.'
        if len(set(names)) != len(names):
            return 'Use a different name for each team.'
        if not enabled and len(self.game.players) > 8:
            return 'Individual mode supports eight players. Remove players before turning team mode off.'
        return ''

    def apply(self):
        if self.validation_error():
            return False
        draft = self.draft()
        if self.game and draft != self.current_settings():
            if not self.game.configure_teams(*draft):
                return False
        self._saved = self.current_settings()
        self.refresh_controls()
        return True

    def refresh_controls(self):
        available = self.game is not None and self.game.current_round is None
        self.enabled.setEnabled(available)
        on = self.enabled.isChecked()
        self.mode_status.setText('Enabled' if on else 'Off')
        self.count.setEnabled(available and on)
        self.minus.setEnabled(available and on and self.count.value() > 2)
        self.plus.setEnabled(available and on and self.count.value() < 8)
        for i, (field, name) in enumerate(zip(self.team_rows, self.names)):
            field.setVisible(i < self.count.value())
            name.setEnabled(available and on)
        self.roster_button.setEnabled(self.game is not None)
        players = len(self.game.players) if self.game else 0
        occupied = len(self.game.contestants()) if self.game and self.game.team_mode else 0
        self.roster_summary.setText(f'{players} {"player" if players == 1 else "players"} joined' +
                                    (f' · {occupied} teams with members' if occupied else ' · Ready when you are'))
        self.lock_notice.setText('Changes apply when you save. At least two teams need players to start.'
                                 if available else 'Team setup is locked during play. You can still manage your players.'
                                 if self.game else 'Open a game lobby to set up teams.')

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
