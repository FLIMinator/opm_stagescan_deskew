"""Stage-scan OPM deskewing utilities.

The core package works on one 3-D ``(plane, y, x)`` acquisition volume at a
time. Experiment dimensions such as time, channel, view and position are left
to the surrounding workflow.
"""

from .deskew import deskew_stage_scan

__all__ = ["deskew_stage_scan"]
