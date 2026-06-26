"""Tests for segmentation and aggregate mass properties."""

import numpy as np
import trimesh

from battlebot_sim.mesh.segment import BotModel, segment_mesh


def test_segment_splits_disjoint_solids(two_box_bot):
    a, b, bar = two_box_bot
    combined = trimesh.util.concatenate([a, b, bar])
    parts = segment_mesh(combined)
    assert len(parts) == 3
    # Face ids partition the original faces exactly.
    all_faces = np.concatenate([p.face_ids for p in parts])
    assert sorted(all_faces.tolist()) == list(range(len(combined.faces)))


def test_single_solid_is_one_part(alu_cube_10cm):
    parts = segment_mesh(alu_cube_10cm)
    assert len(parts) == 1


def test_cube_mass_matches_density(alu_cube_10cm, aluminum):
    model = BotModel(alu_cube_10cm, segment_mesh(alu_cube_10cm))
    model.assign_material_to_all(aluminum)
    # 0.1 m cube = 1e-3 m^3; * 2700 kg/m^3 = 2.70 kg.
    assert np.isclose(model.total_mass(), 2.70, rtol=1e-3)


def test_cube_inertia_matches_analytic(alu_cube_10cm, aluminum):
    model = BotModel(alu_cube_10cm, segment_mesh(alu_cube_10cm))
    model.assign_material_to_all(aluminum)
    inertia = model.inertia_tensor()
    # Solid cube: I = (1/6) m a^2 about each principal axis.
    m, a = 2.70, 0.1
    expected = (1.0 / 6.0) * m * a**2  # = 0.0045
    diag = np.diag(inertia)
    assert np.allclose(diag, expected, rtol=1e-3)
    # Off-diagonal terms should be ~0 for an axis-aligned cube at origin.
    off = inertia - np.diag(diag)
    assert np.allclose(off, 0.0, atol=1e-6)


def test_center_of_mass_of_symmetric_pair(aluminum):
    # Two equal cubes symmetric about origin -> COM at origin.
    a = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
    a.apply_translation((-0.2, 0, 0))
    b = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
    b.apply_translation((0.2, 0, 0))
    combined = trimesh.util.concatenate([a, b])
    model = BotModel(combined, segment_mesh(combined))
    model.assign_material_to_all(aluminum)
    assert np.allclose(model.center_of_mass(), [0, 0, 0], atol=1e-6)


def test_merge_reduces_part_count(two_box_bot, aluminum):
    a, b, bar = two_box_bot
    combined = trimesh.util.concatenate([a, b, bar])
    model = BotModel(combined, segment_mesh(combined))
    model.assign_material_to_all(aluminum)
    before = len(model.parts)
    mass_before = model.total_mass()
    model.merge([0, 1])
    assert len(model.parts) == before - 1
    # Mass is conserved across a merge.
    assert np.isclose(model.total_mass(), mass_before, rtol=1e-6)
