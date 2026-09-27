"""Generic TIFF loading for one 3-D volume.

The loader intentionally does not interpret time, channel, view or position.
Those dimensions should be split into individual 3-D volumes by the caller.
"""

from pathlib import Path

import numpy as np
import tifffile


def load_tiff_stack(path):
    """Load one multipage TIFF or a directory of plane TIFFs as ``(plane,y,x)``."""
    path = Path(path)

    if path.is_file():
        stack = tifffile.imread(path)
        return np.asarray(stack)

    files = sorted(
        p for p in path.iterdir()
        if p.is_file() and p.suffix.lower() in {".tif", ".tiff"}
    )
    if not files:
        raise FileNotFoundError(f"No TIFF files found in {path}")

    planes = [tifffile.imread(p) for p in files]
    return np.stack(planes, axis=0)
