"""Material definitions, the preset library, and weight-class validation."""

from gauntlet.materials.assign import NHRL_CLASSES, WeightClass, validate_weight_class
from gauntlet.materials.library import Material, MaterialLibrary, load_default_library

__all__ = [
    "Material",
    "MaterialLibrary",
    "load_default_library",
    "WeightClass",
    "NHRL_CLASSES",
    "validate_weight_class",
]
