"""Core stage-scan OPM deskewing.

This module deliberately contains no microscope-folder or Micro-Manager logic.
It expects one raw stage-scan OPM volume with axes ``(plane, camera_y,
camera_x)`` and reconstructs one Cartesian ``(z, y, x)`` volume.

``theta_acq`` controls the physical acquisition geometry. ``theta_interp`` is
optional and only changes where samples are taken *within* neighbouring raw
planes during interpolation; it does not change the deskew geometry itself.
"""

import math

import numpy as np
from numba import njit, prange


@njit
def bin_3d_stack_xy(stack, bin_size):
    """Average-bin the camera ``y`` and ``x`` axes of a 3-D stack."""
    z, y, x = stack.shape
    yb = y // bin_size
    xb = x // bin_size
    result = np.zeros((z, yb, xb), dtype=stack.dtype)

    for k in range(z):
        for j in range(yb):
            for i in range(xb):
                block_sum = 0.0
                for jj in range(bin_size):
                    for ii in range(bin_size):
                        block_sum += stack[k, j * bin_size + jj, i * bin_size + ii]
                result[k, j, i] = block_sum / (bin_size * bin_size)

    return result


@njit(parallel=True)
def _reslice_stage_scan(
    data_stack,
    theta_acq,
    theta_interp,
    pixel_size,
    scan_step,
    acquisition_offset,
    zero_value=0,
):
    """Inverse-resample a raw oblique stage scan onto a Cartesian output grid."""
    nimg, size_y, size_x = data_stack.shape

    step = scan_step / pixel_size
    tan_theta_acq = math.tan(theta_acq)
    sin_theta_acq = math.sin(theta_acq)
    cos_theta_acq = math.cos(theta_acq)

    scan_end = nimg * scan_step / pixel_size
    nz_out = int(np.ceil(size_y * sin_theta_acq))
    ny_out = int(np.ceil(scan_end + size_y * cos_theta_acq))

    output = np.full((nz_out, ny_out, size_x), zero_value, dtype=np.uint16)

    # theta_interp changes only the in-plane sampling offset between adjacent
    # acquisition planes. A negative value selects the default geometric case.
    if theta_interp < 0.0:
        inplane_sample_shift = cos_theta_acq
    else:
        inplane_sample_shift = (
            cos_theta_acq + sin_theta_acq / math.tan(theta_interp)
        )

    for z_out in prange(nz_out):
        raw_y_at_z = z_out / sin_theta_acq
        y_start = max(int(math.floor(z_out / tan_theta_acq)), 0)
        y_stop = min(int(math.ceil(scan_end + z_out / tan_theta_acq)), ny_out)

        for y_out in range(y_start, y_stop):
            # Position of this output voxel along the acquired stage-scan axis.
            virtual_plane = (
                y_out
                - z_out / tan_theta_acq
                - acquisition_offset / pixel_size
            )
            plane_before = int(math.floor(virtual_plane / step))

            if 0 <= plane_before < nimg - 1:
                frac_after = (virtual_plane - plane_before * step) / step
                frac_before = 1.0 - frac_after

                # Fetch the corresponding in-plane positions from the two
                # neighbouring acquired images. theta_interp modifies only this
                # in-plane lookup direction.
                pos_before_f = raw_y_at_z + frac_after * inplane_sample_shift
                pos_after_f = raw_y_at_z - frac_before * inplane_sample_shift

                pos_before = int(math.floor(pos_before_f))
                pos_after = int(math.floor(pos_after_f))

                if (1 <= pos_before < size_y - 1) and (1 <= pos_after < size_y - 1):
                    dy_before = pos_before_f - pos_before
                    dy_after = pos_after_f - pos_after

                    plane_earlier = data_stack[plane_before]
                    plane_later = data_stack[plane_before + 1]

                    # Bilinear interpolation using two adjacent acquisition
                    # planes and two neighbouring samples within each plane.
                    w1 = frac_after * dy_after
                    w2 = frac_after * (1.0 - dy_after)
                    w3 = frac_before * dy_before
                    w4 = frac_before * (1.0 - dy_before)

                    for x in range(size_x):
                        value = (
                            w1 * plane_later[pos_after, x]
                            + w2 * plane_later[pos_after - 1, x]
                            + w3 * plane_earlier[pos_before, x]
                            + w4 * plane_earlier[pos_before - 1, x]
                        )
                        output[z_out, y_out, x] = min(
                            65535, max(0, int(value + 0.5))
                        )

    return output


def subsample_planes(stack, plane_stride=1, scan_step_um=1.0):
    """Subsample acquisition planes and return the corresponding scan step."""
    if plane_stride == 1:
        return stack, scan_step_um
    return stack[::plane_stride], scan_step_um * plane_stride


def deskew_stage_scan(
    stack,
    pixel_size_um,
    scan_step_um,
    theta_deg,
    *,
    binning=1,
    plane_stride=1,
    theta_interp_deg=None,
    acquisition_offset_um=0.0,
    reverse_plane_order=False,
):
    """Deskew one stage-scanned OPM volume.

    Parameters
    ----------
    stack : numpy.ndarray
        Raw volume with shape ``(plane, camera_y, camera_x)``.
    pixel_size_um : float
        Camera-plane pixel size in micrometres before software binning.
    scan_step_um : float
        Physical stage displacement between successive acquired planes.
    theta_deg : float
        Oblique acquisition-plane angle in degrees.
    binning : int, optional
        Integer XY software binning applied before deskewing.
    plane_stride : int, optional
        Keep every Nth acquisition plane. The effective scan step is increased
        by the same factor.
    theta_interp_deg : float or None, optional
        Optional interpolation-axis angle. This changes only the in-plane
        sampling offset used between neighbouring acquisition planes.
    acquisition_offset_um : float, optional
        Constant offset along the acquisition scan direction.
    reverse_plane_order : bool, optional
        Reverse the acquisition-plane sequence before reconstruction when the
        source data were stored opposite to the expected scan direction.

    Returns
    -------
    numpy.ndarray
        Deskewed ``uint16`` volume with axes ``(z, y, x)``.
    """
    data = np.asarray(stack)
    if data.ndim != 3:
        raise ValueError("stack must have shape (plane, y, x)")

    if reverse_plane_order:
        data = data[::-1]

    if binning > 1:
        data = bin_3d_stack_xy(data, binning)

    data, effective_scan_step = subsample_planes(
        data,
        plane_stride=plane_stride,
        scan_step_um=scan_step_um,
    )

    theta_acq = math.radians(theta_deg)
    theta_interp = (
        -1.0 if theta_interp_deg is None else math.radians(theta_interp_deg)
    )

    return _reslice_stage_scan(
        data,
        theta_acq,
        theta_interp,
        pixel_size_um * binning,
        effective_scan_step,
        acquisition_offset_um,
    )
