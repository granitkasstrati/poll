"""Settings: valuation assumptions, Claude API key, data cache."""

from __future__ import annotations

import os

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout,
)

from .. import data as data_mod
from .state import AppState
from .theme import theme_icon
from .widgets import dim_label


class SettingsDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Configure Munger Lens")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)

        a = state.assumptions
        val = QGroupBox("Valuation assumptions")
        form = QFormLayout(val)
        self.discount = QDoubleSpinBox(suffix=" %", decimals=1, minimum=4.0, maximum=20.0, singleStep=0.5, value=a.discount_rate * 100)
        self.discount.setToolTip("Your required annual return, used by every DCF. 9–10% is a common equity hurdle.")
        self.aaa = QDoubleSpinBox(suffix=" %", decimals=2, minimum=1.0, maximum=12.0, singleStep=0.05, value=a.aaa_yield * 100)
        self.aaa.setToolTip("Graham's Y. Check the current Moody's Aaa corporate yield (FRED series AAA).")
        form.addRow("Discount rate (DCF):", self.discount)
        form.addRow("AAA corporate bond yield (Graham):", self.aaa)
        lay.addWidget(val)

        ai = QGroupBox("Claude research memos")
        ai_l = QFormLayout(ai)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("sk-ant-…")
        self.key.setText(os.environ.get("ANTHROPIC_API_KEY", ""))
        reveal = QAction(theme_icon("view-visible", "password-show-on"), "Show", self.key)
        reveal.setCheckable(True)
        reveal.toggled.connect(lambda on: self.key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        self.key.addAction(reveal, QLineEdit.ActionPosition.TrailingPosition)
        ai_l.addRow("Anthropic API key:", self.key)
        env = state.env_file()
        ai_l.addRow(dim_label(f"Stored in {env} (readable only by you)." if env else
                              "Running from source: the key is used for this session only. "
                              "Export ANTHROPIC_API_KEY to make it permanent."))
        lay.addWidget(ai)

        data = QGroupBox("Market data")
        d_l = QVBoxLayout(data)
        d_l.addWidget(dim_label(f"Yahoo Finance data is cached for 12 hours per ticker in {data_mod.CACHE_DIR}."))
        clear = QPushButton(theme_icon("edit-clear-history", "edit-clear"), "Clear cached data")
        clear.clicked.connect(self._clear)
        d_l.addWidget(clear)
        lay.addWidget(data)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _clear(self) -> None:
        self.state.clear_cache()
        QMessageBox.information(self, "Cache cleared", "Cached market data was removed. It will be re-downloaded as needed.")

    def accept(self) -> None:
        self.state.set_assumptions(self.discount.value() / 100, self.aaa.value() / 100)
        self.state.save_api_key(self.key.text())
        super().accept()
