# cgt_cell_analysis_demo/core/workers/_well_index_common.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.decomposition import PCA
from sklearn.neighbors import KDTree

logger = logging.getLogger(__name__)


# ---------------------------- Dataclass (inputs/outputs/config) ----------------------------
@dataclass
class RefPaths:
    sensor_map_tif: Path
    marker_7x7_csv: Path | None = None
    marker_5x5_csv: Path | None = None
    well_csv: Path | None = None


@dataclass
class PcrInputs:
    pcr_image: Path  # well_1cycle.png
    rawdata_g: Path  # rawData_G.csv
    rawdata_r: Path  # rawData_R.csv


# ---------------------------- Common utilities ----------------------------
def ensure_dir(p: Path) -> Path:
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p


def process_image(
    image: np.ndarray,
    out_dir: Path,
    *,
    is_optical: bool = False,
    is_marker: bool = False,
    is_reference: bool = False,
    debug: bool = False,
) -> np.ndarray:
    """Image preprocessing pipeline."""
    out_dir = ensure_dir(out_dir)

    if is_reference:
        # Reference binary
        _, binary = cv2.threshold(image, 50, 255, cv2.THRESH_BINARY_INV)
        if debug:
            cv2.imwrite(
                str(
                    out_dir
                    / ("Ref_marker_binary_image.png" if is_marker else "Ref_well_binary_image.png")
                ),
                binary,
            )
        return binary

    if is_optical:
        # Optical: branch parameters by well vs. marker
        if is_marker:
            _, binary = cv2.threshold(image, 230, 255, cv2.THRESH_BINARY_INV)
            if debug:
                cv2.imwrite(str(out_dir / "marker_binary_image.png"), binary)
            return binary
        # Well detection
        blurred = cv2.medianBlur(image, 11)
        _, binary = cv2.threshold(blurred, 230, 255, cv2.THRESH_BINARY_INV)
        if debug:
            # cv2.imwrite(str(out_dir / "blurred_image.png"), blurred)
            cv2.imwrite(str(out_dir / "well_binary_image.png"), binary)
        return binary

    # PCR image markers - brightness-independent processing
    if is_marker:
        # Adaptive gamma correction based on image brightness
        mean_brightness = np.mean(image)
        if mean_brightness < 50:  # Very dark image
            gamma = 0.8  # Increase brightness more
        elif mean_brightness > 200:  # Very bright image
            gamma = 2.0  # Increase contrast more
        else:
            gamma = 1.5  # Standard gamma

        logger.debug("gamma: %s", gamma)

        inv = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv) * 255 for i in np.arange(256)]).astype("uint8")
        gamma_img = cv2.LUT(image, table)

        # Adaptive brightness and contrast adjustment
        if mean_brightness < 50:
            alpha = 1 + 150 / 100.0  # More contrast for dark images
            beta = 20  # More brightness
        elif mean_brightness > 200:
            alpha = 1 + 50 / 100.0  # Less contrast for bright images
            beta = 0  # No additional brightness
        else:
            alpha = 1 + 100 / 100.0  # Standard contrast
            beta = 10  # Standard brightness

        logger.debug("alpha: %s, beta: %s", alpha, beta)
        bright = cv2.convertScaleAbs(gamma_img, alpha=alpha, beta=beta)
        blurred = cv2.medianBlur(bright, 5)

        # Adaptive thresholding based on image characteristics
        if mean_brightness < 50:
            threshold = 30  # Lower threshold for dark images
        elif mean_brightness > 200:
            threshold = 50  # Higher threshold for bright images
        else:
            threshold = 40  # Standard threshold
        # Ensure threshold is at least 10 above top-left brightness
        try:
            top_left_val = int(image[0, 0])
        except Exception:
            top_left_val = int(mean_brightness)
        min_required = int(np.clip(top_left_val + 10, 0, 255))
        if threshold < min_required + 10:
            threshold = min_required + 10

        logger.debug("threshold: %s", threshold)
        _, binary = cv2.threshold(blurred, threshold, 255, cv2.THRESH_BINARY_INV)

        if debug:
            cv2.imwrite(str(out_dir / "gamma_image.png"), gamma_img)
            cv2.imwrite(str(out_dir / "bright_contrast_image.png"), bright)
            cv2.imwrite(str(out_dir / "blurred_image.png"), blurred)
            cv2.imwrite(str(out_dir / "marker_binary_image.png"), binary)
        return binary

    # Default binary
    _, binary = cv2.threshold(image, 50, 255, cv2.THRESH_BINARY_INV)
    if debug:
        cv2.imwrite(str(out_dir / "well_binary_image.png"), binary)
    return binary


def _detect_optical_contours(image: np.ndarray, is_reference: bool = False):
    """
    Detect wells in an optical image using contour analysis.
    Criteria:
        1) Contour area within the IQR range
        2) Contours that do not touch the image border
        3) (Optional) vertex-count criterion is commented out
    Returns:
        well_centers: center coordinates (sorted by descending y)
        filtered_contours: list of selected contours
    """
    contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = image.shape[:2]

    # Compute contour areas
    areas = [cv2.contourArea(contour) for contour in contours]

    if not areas:
        return [], []

    if is_reference:
        lower_bound = 0
        upper_bound = max(areas)
    else:
        q1 = np.percentile(areas, 25)
        q3 = np.percentile(areas, 75)
        iqr = q3 - q1
        lower_bound = max(q1 - 5 * iqr, 0)
        upper_bound = q3 + 5 * iqr

    filtered_contours = []
    for contour, area in zip(contours, areas):
        if lower_bound < area <= upper_bound:  # Criteria 1 & 2
            x, y, w, h = cv2.boundingRect(contour)
            if x > 0 and y > 0 and x + w < width and y + h < height:  # Criteria 3
                filtered_contours.append(contour)

    # Extract center coordinates
    well_centers = []
    for contour in filtered_contours:
        M = cv2.moments(contour)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        well_centers.append((cx, cy))

    rev_well_centers = well_centers[::-1]
    return rev_well_centers, filtered_contours


