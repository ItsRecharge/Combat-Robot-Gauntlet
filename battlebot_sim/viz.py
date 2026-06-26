"""PyVista rendering helpers shared by the interactive viewport and the report
exporter. This module is free of Qt and MuJoCo so it can render off-screen.

Two damage fields can be displayed on the bot mesh:
- "energy"  : accumulated impact energy (relative), inferno colormap
- "failure" : failure margin (peak stress / yield), turbo colormap; values >= 1
              mean the material would yield.
"""

from __future__ import annotations

import numpy as np
import pyvista as pv

from battlebot_sim.damage.fields import vertex_scalars
from battlebot_sim.damage.model import DamageResult
from battlebot_sim.mesh.segment import BotModel

FIELD_SPECS = {
    "energy": {"title": "Impact Energy (J)", "cmap": "inferno"},
    "failure": {"title": "Failure Margin (stress / yield)", "cmap": "turbo"},
}


def bot_polydata(bot: BotModel) -> pv.PolyData:
    """A PyVista mesh of the bot's original (full-detail) geometry."""
    m = bot.original
    faces = np.hstack(
        [np.full((len(m.faces), 1), 3, dtype=np.int64), m.faces.astype(np.int64)]
    ).ravel()
    return pv.PolyData(np.asarray(m.vertices, dtype=float), faces)


def field_values(bot: BotModel, result: DamageResult, mode: str) -> np.ndarray:
    """Per-vertex (smoothed) values for the requested field."""
    fv = result.energy_per_face if mode == "energy" else result.failure_margin_per_face
    m = bot.original
    return vertex_scalars(m.faces, len(m.vertices), fv)


def attach_field(poly: pv.PolyData, bot: BotModel, result: DamageResult, mode: str):
    """Attach a field to a PolyData and return (cmap, clim, title)."""
    vals = field_values(bot, result, mode)
    poly.point_data[mode] = vals
    poly.set_active_scalars(mode)
    spec = FIELD_SPECS[mode]
    if mode == "failure":
        clim = [0.0, max(1.0, float(vals.max()))]
    else:
        clim = [0.0, max(1e-9, float(vals.max()))]
    return spec["cmap"], clim, spec["title"]


def render_heatmap_png(
    bot: BotModel,
    result: DamageResult,
    mode: str,
    path: str,
    size: tuple[int, int] = (960, 720),
) -> str:
    """Render one heatmap to a PNG off-screen. Returns the path written."""
    poly = bot_polydata(bot)
    cmap, clim, title = attach_field(poly, bot, result, mode)
    plotter = pv.Plotter(off_screen=True, window_size=list(size))
    plotter.set_background("white")
    plotter.add_mesh(
        poly, scalars=mode, cmap=cmap, clim=clim, show_edges=False,
        scalar_bar_args={"title": title, "color": "black"},
    )
    if mode == "failure":
        # Mark the failure threshold (margin = 1) as a labelled contour-ish note.
        plotter.add_text("red >= yield", position="upper_right", font_size=10, color="black")
    plotter.add_axes(color="black")
    plotter.view_isometric()
    plotter.screenshot(path)
    plotter.close()
    return path
