"""The beginner-friendly Ollama model picker."""
import sys
import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget

from jparty.local_models import SUGGESTED_MODELS, canonical_model, model_size
from jparty.settings_widgets import SettingsComboBox


class LocalModelsPanel(QWidget):
    selection_changed = pyqtSignal()

    def __init__(self, manager, selected, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._selected = selected
        self._inventory_signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        hint = QLabel('Ollama runs AI models on your computer. Install and open Ollama, then choose a model for JParty. Models load automatically when needed.')
        hint.setWordWrap(True)
        hint.setProperty('muted', True)
        layout.addWidget(hint)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.install_button = QPushButton('Install Ollama')
        self.install_button.clicked.connect(self.install)
        self.start_button = QPushButton('Open/Start Ollama')
        self.start_button.clicked.connect(manager.start)
        self.refresh_button = QPushButton('Refresh')
        self.refresh_button.clicked.connect(manager.refresh)
        for button in (self.install_button, self.start_button, self.refresh_button):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        row = QHBoxLayout()
        model_label = QLabel('Installed model:')
        model_label.setFixedWidth(220)
        row.addWidget(model_label)
        self.model_combo = SettingsComboBox()
        self.model_combo.setAccessibleName('Installed local AI model')
        self.model_combo.setMinimumWidth(0)
        row.addWidget(self.model_combo, 1)
        layout.addLayout(row)
        self.model_status = QLabel()
        self.model_status.setWordWrap(True)
        layout.addWidget(self.model_status)
        self.download_toggle = QPushButton('Download a model…')
        self.download_toggle.setCheckable(True)
        self.download_toggle.toggled.connect(self._show_downloads)
        layout.addWidget(self.download_toggle)
        self.download_area = QWidget()
        downloads = QVBoxLayout(self.download_area)
        downloads.setContentsMargins(0, 0, 0, 0)
        downloads.setSpacing(10)
        self.suggestions = SettingsComboBox()
        self.suggestions.setAccessibleName('Model to download')
        for name, title, _description in SUGGESTED_MODELS:
            self.suggestions.addItem(title, name)
        self.suggestions.addItem('Other model · enter its Ollama name', '__custom__')
        downloads.addWidget(self.suggestions)
        self.description = QLabel()
        self.description.setProperty('muted', True)
        self.description.setWordWrap(True)
        downloads.addWidget(self.description)
        self.custom_name = QLineEdit()
        self.custom_name.setPlaceholderText('Ollama model name, e.g. llama3.2:3b')
        self.custom_name.setAccessibleName('Custom Ollama model name')
        downloads.addWidget(self.custom_name)
        self.library_button = QPushButton('Browse Ollama models ↗')
        self.library_button.clicked.connect(lambda: webbrowser.open('https://ollama.com/library'))
        downloads.addWidget(self.library_button)
        download_actions = QHBoxLayout()
        self.download_button = QPushButton('Download && select')
        self.download_button.setObjectName('primaryButton')
        self.download_button.clicked.connect(self.download)
        self.cancel_button = QPushButton('Cancel download')
        self.cancel_button.clicked.connect(manager.cancel)
        download_actions.addWidget(self.download_button)
        download_actions.addWidget(self.cancel_button)
        download_actions.addStretch()
        downloads.addLayout(download_actions)
        layout.addWidget(self.download_area)
        self.progress_bar = QProgressBar()
        self.progress_bar.setAccessibleName('Model download progress')
        self.progress_bar.setFixedHeight(18)
        layout.addWidget(self.progress_bar)
        self.download_status = QLabel()
        self.download_status.setWordWrap(True)
        self.download_status.setTextFormat(self.status.textFormat())
        layout.addWidget(self.download_status)
        self.model_combo.currentIndexChanged.connect(self._selected_changed)
        self.suggestions.currentIndexChanged.connect(self._suggestion_changed)
        manager.changed.connect(self.refresh)
        manager.downloaded.connect(self.select_model)
        manager.services.changed.connect(self.refresh)
        if manager.download_model:
            index = self.suggestions.findData(manager.download_model)
            self.suggestions.setCurrentIndex(index if index >= 0 else self.suggestions.findData('__custom__'))
            self.custom_name.setText(manager.download_model)
        self._suggestion_changed()
        self.download_toggle.setChecked(manager.download_reply is not None)
        self._show_downloads(self.download_toggle.isChecked())
        self.refresh()

    @property
    def selected_model(self):
        return self._selected

    def install(self):
        platform = 'mac' if sys.platform == 'darwin' else 'windows' if sys.platform == 'win32' else 'linux'
        webbrowser.open(f'https://ollama.com/download/{platform}')

    def _show_downloads(self, show):
        self.download_area.setVisible(show)
        self.download_toggle.setText('Hide model downloads' if show else 'Download a model…')

    def _suggestion_changed(self):
        custom = self.suggestions.currentData() == '__custom__'
        self.custom_name.setVisible(custom)
        self.library_button.setVisible(custom)
        self.description.setText('Enter a downloadable text model’s Ollama name. Downloads use disk space and require internet.' if custom
                                 else SUGGESTED_MODELS[self.suggestions.currentIndex()][2])

    def _selected_changed(self):
        value = self.model_combo.currentData()
        if value:
            self._selected = value
            self.manager.check_model(value)
            self.refresh()
            self.selection_changed.emit()

    def select_model(self, name):
        self._selected = name
        self.refresh()
        self.selection_changed.emit()

    def download(self):
        name = self.suggestions.currentData()
        self.manager.download(self.custom_name.text() if name == '__custom__' else name)

    def refresh(self):
        manager = self.manager
        self.status.setText(manager.message)
        signature = ([(m['name'], m['size']) for m in manager.models], self._selected, manager.online)
        # Routine status checks must not close a dropdown the user is browsing.
        if signature != self._inventory_signature:
            self._inventory_signature = signature
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            for model in manager.models:
                self.model_combo.addItem(f"{model['name']} · {model_size(model['size'])}", model['name'])
            selected = next((i for i in range(self.model_combo.count())
                             if canonical_model(self.model_combo.itemData(i)) == canonical_model(self._selected)), -1)
            if selected < 0:
                suffix = 'not installed' if manager.online else 'Ollama offline'
                self.model_combo.insertItem(0, f'{self._selected} · {suffix}', self._selected)
                selected = 0
            self.model_combo.setCurrentIndex(selected)
            self.model_combo.blockSignals(False)
        manager.check_model(self._selected)
        if manager.selected_ready(self._selected):
            detail = 'Ready. Save changes to use this model for hosting, judging, and image search.'
        elif not manager.online:
            detail = 'Your selection is remembered. Start Ollama to see installed models.'
        elif not any(canonical_model(m['name']) == canonical_model(self._selected) for m in manager.models):
            detail = 'This model is not installed. Choose an installed model or download one below.'
        elif manager.capabilities.get(canonical_model(self._selected)) is False:
            detail = 'This model cannot generate text. Choose a text model for JParty.'
        elif manager.services.busy:
            detail = 'Waiting for the service command to finish…'
        elif manager.capabilities.get(canonical_model(self._selected)) is True:
            detail = 'Refreshing model status…'
        elif canonical_model(self._selected) in manager.capabilities:
            detail = 'Could not verify this model. Update Ollama, then choose Refresh.'
        else:
            detail = 'Checking whether this model can generate text…'
        self.model_status.setText(detail)
        busy = manager.busy or manager.services.busy
        self.start_button.setEnabled(not busy and not manager.online)
        self.refresh_button.setEnabled(not manager.checking)
        self.model_combo.setEnabled(not busy)
        self.suggestions.setEnabled(not busy)
        self.custom_name.setEnabled(not busy)
        self.download_button.setEnabled(manager.online and not busy)
        self.cancel_button.setVisible(manager.download_reply is not None)
        self.download_status.setText(manager.download_message)
        self.download_status.setVisible(bool(manager.download_message))
        self.progress_bar.setVisible(manager.download_reply is not None)
        if manager.progress is None:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(manager.progress)
