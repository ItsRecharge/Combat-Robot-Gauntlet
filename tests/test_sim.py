"""Integration tests for the MuJoCo engine, MJCF build, and stress battery."""

import numpy as np
import trimesh

from battlebot_sim.arena.nhrl import build_arena
from battlebot_sim.materials.assign import NHRL_CLASSES
from battlebot_sim.mesh.segment import BotModel, segment_mesh
from battlebot_sim.sim.engine import SimEngine
from battlebot_sim.sim.battery import StressBattery, run_battery


def _make_bot(aluminum):
    """A two-cube + brace bot, all aluminium, in metres."""
    a = trimesh.creation.box(extents=(0.08, 0.08, 0.05))
    a.apply_translation((-0.10, 0, 0))
    b = trimesh.creation.box(extents=(0.08, 0.08, 0.05))
    b.apply_translation((0.10, 0, 0))
    bar = trimesh.creation.box(extents=(0.12, 0.02, 0.02))
    combined = trimesh.util.concatenate([a, b, bar])
    model = BotModel(combined, segment_mesh(combined))
    model.assign_material_to_all(aluminum)
    return model


def test_engine_compiles_and_steps(aluminum):
    arena = build_arena(NHRL_CLASSES["3lb"])
    bot = _make_bot(aluminum)
    engine = SimEngine(arena, bot)
    assert engine.model.ngeom >= 6 + len(bot.parts)  # arena + bot parts
    engine.reset()
    engine.set_pose(arena.center_point())
    for _ in range(100):
        engine.step()
    pos, quat = engine.get_pose()
    assert np.all(np.isfinite(pos)) and np.all(np.isfinite(quat))


def test_drop_produces_floor_contacts(aluminum):
    arena = build_arena(NHRL_CLASSES["3lb"])
    bot = _make_bot(aluminum)
    engine = SimEngine(arena, bot)
    engine.reset()
    engine.set_pose(np.array([0.0, 0.0, 0.3]))  # above the floor
    saw_contact = False
    for _ in range(2000):
        engine.step()
        if any(c["other"] == "floor" for c in engine.read_contacts()):
            saw_contact = True
            break
    assert saw_contact, "bot never contacted the floor after a drop"


def test_full_battery_runs(aluminum):
    arena = build_arena(NHRL_CLASSES["12lb"])
    bot = _make_bot(aluminum)
    engine = SimEngine(arena, bot)
    battery = StressBattery(arena, NHRL_CLASSES["12lb"])
    trace = run_battery(engine, battery, fps=30)

    assert len(battery.events) >= 6
    assert len(trace.frames) > 0
    assert trace.total_contacts() > 0
    # Every contact maps to a real part and carries finite force.
    for c in trace.contacts:
        assert 0 <= c.part_index < len(bot.parts)
        assert np.isfinite(c.normal_force)
    # The opponent strike should be represented.
    assert any(c.other == "opponent_weapon" for c in trace.contacts)


def test_overweight_bot_still_simulates(aluminum):
    # Steel-dense scaling is irrelevant here; just confirm no crash with a big bot.
    arena = build_arena(NHRL_CLASSES["30lb"])
    bot = _make_bot(aluminum)
    engine = SimEngine(arena, bot)
    engine.set_pose(arena.center_point())
    for _ in range(200):
        engine.step()
    assert np.all(np.isfinite(engine.get_pose()[0]))
