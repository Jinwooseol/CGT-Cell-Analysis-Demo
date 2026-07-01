import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem

from cgt_cell_analysis_demo.ui.panels.base_file_tree_panel import (
    BaseFileLoadingWorker,
    BaseFileTreePanel,
)
from cgt_cell_analysis_demo.util.logger import log_format


class FileLoadingWorker(BaseFileLoadingWorker):
    """Background thread worker for file loading operations"""

    pass


class FileTreePanel(BaseFileTreePanel):
    """File tree panel for processing with sample structure validation"""

    def __init__(self, panel_type="Processing"):
        super().__init__(panel_type=panel_type)

    def _get_add_folder_tooltip(self):
        """Get the tooltip text for add folder button"""
        return "Add Folder"

    def _get_dialog_title(self):
        """Get the dialog title for folder selection"""
        return "Select Folder (Root or Sample)"

    def _get_loading_message(self, path_name):
        """Get the loading message"""
        return f"Loading files from {path_name}..."

    def _get_sample_type_text(self):
        """Get the sample type text"""
        return "Sample"

    def _get_context_menu_text(self):
        """Get the context menu text"""
        return "New Folder"

    def _get_remove_tooltip(self):
        """Get the remove tooltip text"""
        return "Select a root or sample to remove from tree"

    def _get_clear_message(self):
        """Get the clear selection message"""
        return "File tree selection cleared"

    def _create_loading_worker(self, path: Path):
        """Create the appropriate loading worker"""
        return FileLoadingWorker(self, path)

    def _add_folder_to_tree(self, path: Path):
        """Add a folder to the tree widget"""
        # Check if this is a sample folder (contains Optical_Data and/or PCR_Data)
        is_sample_folder = self._is_sample_folder(path)

        # Check if this folder is already in the tree
        if self._is_folder_already_in_tree(path):
            self.log.emit(log_format(f"Folder already exists in tree: {path}"))
            return

        if is_sample_folder:
            # This is a sample folder - add it directly as a sample
            self.log.emit(log_format(f"Loading sample folder: {path.name}"))
            self._add_sample_to_tree(None, path)
        else:
            # This is a parent folder - add as root and populate with samples
            self.log.emit(log_format(f"Loading parent folder: {path.name}"))
            root_item = QTreeWidgetItem(self.tree)
            root_item.setText(0, path.name)
            root_item.setText(1, "Root")
            root_item.setText(2, str(path))
            root_item.setData(0, Qt.UserRole, str(path))

            # Add sample directories
            self._populate_sample_tree(root_item, path)

            # Expand root
            root_item.setExpanded(True)

    def _populate_sample_tree(self, parent_item: QTreeWidgetItem, path: Path):
        """Populate tree with sample structure"""
        sample_count = 0
        try:
            for item in sorted(path.iterdir()):
                if item.is_dir():
                    # Check if this looks like a sample directory
                    if self._is_sample_folder(item):
                        self._add_sample_to_tree(parent_item, item)
                        sample_count += 1

        except PermissionError:
            pass

        if sample_count > 0:
            self.log.emit(log_format(f"Found {sample_count} sample(s) in parent folder"))

    def _is_sample_folder(self, path: Path):
        """Check if a folder is a sample folder"""
        if self.panel_type == "Training":
            # For training panels, check if folder contains training images
            return self._contains_training_images(path)
        else:
            # For processing panels, check for Optical_Data and/or PCR_Data
            try:
                optical_dir = path / "Optical_Data"
                pcr_dir = path / "PCR_Data"
                return (optical_dir.exists() and optical_dir.is_dir()) or (
                    pcr_dir.exists() and pcr_dir.is_dir()
                )
            except PermissionError:
                return False

    def _contains_training_images(self, path: Path) -> bool:
        """Check if a folder contains training images"""
        if not path.exists() or not path.is_dir():
            return False

        image_extensions = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

        try:
            # Check for images directly in the folder
            for file_path in path.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                    return True

            # If no images in root, check subdirectories
            for subdir in path.iterdir():
                if subdir.is_dir():
                    for file_path in subdir.iterdir():
                        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                            return True

        except PermissionError:
            pass

        return False

    def _add_sample_data(self, sample_item: QTreeWidgetItem, sample_path: Path):
        """Add sample-specific data for processing"""
        if self.panel_type == "Training":
            # For training panels, show individual training images as dropdown
            self._add_training_images(sample_item, sample_path)
        else:
            # For processing panels, use the original structure
            # Add Optical_Data if exists
            optical_dir = sample_path / "Optical_Data"
            if optical_dir.exists() and optical_dir.is_dir():
                optical_item = QTreeWidgetItem(sample_item)
                optical_item.setText(0, "Optical_Data")
                optical_item.setText(1, "Data")
                optical_item.setText(2, str(optical_dir))
                optical_item.setData(0, Qt.UserRole, str(optical_dir))

                # Add image folders
                self._add_image_folders(optical_item, optical_dir)

            # Add PCR_Data if exists
            pcr_dir = sample_path / "PCR_Data"
            if pcr_dir.exists() and pcr_dir.is_dir():
                pcr_item = QTreeWidgetItem(sample_item)
                pcr_item.setText(0, "PCR_Data")
                pcr_item.setText(1, "Data")
                pcr_item.setText(2, str(pcr_dir))
                pcr_item.setData(0, Qt.UserRole, str(pcr_dir))

                # Add PCR files and folders
                self._add_pcr_files(pcr_item, pcr_dir)

    def _add_training_images(self, sample_item: QTreeWidgetItem, sample_path: Path):
        """Add individual training images as dropdown items for training panels"""
        # Look for training images in the sample folder
        training_images = self._find_training_images(sample_path)
        labels = self._load_labels_from_csv(sample_path)

        if training_images and labels:
            # Add a "Training Images" folder item
            training_item = QTreeWidgetItem(sample_item)
            training_item.setText(0, "Training Images")
            training_item.setText(1, "Images")
            training_item.setText(2, str(sample_path))
            training_item.setData(0, Qt.UserRole, str(sample_path))

            # Add individual image files as children
            for image_path in training_images:
                image_item = QTreeWidgetItem(training_item)
                image_item.setText(0, image_path.name)
                image_item.setText(1, "Image")
                image_item.setText(2, str(image_path))
                image_item.setData(0, Qt.UserRole, str(image_path))

                image_name = image_path.name.split(".")[0]

                # Add label information if available
                if image_name in labels:
                    image_item.setText(3, labels[image_name])
                else:
                    image_item.setText(3, "No label")

            # Expand the training images folder
            training_item.setExpanded(True)
        else:
            # No training images found
            no_images_item = QTreeWidgetItem(sample_item)
            no_images_item.setText(0, "No Training Images")
            no_images_item.setText(1, "Info")
            no_images_item.setText(2, str(sample_path))
            no_images_item.setData(0, Qt.UserRole, str(sample_path))

    def _find_training_images(self, sample_path: Path) -> list:
        """Find training images in the sample folder"""
        training_images = []
        image_extensions = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

        try:
            # Look for images directly in the sample folder
            for file_path in sample_path.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                    training_images.append(file_path)

            # If no images found in root, look in subdirectories
            if not training_images:
                for subdir in sample_path.iterdir():
                    if subdir.is_dir():
                        for file_path in subdir.iterdir():
                            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                                training_images.append(file_path)

            # Sort images by name
            training_images.sort(key=lambda x: x.name)

        except PermissionError:
            pass

        return training_images

    def _load_labels_from_csv(self, folder_path: Path) -> dict:
        """Load label data from *_labels.csv file in the given folder"""
        if not folder_path.exists() or not folder_path.is_dir():
            return {}

        # Look for *_labels.csv files in the folder
        label_files = list(folder_path.glob("*_labels.csv"))
        if not label_files:
            return {}

        # Use the first found label file
        label_file = label_files[0]
        labels = {}

        self.log.emit(log_format(f"Loading labels from {label_file}"))
        try:
            with open(label_file, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Expect columns: Image Name, Label
                    if "Image Name" in row and "Label" in row:
                        image_name = row["Image Name"]
                        label_value = row["Label"]
                        labels[image_name] = label_value
        except Exception as e:
            self.log.emit(log_format(f"Error reading label file {label_file}: {e}"))

        return labels

    def _add_image_folders(self, parent_item: QTreeWidgetItem, optical_dir: Path):
        """Add image folders to optical data"""
        try:
            for item in sorted(optical_dir.iterdir()):
                if item.is_dir():
                    # Count images in folder
                    image_count = len(
                        [
                            f
                            for f in item.iterdir()
                            if f.is_file()
                            and f.suffix.lower()
                            in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
                        ]
                    )

                    folder_item = QTreeWidgetItem(parent_item)
                    folder_item.setText(0, f"{item.name} ({image_count} images)")
                    folder_item.setText(1, "Images")
                    folder_item.setText(2, str(item))
                    folder_item.setData(0, Qt.UserRole, str(item))
        except PermissionError:
            pass

    def _add_pcr_files(self, parent_item: QTreeWidgetItem, pcr_dir: Path):
        """Add PCR files and folders"""
        try:
            # Add .odpi files
            for file in sorted(pcr_dir.iterdir()):
                if file.is_file() and file.suffix.lower() == ".odpi":
                    file_item = QTreeWidgetItem(parent_item)
                    file_item.setText(0, file.name)
                    file_item.setText(1, "ODPI")
                    file_item.setText(2, str(file))
                    file_item.setData(0, Qt.UserRole, str(file))

            # Add data folders
            for item in sorted(pcr_dir.iterdir()):
                if item.is_dir():
                    # Count files in folder
                    file_count = len([f for f in item.iterdir() if f.is_file()])

                    folder_item = QTreeWidgetItem(parent_item)
                    folder_item.setText(0, f"{item.name} ({file_count} files)")
                    folder_item.setText(1, "Data")
                    folder_item.setText(2, str(item))
                    folder_item.setData(0, Qt.UserRole, str(item))
        except PermissionError:
            pass

    def _search_files_recursively(self, root_path: Path):
        """Search for test samples with hierarchical structure"""
        self.log.emit(log_format(f"Searching for test samples in: {root_path}"))

        found_samples = []
        optical_extensions = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
        pcr_extensions = {".odpi2", ".csv", ".png"}

        try:
            # Check if this is a sample folder itself
            is_sample_folder = self._is_sample_folder(root_path)
            self.log.emit(
                log_format(f"Root path '{root_path.name}' is sample folder: {is_sample_folder}")
            )

            if is_sample_folder:
                # This is a sample folder - analyze it directly
                self.log.emit(log_format(f"Analyzing sample folder: {root_path.name}"))
                sample_info = self._analyze_sample_structure(
                    root_path, optical_extensions, pcr_extensions
                )
                if sample_info:
                    found_samples.append(sample_info)
                    self.log.emit(log_format(f"Loaded sample folder: {root_path.name}"))
                else:
                    self.log.emit(
                        log_format(
                            f"Sample folder '{root_path.name}' analysis returned no valid data"
                        )
                    )
            else:
                # This is a parent folder - look for sample directories
                self.log.emit(log_format(f"Searching for sample directories in: {root_path.name}"))
                sample_count = 0
                for sample_dir in root_path.iterdir():
                    if sample_dir.is_dir():
                        sample_count += 1
                        self.log.emit(log_format(f"Checking directory: {sample_dir.name}"))
                        try:
                            sample_info = self._analyze_sample_structure(
                                sample_dir, optical_extensions, pcr_extensions
                            )
                            if sample_info:
                                found_samples.append(sample_info)
                                self.log.emit(log_format(f"Found valid sample: {sample_dir.name}"))
                            else:
                                self.log.emit(
                                    log_format(
                                        f"Directory '{sample_dir.name}' is not a valid sample"
                                    )
                                )
                        except Exception as e:
                            self.log.emit(
                                log_format(f"Error analyzing directory '{sample_dir.name}': {e}")
                            )
                self.log.emit(log_format(f"Checked {sample_count} directories in root folder"))

        except Exception as e:
            self.log.emit(log_format(f"Error searching samples: {e}"))

        # Store the found samples for later retrieval, sorted alphabetically
        # This ensures the first sample in the tree is the first sample processed
        self.current_samples = sorted(found_samples, key=lambda x: x.get("sample_id", ""))

        self.log.emit(log_format(f"Found {len(found_samples)} test samples"))
        # Log the order of samples for debugging
        for i, sample in enumerate(self.current_samples):
            sample_id = sample.get("sample_id", "Unknown")
            self.log.emit(log_format(f"Sample {i + 1}: {sample_id}"))
        self.samples_found.emit(self.current_samples)

        # Emit loading finished signal
        self.loading_finished.emit()

    def _analyze_sample_structure(
        self, sample_path: Path, optical_extensions: set, pcr_extensions: set
    ):
        """Analyze a sample directory for the expected structure"""
        sample_name = sample_path.name
        self.log.emit(log_format(f"Analyzing sample structure for: {sample_name}"))

        sample_info = {
            "sample_id": sample_name,
            "sample_path": str(sample_path),
            "optical_data": None,
            "pcr_data": None,
            "is_valid": False,
        }

        # Use the existing find methods to locate optical and PCR folders
        optical_folder = self._find_optical_folder(sample_path)
        pcr_folder = self._find_pcr_folder(sample_path)

        # Set optical data if found
        if optical_folder:
            sample_info["optical_data"] = {
                "path": str(optical_folder),
                "image_folders": [
                    {"folder_name": optical_folder.name, "folder_path": str(optical_folder)}
                ],
                "total_images": len(list(optical_folder.glob("*.bmp"))),
            }
            self.log.emit(
                log_format(
                    f"  Found optical data: {sample_info['optical_data']['total_images']} BMP files"
                )
            )

        # Set PCR data if found
        if pcr_folder:
            sample_info["pcr_data"] = {
                "path": str(pcr_folder),
                "odpi_files": [],
                "data_folders": [{"folder_name": pcr_folder.name, "folder_path": str(pcr_folder)}],
                "total_files": len(list(pcr_folder.iterdir())),
            }
            self.log.emit(log_format(f"  Found PCR data: {pcr_folder.name}"))

        # Sample is valid if it has either optical or PCR data
        sample_info["is_valid"] = (
            sample_info["optical_data"] is not None or sample_info["pcr_data"] is not None
        )
        self.log.emit(log_format(f"  Sample '{sample_name}' is valid: {sample_info['is_valid']}"))

        return sample_info if sample_info["is_valid"] else None

    def _find_optical_folder(self, sample_path: Path) -> Path:
        """Find optical image folder in the sample"""
        if not sample_path.exists() or not sample_path.is_dir():
            return None

        # Look for optical data folders
        for subdir in sample_path.iterdir():
            if subdir.is_dir() and subdir.name.lower() == "optical_data":
                if self._contains_optical_files(subdir):
                    return subdir
                else:
                    for subsubdir in subdir.iterdir():
                        if subsubdir.is_dir() and self._contains_optical_files(subsubdir):
                            return subsubdir

        return None

    def _contains_optical_files(self, path: Path) -> bool:
        """Check if the path contains BMP files and warn if less than 36 files"""
        if not path.exists() or not path.is_dir():
            return False

        # Count BMP files in the directory
        bmp_files = list(path.glob("*.bmp"))
        bmp_count = len(bmp_files)

        if bmp_count > 0:
            # Warn if there are fewer than 36 BMP files
            if bmp_count < 36:
                self.log.emit(
                    log_format(
                        f"Warning: Found only {bmp_count} BMP files in {path.name}, expected at least 36"
                    )
                )
            return True

        return False

    def _find_pcr_folder(self, sample_path: Path) -> Path:
        """Find PCR data folder in the sample by looking for specific PCR files"""
        if not sample_path.exists() or not sample_path.is_dir():
            return None

        # Look for folders containing the specific PCR files
        for subdir in sample_path.iterdir():
            if subdir.is_dir() and subdir.name.lower() == "pcr_data":
                if self._contains_pcr_files(subdir):
                    return subdir
                else:
                    for subsubdir in subdir.iterdir():
                        if subsubdir.is_dir() and self._contains_pcr_files(subsubdir):
                            return subsubdir

        return None

    def _contains_pcr_files(self, folder: Path) -> bool:
        """Check if folder contains the specific PCR files: rawData_G.csv, rawData_R.csv, well_1cycle.png"""
        if not folder.exists() or not folder.is_dir():
            return False

        # Check for the specific PCR files
        required_files = ["rawData_G.csv", "rawData_R.csv", "well_1cycle.png"]
        found_files = set()

        for file_path in folder.iterdir():
            if file_path.is_file():
                file_name = file_path.name
                if file_name in required_files:
                    found_files.add(file_name)

        # Return True if all required files are found
        return len(found_files) == len(required_files)

    def _handle_image_selection(self, item: QTreeWidgetItem):
        """Handle when an image is selected"""
        path_data = item.data(0, Qt.UserRole)
        if path_data:
            image_path = Path(path_data)
            self.log.emit(log_format(f"Image selected: {image_path}"))

        self.image_selected.emit(self.panel_type, image_path)

    def _handle_sample_selection(self, item: QTreeWidgetItem):
        """Handle when a sample is selected"""
        path_data = item.data(0, Qt.UserRole)
        file_type = item.text(1)

        if not path_data:
            return

        current_path = Path(path_data)
        current_name = item.text(0)
        parent = item.parent()

        # Determine sample path and name based on item type
        sample_path, sample_name = self._get_sample_info(
            item, file_type, current_path, current_name, parent
        )

        if not sample_path:
            self._clear_pipeline_inputs()
            return

        # Find optical and PCR data folders
        optical_folder = self._find_optical_folder(sample_path)
        pcr_folder = self._find_pcr_folder(sample_path)

        # Log selection details
        self._log_sample_selection(sample_path, sample_name, current_path, current_name)

        # Create and emit sample data
        sample_data = {
            "sample_name": sample_name,
            "sample_path": str(sample_path),
            "optical_folder": str(optical_folder) if optical_folder else None,
            "pcr_folder": str(pcr_folder) if pcr_folder else None,
            "training_folder": str(current_path) if self.panel_type == "Training" else None,
        }

        self.sample_selected.emit(sample_data)
        self.log.emit(log_format(f"Sample selected: {sample_name}"))
        if optical_folder:
            self.log.emit(log_format(f"  Optical folder: {optical_folder}"))
        if pcr_folder:
            self.log.emit(log_format(f"  PCR folder: {pcr_folder}"))

    def _get_sample_info(
        self,
        item: QTreeWidgetItem,
        file_type: str,
        current_path: Path,
        current_name: str,
        parent: QTreeWidgetItem,
    ):
        """Extract sample path and name based on item type"""
        if file_type == "Sample":
            return current_path, current_name

        elif file_type == "Data" and parent is not None:
            sample_path = Path(parent.data(0, Qt.UserRole))
            sample_name = parent.text(0)
            return sample_path, sample_name

        elif file_type == "Root":
            # Find first sample in root folder
            for i in range(item.childCount()):
                child = item.child(i)
                if child.text(1) == "Sample":
                    return Path(child.data(0, Qt.UserRole)), child.text(0)
            return None, None

        else:
            # Walk up tree to find sample parent
            current_item = item
            while current_item.parent() is not None:
                current_item = current_item.parent()
                if current_item.text(1) == "Sample":
                    return Path(current_item.data(0, Qt.UserRole)), current_item.text(0)
            return None, None

    def _log_sample_selection(
        self, sample_path: Path, sample_name: str, current_path: Path, current_name: str
    ):
        """Log sample selection details"""
        self.log.emit(log_format(f"Sample path: {sample_path}"))
        self.log.emit(log_format(f"Sample name: {sample_name}"))
        self.log.emit(log_format(f"Current path: {current_path}"))
        self.log.emit(log_format(f"Current name: {current_name}"))

    def _clear_pipeline_inputs(self):
        """Clear all pipeline inputs when non-sample is selected"""
        # Create empty sample data to clear inputs
        empty_sample_data = {
            "sample_name": "",
            "sample_path": "",
            "optical_folder": None,
            "pcr_folder": None,
        }

        # Emit signal to clear pipeline inputs
        self.sample_selected.emit(empty_sample_data)
        self.log.emit(log_format("Pipeline inputs cleared - no sample selected"))

    def _is_sample_item(self, item: QTreeWidgetItem) -> bool:
        """Check if the item represents a sample (not a root folder)"""
        if not item:
            return False

        # 1) Trust the explicit Type column first
        file_type = item.text(1)
        if file_type == "Root":
            return False
        if file_type == "Sample":
            return True
        if file_type == "Data":
            # A data folder directly under a Sample implies the parent is the sample
            parent = item.parent()
            return bool(parent and parent.text(1) == "Sample")

        # 2) Fallback to structural inference when Type is missing/unknown
        path_data = item.data(0, Qt.UserRole)
        if not path_data:
            return False
        path = Path(path_data)

        if path.exists() and path.is_dir():
            try:
                subdirs = [d.name.lower() for d in path.iterdir() if d.is_dir()]
            except PermissionError:
                subdirs = []
            if "optical_data" in subdirs or "pcr_data" in subdirs:
                return True

        # 3) As a last resort, if this is a data folder directly under a folder
        #    that looks like a sample (based on Type), treat parent as sample
        parent = item.parent()
        if parent and parent.text(1) == "Sample":
            item_text = item.text(0).lower()
            return item_text in ["optical_data", "pcr_data"]

        return False

    def _is_image_item(self, item: QTreeWidgetItem) -> bool:
        """Check if the item represents an image"""
        if not item:
            return False
        file_type = item.text(1)
        return file_type == "Image"