def _detect_pcr_contours(
    image: np.ndarray,
    *,
    is_marker=False,
    is_reference=False,
    bounding_box_filter=True,
    kernel_size=6,
    area_lower_bound=None,
    area_upper_bound=None,
    use_relaxed_detection=False,
    expected_count=None,
):
    """
    Detect contours with configurable area bounds and optional relaxed detection.

    Args:
        image: Binary image for contour detection
        is_marker: Whether detecting markers (uses fixed area bounds)
        is_reference: Whether this is reference data
        bounding_box_filter: Whether to apply bounding box filtering
        kernel_size: Grid kernel size for filtering
        area_lower_bound: Custom lower bound for area filtering (overrides default)
        area_upper_bound: Custom upper bound for area filtering (overrides default)
        use_relaxed_detection: Whether to use relaxed area bounds for better detection
        expected_count: Expected number of contours (for relaxed detection)

    Returns:
        centers: List of (x, y) contour centers
        filtered: List of filtered contours
    """
    contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return [], []
    areas = np.array([cv2.contourArea(c) for c in contours], dtype=float)

    # Determine area bounds
    if area_lower_bound is not None and area_upper_bound is not None:
        # Use custom bounds
        low, high = area_lower_bound, area_upper_bound
    else:
        # Default bounds based on reference/data type
        low, high = (
            (0, float(areas.max()))
            if is_reference
            else (np.percentile(areas, 25) - 10, np.percentile(areas, 75) + 10)
        )

    # Apply relaxed detection if requested and insufficient contours found
    if use_relaxed_detection and expected_count and len(contours) < expected_count:
        # Use more lenient area filtering
        q1, q3 = np.percentile(areas, 15), np.percentile(areas, 85)
        iqr = q3 - q1
        low = max(q1 - 2 * iqr, 0.1)
        high = q3 + 2 * iqr
        logger.debug("Using relaxed detection: area bounds [%.2f, %.2f]", low, high)

    filtered, centers = [], []
    h, w = image.shape[:2]
    if is_reference:
        top, bot, left, right = 0, h, 0, w
    else:
        h_unit, w_unit = h // (kernel_size + 1), w // (kernel_size + 1)
        top, bot, left, right = h_unit, h_unit * kernel_size, w_unit, w_unit * kernel_size

    logger.debug("top, bot, left, right: %s, %s, %s, %s", top, bot, left, right)
    for c, a in zip(contours, areas):
        if low <= a <= high:
            logger.debug("area=%s low=%s high=%s", a, low, high)
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
            x, y, ww, hh = cv2.boundingRect(c)
            if not bounding_box_filter or (left <= x <= right and top <= y <= bot):
                filtered.append(c)
                centers.append((cx, cy))

    return centers[::-1], filtered


def _detect_pcr_marker_contours(
    image: np.ndarray,
    *,
    kernel_size: int = 6,
    area_lower_bound: float | None = None,
    area_upper_bound: float | None = None,
) -> tuple[list[list[np.ndarray]], list[list[np.ndarray]]]:
    """
    Detect marker contours in each of the 5x5 inner grid areas and return
    a list of 25 entries, each containing the contours for that cell.

    The grid is derived from `kernel_size` (default 6), using inner intersections
    i=1..kernel_size-1 and j=1..kernel_size-1. Contours are shifted to full-image
    coordinates.

    Returns:
        List of 25 lists of contours (row-major over i then j)
    """

    marker_kernel_size = kernel_size - 1

    h_spacing = 178.0
    w_spacing = 192.0

    h, w = image.shape[:2]
    markers: list[list[np.ndarray]] = [[] for _ in range(marker_kernel_size * marker_kernel_size)]
    marker_contours: list[np.ndarray] = [[] for _ in range(marker_kernel_size * marker_kernel_size)]

    def cell_index(ii: int, jj: int) -> int:
        # Map (i=1..5, j=1..5) to 0..24 row-major
        return (ii - 1) * marker_kernel_size + (jj - 1)

    for i in range(1, marker_kernel_size + 1):
        for j in range(1, marker_kernel_size + 1):
            roi_cy = h - i * h_spacing
            roi_cx = w - j * w_spacing
            y0 = int(max(0, roi_cy - h_spacing / 4))
            y1 = int(min(h, roi_cy + h_spacing / 4))
            x0 = int(max(0, roi_cx - w_spacing / 4))
            x1 = int(min(w, roi_cx + w_spacing / 4))
            if y1 <= y0 or x1 <= x0:
                continue
            roi = image[y0:y1, x0:x1]
            sub_contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not sub_contours:
                continue

            # Optional area filtering per cell if bounds are given
            shifted_list: list[np.ndarray] = []
            shifted_contours: list[np.ndarray] = []
            for sc in sub_contours:
                if sc is None or len(sc) == 0:
                    continue
                if area_lower_bound is not None and area_upper_bound is not None:
                    a = float(cv2.contourArea(sc))
                    if not (area_lower_bound <= a <= area_upper_bound):
                        continue
                shifted = sc + np.array([[x0, y0]], dtype=sc.dtype)
                shifted_list.append(shifted)
                shifted_contours.append(sc)

            idx = cell_index(i, j)
            if shifted_list:
                markers[idx].extend(shifted_list)
                marker_contours[idx].extend(shifted_contours)

    return markers, marker_contours


def detect_markers(
    binary: np.ndarray,
    *,
    is_reference=False,
    kernel_size=6,
    area_lower_bound=None,
    area_upper_bound=None,
):
    """
    Detect markers with enhanced grid-based filtering for precise 25-marker detection.

    Args:
        binary: Binary image for marker detection
        is_reference: Whether this is reference data
        kernel_size: Grid kernel size for filtering
        expected_count: Expected number of markers (default 25 for 5x5 grid)
        area_lower_bound: Custom lower bound for area filtering
        area_upper_bound: Custom upper bound for area filtering
        use_relaxed_detection: Whether to use relaxed detection when insufficient markers found

    Returns:
        centers: List of (x, y) marker centers
        contours: List of detected contours
    """
    # For 25-marker detection, use stricter area bounds if not specified
    if not is_reference and area_lower_bound is None and area_upper_bound is None:
        area_lower_bound = 50.0  # Stricter lower bound
        area_upper_bound = 80.0  # Stricter upper bound

    # First attempt with standard detection
    markers, marker_contours = _detect_pcr_marker_contours(
        binary,
        kernel_size=kernel_size,
        area_lower_bound=area_lower_bound,
        area_upper_bound=area_upper_bound,
    )

    centers, contours = _filter_markers_by_grid_pattern(binary, markers, marker_contours)

    return centers, contours


