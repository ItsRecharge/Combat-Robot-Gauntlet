"""Load an STL, split it into parts, and aggregate mass properties.

Geometry is kept in SI metres throughout. STL files carry no units, so `load_bot`
accepts a `scale_to_m` factor (e.g. 0.001 for a millimetre STL). Mass properties
(mass, centre of mass, inertia tensor) are derived from per-part volume and the
assigned material density.

Non-watertight parts have an ill-defined volume; for those we fall back to the
convex hull so mass stays positive and finite, and flag the part so the UI can
warn the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from battlebot_sim.materials.library import Material


def _mass_properties(mesh: trimesh.Trimesh, density: float):
    """Return (mass_kg, center_mass(3,), inertia(3,3)) for `mesh` at `density`.

    Inertia is taken about the mesh's own centre of mass. Falls back to the
    convex hull when the mesh is not watertight (volume otherwise unreliable).
    """
    source = mesh if mesh.is_watertight else mesh.convex_hull
    source = source.copy()
    source.density = float(density)
    mass = float(source.mass)
    com = np.asarray(source.center_mass, dtype=float)
    inertia = np.asarray(source.moment_inertia, dtype=float)
    return mass, com, inertia


def _shift_inertia(inertia: np.ndarray, mass: float, offset: np.ndarray) -> np.ndarray:
    """Parallel-axis shift of an inertia tensor by `offset` (com -> new point)."""
    d = np.asarray(offset, dtype=float)
    return inertia + mass * (float(d @ d) * np.eye(3) - np.outer(d, d))


@dataclass
class Part:
    """One connected solid chunk of the bot mesh, with an optional material."""

    index: int
    mesh: trimesh.Trimesh
    face_ids: np.ndarray                 # indices into the original mesh's faces
    name: str = ""
    material: Material | None = None
    is_brace: bool = False
    watertight_fallback: bool = field(init=False, default=False)

    def __post_init__(self):
        if not self.name:
            self.name = f"part_{self.index}"
        self.watertight_fallback = not bool(self.mesh.is_watertight)

    @property
    def volume_m3(self) -> float:
        src = self.mesh if self.mesh.is_watertight else self.mesh.convex_hull
        return abs(float(src.volume))

    @property
    def surface_area_m2(self) -> float:
        return float(self.mesh.area)

    @property
    def centroid(self) -> np.ndarray:
        return np.asarray(self.mesh.centroid, dtype=float)

    @property
    def bounds(self) -> np.ndarray:
        return np.asarray(self.mesh.bounds, dtype=float)

    @property
    def mass_kg(self) -> float:
        if self.material is None:
            return 0.0
        return self.volume_m3 * self.material.density

    def mass_properties(self):
        """(mass, com, inertia-about-own-com). Zero mass if no material yet."""
        if self.material is None:
            return 0.0, self.centroid, np.zeros((3, 3))
        return _mass_properties(self.mesh, self.material.density)


def segment_mesh(mesh: trimesh.Trimesh) -> list[Part]:
    """Split a mesh into parts by connected components of the face graph.

    Each disconnected solid chunk becomes one Part. Face indices into the
    original mesh are preserved so damage can be mapped back to the source faces.
    """
    n_faces = len(mesh.faces)
    if n_faces == 0:
        return []

    adjacency = mesh.face_adjacency  # (k, 2) pairs of touching faces
    components = trimesh.graph.connected_components(
        adjacency, nodes=np.arange(n_faces)
    )
    # Order parts largest-first for stable, intuitive numbering.
    components = sorted(components, key=len, reverse=True)

    parts: list[Part] = []
    for i, face_ids in enumerate(components):
        face_ids = np.asarray(face_ids, dtype=np.int64)
        submesh = mesh.submesh([face_ids], append=False, repair=False)[0]
        parts.append(Part(index=i, mesh=submesh, face_ids=face_ids))
    return parts


class BotModel:
    """A segmented bot: the original mesh plus its parts and aggregate properties."""

    def __init__(self, original: trimesh.Trimesh, parts: list[Part]):
        self.original = original
        self.parts = parts

    # ---- editing ---------------------------------------------------------
    def assign_material(self, part_index: int, material: Material) -> None:
        self.parts[part_index].material = material

    def assign_material_to_all(self, material: Material) -> None:
        for p in self.parts:
            p.material = material

    def set_brace(self, part_index: int, is_brace: bool = True) -> None:
        self.parts[part_index].is_brace = is_brace

    def merge(self, indices: list[int]) -> None:
        """Merge several parts into one, keeping the lowest index's material."""
        indices = sorted(set(indices))
        if len(indices) < 2:
            return
        keep = self.parts[indices[0]]
        merged_faces = np.concatenate([self.parts[i].face_ids for i in indices])
        merged_mesh = self.original.submesh([merged_faces], append=True, repair=False)
        new_part = Part(
            index=keep.index,
            mesh=merged_mesh,
            face_ids=merged_faces,
            name=keep.name,
            material=keep.material,
            is_brace=any(self.parts[i].is_brace for i in indices),
        )
        remaining = [p for j, p in enumerate(self.parts) if j not in indices]
        remaining.insert(0, new_part)
        self.parts = self._reindex(remaining)

    @staticmethod
    def _reindex(parts: list[Part]) -> list[Part]:
        for new_i, p in enumerate(parts):
            p.index = new_i
        return parts

    # ---- aggregate mass properties --------------------------------------
    def total_mass(self) -> float:
        return float(sum(p.mass_kg for p in self.parts))

    def center_of_mass(self) -> np.ndarray:
        m_total = self.total_mass()
        if m_total <= 0:
            return np.asarray(self.original.centroid, dtype=float)
        acc = np.zeros(3)
        for p in self.parts:
            m, com, _ = p.mass_properties()
            acc += m * com
        return acc / m_total

    def inertia_tensor(self) -> np.ndarray:
        """Inertia tensor (3x3, kg*m^2) about the bot's centre of mass."""
        com_total = self.center_of_mass()
        inertia = np.zeros((3, 3))
        for p in self.parts:
            m, com, i_local = p.mass_properties()
            if m <= 0:
                continue
            inertia += _shift_inertia(i_local, m, com_total - com)
        return inertia

    def assigned(self) -> bool:
        """True once every part has a material."""
        return all(p.material is not None for p in self.parts)


def load_bot(path: str, scale_to_m: float = 1.0) -> BotModel:
    """Load an STL from `path`, scale into metres, and segment it into parts."""
    mesh = trimesh.load(path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"{path!r} did not load as a single triangle mesh")
    if scale_to_m != 1.0:
        mesh.apply_scale(float(scale_to_m))
    parts = segment_mesh(mesh)
    return BotModel(original=mesh, parts=parts)
