from pathlib import Path

import pandas as pd

from cgt_cell_analysis_demo.core.workers.base_worker import BaseWorker
from cgt_cell_analysis_demo.io.csv_io import read_two_row_header, write_two_row_header
from cgt_cell_analysis_demo.util.logger import log_format


class MergeCellCountPcr(BaseWorker):
    def __init__(
        self, sample_id: str, step2_output_folder: str, step3_output_folder: str, output_folder: str
    ):
        super().__init__()
        self.sample_id = sample_id
        self.step2_output_folder = Path(step2_output_folder)
        self.step3_output_folder = Path(step3_output_folder)
        self.output_folder = Path(output_folder)

    def run(self):
        """Main execution method for the worker"""
        try:
            self.signals.log.emit(
                log_format(f"Starting merge cell count PCR for sample: {self.sample_id}")
            )

            # Check if input folders exist
            if not self.step2_output_folder.exists():
                self.signals.error.emit(
                    log_format(
                        f"Step 2 output folder does not exist: {self.step2_output_folder}",
                        level="Error",
                    )
                )
                return

            if not self.step3_output_folder.exists():
                self.signals.error.emit(
                    log_format(
                        f"Step 3 output folder does not exist: {self.step3_output_folder}",
                        level="Error",
                    )
                )
                return

            # Create output folder
            self.output_folder.mkdir(parents=True, exist_ok=True)

            # Load cell count data from step 2
            cell_count_file = self.step2_output_folder / "Predicted_Cell_Count.csv"
            if not cell_count_file.exists():
                self.signals.error.emit(
                    log_format(f"Cell count file not found: {cell_count_file}", level="Error")
                )
                return

            self.signals.log.emit(log_format(f"Loading cell count data from: {cell_count_file}"))
            cell_count_df = pd.read_csv(cell_count_file)
            self.signals.log.emit(log_format(f"Cell count data loaded: {len(cell_count_df)} rows"))
            self.signals.log.emit(log_format(f"Cell count columns: {list(cell_count_df.columns)}"))

            # Validate required columns exist
            required_columns = ["Absolute Well Number", "Average Cell Count Score", "Cell Count"]
            missing_columns = [col for col in required_columns if col not in cell_count_df.columns]
            if missing_columns:
                self.signals.error.emit(
                    log_format(
                        f"Missing required columns in cell count data: {missing_columns}",
                        level="Error",
                    )
                )
                return

            # Process both G and R channel files
            saved_files = []
            for channel in ["G", "R"]:
                try:
                    self._process_channel(channel, cell_count_df)
                    saved_files.append(f"rawCellData_{channel}.csv")
                except Exception as e:
                    self.signals.error.emit(
                        log_format(f"Failed to process {channel} channel: {str(e)}", level="Error")
                    )
                    # Continue with other channel even if one fails
                    continue

            self.signals.done.emit(
                {
                    "output_folder": str(self.output_folder),
                    "sample_id": self.sample_id,
                    "merged_files": saved_files,
                }
            )

        except Exception as e:
            self.signals.error.emit(
                log_format(f"Merge cell count PCR failed: {str(e)}", level="Error")
            )
            raise

    def _process_channel(self, channel: str, cell_count_df: pd.DataFrame):
        """Process a specific channel (G or R)"""
        try:
            self.signals.log.emit(log_format(f"Processing {channel} channel"))

            # Load labeled raw data from step 3
            labeled_file = self.step3_output_folder / f"Labeled_rawData_{channel}.csv"
            if not labeled_file.exists():
                self.signals.error.emit(
                    log_format(f"Labeled raw data file not found: {labeled_file}", level="Error")
                )
                return

            self.signals.log.emit(log_format(f"Loading labeled raw data from: {labeled_file}"))

            # Read the file preserving its two-row metadata header.
            header, body = read_two_row_header(labeled_file)

            self.signals.log.emit(log_format(f"Labeled raw data loaded: {len(body)} rows"))

            # Check if Absolute Well Number column exists
            if "Absolute Well Number" not in body.columns:
                self.signals.error.emit(
                    log_format(
                        f"Absolute Well Number column not found in {channel} channel data",
                        level="Error",
                    )
                )
                return

            body["Absolute Well Number"] = body["Absolute Well Number"].fillna(-1).astype(int)
            cell_count_df["Absolute Well Number"] = (
                cell_count_df["Absolute Well Number"].fillna(-1).astype(int)
            )

            # Merge cell count data with labeled raw data
            self.signals.log.emit(
                log_format(f"Merging cell count data with {channel} channel data")
            )
            merged_df = body.merge(
                cell_count_df[["Absolute Well Number", "Average Cell Count Score", "Cell Count"]],
                on="Absolute Well Number",
                how="left",
            )

            # Fill NaN values with 0 for wells without cell count data
            merged_df["Average Cell Count Score"] = merged_df["Average Cell Count Score"].fillna(0)
            merged_df["Cell Count"] = merged_df["Cell Count"].fillna(0).astype(int)

            # Save merged data
            output_file = self.output_folder / f"rawCellData_{channel}.csv"
            self._save_merged_csv(header, merged_df, output_file)

            self.signals.log.emit(
                log_format(f"Saved merged {channel} channel data to: {output_file}")
            )

        except Exception as e:
            self.signals.error.emit(
                log_format(f"Failed to process {channel} channel: {str(e)}", level="Error")
            )
            raise

    def _save_merged_csv(self, header: pd.DataFrame, body: pd.DataFrame, output_path: Path):
        """Save merged CSV with its preserved two-row metadata header."""
        try:
            write_two_row_header(header, body, output_path)
        except Exception as e:
            self.signals.error.emit(
                log_format(f"Failed to save merged CSV: {str(e)}", level="Error")
            )
            raise