def _filter_markers_by_grid_pattern(
    binary: np.ndarray, markers: list[list[np.ndarray]], marker_contours: list[list[np.ndarray]]
):
    """
    Filter markers to find exactly one marker per 5x5 cell.

    Rules:
    - If multiple candidates in a cell, select the one best aligned to its row/column median lines
      (horizontal and vertical) estimated from all candidates.
    - If a cell has no candidate, synthesize a marker at the intersection of the row and column
      median lines.

    Args:
            binary: Binary image
            markers: per-cell candidate contours (full-image coordinates)
            marker_contours: same shape as markers (unused; kept for compatibility)

    Returns:
            filtered_centers: 25 centers in row-major order
            filtered_contours: 25 contours (synthetic small box when missing)
    """
    # Derive grid size (expecting 25 cells => 5x5)
    num_cells = len(markers)
    if num_cells == 0:
        return [], []
    grid_size = int(np.sqrt(num_cells))
    if grid_size * grid_size != num_cells:
        # Fallback: treat as 5x5 if count mismatches
        grid_size = 5

    # Helper to compute center of a contour
    def contour_center(c: np.ndarray) -> tuple[int, int] | None:
        M = cv2.moments(c)
        if M["m00"] == 0:
            return None
        x = int(M["m10"] / M["m00"])
        y = int(M["m01"] / M["m00"])
        return (x, y)

    # Gather candidate centers per cell
    centers_by_cell: list[list[tuple[int, int]]] = [[] for _ in range(num_cells)]
    areas_by_cell: list[list[float]] = [[] for _ in range(num_cells)]
    for idx, cell_contours in enumerate(markers):
        for c in cell_contours:
            cc = contour_center(c)
            if cc is None:
                continue
            centers_by_cell[idx].append(cc)
            areas_by_cell[idx].append(float(cv2.contourArea(c)))

    # Estimate row-wise Y medians and column-wise X medians from candidates
    row_y: list[float] = []
    col_x: list[float] = []
    for r in range(grid_size):
        row_vals = []
        for c in range(grid_size):
            idx = r * grid_size + c
            row_vals.extend([cy for (_, cy) in centers_by_cell[idx]])
        row_y.append(float(np.median(row_vals)) if len(row_vals) > 0 else 0.0)
    for c in range(grid_size):
        col_vals = []
        for r in range(grid_size):
            idx = r * grid_size + c
            col_vals.extend([cx for (cx, _) in centers_by_cell[idx]])
        col_x.append(float(np.median(col_vals)) if len(col_vals) > 0 else 0.0)

    # If medians are zero (no candidates anywhere), fall back to image center grid using spacing
    if all(v == 0.0 for v in row_y) or all(v == 0.0 for v in col_x):
        H, W = binary.shape[:2]
        # Estimate spacing from image and expected 5x5 inner grid
        v_spacing = max(1.0, H / (grid_size + 1))
        h_spacing = max(1.0, W / (grid_size + 1))
        row_y = [float(H - (i + 1) * v_spacing) for i in range(grid_size)]
        col_x = [float(W - (j + 1) * h_spacing) for j in range(grid_size)]

    selected_centers: list[tuple[int, int]] = []
    selected_contours: list[np.ndarray] = []

    for r in range(grid_size):
        for c in range(grid_size):
            idx = r * grid_size + c
            cands = centers_by_cell[idx]
            conts = markers[idx]
            if len(cands) == 0:
                # Synthesize a small square contour at grid intersection
                xs = int(round(col_x[c]))
                ys = int(round(row_y[r]))
                half = 2
                box = np.array(
                    [
                        [[xs - half, ys - half]],
                        [[xs + half, ys - half]],
                        [[xs + half, ys + half]],
                        [[xs - half, ys + half]],
                    ],
                    dtype=np.int32,
                )
                selected_centers.append((xs, ys))
                selected_contours.append(box)
                continue

            # Score candidates by alignment to row/column medians
            r_y = row_y[r]
            c_x = col_x[c]
            scores: list[tuple[float, int]] = []
            for i, (cx, cy) in enumerate(cands):
                align_score = abs(cy - r_y) + abs(cx - c_x)
                # Secondary: prefer area close to cell median
                if len(areas_by_cell[idx]) > 0:
                    cell_med_area = float(np.median(areas_by_cell[idx]))
                    area = float(cv2.contourArea(conts[i]))
                    area_penalty = abs(area - cell_med_area) * 0.05
                    align_score += area_penalty
                scores.append((align_score, i))
            scores.sort(key=lambda x: x[0])
            best_i = scores[0][1]
            selected_centers.append(cands[best_i])
            selected_contours.append(conts[best_i])

    return selected_centers[::-1], selected_contours[::-1]


def detect_wells(
    binary: np.ndarray,
    *,
    is_reference=False,
    is_optical=False,
    kernel_size=6,
    area_lower_bound=None,
    area_upper_bound=None,
    use_relaxed_detection=False,
    expected_count=None,
):
    """
    Detect wells with configurable parameters.

    Args:
        binary: Binary image for well detection
        is_reference: Whether this is reference data
        is_optical: Whether this is optical image (uses different detection method)
        kernel_size: Grid kernel size for filtering
        area_lower_bound: Custom lower bound for area filtering
        area_upper_bound: Custom upper bound for area filtering
        use_relaxed_detection: Whether to use relaxed detection
        expected_count: Expected number of wells (for relaxed detection)

    Returns:
        centers: List of (x, y) well centers
        contours: List of detected contours
    """
    if is_optical:
        return _detect_optical_contours(binary, is_reference=is_reference)
    else:
        return _detect_pcr_contours(
            binary,
            is_marker=False,
            is_reference=is_reference,
            bounding_box_filter=False,
            kernel_size=kernel_size,
            area_lower_bound=area_lower_bound,
            area_upper_bound=area_upper_bound,
            use_relaxed_detection=use_relaxed_detection,
            expected_count=expected_count,
        )


# # ================================================================
# # 1. Candidate-point detection (Adaptive Threshold + Morphology + Contour)
# # ================================================================
# def detect_candidates_roi(
#     gray,
#     out_dir: Path,
#     roi_fraction=0.75, roi_rect=None,
#     area_min=4, area_max=120,
#     block_size=31, C=5, open_kernel=3
# ):
#     H, W = gray.shape[:2]
#     if roi_rect is None:
#         s = int(min(H, W) * roi_fraction)
#         x = (W - s)//2; y = (H - s)//2; w = h = s
#     else:
#         x, y, w, h = map(int, roi_rect)
#     roi = gray[y:y+h, x:x+w]

#     h_unit, w_unit = h // (kernel_size+1), w // (kernel_size+1)
#     top, bot, left, right = h_unit, h_unit*kernel_size, w_unit, w_unit*kernel_size

#     contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
#     filtered, pts = [], []
#     for c in contours:
#         a = cv2.contourArea(c)
#         if area_min <= a <= area_max:
#             M = cv2.moments(c)
#             if M["m00"] != 0:
#                 cx = x + (M["m10"]/M["m00"])
#                 cy = y + (M["m01"]/M["m00"])
#                 pts.append((float(cx), float(cy)))
#                 filtered.append(c)
#     return np.array(pts, dtype=np.float32), (x,y,w,h), filtered


