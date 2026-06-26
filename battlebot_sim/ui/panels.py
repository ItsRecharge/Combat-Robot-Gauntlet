"""Control panels for the main window: parts/materials, setup, and results."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from battlebot_sim.materials.assign import NHRL_CLASSES
from battlebot_sim.materials.library import MaterialLibrary
from battlebot_sim.mesh.segment import BotModel


class PartsPanel(QtWidgets.QGroupBox):
    """A table of parts with per-part material + brace selection."""

    changed = QtCore.Signal()       # emitted when any material/brace changes

    def __init__(self, library: MaterialLibrary, parent=None):
        super().__init__("Parts & Materials", parent)
        self.library = library
        self.bot: BotModel | None = None

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Part", "Material", "Brace", "Mass (kg)"])
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch)

        self.total_label = QtWidgets.QLabel("Total mass: —")
        self.class_label = QtWidgets.QLabel("")
        self.class_label.setWordWrap(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(self.total_label)
        layout.addWidget(self.class_label)

    def set_bot(self, bot: BotModel) -> None:
        self.bot = bot
        self.table.setRowCount(len(bot.parts))
        for p in bot.parts:
            self.table.setItem(p.index, 0, QtWidgets.QTableWidgetItem(p.name))

            combo = QtWidgets.QComboBox()
            combo.addItems(self.library.names())
            combo.currentTextChanged.connect(
                lambda name, idx=p.index: self._on_material(idx, name))
            self.table.setCellWidget(p.index, 1, combo)

            check = QtWidgets.QCheckBox()
            check.stateChanged.connect(
                lambda state, idx=p.index: self._on_brace(idx, state))
            holder = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(holder)
            hl.addWidget(check)
            hl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            hl.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(p.index, 2, holder)

            self.table.setItem(p.index, 3, QtWidgets.QTableWidgetItem("—"))
            # Apply the default (first) material immediately.
            self._on_material(p.index, combo.currentText())

    def _on_material(self, idx: int, name: str) -> None:
        if self.bot is None:
            return
        self.bot.assign_material(idx, self.library.get(name))
        self._refresh_masses()
        self.changed.emit()

    def _on_brace(self, idx: int, state) -> None:
        if self.bot is None:
            return
        self.bot.set_brace(idx, bool(state))
        self.changed.emit()

    def _refresh_masses(self) -> None:
        if self.bot is None:
            return
        for p in self.bot.parts:
            item = self.table.item(p.index, 3)
            if item:
                item.setText(f"{p.mass_kg:.3f}")
        self.total_label.setText(f"Total mass: {self.bot.total_mass():.3f} kg")

    def update_weight_check(self, message: str, ok: bool) -> None:
        color = "#1a7f37" if ok else "#cf222e"
        self.class_label.setText(f"<span style='color:{color}'>{message}</span>")


class SetupPanel(QtWidgets.QGroupBox):
    """Load STL, choose weight class & units, and run the battery."""

    load_requested = QtCore.Signal(str, float)   # path, scale_to_m
    run_requested = QtCore.Signal(str)            # weight class key

    def __init__(self, parent=None):
        super().__init__("Setup", parent)
        self.class_combo = QtWidgets.QComboBox()
        for key, wc in NHRL_CLASSES.items():
            self.class_combo.addItem(wc.name, key)

        self.unit_combo = QtWidgets.QComboBox()
        self.unit_combo.addItems(["millimetres", "centimetres", "metres"])

        self.load_btn = QtWidgets.QPushButton("Load STL…")
        self.run_btn = QtWidgets.QPushButton("Run stress battery")
        self.run_btn.setEnabled(False)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)            # busy indicator
        self.progress.hide()

        form = QtWidgets.QFormLayout(self)
        form.addRow("Weight class:", self.class_combo)
        form.addRow("STL units:", self.unit_combo)
        form.addRow(self.load_btn)
        form.addRow(self.run_btn)
        form.addRow(self.progress)

        self.load_btn.clicked.connect(self._choose_file)
        self.run_btn.clicked.connect(
            lambda: self.run_requested.emit(self.class_combo.currentData()))

    def _scale_to_m(self) -> float:
        return {"millimetres": 1e-3, "centimetres": 1e-2, "metres": 1.0}[
            self.unit_combo.currentText()]

    def _choose_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open STL", "", "STL files (*.stl);;All files (*)")
        if path:
            self.load_requested.emit(path, self._scale_to_m())

    def current_class_key(self) -> str:
        return self.class_combo.currentData()


class ResultsPanel(QtWidgets.QGroupBox):
    """Heatmap toggle, replay scrubber, summary text, and export."""

    mode_changed = QtCore.Signal(str)       # "solid" | "energy" | "failure"
    frame_changed = QtCore.Signal(int)
    play_toggled = QtCore.Signal(bool)
    export_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__("Results", parent)
        self.solid_btn = QtWidgets.QRadioButton("Solid")
        self.energy_btn = QtWidgets.QRadioButton("Impact energy")
        self.failure_btn = QtWidgets.QRadioButton("Failure margin")
        self.solid_btn.setChecked(True)
        for b, mode in ((self.solid_btn, "solid"),
                        (self.energy_btn, "energy"),
                        (self.failure_btn, "failure")):
            b.toggled.connect(lambda on, m=mode: on and self.mode_changed.emit(m))

        self.play_btn = QtWidgets.QPushButton("Play replay")
        self.play_btn.setCheckable(True)
        self.play_btn.toggled.connect(self.play_toggled.emit)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.frame_changed.emit)

        self.summary = QtWidgets.QTextEdit()
        self.summary.setReadOnly(True)
        self.export_btn = QtWidgets.QPushButton("Export report…")
        self.export_btn.clicked.connect(self.export_requested.emit)

        self.set_enabled(False)

        layout = QtWidgets.QVBoxLayout(self)
        mode_row = QtWidgets.QHBoxLayout()
        for b in (self.solid_btn, self.energy_btn, self.failure_btn):
            mode_row.addWidget(b)
        layout.addLayout(mode_row)
        layout.addWidget(self.play_btn)
        layout.addWidget(self.slider)
        layout.addWidget(self.summary)
        layout.addWidget(self.export_btn)

    def set_enabled(self, on: bool) -> None:
        for w in (self.energy_btn, self.failure_btn, self.play_btn,
                  self.slider, self.export_btn):
            w.setEnabled(on)

    def configure_slider(self, n_frames: int) -> None:
        self.slider.setRange(0, max(0, n_frames - 1))
        self.slider.setValue(0)
