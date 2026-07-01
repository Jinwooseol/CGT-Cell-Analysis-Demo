import os
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from cgt_cell_analysis_demo.core.workers.base_worker import BaseWorker
from cgt_cell_analysis_demo.core.workers.well_index_common import (
    align_image,
    blend_images,
    detect_markers,
    estimate_grid_properties,
    extract_grid_points,
    find_overlap_transform,
    get_center_positioned_image,
    match_well_index,
    process_image,
    read_raw_channel_csv,
    read_ref_csv,
    write_csv,
)
from cgt_cell_analysis_demo.util.logger import log_format

# Standard marker grid spacing (pixels)
MARKER_H_SPACING_PX = 192.0  # horizontal spacing
MARKER_V_SPACING_PX = 178.0  # vertical spacing

# Enable debug mode to save intermediate images
DEBUG_FEATURE = True


class PcrWellIndexingWorker(BaseWorker):
    """
    PCR well indexing worker that processes PCR images and matches wells to reference coordinates.
    """

    def __init__(self, pcr_dir: str, ref_paths, out_dir: str, kernel_size: int = 6):
        super().__init__()
        self.pcr_dir = Path(pcr_dir)
        self.ref_paths = ref_paths
        self.out_dir = Path(out_dir)
        self.kernel_size = kernel_size

    def run(self):
        try:
            self.signals.log.emit(
                log_format(
                    f"[PcrWellIndex] Processing pcr_dir={self.pcr_dir}, out_dir={self.out_dir}"
                )
            )
            step3_start_time = time.time()
            # Ensure output directory exists
            os.makedirs(self.out_dir, exist_ok=True)

            # Step 1: Load reference data
            ref_map_image = cv2.imread(str(self.ref_paths.sensor_map_tif), cv2.IMREAD_GRAYSCALE)
            ref_markers_5x5 = read_ref_csv(self.ref_paths.marker_5x5_csv)
            ref_wells = read_ref_csv(self.ref_paths.well_csv)

            if ref_map_image is None or ref_markers_5x5 is None or ref_wells is None:
                self.signals.error.emit(log_format("Reference data not found"))
                return

            ref_well_centers = ref_wells[["X coordination", "Y coordination"]].to_numpy()

            if DEBUG_FEATURE:
                ref_well_center_image = get_center_positioned_image(
                    ref_map_image,
                    ref_well_centers,
                    self.out_dir,
                    "ref_well_centers.png",
                    dot_color=(255, 0, 0),
                )
                ref_well_index_list = np.arange(1, len(ref_well_centers) + 1).astype(str).tolist()
                ref_well_number_labeled_image = get_center_positioned_image(
                    ref_map_image,
                    ref_well_centers,
                    self.out_dir,
                    "ref_well_numbered.png",
                    contours=None,
                    display_boundary=False,
                    display_well_index=True,
                    display_well_index_list=ref_well_index_list,
                )

            pcr_file = self.pcr_dir / "well_1cycle.png"

            if not pcr_file.exists():
                self.signals.error.emit(log_format("No PCR image files found"))
                return

            self.signals.log.emit(log_format(f"Processing PCR file: {pcr_file.name}"))

            # Process the PCR image
            self._process_pcr_image(
                pcr_file,
                self.out_dir,
                ref_map_image,
                ref_markers_5x5,
                ref_wells,
                ref_well_center_image,
                ref_well_number_labeled_image,
            )

            self.signals.done.emit({"output_folder": str(self.out_dir)})
            step3_end_time = time.time()
            step3_duration = step3_end_time - step3_start_time
            self.signals.log.emit(
                log_format(
                    f"[Step3] Grid estimation and synthesis completed in {step3_duration:.3f} seconds"
                )
            )

        except RuntimeError as e:
            if "canceled" in str(e).lower():
                self.signals.log.emit(log_format("[PcrWellIndex] Canceled by user"))
            else:
                self.signals.error.emit(
                    log_format(f"[PcrWellIndex] Error: {str(e)}", level="Error")
                )
        except Exception as e:
            self.signals.error.emit(log_format(f"[PcrWellIndex] Error: {str(e)}", level="Error"))

    def _process_pcr_image(
        self,
        pcr_file,
        image_folder,
        ref_map_image,
        ref_markers_5x5,
        ref_wells,
        ref_well_center_image,
        ref_well_number_labeled_image,
    ):
        """Process a single PCR image"""
        # Step 1-1: Load PCR image
        pcr_image = cv2.imread(str(pcr_file), cv2.IMREAD_GRAYSCALE)
        if pcr_image is None:
            self.signals.log.emit(log_format(f"  - skip (cannot read {pcr_file.name})"))
            return

        # Step 1-2: Load raw data CSV files
        rawData_G_csv_file = self.pcr_dir / "rawData_G.csv"
        rawData_R_csv_file = self.pcr_dir / "rawData_R.csv"

        G_wells = read_raw_channel_csv(rawData_G_csv_file)
        R_wells = read_raw_channel_csv(rawData_R_csv_file)

        if G_wells is None or R_wells is None:
            self.signals.log.emit(log_format("  - skip (missing rawData CSV files)"))
            return

        G_well_centers = G_wells[["X coordination", "Y coordination"]].to_numpy()
        R_well_centers = R_wells[["X coordination", "Y coordination"]].to_numpy()

        self.signals.progress.emit(20)

        # Step 2: Get marker positions of PCR image
        pcr_marker_binary_image = process_image(
            pcr_image, image_folder, is_marker=True, is_reference=False, debug=DEBUG_FEATURE
        )
        pcr_marker_centers, filtered_marker_contours = detect_markers(
            pcr_marker_binary_image, is_reference=False, kernel_size=self.kernel_size
        )

        if DEBUG_FEATURE and len(pcr_marker_centers) > 0:
            try:
                from cgt_cell_analysis_demo.core.workers.well_index_common import (
                    compute_sub_roi_rects,
                )

                sub_rois = compute_sub_roi_rects(pcr_image.shape, self.kernel_size)
            except Exception:
                sub_rois = []

            _ = get_center_positioned_image(
                pcr_image,
                pcr_marker_centers,
                image_folder,
                "All_Detected_Markers.png",
                dot_color=(0, 0, 255),
                contours=filtered_marker_contours,
                display_boundary=True,
                display_well_index=True,
                display_well_index_list=[str(i + 1) for i in range(len(pcr_marker_centers))],
                sub_roi_rects=sub_rois,
                display_sub_roi=True,
            )

        if len(pcr_marker_centers) < 4:
            self.signals.log.emit(
                log_format(f"  - skip (insufficient markers: {len(pcr_marker_centers)})")
            )
            return

        self.signals.progress.emit(30)

        # Step 3: Estimate grid axes, then use FIXED spacing to synthesize a 5x5 grid
        principal_axes, _, _ = estimate_grid_properties(pcr_marker_centers)
        h_spacing, v_spacing = MARKER_H_SPACING_PX, MARKER_V_SPACING_PX
        self.signals.log.emit(
            log_format(f"  - Using fixed spacing H={h_spacing:.1f}px, V={v_spacing:.1f}px")
        )

        grid_points = extract_grid_points(
            pcr_marker_centers, principal_axes, h_spacing, v_spacing, tolerance=100
        )

        if DEBUG_FEATURE:
            # Save estimated grid to CSV
            grid_df = pd.DataFrame(grid_points)
            if len(grid_df) > 0:
                grid_df.columns = ["X coordination", "Y coordination"]
                grid_df["Well Number"] = range(1, len(grid_df) + 1)
                grid_df.insert(0, "Well Number", grid_df.pop("Well Number"))
                write_csv(grid_df, image_folder / "center_position.csv")
            _ = get_center_positioned_image(
                pcr_image,
                pcr_marker_centers,
                image_folder,
                "Detected_Markers.png",
                dot_color=(0, 0, 255),
                contours=filtered_marker_contours,
                display_boundary=True,
                display_well_index=True,
                display_well_index_list=[str(i + 1) for i in range(len(pcr_marker_centers))],
            )
            _ = get_center_positioned_image(
                pcr_image, G_well_centers, image_folder, "Well_indexing.png"
            )

        self.signals.progress.emit(40)

        # Step 4: Calculate transformation matrix
        ref_marker_points = np.array(ref_markers_5x5[["X coordination", "Y coordination"]])
        self.signals.log.emit(
            log_format(
                f"  - Grid points: {len(grid_points)}, Ref markers: {len(ref_marker_points)}"
            )
        )

        transform_matrix = find_overlap_transform(grid_points, ref_marker_points)
        self.signals.log.emit(log_format("  - Transform matrix calculated"))

        self.signals.progress.emit(60)

        # Step 5: Transform well coordinates
        G_transformed_well_centers = cv2.transform(np.array([G_well_centers]), transform_matrix)[
            0
        ].astype(int)
        R_transformed_well_centers = cv2.transform(np.array([R_well_centers]), transform_matrix)[
            0
        ].astype(int)

        G_transformed_wells = pd.DataFrame(G_transformed_well_centers)
        G_transformed_wells.columns = ["X coordination", "Y coordination"]
        G_transformed_wells["Well Number"] = G_wells["Well Number"]
        G_transformed_wells.insert(0, "Well Number", G_transformed_wells.pop("Well Number"))

        R_transformed_wells = pd.DataFrame(R_transformed_well_centers)
        R_transformed_wells.columns = ["X coordination", "Y coordination"]
        R_transformed_wells["Well Number"] = R_wells["Well Number"]
        R_transformed_wells.insert(0, "Well Number", R_transformed_wells.pop("Well Number"))

        if DEBUG_FEATURE:
            aligned_image = align_image(
                pcr_image, transform_matrix, (ref_map_image.shape[1], ref_map_image.shape[0])
            )
            well_center_image = get_center_positioned_image(
                aligned_image, G_transformed_well_centers, image_folder, "Well_indexing.png"
            )
            blended_image = blend_images(ref_well_center_image, well_center_image)
            cv2.imwrite(str(image_folder / "Blended_Image.png"), blended_image)

        self.signals.progress.emit(80)

        # Step 6: Match wells to reference coordinates
        G_matched_well_centers = match_well_index(ref_wells, G_transformed_wells, threshold=25)
        R_matched_well_centers = match_well_index(ref_wells, R_transformed_wells, threshold=25)

        self.signals.log.emit(
            log_format(
                f"  - G wells matched: {len(G_matched_well_centers)}, R wells matched: {len(R_matched_well_centers)}"
            )
        )

        # Save results
        self._save_matched_results(
            image_folder,
            aligned_image,
            ref_well_number_labeled_image,
            G_matched_well_centers,
            R_matched_well_centers,
            rawData_G_csv_file,
            rawData_R_csv_file,
        )

        self.signals.progress.emit(100)

    def _save_matched_results(
        self,
        image_folder,
        aligned_image,
        ref_well_number_labeled_image,
        G_matched_well_centers,
        R_matched_well_centers,
        rawData_G_csv_file,
        rawData_R_csv_file,
    ):
        """Save matched well results"""
        if DEBUG_FEATURE:
            # Save G channel results
            G_output_file_path = image_folder / "Absolute_Well_Number_G.csv"
            G_matched_well_centers.to_csv(G_output_file_path, index=False)

            G_matched_well_center_points = (
                G_matched_well_centers[["X coordination", "Y coordination"]].to_numpy().tolist()
            )
            G_well_index_list = (
                G_matched_well_centers["Absolute Well Number"].astype(str).to_numpy().tolist()
            )

            G_matched_well_center_image = get_center_positioned_image(
                aligned_image,
                G_matched_well_center_points,
                image_folder,
                "Matched_Well_indexing_G.png",
                contours=None,
                display_boundary=False,
                display_well_index=True,
                display_well_index_list=G_well_index_list,
            )

            G_blended_image = blend_images(
                ref_well_number_labeled_image, G_matched_well_center_image
            )
            cv2.imwrite(str(image_folder / "Blended_Matching_Label_Image_G.png"), G_blended_image)

            # Save R channel results
            R_output_file_path = image_folder / "Absolute_Well_Number_R.csv"
            R_matched_well_centers.to_csv(R_output_file_path, index=False)

            R_matched_well_center_points = (
                R_matched_well_centers[["X coordination", "Y coordination"]].to_numpy().tolist()
            )
            R_well_index_list = (
                R_matched_well_centers["Absolute Well Number"].astype(str).to_numpy().tolist()
            )

            R_matched_well_center_image = get_center_positioned_image(
                aligned_image,
                R_matched_well_center_points,
                image_folder,
                "Matched_Well_indexing_R.png",
                contours=None,
                display_boundary=False,
                display_well_index=True,
                display_well_index_list=R_well_index_list,
            )

            R_blended_image = blend_images(
                ref_well_number_labeled_image, R_matched_well_center_image
            )
            cv2.imwrite(str(image_folder / "Blended_Matching_Label_Image_R.png"), R_blended_image)

        # Add CGT data to rawData CSV files
        G_output_file_path = image_folder / "Labeled_rawData_G.csv"
        R_output_file_path = image_folder / "Labeled_rawData_R.csv"
        self._add_CGT_data_to_rawData_csv(
            rawData_G_csv_file, G_output_file_path, G_matched_well_centers
        )
        self._add_CGT_data_to_rawData_csv(
            rawData_R_csv_file, R_output_file_path, R_matched_well_centers
        )

    def _add_CGT_data_to_rawData_csv(self, csv_file_path, output_file_path, matched_wells):
        """Add CGT data to rawData CSV file"""
        try:
            matched_well_idxs = matched_wells[["Well Number", "Absolute Well Number"]]

            # 1) Preserve the two-row metadata header and load the body
            header = pd.read_csv(csv_file_path, encoding="utf8", nrows=2, header=None)
            body = pd.read_csv(csv_file_path, encoding="utf8", header=2)

            # 2) Drop Unnamed columns
            body = body.loc[:, ~body.columns.str.contains(r"^Unnamed")]
            body = body.merge(matched_well_idxs, on="Well Number", how="left")

            matched_well_centers = matched_wells["Well Number"]
            matched_well_centers.columns = ["Well Number"]
            body = body.merge(matched_well_centers, on="Well Number", how="left")

            header.to_csv(output_file_path, index=False, mode="w", header=False)
            body.to_csv(output_file_path, index=False, mode="a", header=True)
        except Exception as e:
            self.signals.log.emit(log_format(f"Error processing CSV {csv_file_path}: {str(e)}"))
