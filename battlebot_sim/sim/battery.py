"""The automated stress battery: a deterministic sequence of combat-like events,
scaled by NHRL weight class, that fling the bot around the cage.

Events:
- drops      : released from near the ceiling at several orientations
- wall slams : launched into a wall at class speed and several incidence angles
- tumble     : launched spinning across the cage
- opponent   : a weapon strike modelled as a short, strong impulse at a face,
               which both physically launches the bot and emits a synthetic
               contact so the strike registers in the damage map

Energies scale with the class: heavier classes carry more kinetic energy and
absorb stronger weapon hits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from battlebot_sim.arena.nhrl import Arena
from battlebot_sim.materials.assign import WeightClass
from battlebot_sim.mesh.segment import BotModel
from battlebot_sim.sim.engine import SimEngine
from battlebot_sim.sim.recorder import ContactEvent, FrameSample, SimTrace


@dataclass
class Strike:
    """A scheduled opponent-weapon impulse during an event."""

    t_start: float
    t_end: float
    direction: np.ndarray     # unit force direction (into the bot)
    energy_j: float           # kinetic energy delivered


@dataclass
class BatteryEvent:
    """One scripted scenario the bot is put through."""

    name: str
    duration: float
    init_pos: np.ndarray
    init_quat: np.ndarray = field(default_factory=lambda: np.array([1.0, 0, 0, 0]))
    init_linvel: np.ndarray = field(default_factory=lambda: np.zeros(3))
    init_angvel: np.ndarray = field(default_factory=lambda: np.zeros(3))
    strike: Strike | None = None


def class_speed(wc: WeightClass) -> float:
    """Representative collision speed (m/s) for a class."""
    return {"3lb": 6.0, "12lb": 8.0, "30lb": 10.0}.get(wc.key, 7.0)


def class_strike_energy(wc: WeightClass) -> float:
    """Representative opponent-weapon energy (J): ~200 J per kg of class limit."""
    return 200.0 * wc.max_mass_kg


class StressBattery:
    """Builds and holds the list of events for a class + arena."""

    def __init__(self, arena: Arena, weight_class: WeightClass):
        self.arena = arena
        self.weight_class = weight_class
        self.events = self._build()

    def _build(self) -> list[BatteryEvent]:
        L, W, H = self.arena.interior
        v = class_speed(self.weight_class)
        e_strike = class_strike_energy(self.weight_class)
        drop_z = max(H * 0.85, 0.2)
        events: list[BatteryEvent] = []

        # --- drops at several orientations ---
        orientations = {
            "flat": np.array([1.0, 0, 0, 0]),
            "tilted": np.array([0.92, 0.38, 0, 0]),       # ~45 deg about X
            "corner": np.array([0.88, 0.33, 0.33, 0.0]),
        }
        for name, quat in orientations.items():
            events.append(BatteryEvent(
                name=f"drop_{name}", duration=1.2,
                init_pos=np.array([0.0, 0.0, drop_z]),
                init_quat=quat / np.linalg.norm(quat),
            ))

        # --- wall slams at several incidence angles ---
        for ang_deg in (0, 30, 60):
            a = np.radians(ang_deg)
            vel = np.array([np.cos(a), np.sin(a), 0.0]) * v
            events.append(BatteryEvent(
                name=f"wall_slam_{ang_deg}deg", duration=0.9,
                init_pos=np.array([-L * 0.3, 0.0, H * 0.4]),
                init_linvel=vel,
            ))

        # --- tumble across the cage ---
        events.append(BatteryEvent(
            name="tumble", duration=1.8,
            init_pos=np.array([-L * 0.25, -W * 0.2, H * 0.5]),
            init_linvel=np.array([v * 0.7, v * 0.4, 0.0]),
            init_angvel=np.array([8.0, 12.0, 5.0]),
        ))

        # --- opponent weapon strikes from two directions ---
        for name, d in (("side", np.array([-1.0, 0, 0])), ("top", np.array([0, 0, -1.0]))):
            events.append(BatteryEvent(
                name=f"opponent_{name}", duration=1.0,
                init_pos=np.array([0.0, 0.0, H * 0.25]),
                strike=Strike(t_start=0.15, t_end=0.16, direction=d, energy_j=e_strike),
            ))
        return events


def _quat_matrix(quat) -> np.ndarray:
    """Body->world rotation matrix from a MuJoCo (w, x, y, z) quaternion."""
    from scipy.spatial.transform import Rotation
    return Rotation.from_quat([quat[1], quat[2], quat[3], quat[0]]).as_matrix()


def _nearest_part(bot: BotModel, world_point: np.ndarray, pos, quat) -> int:
    """Index of the part whose (transformed) centroid is closest to a point."""
    R = _quat_matrix(quat)
    best, best_d = 0, np.inf
    for p in bot.parts:
        c = R @ p.centroid + pos
        d = np.linalg.norm(c - world_point)
        if d < best_d:
            best, best_d = p.index, d
    return best


def run_battery(engine: SimEngine, battery: StressBattery, fps: int = 30) -> SimTrace:
    """Run every event, recording bot poses (for replay) and contacts (for damage)."""
    dt = engine.timestep
    bot = engine.bot
    trace = SimTrace(dt=dt, n_parts=len(bot.parts))
    record_every = max(1, int(round((1.0 / fps) / dt)))

    # Bot half-size along each axis, for placing strike points on a face.
    half = (bot.original.bounds[1] - bot.original.bounds[0]) / 2.0
    center_local = bot.original.centroid
    mass = max(bot.total_mass(), 1e-6)

    t_global = 0.0
    for ev in battery.events:
        engine.reset()
        engine.clear_applied()
        engine.set_pose(ev.init_pos, ev.init_quat)
        engine.set_velocity(ev.init_linvel, ev.init_angvel)

        n_steps = int(round(ev.duration / dt))
        for s in range(n_steps):
            t_local = s * dt
            engine.clear_applied()

            pos, quat = engine.get_pose()
            R = _quat_matrix(quat)            # body -> world rotation

            # Scheduled opponent strike: physical impulse + synthetic contact.
            if ev.strike and ev.strike.t_start <= t_local < ev.strike.t_end:
                strike = ev.strike
                window = max(strike.t_end - strike.t_start, dt)
                dv = np.sqrt(2.0 * strike.energy_j / mass)
                force_mag = mass * dv / window
                # Land on the face whose outward normal opposes the strike dir.
                axis = int(np.argmax(np.abs(strike.direction)))
                offset = np.zeros(3)
                offset[axis] = -np.sign(strike.direction[axis]) * half[axis]
                local_point = center_local + offset
                world_point = R @ local_point + pos
                engine.apply_impulse(strike.direction * force_mag, world_point)
                trace.contacts.append(ContactEvent(
                    time=t_global + t_local, event=ev.name,
                    pos=world_point, local_pos=local_point, normal=-strike.direction,
                    normal_force=force_mag, tangential_force=0.0,
                    rel_speed=dv,
                    part_index=_nearest_part(bot, world_point, pos, quat),
                    other="opponent_weapon",
                ))

            engine.step()

            for c in engine.read_contacts():
                local_pos = R.T @ (c["pos"] - pos)
                trace.contacts.append(ContactEvent(
                    time=t_global + t_local, event=ev.name,
                    pos=c["pos"], local_pos=local_pos, normal=c["normal"],
                    normal_force=c["normal_force"],
                    tangential_force=c["tangential_force"],
                    rel_speed=c["rel_speed"],
                    part_index=c["part_index"], other=c["other"],
                ))

            if s % record_every == 0:
                trace.frames.append(FrameSample(
                    time=t_global + t_local, pos=pos, quat=quat, event=ev.name))

        t_global += ev.duration
    return trace
