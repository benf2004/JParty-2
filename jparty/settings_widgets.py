"""Shared settings controls."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPolygonF
from PyQt6.QtWidgets import QComboBox, QGroupBox, QVBoxLayout


def settings_card(title):
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(16, 24, 16, 16)
    layout.setSpacing(12)
    return box, layout


class SettingsComboBox(QComboBox):
    """Paint a visible arrow even when the platform stylesheet hides it."""
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#637089' if self.isEnabled() else '#a4adbd'))
        x, y = self.width() - 17, self.height() / 2
        painter.drawPolygon(QPolygonF([QPointF(x - 4, y - 2), QPointF(x + 4, y - 2), QPointF(x, y + 3)]))