# ================================================================
# 2. Lattice-vector estimation (fast mean-direction computation via KDTree)
# ================================================================
def estimate_lattice_vectors_fast(pts, exp_dx=192, exp_dy=178, tol=0.25, sample_max=50):
    if len(pts) < 8:
        return None, None
    if len(pts) > sample_max:
        sel = np.random.choice(len(pts), sample_max, replace=False)
        psub = pts[sel]
    else:
        psub = pts

    tree = KDTree(psub)
    rad = max(exp_dx, exp_dy) * (1 + tol)
    ind = tree.query_radius(psub, r=rad)

    cand_dx, cand_dy = [], []
    for i, neigh in enumerate(ind):
        pi = psub[i]
        for j in neigh:
            if j <= i:
                continue
            v = psub[j] - pi
            L = np.linalg.norm(v)
            if exp_dx * (1 - tol) <= L <= exp_dx * (1 + tol):
                cand_dx.append(v)
            elif exp_dy * (1 - tol) <= L <= exp_dy * (1 + tol):
                cand_dy.append(v)
    if len(cand_dx) < 3 or len(cand_dy) < 3:
        return None, None

    cand_dx = np.array(cand_dx, dtype=np.float32)
    cand_dy = np.array(cand_dy, dtype=np.float32)
    mean_dx = cand_dx.mean(axis=0)
    mean_dy = cand_dy.mean(axis=0)

    def align(vecs, ref):
        s = np.sign(vecs @ ref)
        s[s == 0] = 1
        return vecs * s[:, None]

    cand_dx = align(cand_dx, mean_dx)
    cand_dy = align(cand_dy, mean_dy)

    v1 = cand_dx.mean(axis=0)
    v2 = cand_dy.mean(axis=0)

    v1 = v1 * (exp_dx / (np.linalg.norm(v1) + 1e-6))
    v2 = v2 * (exp_dy / (np.linalg.norm(v2) + 1e-6))

    cosang = abs(np.dot(v1, v2)) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    if cosang > 0.9:
        v2 = np.array([-v1[1], v1[0]], dtype=np.float32)
        v2 *= exp_dy / (np.linalg.norm(v2) + 1e-6)

    return v1, v2


# ================================================================
# 3. Grid fitting (generate expected 5x5 positions, then nearest-neighbor matching)
# ================================================================
def fit_grid(pts, v1, v2, grid=(5, 5), r_tol=22, trials=400):
    if v1 is None or v2 is None or len(pts) == 0:
        return None, {}, list(range(grid[0] * grid[1]))
    rows, cols = grid
    tree = KDTree(pts)

    best_score, best_origin, best_data = -1, None, None
    for _ in range(trials):
        origin = pts[np.random.randint(0, len(pts))]
        expected = [origin + c * v1 + r * v2 for r in range(rows) for c in range(cols)]
        expected = np.array(expected, dtype=np.float32)

        d, idx = tree.query(expected, k=1)
        matched, missing, score = {}, [], 0
        for i, (dist, j) in enumerate(zip(d[:, 0], idx[:, 0])):
            if dist <= r_tol:
                matched[i] = int(j)
                score += 1
            else:
                missing.append(i)

        if score > best_score or (
            score == best_score and d[:, 0].sum() < (best_data[2] if best_data else 1e9)
        ):
            best_score, best_origin = score, origin
            best_data = (matched, missing, d[:, 0].sum(), expected)

    return best_origin, best_data[0], best_data[1], best_data[3]


# ================================================================
# 4. Row-major ordering (fill missing slots with expected positions)
# ================================================================
def order_row_major(origin, v1, v2, matches, pts, expected, grid=(5, 5)):
    ordered = []
    for i in range(grid[0] * grid[1]):
        if i in matches:
            ordered.append(tuple(map(float, pts[matches[i]])))
        else:
            ordered.append(tuple(map(float, expected[i])))
    return ordered


def get_center_positioned_image(
    image: np.ndarray,
    well_centers: list[tuple[int, int]],
    image_folder: Path,
    file_name: str = "",
    dot_color: tuple[int, int, int] = (0, 0, 255),
    dot_radius: int = 2,
    contours: list | None = None,
    display_boundary: bool = False,
    sub_roi_rects: list[tuple[int, int, int, int]] | None = None,
    display_sub_roi: bool = False,
    display_well_index: bool = False,
    display_well_index_list: list | None = None,
    display_coordination: bool = False,
) -> np.ndarray:
    """
    Take an original/gray image and overlay well centers, contours, and index/coordinates,
    optionally saving the result to a file.

    Args:
        image: input image (gray or BGR).
        well_centers: list of (cx, cy).
        image_folder: destination folder.
        file_name: output file name (empty string = do not save).
        dot_color: dot color (BGR).
        dot_radius: dot radius.
        contours: list of contours to draw.
        display_boundary: whether to draw contours.
        display_well_index: whether to draw well numbers.
        display_well_index_list: well numbers (required when display_well_index=True).
        display_coordination: whether to draw coordinate text.

    Returns:
        display_image: visualized numpy array (BGR).
    """
    # Gray -> BGR conversion
    if len(image.shape) == 2:
        display_image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        display_image = image.copy()

    # Draw boundaries
    if contours is not None and display_boundary:
        cv2.drawContours(display_image, contours, -1, (0, 255, 0), 1)  # green

    # Draw sub-ROI boundaries
    if sub_roi_rects is not None and display_sub_roi:
        for x, y, w, h in sub_roi_rects:
            x0 = max(0, int(x))
            y0 = max(0, int(y))
            x1 = min(display_image.shape[1] - 1, int(x + w))
            y1 = min(display_image.shape[0] - 1, int(y + h))
            cv2.rectangle(display_image, (x0, y0), (x1, y1), (0, 255, 255), 1)  # yellow

    # Draw centers + text
    for i, (cx, cy) in enumerate(well_centers):
        if (
            display_well_index
            and display_well_index_list is not None
            and i < len(display_well_index_list)
        ):
            text = str(display_well_index_list[i])
            cv2.putText(
                display_image,
                text,
                (int(cx) - 10, int(cy) - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 0, 0),
                1,
            )

        elif display_coordination:
            cv2.putText(
                display_image,
                f"({cx}, {cy})",
                (int(cx) - 10, int(cy) - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 0, 0),
                1,
            )

        cv2.circle(display_image, (int(cx), int(cy)), dot_radius, dot_color, -1)

    # Save
    if file_name:
        image_folder = Path(image_folder)
        image_folder.mkdir(parents=True, exist_ok=True)
        display_image_path = image_folder / file_name
        cv2.imwrite(str(display_image_path), display_image)

    return display_image


