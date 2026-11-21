"""Pixel verifier for a native D2D bitmap rendered into an opaque HWND client."""
from __future__ import annotations

from fractions import Fraction
import hashlib
from pathlib import Path


SOURCE_WIDTH = 1920
SOURCE_HEIGHT = 1080
CHANNEL_TOLERANCE = 1
SOURCE_BOUNDARY_EPSILON = Fraction(1, 10000)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _frame_mismatch(x, y, source_xy, expected, actual, candidates=()):
    error = max(abs(a - b) for a, b in zip(expected, actual))
    return RuntimeError(
        'D2D_WINDOW_FRAME_PIXEL_MISMATCH '
        f'capture_xy=({x},{y}) source_xy={source_xy} '
        f'expected_rgba={expected} actual_rgba={actual} max_channel_error={error} '
        f'tolerance={CHANNEL_TOLERANCE} boundary_candidate_rgba={tuple(candidates)}')


def verify_frame(source_png: Path, capture_png: Path, width: int, height: int) -> dict:
    """Compare a nearest-sampled source frame with an opaque native HWND capture.

    Destination geometry and pixel-center sampling are derived here, independently
    of the native host. One-pixel bands around fractional destination edges are
    reported separately. Source coordinates within 1e-4 texel of an integer
    boundary may match either adjacent nearest-sampled texel; those pixels remain
    checked and are never discarded.
    """
    if type(width) is not int or type(height) is not int or not (0 < width <= 32768 and 0 < height <= 32768):
        raise ValueError('D2D_WINDOW_FRAME_INVALID_DIMENSIONS width and height must be positive and at most 32768')
    if width * height * 4 > 256 * 1024 * 1024:
        raise ValueError('D2D_WINDOW_FRAME_INVALID_DIMENSIONS capture exceeds the 256 MiB pixel bound')

    # Keep this import local: the frozen verifier closure records the dependency
    # on the existing strict PNG decoder without introducing a duplicate parser.
    from render_ui_popup import png_pixels

    source_png, capture_png = Path(source_png), Path(capture_png)
    source = png_pixels(source_png)
    capture = png_pixels(capture_png, expected_dimensions=(width, height))
    for pixel in range(width * height):
        alpha_offset = pixel * 4 + 3
        if capture[alpha_offset] != 255:
            x, y = pixel % width, pixel // width
            actual = tuple(capture[pixel * 4:pixel * 4 + 4])
            raise RuntimeError(
                'D2D_WINDOW_FRAME_CAPTURE_ALPHA_NOT_OPAQUE '
                f'capture_xy=({x},{y}) actual_rgba={actual} expected_alpha=255')
    scale = min(Fraction(width, SOURCE_WIDTH), Fraction(height, SOURCE_HEIGHT))
    display_width = SOURCE_WIDTH * scale
    display_height = SOURCE_HEIGHT * scale
    left = (Fraction(width) - display_width) / 2
    top = (Fraction(height) - display_height) / 2
    right, bottom = left + display_width, top + display_height

    def axis_samples(extent, source_extent, offset, axis_scale):
        far_edge = offset + axis_scale * source_extent
        rows = []
        for pos in range(extent):
            center = Fraction(2 * pos + 1, 2)
            inside = offset <= center < far_edge
            edge = ((offset.denominator != 1 and abs(center - offset) <= 1) or
                    (far_edge.denominator != 1 and abs(center - far_edge) <= 1))
            source_pos = (center - offset) / axis_scale if inside else None
            if source_pos is None:
                sample = None
                boundary = False
                candidates = ()
            else:
                sample = source_pos.numerator // source_pos.denominator
                nearest = round(float(source_pos))
                distance = abs(source_pos - nearest)
                boundary = distance <= SOURCE_BOUNDARY_EPSILON
                candidates = tuple(sorted({value for value in (nearest - 1, nearest)
                                           if 0 <= value < source_extent})) if boundary else ()
            rows.append((sample, inside, edge, boundary, candidates))
        return rows

    xs = axis_samples(width, SOURCE_WIDTH, left, scale)
    ys = axis_samples(height, SOURCE_HEIGHT, top, scale)
    edge_excluded = source_boundary_candidates = source_boundary_options = 0
    source_boundary_alternative_pixels = source_boundary_left_x = source_boundary_left_y = 0
    interior_checked = letterbox_checked = 0
    maximum_error = 0
    first_mismatch = None
    stride_source = SOURCE_WIDTH * 4
    stride_capture = width * 4

    for y, (sy, in_y, edge_y, boundary_y, candidates_y) in enumerate(ys):
        row_offset = y * stride_capture
        source_row = sy * stride_source if in_y else 0
        for x, (sx, in_x, edge_x, boundary_x, candidates_x) in enumerate(xs):
            offset = row_offset + x * 4
            actual = tuple(capture[offset:offset + 4])
            if edge_x or edge_y:
                edge_excluded += 1
                continue
            if in_x and in_y:
                source_offset = source_row + sx * 4
                sr, sg, sb, alpha = source[source_offset:source_offset + 4]
                expected = ((sr * alpha + 127) // 255,
                            (sg * alpha + 127) // 255,
                            (sb * alpha + 127) // 255, 255)
                source_xy = (sx, sy)
                interior_checked += 1
                boundary = boundary_x or boundary_y
                x_options = candidates_x if boundary_x else (sx,)
                y_options = candidates_y if boundary_y else (sy,)
                if boundary:
                    source_boundary_candidates += 1
                    source_boundary_options += len(x_options) * len(y_options)
            else:
                expected = (0, 0, 0, 255)
                source_xy = None
                letterbox_checked += 1
                boundary = False
                x_options = y_options = ()
            error = max(abs(a - b) for a, b in zip(expected, actual))
            if error > CHANNEL_TOLERANCE:
                matches = []
                if boundary:
                    for candidate_y in y_options:
                        for candidate_x in x_options:
                            candidate_offset = (candidate_y * SOURCE_WIDTH + candidate_x) * 4
                            cr, cg, cb, ca = source[candidate_offset:candidate_offset + 4]
                            candidate_rgba = ((cr * ca + 127) // 255,
                                              (cg * ca + 127) // 255,
                                              (cb * ca + 127) // 255, 255)
                            candidate_error = max(abs(a - b) for a, b in zip(candidate_rgba, actual))
                            if candidate_error <= CHANNEL_TOLERANCE:
                                dx = Fraction(candidate_x) - (Fraction(x * 2 + 1, 2) - left) / scale
                                dy = Fraction(candidate_y) - (Fraction(y * 2 + 1, 2) - top) / scale
                                matches.append((dx * dx + dy * dy, candidate_y, candidate_x,
                                                candidate_rgba, candidate_error))
                if matches:
                    _, selected_y, selected_x, selected_rgba, selected_error = min(matches)
                    source_boundary_alternative_pixels += 1
                    source_boundary_left_x += int(selected_x < sx)
                    source_boundary_left_y += int(selected_y < sy)
                    error = selected_error
                else:
                    candidate_rgba = []
                    for candidate_y in y_options:
                        for candidate_x in x_options:
                            candidate_offset = (candidate_y * SOURCE_WIDTH + candidate_x) * 4
                            cr, cg, cb, ca = source[candidate_offset:candidate_offset + 4]
                            candidate_rgba.append(((cr * ca + 127) // 255,
                                                   (cg * ca + 127) // 255,
                                                   (cb * ca + 127) // 255, 255))
                    first_mismatch = (x, y, source_xy, expected, actual, candidate_rgba)
                    break
            maximum_error = max(maximum_error, error)
        if first_mismatch:
            break

    if first_mismatch:
        raise _frame_mismatch(*first_mismatch)

    checked = interior_checked + letterbox_checked
    total = width * height
    if checked == 0:
        raise RuntimeError('D2D_WINDOW_FRAME_NO_STABLE_PIXELS')
    return {
        'status': 'D2D_WINDOW_FRAME_PIXEL_PARITY_PASS',
        'source_dimensions': [SOURCE_WIDTH, SOURCE_HEIGHT],
        'capture_dimensions': [width, height],
        'display_rect': {
            'left': float(left), 'top': float(top),
            'right': float(right), 'bottom': float(bottom),
            'width': float(display_width), 'height': float(display_height),
        },
        'scale': {'numerator': scale.numerator, 'denominator': scale.denominator},
        'stable_interior_pixels_checked': interior_checked,
        'opaque_black_letterbox_pixels_checked': letterbox_checked,
        'fractional_destination_edge_pixels_excluded': edge_excluded,
        'source_boundary_candidate_epsilon_texels': float(SOURCE_BOUNDARY_EPSILON),
        'source_boundary_candidate_pixels': source_boundary_candidates,
        'source_boundary_candidate_sample_points': source_boundary_options,
        'source_boundary_alternative_selected_pixels': source_boundary_alternative_pixels,
        'source_boundary_left_neighbor_x_selections': source_boundary_left_x,
        'source_boundary_left_neighbor_y_selections': source_boundary_left_y,
        'source_boundary_pixels_excluded': 0,
        'source_boundary_exclusion_fraction_of_source': 0.0,
        'total_capture_pixels': total,
        'total_excluded_pixels': total - checked,
        'maximum_channel_error': maximum_error,
        'channel_tolerance': CHANNEL_TOLERANCE,
        'capture_alpha_required': 255,
        'source_png_sha256': _sha256_path(source_png),
        'source_rgba_pixels_sha256': _sha256(source),
        'capture_png_sha256': _sha256_path(capture_png),
        'capture_rgba_pixels_sha256': _sha256(capture),
        'pixel_parity_verified': True,
        'same_swapchain_buffer_verified': False,
        'capture_origin_verified': False,
        'desktop_capture_verified': False,
        'human_visual_review_verified': False,
    }


def verify_closed_frame(source_png: Path, capture_png: Path, width: int, height: int) -> dict:
    """Require a transparent blank source and its opaque-black HWND readback."""
    if type(width) is not int or type(height) is not int or not (0 < width <= 32768 and 0 < height <= 32768):
        raise ValueError('D2D_CLOSED_FRAME_INVALID_DIMENSIONS width and height must be positive and at most 32768')
    if width * height * 4 > 256 * 1024 * 1024:
        raise ValueError('D2D_CLOSED_FRAME_INVALID_DIMENSIONS capture exceeds the 256 MiB pixel bound')

    # Reuse the same bounded, CRC-checked PNG decoder as the nonblank verifier.
    from render_ui_popup import png_pixels

    source_png, capture_png = Path(source_png), Path(capture_png)
    source = png_pixels(source_png)
    capture = png_pixels(capture_png, expected_dimensions=(width, height))
    source_pixels_checked = 0
    for pixel in range(1920 * 1080):
        offset = pixel * 4
        rgba = tuple(source[offset:offset + 4])
        source_pixels_checked += 1
        if rgba != (0, 0, 0, 0):
            x, y = pixel % 1920, pixel // 1920
            raise RuntimeError(
                'D2D_CLOSED_FRAME_SOURCE_NOT_TRANSPARENT_BLACK '
                f'source_xy=({x},{y}) actual_rgba={rgba} expected_rgba=(0,0,0,0)')

    capture_pixels_checked = 0
    for pixel in range(width * height):
        offset = pixel * 4
        rgba = tuple(capture[offset:offset + 4])
        capture_pixels_checked += 1
        if rgba != (0, 0, 0, 255):
            x, y = pixel % width, pixel // width
            raise RuntimeError(
                'D2D_CLOSED_FRAME_CAPTURE_NOT_OPAQUE_BLACK '
                f'capture_xy=({x},{y}) actual_rgba={rgba} expected_rgba=(0,0,0,255)')

    return {
        'status': 'D2D_CLOSED_FRAME_PIXEL_PARITY_PASS',
        'source_dimensions': [1920, 1080],
        'capture_dimensions': [width, height],
        'source_rgba_expected': [0, 0, 0, 0],
        'capture_rgba_expected': [0, 0, 0, 255],
        'source_pixels_checked': source_pixels_checked,
        'capture_pixels_checked': capture_pixels_checked,
        'total_pixels_checked': source_pixels_checked + capture_pixels_checked,
        'channel_tolerance': 0,
        'excluded_pixels': 0,
        'source_png_sha256': _sha256_path(source_png),
        'source_rgba_pixels_sha256': _sha256(source),
        'capture_png_sha256': _sha256_path(capture_png),
        'capture_rgba_pixels_sha256': _sha256(capture),
        'blank_source_content_verified': True,
        'opaque_black_capture_content_verified': True,
        'pixel_content_verified': True,
        'pixel_origin_verified': False,
        'same_swapchain_buffer_verified': False,
        'capture_origin_verified': False,
        'desktop_capture_verified': False,
        'human_visual_review_verified': False,
    }
