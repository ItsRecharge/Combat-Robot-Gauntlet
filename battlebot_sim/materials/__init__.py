"""Material definitions, the preset library, and weight-class validation."""

from battlebot_sim.materials.library import Material, MaterialLibrary, load_default_library
from battlebot_sim.materials.assign import WeightClass, NHRL_CLASSES, validate_weight_class

__all__ = [
    "Material",
    "MaterialLibrary",
    "load_default_library",
    "WeightClass",
    "NHRL_CLASSES",
    "validate_weight_class",
]