def compute_sub_roi_rects(
    image_shape: tuple[int, int], kernel_size: int
) -> list[tuple[int, int, int, int]]:
    """
    Compute grid-aligned sub-ROI rectangles for visualization.

    The grid uses (kernel_size+1) units per dimension and places sub-ROIs at
    internal grid intersections (i=1..kernel_size-1, j=1..kernel_size-1).

    Args:
        image_shape: (H, W) of the image.
        kernel_size: Grid kernel size used elsewhere (e.g., 6 for 5x5 inner points).
        size_fraction: Fraction of the unit cell size to use for each sub-ROI rectangle.

    Returns:
        List of (x, y, w, h) rectangles in image coordinates.
    """
    h_spacing = 178.0
    w_spacing = 192.0

    H, W = int(image_shape[0]), int(image_shape[1])
    rects: list[tuple[int, int, int, int]] = []
    for i in range(1, kernel_size):
        for j in range(1, kernel_size):
            # Center of the sub-ROI around grid intersections
            cy = H - i * h_spacing
            cx = W - j * w_spacing
            x0 = int(max(0, min(W - 1, cx - w_spacing / 4)))
            y0 = int(max(0, min(H - 1, cy - h_spacing / 4)))
            rw = int(max(1, w_spacing / 2))
            rh = int(max(1, h_spacing / 2))
            # Clip rectangle to image bounds
            if x0 + rw > W:
                rw = W - x0
            if y0 + rh > H:
                rh = H - y0
            rects.append((x0, y0, rw, rh))

    return rects


def estimate_grid_properties(points: list[tuple[int, int]]):
    pts = np.array(points, dtype=float)
    if len(pts) < 2:
        return np.eye(2), 1.0, 1.0
    pca = PCA(n_components=2).fit(pts)
    axes = pca.components_  # (2,2)

    px = np.dot(pts, axes[0])
    py = np.dot(pts, axes[1])

    dx = np.abs(np.diff(np.sort(px)))
    dy = np.abs(np.diff(np.sort(py)))
    dx = dx[dx > 20]
    dy = dy[dy > 20]

    hx = float(np.median(np.abs(dx)))
    hy = float(np.median(np.abs(dy)))

    if hx <= 0:
        hx = 1.0
    if hy <= 0:
        hy = 1.0
    return axes, hx, hy


