"""Micro-Manager workflow for the current stage-scanning OPM/dOPM layout.

The folder parsing and view-dependent flips in this file are *system-specific*
acquisition conventions. They are intentionally kept outside the general
stage-scan deskew algorithm.
"""

import argparse
import gc
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import tifffile

from opm_deskew.deskew import deskew_stage_scan
from opm_deskew.io.micromanager import load_micromanager_stack


def get_tp_indices(folder_name):
    """Extract ``t`` and ``p`` indices from a folder name such as ``t001_p003``."""
    match = re.search(r"t(\d+)_p(\d+)", folder_name)
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)


def reverse_input_planes_for_system(folder_path):
    """Return whether this particular dOPM acquisition stores planes reversed.

    Both current view folders are reversed before deskewing. This is an
    acquisition convention of the microscope/workflow, not a general OPM rule.
    """
    folder_lower = str(folder_path).lower()
    if "view1" in folder_lower or "view2" in folder_lower:
        return True
    raise ValueError("Cannot determine view from folder name")


def flip_output_for_system(folder_path):
    """Return whether this system's reconstructed output needs a final Z flip."""
    return "view2" in str(folder_path).lower()


def find_camera_folders(root_dir):
    """Find Micro-Manager camera folders used by the current acquisition layout."""
    return [
        os.path.join(root, directory)
        for root, directories, _ in os.walk(root_dir)
        for directory in directories
        if "Hamamatsu" in directory
    ]


def _process_single_folder(params):
    """Load, deskew and save one camera folder inside a worker process."""
    (
        folder,
        out_dir,
        pixel_size_um,
        scan_step_um,
        theta_deg,
        theta_interp_deg,
        acquisition_offset_um,
        binning,
        plane_stride,
        save_mip,
    ) = params

    try:
        base_name = os.path.basename(os.path.dirname(folder))
        start = time.perf_counter()

        stack = load_micromanager_stack(folder)
        resliced = deskew_stage_scan(
            stack,
            pixel_size_um=pixel_size_um,
            scan_step_um=scan_step_um,
            theta_deg=theta_deg,
            binning=binning,
            plane_stride=plane_stride,
            theta_interp_deg=theta_interp_deg,
            acquisition_offset_um=acquisition_offset_um,
            reverse_plane_order=reverse_input_planes_for_system(folder),
        )

        # This view-2 flip normalises the output orientation for the current
        # dual-view system. Other microscopes may need different conventions.
        if flip_output_for_system(folder):
            resliced = np.flip(resliced, axis=0)

        os.makedirs(out_dir, exist_ok=True)
        tifffile.imwrite(os.path.join(out_dir, f"{base_name}.tif"), resliced)

        if save_mip:
            tifffile.imwrite(
                os.path.join(out_dir, f"{base_name}_MIP.tif"),
                np.max(resliced, axis=0),
            )

        elapsed = time.perf_counter() - start
        return f"Done: {base_name} ({elapsed:.2f}s)"
    except Exception as exc:
        return f"Error {folder}: {exc}"
    finally:
        gc.collect()


def batch_process_micromanager(
    root_dir,
    output_dir,
    pixel_size_um,
    scan_step_um,
    theta_deg,
    *,
    theta_interp_deg=None,
    acquisition_offset_um=0.0,
    binning=1,
    plane_stride=1,
    workers=8,
    live_mode=False,
    resume=True,
    save_mip=True,
):
    """Process all matching camera folders in one Micro-Manager acquisition."""
    subfolders = find_camera_folders(root_dir)

    # In live mode, leave the newest time/position folder alone because it may
    # still be receiving data from Micro-Manager.
    if live_mode:
        folder_data = []
        for folder in subfolders:
            t, p = get_tp_indices(os.path.basename(os.path.dirname(folder)))
            if t is not None:
                folder_data.append((folder, t, p))

        if folder_data:
            max_t = max(item[1] for item in folder_data)
            max_p = max(item[2] for item in folder_data if item[1] == max_t)
            subfolders = [
                item[0]
                for item in folder_data
                if not (item[1] == max_t and item[2] == max_p)
            ]

    if resume and os.path.exists(output_dir):
        existing = {
            filename.removesuffix(".tif")
            for filename in os.listdir(output_dir)
            if filename.endswith(".tif") and not filename.endswith("_MIP.tif")
        }
        subfolders = [
            folder
            for folder in subfolders
            if os.path.basename(os.path.dirname(folder)) not in existing
        ]

    if not subfolders:
        print("Nothing new to process.")
        return

    tasks = [
        (
            folder,
            output_dir,
            pixel_size_um,
            scan_step_um,
            theta_deg,
            theta_interp_deg,
            acquisition_offset_um,
            binning,
            plane_stride,
            save_mip,
        )
        for folder in subfolders
    ]

    print(
        f"Starting parallel processing on {len(tasks)} folders "
        f"using {workers} workers..."
    )

    with ProcessPoolExecutor(max_workers=workers) as executor:
        for result in executor.map(_process_single_folder, tasks):
            print(result)


def main():
    """Command-line entry point for the Micro-Manager workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--pixel-size", type=float, required=True, dest="pixel_size_um")
    parser.add_argument("--scan-step", type=float, required=True, dest="scan_step_um")
    parser.add_argument("--theta", type=float, required=True, dest="theta_deg")
    parser.add_argument("--binning", type=int, default=1)
    parser.add_argument("--plane-stride", type=int, default=1)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--theta-interp", type=float, default=None, dest="theta_interp_deg")
    parser.add_argument("--live", action="store_true", dest="live_mode")
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    parser.add_argument("--no-mip", action="store_false", dest="save_mip")
    args = parser.parse_args()

    batch_process_micromanager(**vars(args))


if __name__ == "__main__":
    main()
