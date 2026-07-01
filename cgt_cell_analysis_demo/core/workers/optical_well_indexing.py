# cgt_cell_analysis_demo/core/workers/optical_well_index.py
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from cgt_cell_analysis_demo.core.workers.base_worker import BaseWorker
from cgt_cell_analysis_demo.core.workers.well_index_common import (
    RefPaths,
    align_image,
    blend_images,
    detect_wells,
    ensure_dir,
    estimate_grid_properties,
    extract_grid_points,
    find_missing_hex_centers,
    find_overlap_transform,
    get_center_positioned_image,
    get_ref_tile_marker,
    match_well_index,
    process_image,
    read_ref_csv,
    save_well_images_direct,
    sort_contours_by_centers,
    transform_points,
    write_csv,
)
from cgt_cell_analysis_demo.util.logger import log_format


class OpticalWellIndexWorker(BaseWorker):
    """
    Take a folder of optical tile images (e.g. YYMMDD_hhmmss_##.bmp) and, for each tile,
    perform well indexing -> coordinate transform -> Well image cropping.
    Outputs:
      - per-tile debug images / CSV (out/<tile_name>/*)
      - well crop (out/Well_Image/Well_<absIndex>_<tile>.png)
    """

    def __init__(
        self,
        tiles_dir: str,  # folder of optical tile images
        ref: RefPaths,  # reference paths (sensor_map, 7x7, wells)
        out_dir: str,  # output root (e.g. work/<sid>/03_opt_extract)
        kernel_size: int = 6,
        debug: bool = True,
    ):
        super().__init__()
        self.tiles_dir = Path(tiles_dir)
        self.ref = ref
        self.out_dir = Path(out_dir)
        self.kernel_size = kernel_size
        self.debug = debug

    def run(self):
        try:
            start_time = time.perf_counter()
            # Enable OpenCV global optimizations to speed up filters, transforms, and I/O
            cv2.setUseOptimized(True)
            cv2.setNumThreads(0)  # let OpenCV decide, avoids Python-level GIL contention
            ensure_dir(self.out_dir)

            # Step 1: Load reference sensor map datas
            ref_img = cv2.imread(str(self.ref.sensor_map_tif), cv2.IMREAD_GRAYSCALE)
            ref_markers_7x7 = (
                read_ref_csv(self.ref.marker_7x7_csv) if self.ref.marker_7x7_csv else None
            )
            ref_wells = read_ref_csv(self.ref.well_csv) if self.ref.well_csv else None
            if ref_img is None or ref_markers_7x7 is None or ref_wells is None:
                self.signals.error.emit(
                    log_format("Reference data not found (sensor map / markers7x7 / wells).")
                )
                return

            ref_well_centers = ref_wells[["X coordination", "Y coordination"]].to_numpy()
            ref_well_center_image = get_center_positioned_image(
                ref_img, ref_well_centers, self.out_dir, "", (255, 0, 0)
            )
            ref_well_index_list = np.arange(1, len(ref_well_centers) + 1).astype(str).tolist()
            ref_well_number_labeled_image = get_center_positioned_image(
                ref_img,
                ref_well_centers,
                self.out_dir,
                "",
                contours=None,
                display_boundary=False,
                display_well_index=True,
                display_well_index_list=ref_well_index_list,
            )

            tile_files = sorted(
                [
                    p
                    for p in self.tiles_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in (".bmp")
                ]
            )
            total = len(tile_files)
            if not total:
                self.signals.error.emit(log_format("No tile images in optical folder."))
                return

            self.signals.log.emit(log_format(f"Total {total} tile images found"))

            well_img_dir = ensure_dir(self.out_dir / "Well_Image")
            for i, tile in enumerate(tile_files, 1):
                self.check_abort()  # Check for cancellation before processing each tile

                # Update progress more frequently for better responsiveness
                progress = int((i - 1) / total * 100)
                self.signals.progress.emit(progress)

                tile_name = tile.stem

                # Infer the tile number (digits after the last underscore)
                try:
                    tile_num = int(tile_name.split("_")[-1])
                except Exception:
                    tile_num = i

                tile_out = ensure_dir(self.out_dir / tile_name)
                self.signals.log.emit(log_format(f"Processing tile: {tile.name}"))

                # Step 2: Read tile image
                ori_tile_img = cv2.imread(str(tile), cv2.IMREAD_GRAYSCALE)
                if ori_tile_img is None:
                    self.signals.log.emit(log_format("  - skip (cannot read)"))
                    continue

                # Image binarization
                opt_well_binary_img = process_image(
                    ori_tile_img,
                    tile_out,
                    is_optical=True,
                    is_marker=False,
                    is_reference=False,
                    debug=self.debug,
                )

                # Find wells from optical time image
                opt_well_centers, well_contours = detect_wells(
                    opt_well_binary_img,
                    is_reference=False,
                    is_optical=True,
                    kernel_size=self.kernel_size,
                )
                if len(opt_well_centers) < 4 or len(well_contours) < 4:
                    self.signals.log.emit(
                        log_format(f"  - wells not enough ({len(opt_well_centers)})")
                    )
                    continue

                # Find markers from optical time image
                opt_marker_centers = find_missing_hex_centers(
                    opt_well_binary_img, opt_well_centers, threshold=20
                )
                if len(opt_marker_centers) != 4:
                    self.signals.log.emit(
                        log_format(f"  - markers not enough ({len(opt_marker_centers)}) → skip")
                    )
                    continue
                if self.debug:
                    self.signals.log.emit(
                        log_format(f"  - markers found ({len(opt_marker_centers)})")
                    )
                    _ = get_center_positioned_image(
                        ori_tile_img,
                        opt_marker_centers,
                        tile_out,
                        "Marker.png",
                        dot_color=(0, 0, 255),
                        dot_radius=5,
                    )

                # Grid PCA -> select grid points
                axes, hx, hy = estimate_grid_properties(opt_marker_centers)

                grid_pts = extract_grid_points(opt_marker_centers, axes, hx, hy, tolerance=100)

                if len(grid_pts) != 4:
                    self.signals.log.emit(log_format("  - grid points not sufficient"))
                    continue

                if self.debug:
                    df_grid_pts = pd.DataFrame(
                        grid_pts, columns=["X coordination", "Y coordination"]
                    )
                    df_grid_pts["Well Number"] = range(1, len(df_grid_pts) + 1)
                    df_grid_pts.insert(0, "Well Number", df_grid_pts.pop("Well Number"))
                    write_csv(df_grid_pts, tile_out / "center_position.csv")

                self.signals.log.emit(log_format(f"  - grid points found ({len(grid_pts)})"))

                h, w = ref_img.shape[:2]
                ref_tile_marker = get_ref_tile_marker(
                    ref_markers_7x7[["X coordination", "Y coordination"]].to_numpy().tolist(),
                    w,
                    h,
                    tile_num - 1,
                )

                if self.debug:
                    _ = get_center_positioned_image(
                        ref_img,
                        ref_tile_marker,
                        tile_out,
                        "Ref_Tile_Marker.png",
                        dot_color=(0, 0, 255),
                        dot_radius=5,
                    )

                # Estimate an affine transform against part of the reference (7x7)
                affine = find_overlap_transform(np.array(grid_pts), np.array(ref_tile_marker))
                self.check_abort()  # Check for cancellation after heavy computation

                self.signals.log.emit(log_format(f"  - overlap transform found ({len(affine)})"))

                # Transform well centers -> match against reference wells
                tr_well_centers = transform_points(opt_well_centers, affine)
                self.check_abort()  # Check for cancellation after another heavy computation
                tr_df = pd.DataFrame(tr_well_centers, columns=["X coordination", "Y coordination"])
                tr_df["Well Number"] = list(range(len(tr_df)))

                if self.debug:
                    aligned_image = align_image(
                        ori_tile_img, affine, (ref_img.shape[1], ref_img.shape[0])
                    )
                    well_center_image = get_center_positioned_image(
                        aligned_image, tr_well_centers, tile_out, ""
                    )

                    blended_image = blend_images(ref_well_center_image, well_center_image)
                    blended_image_path = tile_out / "Blended_Image.png"
                    cv2.imwrite(str(blended_image_path), blended_image)

                matched_wells = match_well_index(ref_wells, tr_df, threshold=25)

                if matched_wells.empty:
                    self.signals.log.emit(log_format("  - match failed (empty)"))
                    continue

                self.signals.log.emit(log_format(f"  - match found ({len(matched_wells)})"))

                matched_well_points = (
                    matched_wells[["X coordination", "Y coordination"]].to_numpy().tolist()
                )
                abs_well_idx_list = (
                    matched_wells["Absolute Well Number"].astype(str).to_numpy().tolist()
                )
                tile_idx_list = matched_wells["Well Number"].to_numpy().tolist()

                self.signals.log.emit(log_format(f"  - tile idx list found ({len(tile_idx_list)})"))

                if self.debug:
                    matched_well_center_image = get_center_positioned_image(
                        aligned_image,
                        matched_well_points,
                        tile_out,
                        "Matched_Well_indexing.png",
                        contours=None,
                        display_boundary=False,
                        display_well_index=True,
                        display_well_index_list=abs_well_idx_list,
                    )

                    blended_image = blend_images(
                        ref_well_number_labeled_image, matched_well_center_image
                    )
                    blended_image_path = tile_out / "Blended_Matching_Label_Image.png"
                    cv2.imwrite(str(blended_image_path), blended_image)

                # Order contours -> save well crops
                sorted_cs = sort_contours_by_centers(tile_idx_list, opt_well_centers, well_contours)
                # Direct-save wells to reduce memory and I/O overhead
                save_well_images_direct(
                    ori_tile_img,
                    sorted_cs,
                    abs_well_idx_list,
                    well_img_dir,
                    tile_num,
                    png_compression=1,
                )

                # Save CSV / debug output
                write_csv(matched_wells, tile_out / "Absolute_Well_Number.csv")
                self.signals.log.emit(
                    log_format(f"  - csv saved ({tile_out / 'Absolute_Well_Number.csv'}")
                )

                # timing
                self.signals.progress.emit(int(i / total * 100))

            elapsed = time.perf_counter() - start_time
            self.signals.done.emit(
                {"output_folder": str(self.out_dir), "elapsed_time": f"{elapsed:.3f} s"}
            )
        except RuntimeError as e:
            if "canceled" in str(e).lower():
                self.signals.log.emit(log_format("[OptWellIndex] Canceled by user"))
            else:
                self.signals.error.emit(
                    log_format(f"[OptWellIndex] Error: {str(e)}", level="Error")
                )
        except Exception as e:
            self.signals.error.emit(log_format(str(e), level="Error"))
