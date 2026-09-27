"""Small input helpers for TIFF-based OPM data."""

from .tiff import load_tiff_stack
from .micromanager import load_micromanager_stack

__all__ = ["load_tiff_stack", "load_micromanager_stack"]
