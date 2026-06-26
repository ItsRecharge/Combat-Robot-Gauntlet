"""Main application window: wires the panels and viewport to the pipeline."""

from __future__ import annotations

import os

from PySide6 import QtCore, QtWidgets

from battlebot_sim.arena.nhrl import build_arena
from battlebot_sim.damage.braces import apply_brace_sharing
from battlebot_sim.damage.model import compute_damage
from battlebot_sim.materials.assign import NHRL_CLASSES, validate_weight_class
from battlebot_sim.materials.library import load_default_library
from battlebot_sim.mesh.segment import load_bot
from battlebot_sim.report.export import export_report
from battlebot_sim.sim.battery import StressBattery, run_battery
from battlebot_sim.sim.engine import SimEngine
from battlebot_sim.ui.panels import PartsPanel, ResultsPanel, SetupPanel
from battlebot_sim.ui.viewport import BotViewport


class SimWorker(QtCore.QObject):
    """Runs the battery + damage model off the UI thread."""

    finished = QtCore.Signal(object, object)   # (trace, result)
    failed = QtCore.Signal(str)

    def __init__(self, bot, arena, weight_class, library):
        super().__init__()
        self.bot, self.arena = bot, arena
        self.weight_class, self.library = weight_class, library

    @QtCore.Slot()
    def run(self) -> None:
        try:
            engine = SimEngine(self.arena, self.bot)
            battery = StressBattery(self.arena, self.weight_class)
            trace = run_battery(engine, battery, fps=30)
            result = compute_damage(trace, self.bot, self.arena, self.library)
            result = apply_brace_sharing(result, self.bot)
            self.finished.emit(trace, result)
        except Exception as exc:        # surface failures to the UI, don't swallow
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BattleBot Damage Simulator")
        self.resize(1280, 820)

        self.library = load_default_library()
        self.bot = None
        self.arena = None
        self.trace = None
        self.result = None
        self._thread = None
        self._worker = None

        # --- widgets ---
        self.viewport = BotViewport(self)
        self.setup_panel = SetupPanel()
        self.parts_panel = PartsPanel(self.library)
        self.results_panel = ResultsPanel()

        side = QtWidgets.QWidget()
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.addWidget(self.setup_panel)
        side_layout.addWidget(self.parts_panel)
        side_layout.addWidget(self.results_panel)
        side.setMaximumWidth(460)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.viewport)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 1)
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Load an STL to begin.")

        # --- replay timer ---
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance_frame)

        # --- signals ---
        self.setup_panel.load_requested.connect(self.load_stl)
        self.setup_panel.run_requested.connect(self.run_simulation)
        self.parts_panel.changed.connect(self._update_weight_check)
        self.results_panel.mode_changed.connect(self._on_mode)
        self.results_panel.frame_changed.connect(self.viewport.show_frame)
        self.results_panel.play_toggled.connect(self._on_play)
        self.results_panel.export_requested.connect(self.export)

    # ---- load / setup ----------------------------------------------------
    @QtCore.Slot(str, float)
    def load_stl(self, path: str, scale_to_m: float) -> None:
        try:
            self.bot = load_bot(path, scale_to_m=scale_to_m)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(exc))
            return
        self.result = self.trace = None
        self.results_panel.set_enabled(False)
        self.results_panel.solid_btn.setChecked(True)

        wc = NHRL_CLASSES[self.setup_panel.current_class_key()]
        self.arena = build_arena(wc)
        self.viewport.clear()
        self.viewport.set_bot(self.bot)
        self.viewport.show_arena(self.arena)
        self.parts_panel.set_bot(self.bot)
        self._update_weight_check()
        self.setup_panel.run_btn.setEnabled(True)
        self.statusBar().showMessage(
            f"Loaded {os.path.basename(path)} — {len(self.bot.parts)} parts.")

    def _update_weight_check(self) -> None:
        if self.bot is None:
            return
        wc = NHRL_CLASSES[self.setup_panel.current_class_key()]
        check = validate_weight_class(self.bot.total_mass(), wc)
        self.parts_panel.update_weight_check(check.message, check.ok)

    # ---- run simulation --------------------------------------------------
    @QtCore.Slot(str)
    def run_simulation(self, class_key: str) -> None:
        if self.bot is None:
            return
        wc = NHRL_CLASSES[class_key]
        self.arena = build_arena(wc)
        self.viewport.show_arena(self.arena)
        self.setup_panel.run_btn.setEnabled(False)
        self.setup_panel.progress.show()
        self.statusBar().showMessage("Running stress battery…")

        self._thread = QtCore.QThread(self)
        self._worker = SimWorker(self.bot, self.arena, wc, self.library)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_sim_done)
        self._worker.failed.connect(self._on_sim_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    @QtCore.Slot(object, object)
    def _on_sim_done(self, trace, result) -> None:
        self.trace, self.result = trace, result
        self.viewport.set_trace(trace)
        self.viewport.set_result(result)
        self.results_panel.configure_slider(self.viewport.n_frames)
        self.results_panel.set_enabled(True)
        self.setup_panel.progress.hide()
        self.setup_panel.run_btn.setEnabled(True)
        self._write_summary()
        self.statusBar().showMessage(
            f"Done: {trace.total_contacts()} contacts, {self.viewport.n_frames} frames.")

    @QtCore.Slot(str)
    def _on_sim_failed(self, message: str) -> None:
        self.setup_panel.progress.hide()
        self.setup_panel.run_btn.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "Simulation failed", message)
        self.statusBar().showMessage("Simulation failed.")

    def _write_summary(self) -> None:
        if self.result is None:
            return
        failing = self.result.parts_that_fail()
        lines = []
        if failing:
            names = ", ".join(self.bot.parts[i].name for i in failing)
            lines.append(f"⚠️ {len(failing)} part(s) predicted to yield: {names}")
        else:
            lines.append("✅ No part exceeded its material yield.")
        lines.append("")
        for p in self.bot.parts:
            m = self.result.part_max_margin.get(p.index, 0.0)
            lines.append(f"{p.name}: max margin {m:.2f}"
                         + ("  FAIL" if m >= 1.0 else ""))
        self.results_panel.summary.setPlainText("\n".join(lines))

    # ---- results interactions -------------------------------------------
    @QtCore.Slot(str)
    def _on_mode(self, mode: str) -> None:
        self.viewport.show_heatmap(mode)

    @QtCore.Slot(bool)
    def _on_play(self, playing: bool) -> None:
        if playing and self.viewport.n_frames:
            # Replay shows motion on the plain surface.
            self.results_panel.solid_btn.setChecked(True)
            self._timer.start()
        else:
            self._timer.stop()

    def _advance_frame(self) -> None:
        nxt = (self.results_panel.slider.value() + 1) % max(1, self.viewport.n_frames)
        self.results_panel.slider.setValue(nxt)

    # ---- export ----------------------------------------------------------
    @QtCore.Slot()
    def export(self) -> None:
        if self.result is None:
            return
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder")
        if not out_dir:
            return
        wc = NHRL_CLASSES[self.setup_panel.current_class_key()]
        try:
            paths = export_report(self.bot, self.result, wc, out_dir, trace=self.trace)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))
            return
        QtWidgets.QMessageBox.information(
            self, "Report exported", f"Wrote:\n{paths['report']}")
