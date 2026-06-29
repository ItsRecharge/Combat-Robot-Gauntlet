"""Tests for NHRL cage geometry."""

from gauntlet.arena.nhrl import build_arena
from gauntlet.materials.assign import NHRL_CLASSES


def test_arena_has_six_surfaces():
    arena = build_arena(NHRL_CLASSES["12lb"])
    roles = sorted(g.role for g in arena.geoms)
    assert roles == ["ceiling", "floor", "wall", "wall", "wall", "wall"]


def test_floor_top_surface_at_zero():
    arena = build_arena(NHRL_CLASSES["3lb"])
    floor = next(g for g in arena.geoms if g.role == "floor")
    # center_z + half_extent_z == 0  -> top of floor at z = 0
    assert abs(floor.center[2] + floor.half_extents[2]) < 1e-9
    assert arena.floor_z == 0.0


def test_ceiling_at_cage_height():
    cls = NHRL_CLASSES["30lb"]
    arena = build_arena(cls)
    assert abs(arena.ceiling_z - cls.cage_height_m) < 1e-9


def test_walls_enclose_interior():
    cls = NHRL_CLASSES["12lb"]
    arena = build_arena(cls)
    L, W, _ = arena.interior
    px = next(g for g in arena.geoms if g.name == "wall_px")
    nx = next(g for g in arena.geoms if g.name == "wall_nx")
    # Inner faces of the +X / -X walls bound the interior length.
    inner_px = px.center[0] - px.half_extents[0]
    inner_nx = nx.center[0] + nx.half_extents[0]
    assert abs(inner_px - L / 2) < 1e-9
    assert abs(inner_nx + L / 2) < 1e-9


def test_floor_material_is_steel():
    arena = build_arena(NHRL_CLASSES["3lb"])
    assert "Steel" in arena.material_of("floor")
    assert "Polycarbonate" in arena.material_of("wall_px")
