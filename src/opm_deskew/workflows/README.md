# Micro-Manager stage-scan workflow

This folder contains acquisition-specific workflow code built around the general stage-scan OPM deskew routine.

The core deskew function works on one `(plane, y, x)` volume at a time. The workflow here adds the parts needed for the current Micro-Manager stage-scanning OPM/dOPM acquisition: finding volumes on disk, applying the acquisition orientation convention, processing folders in parallel, and writing outputs.

## What the workflow expects

`batch_process_micromanager()` starts from a Micro-Manager acquisition root and searches below it for camera folders whose names contain `Hamamatsu`.

Inside each camera folder it supports either:

- an `NDTiffStack*.tif` stack; or
- an OME-TIFF series (`*.ome.tif`).

The parent acquisition folders are expected to contain names such as:

```text
t000_p000
t000_p001
t001_p000
```

The `t##_p##` indices are used only by the live-mode workflow. They are not part of the deskew calculation.

## Current dOPM orientation convention

The orientation handling in `micromanager.py` is specific to the current dOPM acquisition setup.

For both `view1` and `view2`, the acquired plane sequence is reversed before deskewing. After reconstruction, `view2` is additionally flipped along output `z` so that its reconstructed orientation follows the convention used for the current dual-view workflow.

These are not general rules for OPM or Micro-Manager data. A different microscope, scan direction, optical layout, or storage convention may require different orientation handling.

The deskew algorithm itself is independent of these choices.

## Basic use

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

Each discovered camera folder is loaded as one `(plane, y, x)` volume, deskewed, and saved as a TIFF. By default a maximum-intensity projection is also written.

## `resume`

With `resume=True` (the default), the workflow checks the output directory before processing. If the deskewed TIFF for a volume is already present, that volume is skipped.

This is useful when processing is interrupted or when the same acquisition folder is scanned repeatedly for new data.

```python
resume=True
```

means:

```text
already has output -> skip
no output yet       -> process
```

Use `resume=False` if you deliberately want to reprocess everything.

## `live_mode`

`live_mode=True` is intended for running the workflow while Micro-Manager is still acquiring data.

The workflow finds the highest time index and then the highest position index within that time point. That newest `t/p` folder is skipped because it may still be receiving data.

For example:

```text
t000_p000   eligible
t000_p001   eligible
t000_p002   newest -> skipped in live mode
```

Once acquisition advances to a newer folder, the previously skipped folder becomes eligible on the next run.

This is deliberately a simple acquisition-order heuristic. It does not inspect file locks or attempt to determine whether individual TIFF files are actively being written.

## Using `live_mode` and `resume` together

The two options are designed to work together.

With:

```python
live_mode=True
resume=True
```

the workflow processes only volumes that:

1. are not the newest `t/p` folder; and
2. do not already have a deskewed output.

For example:

```text
t000_p000   already processed    -> skip
t000_p001   already processed    -> skip
t000_p002   new                  -> process
t000_p003   newest / potentially live -> skip
```

On a later run, once `t000_p004` exists, `t000_p003` is no longer considered the live folder and can be processed.

This makes it possible to rerun the command periodically during a long acquisition without repeatedly deskewing completed volumes.

## Other experiment dimensions

The workflow handles the particular folder organisation used by the current Micro-Manager acquisition. The core package does not generally manage dimensions such as:

```text
time x channel x view x position x volume
```

For a different experiment layout, the surrounding workflow should decide how those dimensions are enumerated and then pass each individual `(plane, y, x)` stage-scan volume to `deskew_stage_scan()`.

This keeps the numerical reconstruction separate from experiment organisation.

## Command-line example

```bash
opm-deskew-mm Z:\path\to\acquisition D:\temp\resliced \
    --pixel-size 0.35 \
    --scan-step 2.0 \
    --theta 35 \
    --binning 4 \
    --workers 12 \
    --live
```

`resume` is enabled by default. Pass `--no-resume` to reprocess existing outputs.

The notebook `notebooks/01_micromanager_stage_scan.ipynb` demonstrates the same workflow interactively.