def extract_grid_points(
    points: list[tuple[int, int]] | np.ndarray,
    principal_axes: np.ndarray,
    h_spacing: float,
    v_spacing: float,
    tolerance: float = 5.0,
) -> list[tuple[int, int]]:
    """
    Extract grid-aligned points from noisy/mixed points using PCA orientation and spacing.

    Args:
        points: (N,2) array-like of (x,y) input points.
        principal_axes: (2,2) PCA components (principal directions).
        h_spacing: estimated horizontal grid spacing.
        v_spacing: estimated vertical grid spacing.
        tolerance: distance tolerance for accepting a snapped grid point.

    Returns:
        grid_points: list of (x,y) integer tuples in the original coordinate system.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("points must be an array of shape (N,2)")

    # 1) Transform coordinates onto the PCA axes (aligned coordinates)
    rotated_points = np.dot(pts, principal_axes.T)

    grid_points: list[tuple[int, int]] = []

    for point in rotated_points:
        # 2) Normalize to grid units (round to nearest multiple of spacing)
        # norm_x = round(p[0] / h_spacing)
        # norm_y = round(p[1] / v_spacing)

        # snapped = np.array([norm_x, norm_y])
        # print(f"snapped: {snapped}")

        # 3) Restore to the original coordinate system
        original_point = np.dot(point, principal_axes)

        # 4) Check distance to surrounding points
        dists = np.linalg.norm(pts - original_point, axis=1)

        if np.any(dists <= tolerance):
            grid_points.append((int(original_point[0]), int(original_point[1])))

    return grid_points


def estimate_5x5_marker_grid(
    partial_points: list[tuple[int, int]] | np.ndarray,
    *,
    principal_axes: np.ndarray | None = None,
    h_spacing: float | None = None,
    v_spacing: float | None = None,
    image_shape: tuple[int, int] | None = None,
    sort_row_major: bool = True,
) -> list[tuple[int, int]]:
    """
    Estimate a complete 5x5 grid of marker positions from a subset of detected points.

    The function leverages the grid nature (constant spacing) by:
      1) Estimating principal axes with PCA (if not provided)
      2) Estimating grid spacing via median nearest-neighbor distances (if not provided)
      3) Snapping an origin offset using modulo statistics in the PCA-aligned frame
      4) Producing a 5x5 lattice centered near the observed mean position

    Args:
        partial_points: Subset of detected marker centers [(x, y), ...]
        principal_axes: Optional (2,2) PCA axes. If None, they are estimated
        h_spacing: Optional estimated spacing along axis-0
        v_spacing: Optional estimated spacing along axis-1
        image_shape: Optional (H, W) used to clip/validate points (not required)
        sort_row_major: If True, order by rows (y) then columns (x) in the original frame

    Returns:
        List of 25 (x, y) integer positions in the original coordinate system
    """
    pts = np.asarray(partial_points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) == 0:
        return []

    # 1) Axes and spacing
    if principal_axes is None or h_spacing is None or v_spacing is None:
        axes, hx, hy = estimate_grid_properties(pts.tolist())
        if principal_axes is None:
            principal_axes = axes
        if h_spacing is None:
            h_spacing = hx
        if v_spacing is None:
            v_spacing = hy

    # 2) Rotate into aligned coordinate system
    aligned = np.dot(pts, principal_axes.T)  # shape (N,2)

    rx = np.mod(aligned[:, 0], h_spacing)
    ry = np.mod(aligned[:, 1], v_spacing)
    # Median is robust here
    ox = float(np.median(rx))
    oy = float(np.median(ry))

    # 4) Choose a 5x5 window centered near the observed mean
    mean_x, mean_y = np.mean(aligned, axis=0)
    # Compute integer grid indices for the mean
    k_mean = int(round((mean_x - ox) / h_spacing))
    l_mean = int(round((mean_y - oy) / v_spacing))

    # Build 5x5 indices centered around (k_mean, l_mean)
    # Center the window so that the mean sits roughly in the middle (index 2)
    k0 = k_mean - 2
    l0 = l_mean - 2

    grid_points = []
    for li in range(l0, l0 + 5):
        for k in range(k0, k0 + 5):
            gx = ox + k * h_spacing
            gy = oy + li * v_spacing
            # Transform back to original frame
            original = gx * principal_axes[0] + gy * principal_axes[1]
            x, y = int(round(original[0])), int(round(original[1]))
            # Optional clipping by image shape if provided
            if image_shape is not None:
                H, W = image_shape
                if not (0 <= x < W and 0 <= y < H):
                    # Skip points falling outside the image canvas
                    continue
            grid_points.append((x, y))

    if sort_row_major and len(grid_points) > 0:
        grid_points.sort(key=lambda p: (p[1], p[0]))

    # If clipping removed some points, we may return less than 25
    return grid_points


def snap_grid_to_detected_points(
    estimated_points: list[tuple[int, int]] | np.ndarray,
    detected_points: list[tuple[int, int]] | np.ndarray,
    *,
    tolerance: float = 15.0,
) -> list[tuple[int, int]]:
    """
    Snap each estimated grid node to the nearest actually detected marker point
    within a distance tolerance. Points with no nearby detection are kept as-is.

    Args:
        estimated_points: Grid nodes to be snapped
        detected_points: Observed marker centers
        tolerance: Maximum distance to accept a snap

    Returns:
        List of snapped points (same length/order as estimated_points)
    """
    est = np.asarray(estimated_points, dtype=float)
    det = np.asarray(detected_points, dtype=float)
    if est.size == 0:
        return []
    if det.size == 0:
        return [(int(round(x)), int(round(y))) for x, y in est]

    tree = cKDTree(det)
    snapped: list[tuple[int, int]] = []
    for p in est:
        dist, idx = tree.query(p)
        if np.isfinite(dist) and dist <= float(tolerance):
            qx, qy = det[int(idx)]
            snapped.append((int(round(qx)), int(round(qy))))
        else:
            snapped.append((int(round(p[0])), int(round(p[1]))))
    return snapped


def get_ref_tile_marker(
    marker_points: list[tuple[int, int]],
    width: int,
    height: int,
    tile_num: int,
    tile_size: int = 6,
) -> list[tuple[int, int]]:
    """
    From all reference marker points, keep only those inside a specific tile region.

    Args:
        marker_points: list of (x, y) marker coordinates
        width: full sensor map width
        height: full sensor map height
        tile_num: current tile index (0 .. tile_size^2-1)
        tile_size: grid size (default 6 -> 6x6 tile)

    Returns:
        tile_markers: marker coordinates inside the given tile region
    """
    tile_markers: list[tuple[int, int]] = []

    tile_y, tile_x = divmod(tile_num, tile_size)
    h_unit = int(height / (tile_size + 1))
    w_unit = int(width / (tile_size + 1))

    top, bottom = h_unit * tile_y, h_unit * (tile_y + 2)
    left, right = w_unit * tile_x, w_unit * (tile_x + 2)

    for x, y in marker_points:
        if left <= x <= right and top <= y <= bottom:
            tile_markers.append((x, y))

    return tile_markers


def find_overlap_transform(points_img1, points_img2):
    """Find transformation matrix between two point sets with validation."""
    # Convert to numpy arrays if not already
    pts1 = np.asarray(points_img1, dtype=np.float32)
    pts2 = np.asarray(points_img2, dtype=np.float32)

    # Validate input points
    if len(pts1) < 3 or len(pts2) < 3:
        logger.warning(
            "Insufficient points for transformation. pts1: %d, pts2: %d", len(pts1), len(pts2)
        )
        return np.eye(2, 3, dtype=np.float32)

    if pts1.shape[1] != 2 or pts2.shape[1] != 2:
        logger.warning("Invalid point dimensions. pts1: %s, pts2: %s", pts1.shape, pts2.shape)
        return np.eye(2, 3, dtype=np.float32)

    if len(pts1) != len(pts2):
        logger.warning("Mismatched point counts. pts1: %d, pts2: %d", len(pts1), len(pts2))
        # Use the minimum count
        min_count = min(len(pts1), len(pts2))
        pts1 = pts1[:min_count]
        pts2 = pts2[:min_count]

    try:
        matrix, _ = cv2.estimateAffinePartial2D(pts1, pts2)
        if matrix is None:
            logger.warning("Failed to estimate transformation matrix")
            return np.eye(2, 3, dtype=np.float32)
        return matrix
    except cv2.error as e:
        logger.error("OpenCV error in estimateAffinePartial2D: %s", e)
        return np.eye(2, 3, dtype=np.float32)


def read_ref_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8", header=0)

    # Strip column names and find matching columns (allowing spaces before and after column names)
    rename_dict = {}
    for col in df.columns:
        stripped = col.strip()
        rename_dict[col] = stripped

    return df[list(rename_dict.keys())].rename(columns=rename_dict)


def read_raw_channel_csv(path: Path) -> pd.DataFrame:
    # header=2 (body)
    df = pd.read_csv(path, encoding="utf-8", header=2)
    rename_dict = {}
    for col in df.columns:
        stripped = col.strip()
        rename_dict[col] = stripped

    return df[list(rename_dict.keys())].rename(columns=rename_dict)


def write_csv(df: pd.DataFrame, path: Path):
    path = Path(path)
    ensure_dir(path.parent)
    df.to_csv(path, index=False)


def match_well_index(
    ref_points: pd.DataFrame, target_points: pd.DataFrame, *, threshold: float = 25.0
) -> pd.DataFrame:
    """Match wells by iterating over reference points and finding nearby target points.

    Mirrors the provided logic:
      - KDTree is built on target points
      - Iterate reference points; for each, find all target points within `threshold`
      - If multiple nearby, choose the closest by Euclidean distance
      - Output columns ordered as ['Well Number', 'X coordination', 'Y coordination', 'Absolute Well Number']
    """
    if ref_points is None or ref_points.empty or target_points is None or target_points.empty:
        return pd.DataFrame(
            columns=["Well Number", "X coordination", "Y coordination", "Absolute Well Number"]
        )

    # Extract indices and positions
    ref_point_idxs = (
        ref_points["Well Number"]
        if "Well Number" in ref_points.columns
        else pd.Series(range(len(ref_points)))
    )
    ref_point_pos = ref_points[["X coordination", "Y coordination"]].to_numpy(dtype=float)

    target_point_idxs = (
        target_points["Well Number"]
        if "Well Number" in target_points.columns
        else pd.Series(range(len(target_points)))
    )
    target_point_pos = target_points[["X coordination", "Y coordination"]].to_numpy(dtype=float)

    tree = cKDTree(target_point_pos)

    results = []
    for ref_idx, ref_point in enumerate(ref_point_pos):
        nearby_indices = tree.query_ball_point(ref_point, threshold)
        if len(nearby_indices) >= 2:
            pts = target_point_pos[nearby_indices]
            dists = np.linalg.norm(pts - ref_point, axis=1)
            closest_rel = int(np.argmin(dists))
            closest_idx = int(nearby_indices[closest_rel])
            closest_point = target_point_pos[closest_idx]
            results.append(
                [
                    int(target_point_idxs.iloc[closest_idx]),
                    float(closest_point[0]),
                    float(closest_point[1]),
                    int(ref_point_idxs.iloc[ref_idx]),
                ]
            )
        elif len(nearby_indices) == 1:
            idx = int(nearby_indices[0])
            close_point = target_point_pos[idx]
            results.append(
                [
                    int(target_point_idxs.iloc[idx]),
                    float(close_point[0]),
                    float(close_point[1]),
                    int(ref_point_idxs.iloc[ref_idx]),
                ]
            )

    df = pd.DataFrame(
        results, columns=["Well Number", "X coordination", "Y coordination", "Absolute Well Number"]
    )
    return df


def transform_points(points: np.ndarray, affine):
    pts = np.asarray(points, float)
    if pts.ndim == 1:
        pts = pts[None, :]
    return cv2.transform(np.array([pts]), affine)[0].astype(int)


def seperate_into_single_well(gray_img: np.ndarray, contours: list):
    wells = []
    for c in contours:
        mask = np.zeros_like(gray_img)
        cv2.drawContours(mask, [c], -1, 255, thickness=cv2.FILLED)
        cut = cv2.bitwise_and(gray_img, gray_img, mask=mask)
        x, y, w, h = cv2.boundingRect(c)
        wells.append(cut[y : y + h, x : x + w])
    return wells


def save_well_image(well_images, index_list, out_dir: Path, tile_num: int):
    out_dir = ensure_dir(out_dir)
    for img, idx in zip(well_images, index_list):
        cv2.imwrite(str(out_dir / f"Well_{idx}_{tile_num}.png"), img)


def save_well_images_direct(
    gray_img: np.ndarray,
    ordered_contours: list,
    index_list: list,
    out_dir: Path,
    tile_num: int,
    png_compression: int = 1,
):
    """Save cropped wells directly from contours without building an intermediate list.

    Uses ROI-local masks to minimize allocations and sets low PNG compression for speed.
    """
    out_dir = ensure_dir(out_dir)
    params = [cv2.IMWRITE_PNG_COMPRESSION, int(max(0, min(9, png_compression)))]
    for contour, idx in zip(ordered_contours, index_list):
        x, y, w, h = cv2.boundingRect(contour)
        if w <= 0 or h <= 0:
            continue
        roi = gray_img[y : y + h, x : x + w]
        mask = np.zeros((h, w), dtype=gray_img.dtype)
        shifted = contour - np.array([[x, y]])
        cv2.drawContours(mask, [shifted], -1, 255, thickness=cv2.FILLED)
        cut = cv2.bitwise_and(roi, roi, mask=mask)
        cv2.imwrite(str(out_dir / f"Well_{idx}_{tile_num}.png"), cut, params)


def sort_contours_by_centers(idx_list: list[int], centers: list[tuple[int, int]], contours: list):
    center_map: dict[tuple[int, int], Any] = {}
    for c in contours:
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cc = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
        center_map[cc] = c
    ordered = []
    for i in idx_list:
        if i < 0 or i >= len(centers):
            continue
        key = centers[i]
        if key in center_map:
            ordered.append(center_map[key])
    return ordered


# Optical-only - fill in missing markers (simplified port of the attached logic)
def find_missing_hex_centers(
    binary_img: np.ndarray, hex_centers: list[tuple[int, int]], threshold=5
):
    """Estimate missing hexagon centers from 6-neighborhood proximity (accelerated).

    Behavior is unchanged, but the iterative any/hypot checks are replaced by KD-Tree
    queries, accelerating the O(N * directions) neighborhood search to O(log N).
    """
    if not hex_centers:
        return []

    # Precompute base parameters and direction vectors
    hex_size = 170
    angles = np.array([30, 90, 150, 210, 270, 330], dtype=float)
    rad = np.radians(angles)
    directions = np.stack([np.cos(rad), np.sin(rad)], axis=1) * float(hex_size)
    directions = directions.astype(int)

    # Build KDTree (for duplicate and neighborhood checks)
    pts = np.asarray(hex_centers, dtype=float)
    tree = cKDTree(pts) if len(pts) > 0 else None

    candidate_centers: list[tuple[int, int]] = []
    candidate_set: set[tuple[int, int]] = set()

    # Candidate generation: probe the six-direction neighbors of each center
    for cx, cy in pts:
        base = np.array([cx, cy], dtype=float)
        neighbors = base + directions
        # Keep only candidates sufficiently far from existing centers
        if tree is not None:
            mask_far = [len(tree.query_ball_point(n, threshold)) == 0 for n in neighbors]
        else:
            mask_far = [True] * len(neighbors)

        for keep, n in zip(mask_far, neighbors):
            if not keep:
                continue
            xi, yi = int(n[0]), int(n[1])
            key = (xi, yi)
            if key in candidate_set:
                continue

            # Distance-based deduplication to mirror the original any(... <= threshold ...) check
            is_near_existing = False
            for px, py in candidate_centers:
                if (px - xi) * (px - xi) + (py - yi) * (py - yi) <= (threshold * threshold):
                    is_near_existing = True
                    break
            if is_near_existing:
                continue

            candidate_set.add(key)
            candidate_centers.append(key)

    if not candidate_centers:
        return hex_centers

    # Candidate filtering: keep points with >=5 existing centers among the 6 neighbors and valid border/background
    filtered_missing_centers: list[tuple[int, int]] = []
    for x, y in candidate_centers:
        # Do the border/background check first to reduce unnecessary queries
        if not (0 <= y < binary_img.shape[0] and 0 <= x < binary_img.shape[1]):
            continue
        if binary_img[y, x] != 0:
            continue

        if tree is None:
            continue

        neighbor_count = 0
        # Evaluate proximity of the six-direction neighbors to existing centers
        for dx, dy in directions:
            nb = (x + int(dx), y + int(dy))
            if len(tree.query_ball_point(nb, threshold)) > 0:
                neighbor_count += 1
                if neighbor_count >= 5:
                    filtered_missing_centers.append((x, y))
                    break

    if not filtered_missing_centers:
        return hex_centers

    arr = np.array(filtered_missing_centers, dtype=int)
    arr = arr[np.argsort(arr[:, 1])]
    return arr.tolist()


def align_image(image, transform_matrix, output_shape):
    aligned_image = cv2.warpAffine(image, transform_matrix, output_shape, flags=cv2.INTER_LINEAR)
    return aligned_image


def blend_images(image1: np.ndarray, image2: np.ndarray):
    blended = cv2.addWeighted(image1, 0.3, image2, 0.7, 0)
    return blended


# ---------------------------- Image Stitching Functions ----------------------------


def stitch_optical_images(
    image_paths: list[str | Path],
    output_path: str | Path,
    grid_size: tuple[int, int] = (6, 6),
    image_size: tuple[int, int] | None = None,
    overlap: int = 0,
) -> bool:
    """
    Stitch 36 optical images into one whole image with fixed placement order.

    The placement order is:
    - Image 1: top-left corner
    - Image 36: bottom-right corner
    - Images are arranged in a 6x6 grid (left-to-right, top-to-bottom)

    Args:
        image_paths: List of 36 image file paths in order (1-36)
        output_path: Path where the stitched image will be saved
        grid_size: Grid dimensions (rows, cols). Default is (6, 6) for 36 images
        image_size: Target size for each individual image (width, height).
                   If None, uses the size of the first image
        overlap: Number of pixels to overlap between adjacent images (default: 0)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if len(image_paths) != 36:
            logger.error(f"Expected 36 images, got {len(image_paths)}")
            return False

        # Load the first image to determine dimensions
        first_img = cv2.imread(str(image_paths[0]))
        if first_img is None:
            logger.error(f"Could not load first image: {image_paths[0]}")
            return False

        # Use provided image_size or determine from first image
        if image_size is None:
            img_height, img_width = first_img.shape[:2]
        else:
            img_width, img_height = image_size

        # Validate individual image dimensions
        if img_width <= 0 or img_height <= 0:
            logger.error(f"Invalid image dimensions: {img_width}x{img_height}")
            return False

        # Calculate canvas size
        rows, cols = grid_size
        canvas_width = cols * img_width - (cols - 1) * overlap
        canvas_height = rows * img_height - (rows - 1) * overlap

        # Validate canvas dimensions
        if canvas_width <= 0 or canvas_height <= 0:
            logger.error(f"Invalid canvas dimensions: {canvas_width}x{canvas_height}")
            return False

        # Check if canvas is too large for OpenCV (max ~2GB for uint8)
        max_dimension = 65535  # OpenCV's maximum dimension limit
        if canvas_width > max_dimension or canvas_height > max_dimension:
            logger.error(
                f"Canvas dimensions too large for OpenCV: {canvas_width}x{canvas_height} (max: {max_dimension})"
            )
            return False

        # Create canvas (assuming 3-channel BGR images)
        canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)

        logger.info(f"Creating stitched image: {canvas_width}x{canvas_height}")
        logger.info(f"Individual image size: {img_width}x{img_height}")

        # Place images in grid order
        for i, img_path in enumerate(image_paths):
            # Calculate grid position
            row = i // cols
            col = i % cols

            # Load and resize image if needed
            img = cv2.imread(str(img_path))
            if img is None:
                logger.warning(f"Could not load image {i + 1}: {img_path}")
                # Create a black placeholder
                img = np.zeros((img_height, img_width, 3), dtype=np.uint8)
            else:
                # Ensure image has 3 channels (BGR)
                if len(img.shape) == 2:
                    # Convert grayscale to BGR
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                elif len(img.shape) == 3 and img.shape[2] == 4:
                    # Convert BGRA to BGR
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                elif len(img.shape) == 3 and img.shape[2] != 3:
                    logger.warning(
                        f"Image {i + 1} has {img.shape[2]} channels, expected 3. Converting..."
                    )
                    img = (
                        cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                        if img.shape[2] == 1
                        else img[:, :, :3]
                    )

                # Resize if needed
                if img.shape[:2] != (img_height, img_width):
                    img = cv2.resize(img, (img_width, img_height))

            # Calculate position on canvas
            y_start = row * (img_height - overlap)
            y_end = y_start + img_height
            x_start = col * (img_width - overlap)
            x_end = x_start + img_width

            # Ensure we don't exceed canvas bounds
            y_end = min(y_end, canvas_height)
            x_end = min(x_end, canvas_width)

            # Adjust image size if needed
            actual_height = y_end - y_start
            actual_width = x_end - x_start

            if actual_height != img_height or actual_width != img_width:
                img = cv2.resize(img, (actual_width, actual_height))

            # Place image on canvas
            canvas[y_start:y_end, x_start:x_end] = img

            logger.debug(
                f"Placed image {i + 1} at position ({row}, {col}) -> canvas[{y_start}:{y_end}, {x_start}:{x_end}]"
            )

        # Validate canvas before saving
        if canvas.size == 0:
            logger.error("Canvas is empty, cannot save")
            return False

        if canvas.dtype != np.uint8:
            logger.error(f"Canvas has wrong data type: {canvas.dtype}, expected uint8")
            return False

        if len(canvas.shape) != 3 or canvas.shape[2] != 3:
            logger.error(f"Canvas has wrong shape: {canvas.shape}, expected (height, width, 3)")
            return False

        # Save the stitched image
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Attempting to save canvas with shape: {canvas.shape}, dtype: {canvas.dtype}")

        try:
            success = cv2.imwrite(str(output_path), canvas)
            if success:
                logger.info(f"Successfully stitched 36 images into: {output_path}")
                return True
            else:
                logger.error(f"Failed to save stitched image: {output_path}")
                # Try saving as PNG if BMP fails
                if output_path.suffix.lower() == ".bmp":
                    png_path = output_path.with_suffix(".png")
                    logger.info(f"Attempting to save as PNG instead: {png_path}")
                    success = cv2.imwrite(str(png_path), canvas)
                    if success:
                        logger.info(f"Successfully saved as PNG: {png_path}")
                        return True
                    else:
                        logger.error(f"Failed to save as PNG: {png_path}")
                return False
        except Exception as e:
            logger.error(f"OpenCV error saving image: {str(e)}")
            logger.error(
                f"Canvas info - shape: {canvas.shape}, dtype: {canvas.dtype}, size: {canvas.size}"
            )
            # Try saving as PNG if BMP fails
            if output_path.suffix.lower() == ".bmp":
                png_path = output_path.with_suffix(".png")
                logger.info(f"Attempting to save as PNG instead: {png_path}")
                try:
                    success = cv2.imwrite(str(png_path), canvas)
                    if success:
                        logger.info(f"Successfully saved as PNG: {png_path}")
                        return True
                except Exception as png_e:
                    logger.error(f"Failed to save as PNG: {str(png_e)}")
            return False

    except Exception as e:
        logger.error(f"Error stitching images: {str(e)}")
        return False


