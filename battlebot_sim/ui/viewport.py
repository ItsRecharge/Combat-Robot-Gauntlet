"""Embedded PyVista 3D viewport: shows the cage, the bot, the flinging replay,
and the damage heatmaps."""

from __future__ import annotations

import numpy as np
from pyvistaqt import QtInteractor

from battlebot_sim import viz
from battlebot_sim.arena.nhrl import Arena
from battlebot_sim.damage.model import DamageResult
from battlebot_sim.mesh.segment import BotModel
from battlebot_sim.sim.recorder import SimTrace


def _matrix(pos, quat) -> np.ndarray:
    """4x4 body->world transform from pos + MuJoCo (w,x,y,z) quaternion."""
    from scipy.spatial.transform import Rotation
    R = Rotation.from_quat([quat[1], quat[2], quat[3], quat[0]]).as_matrix()
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = np.asarray(pos, dtype=float)
    return M


class BotViewport(QtInteractor):
    """A QtInteractor that renders the bot, arena, replay and heatmaps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_background("white")
        self.bot: BotModel | None = None
        self.poly = None
        self.bot_actor = None
        self.trace: SimTrace | None = None
        self.result: DamageResult | None = None
        self._mode = "solid"   # "solid" | "energy" | "failure"

    # ---- scene setup -----------------------------------------------------
    def set_bot(self, bot: BotModel) -> None:
        self.bot = bot
        self.poly = viz.bot_polydata(bot)
        if self.bot_actor is not None:
            self.remove_actor(self.bot_actor)
        self.bot_actor = self.add_mesh(self.poly, color="#9aa6b2", show_edges=False)
        self.add_axes(color="black")
        self.reset_camera()
        self.render()

    def show_arena(self, arena: Arena) -> None:
        for g in arena.geoms:
            box = self._box(g.center, g.half_extents)
            opacity = 1.0 if g.role == "floor" else 0.12
            color = "#5b6168" if g.role == "floor" else "#88a0c0"
            self.add_mesh(box, color=color, opacity=opacity, name=f"arena_{g.name}")
        self.reset_camera()
        self.render()

    @staticmethod
    def _box(center, half):
        import pyvista as pv
        c, h = np.asarray(center), np.asarray(half)
        return pv.Box(bounds=(c[0] - h[0], c[0] + h[0],
                              c[1] - h[1], c[1] + h[1],
                              c[2] - h[2], c[2] + h[2]))

    # ---- replay ----------------------------------------------------------
    def set_trace(self, trace: SimTrace) -> None:
        self.trace = trace

    @property
    def n_frames(self) -> int:
        return len(self.trace.frames) if self.trace else 0

    def show_frame(self, i: int) -> None:
        """Pose the bot at recorded frame i (used during replay)."""
        if not self.trace or self.bot_actor is None or self.n_frames == 0:
            return
        i = max(0, min(i, self.n_frames - 1))
        f = self.trace.frames[i]
        self.bot_actor.user_matrix = _matrix(f.pos, f.quat)
        self.render()

    # ---- heatmaps --------------------------------------------------------
    def set_result(self, result: DamageResult) -> None:
        self.result = result

    def show_heatmap(self, mode: str) -> None:
        """Switch the bot surface to a damage field ('energy' or 'failure')
        or back to a plain surface ('solid'). Resets the bot to rest pose."""
        if self.bot is None or self.poly is None:
            return
        self._mode = mode
        if self.bot_actor is not None:
            self.remove_actor(self.bot_actor)
        if mode == "solid" or self.result is None:
            self.bot_actor = self.add_mesh(self.poly, color="#9aa6b2")
        else:
            cmap, clim, title = viz.attach_field(self.poly, self.bot, self.result, mode)
            self.bot_actor = self.add_mesh(
                self.poly, scalars=mode, cmap=cmap, clim=clim,
                scalar_bar_args={"title": title, "color": "black"},
            )
        self.bot_actor.user_matrix = np.eye(4)
        self.render()
