"""NHRL test cage as a set of static box surfaces.

The cage is a simple closed box: a steel floor, four polycarbonate walls, and a
polycarbonate ceiling, sized from the chosen weight class. Geometry is pure data
(positions and half-extents in metres) so it can be tested without a physics
engine; `sim.mjcf` turns it into MuJoCo geoms.

Coordinate convention: the cage interior spans
    x in [-L/2, +L/2], y in [-W/2, +W/2], z in [0, H]
with the floor's top surface at z = 0.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gauntlet.materials.assign import WeightClass

WALL_THICKNESS_M = 0.05


@dataclass(frozen=True)
class BoxGeom:
    """A static box surface of the cage."""

    name: str
    center: tuple[float, float, float]
    half_extents: tuple[float, float, float]
    material: str          # material name (for contact-stiffness lookup)
    role: str              # "floor" | "wall" | "ceiling"


@dataclass
class Arena:
    """A built cage: its weight class, interior size, and static box surfaces."""

    weight_class: WeightClass
    interior: tuple[float, float, float]   # (L, W, H) in metres
    geoms: list[BoxGeom]

    @property
    def floor_z(self) -> float:
        return 0.0

    @property
    def ceiling_z(self) -> float:
        return self.interior[2]

    def material_of(self, geom_name: str) -> str:
        for g in self.geoms:
            if g.name == geom_name:
                return g.material
        raise KeyError(geom_name)

    def center_point(self) -> np.ndarray:
        """A sensible spawn point: centred horizontally, mid-height."""
        return np.array([0.0, 0.0, self.interior[2] * 0.5])


def build_arena(weight_class: WeightClass, wall_thickness: float = WALL_THICKNESS_M) -> Arena:
    """Construct the cage box surfaces for a given NHRL weight class."""
    L = weight_class.cage_length_m
    W = weight_class.cage_width_m
    H = weight_class.cage_height_m
    t = wall_thickness
    hl, hw = L / 2.0, W / 2.0
    wall = weight_class.wall_material
    floor = weight_class.floor_material

    geoms: list[BoxGeom] = [
        # Floor: thin slab whose TOP surface sits at z = 0.
        BoxGeom("floor", (0.0, 0.0, -t / 2.0),
                (hl + t, hw + t, t / 2.0), floor, "floor"),
        # Ceiling: bottom surface at z = H.
        BoxGeom("ceiling", (0.0, 0.0, H + t / 2.0),
                (hl + t, hw + t, t / 2.0), wall, "ceiling"),
        # +X / -X walls.
        BoxGeom("wall_px", (hl + t / 2.0, 0.0, H / 2.0),
                (t / 2.0, hw + t, H / 2.0), wall, "wall"),
        BoxGeom("wall_nx", (-hl - t / 2.0, 0.0, H / 2.0),
                (t / 2.0, hw + t, H / 2.0), wall, "wall"),
        # +Y / -Y walls.
        BoxGeom("wall_py", (0.0, hw + t / 2.0, H / 2.0),
                (hl + t, t / 2.0, H / 2.0), wall, "wall"),
        BoxGeom("wall_ny", (0.0, -hw - t / 2.0, H / 2.0),
                (hl + t, t / 2.0, H / 2.0), wall, "wall"),
    ]
    return Arena(weight_class=weight_class, interior=(L, W, H), geoms=geoms)