def stitch_optical_images_from_folder(
    input_folder: str | Path,
    output_path: str | Path,
    file_pattern: str = "*.bmp",
    grid_size: tuple[int, int] = (6, 6),
    image_size: tuple[int, int] | None = None,
    overlap: int = 0,
) -> bool:
    """
    Stitch optical images from a folder into one whole image.

    Args:
        input_folder: Folder containing the optical images
        output_path: Path where the stitched image will be saved
        file_pattern: File pattern to match (default: "*.bmp")
        grid_size: Grid dimensions (rows, cols). Default is (6, 6) for 36 images
        image_size: Target size for each individual image (width, height)
        overlap: Number of pixels to overlap between adjacent images

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        input_folder = Path(input_folder)
        if not input_folder.exists():
            logger.error(f"Input folder does not exist: {input_folder}")
            return False

        # Find all matching image files
        image_files = sorted(input_folder.glob(file_pattern))

        if len(image_files) != 36:
            logger.error(f"Expected 36 images matching '{file_pattern}', found {len(image_files)}")
            logger.info(f"Found files: {[f.name for f in image_files]}")
            return False

        return stitch_optical_images(image_files, output_path, grid_size, image_size, overlap)

    except Exception as e:
        logger.error(f"Error stitching images from folder: {str(e)}")
        return False
