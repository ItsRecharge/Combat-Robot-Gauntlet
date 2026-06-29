"""Damage modelling: turn a SimTrace into per-face energy and failure fields,
including brace load-sharing."""

from gauntlet.damage.braces import apply_brace_sharing
from gauntlet.damage.fields import normalize, vertex_scalars
from gauntlet.damage.model import DamageResult, compute_damage

__all__ = [
    "DamageResult",
    "compute_damage",
    "apply_brace_sharing",
    "normalize",
    "vertex_scalars",
]
