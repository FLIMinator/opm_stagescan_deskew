"""TIFF loading for the Micro-Manager layouts used by this workflow.

This handles the two forms used in the original scripts: an ``NDTiffStack``
file, or a directory containing an OME-TIFF series. It returns one 3-D volume;
experiment dimensions are handled by the workflow rather than this reader.
"""

from pathlib import Path

import numpy as np
from tifffile import TiffFile


def load_micromanager_stack(folder):
    """Load one Micro-Manager camera folder as ``(plane, y, x)``."""
    folder = Path(folder)

    ndtiff_files = sorted(
        p for p in folder.iterdir()
        if "NDTiffStack" in p.name and p.suffix.lower() == ".tif"
    )
    if ndtiff_files:
        with TiffFile(ndtiff_files[0]) as tif:
            return tif.asarray()

    ome_files = sorted(folder.glob("*.ome.tif"))
    if ome_files:
        planes = []
        for path in ome_files:
            with TiffFile(path) as tif:
                for page in tif.pages:
                    planes.append(page.asarray())
        return np.stack(planes, axis=0)

    raise FileNotFoundError(f"No supported Micro-Manager TIFF data in {folder}")
