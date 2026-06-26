"""Headless smoke test for the Qt control panels and their wiring.

Uses the offscreen Qt platform. It deliberately does NOT construct the VTK
viewport (QtInteractor), which requires a real OpenGL context and cannot be
created under the offscreen platform. The full window + viewport is verified
separately by an on-display launch.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "data", "sample_bots", "wedge_bot.stl"
)


@pytest.fixture(scope="module")
def app():
    try:
        from PySide6 import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PySide6 unavailable: {exc}")
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield application


def test_parts_panel_assigns_materials_and_masses(app):
    from battlebot_sim.materials.library import load_default_library
    from battlebot_sim.mesh.segment import load_bot
    from battlebot_sim.ui.panels import PartsPanel

    library = load_default_library()
    bot = load_bot(os.path.abspath(SAMPLE), scale_to_m=1.0)

    panel = PartsPanel(library)
    panel.set_bot(bot)
    # Defaults applied -> every part has a material and positive total mass.
    assert bot.assigned()
    assert bot.total_mass() > 0
    assert panel.table.rowCount() == len(bot.parts)

    # Toggling a brace flag propagates to the model.
    panel._on_brace(0, True)
    assert bot.parts[0].is_brace


def test_setup_and_results_panel_wiring(app):
    from battlebot_sim.ui.panels import ResultsPanel, SetupPanel

    setup = SetupPanel()
    assert setup.current_class_key() in {"3lb", "12lb", "30lb"}
    assert not setup.run_btn.isEnabled()  # disabled until a bot loads

    results = ResultsPanel()
    received = []
    results.mode_changed.connect(received.append)
    results.failure_btn.setChecked(True)
    assert received == ["failure"]

    results.set_enabled(True)
    results.configure_slider(50)
    assert results.slider.maximum() == 49
