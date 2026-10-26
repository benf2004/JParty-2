"""Shared lobby/settings update controls; downloads are always an explicit action."""
from PyQt6.QtCore import QTimer, Qt, QObject
from PyQt6 import sip
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar

from jparty.updater import UpdateManager


class UpdatePanel(QWidget):
    def __init__(self, manager, parent=None, compact=False):
        super().__init__(parent)
        self.manager = manager
        self.compact = compact
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        if compact:
            self.setObjectName('updateNotice')
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.setMinimumWidth(420)
            self.setMaximumWidth(680)
            body.setContentsMargins(16, 12, 16, 12)
            self.setStyleSheet("""
                QWidget#updateNotice { background: #eff5ff; border: 1px solid #cbdcff; border-radius: 10px; }
                QLabel { color: #24436e; font-size: 13px; }
                QPushButton { background: #285ee8; color: white; border: 0; border-radius: 6px;
                              padding: 8px 14px; font-size: 12px; font-weight: 600; }
                QPushButton:disabled { background: #cbd5e4; color: #64748b; }
            """)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        body.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet('QProgressBar { border: 0; background: #e3eaf6; border-radius: 4px; } QProgressBar::chunk { background: #285ee8; border-radius: 4px; }')
        body.addWidget(self.progress_bar)
        actions = QHBoxLayout()
        self.check_button = QPushButton('Check for updates')
        self.check_button.clicked.connect(manager.check)
        actions.addWidget(self.check_button)
        self.action_button = QPushButton()
        self.action_button.setObjectName('primaryButton')
        self.action_button.clicked.connect(self.act)
        actions.addWidget(self.action_button)
        actions.addStretch()
        body.addLayout(actions)
        manager.changed.connect(self.refresh)
        # Settings can stay open across a round transition. Refresh the guard even
        # when the updater itself has no new status to announce.
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def act(self):
        if self.manager.status == 'available':
            self.manager.download()
        elif self.manager.status == 'ready':
            self.manager.install()

    def refresh(self):
        manager = self.manager
        ready = manager.status == 'ready'
        self.status_label.setText(manager.message)
        self.check_button.setVisible(not self.compact and not ready)
        self.check_button.setEnabled(not manager.busy)
        self.action_button.setVisible(manager.status in ('available', 'ready'))
        self.action_button.setText('Restart to update' if ready else 'Download update')
        self.action_button.setEnabled(not ready or manager.can_install())
        self.action_button.setToolTip('Available in the lobby after local service setup finishes.' if ready else 'Download and verify the update; JParty keeps running.')
        self.progress_bar.setVisible(manager.status == 'downloading')
        self.progress_bar.setValue(manager.progress)
        if self.compact:
            self.setVisible(manager.status in ('available', 'downloading', 'ready'))


def manager_for(game, owner):
    manager = getattr(game, 'update_manager', None)
    if not isinstance(manager, UpdateManager) or sip.isdeleted(manager):
        manager = UpdateManager(game)
        manager.setParent(game if isinstance(game, QObject) else owner)
        if game is not None:
            game.update_manager = manager
    return manager
