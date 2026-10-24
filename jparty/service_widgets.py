import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QMessageBox,
)


class LocalServicesPanel(QWidget):
    def __init__(self, manager, config_reader, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.config_reader = config_reader
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.summary = QLabel()
        self.summary.setObjectName('serviceSummary')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        hint = QLabel('Status checks use your saved settings. Save changes before managing services. Setup installs tools and downloads models; Start uses the installed models.')
        hint.setProperty('muted', True)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.rows = {}
        for name in ('Text generation', 'Speech recognition', 'Host voice', 'Answer judge · Kev', 'OpenAI'):
            row = QLabel()
            row.setTextFormat(Qt.TextFormat.PlainText)
            row.setWordWrap(True)
            row.setObjectName('serviceRow')
            layout.addWidget(row)
            self.rows[name] = row
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.buttons = {}
        for action, text in [('setup', 'Set up'), ('start', 'Start services'), ('stop', 'Stop services')]:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, action=action: self.run(action))
            buttons.addWidget(button)
            self.buttons[action] = button
        self.buttons['start'].setObjectName('primaryButton')
        self.check_button = QPushButton('Check status')
        self.check_button.clicked.connect(lambda: manager.refresh())
        buttons.addWidget(self.check_button)
        layout.addLayout(buttons)
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(500)
        self.activity.setPlaceholderText('Service progress and next steps appear here.')
        self.activity.setMinimumHeight(130)
        self.activity.setMaximumHeight(190)
        self.activity.setPlainText(manager.log)
        layout.addWidget(self.activity)
        manager.changed.connect(self.update_status)
        manager.output.connect(self.append_output)
        self.update_status()

    def append_output(self, text):
        # Read the bounded shared log so reopening Settings retains progress.
        self.activity.setPlainText(self.manager.log or text)
        bar = self.activity.verticalScrollBar()
        bar.setValue(bar.maximum())

    def update_status(self):
        manager = self.manager
        self.summary.setText(manager.message)
        present = {row['name']: row for row in manager.results}
        for name, widget in self.rows.items():
            row = present.get(name)
            widget.setVisible(row is not None)
            if row:
                widget.setProperty('state', 'ready' if row['ready'] else 'offline')
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                symbol = '● Ready' if row['ready'] else '○ Needs attention'
                detail = '' if row['ready'] else '\n' + row['detail']
                widget.setText(f"{name}    {symbol}\n{row['endpoint']}{detail}")
        for button in self.buttons.values():
            button.setEnabled(not manager.busy and sys.platform == 'darwin')
        self.check_button.setEnabled(not manager.checking)
        if sys.platform != 'darwin':
            self.summary.setToolTip('Service management is available on macOS. On other platforms, start servers externally and check status.')

    def run(self, action):
        try:
            config = self.manager.config if action == 'stop' else self.config_reader()
            self.manager.run(action, config)
        except ValueError as exc:
            QMessageBox.information(self, 'Local Auto Host', str(exc))
