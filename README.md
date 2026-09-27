# OPM deskew

A small Python package for deskewing **stage-scanned oblique plane microscopy (OPM)** data.

The main design goal is to keep the actual deskew geometry separate from microscope- and acquisition-specific code. The core routine operates on one 3-D volume at a time. A Micro-Manager workflow is included for the folder structure and dual-view orientation conventions used by the current stage-scanning dOPM acquisition.

## Scope

The core deskew function accepts one NumPy array with axes:

```text
(plane, camera_y, camera_x)
```

and reconstructs one Cartesian volume with axes:

```text
(z, y, x)
```

It does **not** manage experiment dimensions such as time, channel, view, stage position or tile. Those dimensions describe how multiple 3-D volumes are organised and should be handled by the caller's workflow.

For example, a larger acquisition may conceptually be organised as:

```text
time × position × view × channel × (plane, y, x)
```

A workflow should extract each individual `(plane, y, x)` volume, apply the appropriate acquisition-orientation convention, deskew it, and preserve its time/channel/view/position identity in the output organisation.

## Stage-scan deskew geometry

In a stage-scanned OPM acquisition, the first array axis is not a Cartesian `z` axis. Each image is an oblique plane, and successive images correspond to translated positions of that plane during the stage scan.

The deskew routine inverse-resamples the raw acquisition directly onto a Cartesian output grid. For each output voxel it determines the two acquired planes that bracket that position and interpolates between samples from those planes.

`theta_acq` (exposed as `theta_deg`) defines the physical orientation of the acquired oblique plane and therefore the deskew geometry.

`theta_interp` is separate. It does **not** change the deskew transform or the location of the output voxel. It changes where, within neighbouring raw planes, intensity samples are taken for interpolation. This allows the interpolation direction to be adjusted independently of the acquisition-plane geometry, for example when using an interpolation direction related to the effective tilted detection PSF.

## Input orientation

The general deskew algorithm assumes that the input volume has a known interpretation:

- `plane` indexes successive images acquired during the stage scan;
- consecutive plane indices are separated by the supplied physical scan step;
- `camera_y` is the in-plane direction involved in the deskew geometry;
- `camera_x` is the orthogonal in-plane direction;
- the sign/order of the acquisition planes and camera axes is known.

The core algorithm does not require one universal microscope orientation. If a dataset was stored with the opposite acquisition-plane order, reverse that order before deskewing or pass `reverse_plane_order=True`.

Camera mounting, optical reflections, scan direction and software storage conventions can all affect orientation. In a dual-view system, the two views may also require different orientation normalisation after reconstruction. Those choices are acquisition-system conventions rather than part of the deskew mathematics.

The included Micro-Manager workflow therefore keeps the current dOPM view/flip rules in `workflows/micromanager.py`, outside the core deskew code.

## Using the repo in VS Code

The repo should work directly in VS Code. The only VS Code extensions needed are:

- **Python** (`ms-python.python`) — needed to select the Python environment and run/debug Python code;
- **Jupyter** (`ms-toolsai.jupyter`) — needed only if you want to run the example notebooks inside VS Code.

Pylance and other linting/formatting extensions are optional; the package does not depend on them.

After cloning or downloading the repo, open the `opm-deskew` folder in VS Code, open a terminal, and create the environment:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -e ".[notebooks]"
```

Then use **Python: Select Interpreter** in VS Code and choose the `.venv` environment. The two notebooks in `notebooks/` can then be opened and run directly.

If you do not need the notebooks, install only the core package with `pip install -e .` and the Jupyter extension is not required.

## Installation

Create an environment and install the package in editable mode:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -e .
```

For the example notebooks:

```bash
pip install -e ".[notebooks]"
```

## Single TIFF stack

For one multipage TIFF containing a single stage-scan volume:

```python
from opm_deskew import deskew_stage_scan
from opm_deskew.io import load_tiff_stack
import tifffile

stack = load_tiff_stack("stage_scan.tif")

result = deskew_stage_scan(
    stack,
    pixel_size_um=0.35,
    scan_step_um=2.0,
    theta_deg=35,
    binning=4,
)

tifffile.imwrite("deskewed.tif", result)
```

A generic TIFF does not contain enough information for this package to infer the microscope's scan direction or view orientation automatically. The user/workflow is responsible for supplying the stack in the expected acquisition order.

See `notebooks/02_single_tiff_stack.ipynb` for the same example interactively.

## Micro-Manager stage-scan workflow

The included workflow supports the two TIFF layouts used by the original scripts:

- an `NDTiffStack*.tif` file inside a camera folder;
- an OME-TIFF series inside a camera folder.

It also retains the current useful folder behaviour:

- finding `Hamamatsu` camera folders;
- parsing `t##_p##` folder names;
- optional live-mode protection for the newest time/position;
- resume behaviour;
- parallel processing;
- optional MIP output;
- current dOPM input/output orientation rules for `view1` and `view2`.

Python usage:

```python
from opm_deskew.workflows.micromanager import batch_process_micromanager

batch_process_micromanager(
    root_dir=r"Z:\path\to\acquisition",
    output_dir=r"D:\temp\resliced",
    pixel_size_um=0.35,
    scan_step_um=2.0,
    theta_deg=35,
    binning=4,
    workers=12,
)
```

Command-line usage:

```bash
opm-deskew-mm Z:\path\to\acquisition D:\temp\resliced \
    --pixel-size 0.35 \
    --scan-step 2.0 \
    --theta 35 \
    --binning 4 \
    --workers 12
```

See `notebooks/01_micromanager_stage_scan.ipynb` for a compact notebook version.

## File layout

```text
opm-deskew/
├── pyproject.toml
├── README.md
├── src/
│   └── opm_deskew/
│       ├── deskew.py
│       ├── io/
│       │   ├── tiff.py
│       │   └── micromanager.py
│       └── workflows/
│           └── micromanager.py
└── notebooks/
    ├── 01_micromanager_stage_scan.ipynb
    └── 02_single_tiff_stack.ipynb
```

The separation is intentional:

```text
input format / experiment workflow
              ↓
      one (plane, y, x) volume
              ↓
       stage-scan OPM deskew
              ↓
         one (z, y, x) volume
```

Suporting work:

The stage-scanning OPM reconstruction approach used here is related to the reconstruction methods described by Vincent Maioli in his PhD thesis, *High-speed 3-D fluorescence imaging by oblique plane microscopy: multi-well plate-reader development, biological applications and image analysis*. The thesis discusses the reconstruction of stage-scanned OPM data and the influence of reconstruction choices on the final image.

Maioli, V. A. (2016), *High-speed 3-D fluorescence imaging by oblique plane microscopy: multi-well plate-reader development, biological applications and image analysis*, PhD thesis, Imperial College London. DOI: 10.25560/68022.