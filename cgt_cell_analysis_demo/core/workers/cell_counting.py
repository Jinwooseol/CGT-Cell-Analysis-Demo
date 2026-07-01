import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torchvision.transforms as transforms
from PIL import Image

from cgt_cell_analysis_demo.core.workers.base_worker import BaseWorker
from cgt_cell_analysis_demo.model.cell_counting_ai_model import CellCountingRegressor
from cgt_cell_analysis_demo.util.logger import log_format

DEFAULT_BATCH_SIZE = 64  # Increased batch size for better GPU utilization
DEFAULT_IMAGE_SIZE = 224
DEFAULT_CONFIDENCE_THRESHOLD = 0.5
DEFAULT_USE_GPU = True
DEFAULT_USE_HALF_PRECISION = True  # Use half precision for faster inference
DEFAULT_NUM_WORKERS = 4  # Number of threads for image loading

# Define preprocessing pipeline for EfficientNet - optimized for speed
transform = transforms.Compose(
    [
        transforms.Resize(
            (224, 224), interpolation=transforms.InterpolationMode.BILINEAR
        ),  # Faster interpolation
        transforms.ToTensor(),  # Convert to tensor
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),  # Normalize
    ]
)

# Optimized transform for batch processing
transform_batch = transforms.Compose(
    [
        transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BILINEAR),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ]
)

# Define GPU device lazily to avoid CUDA initialization at import time
_device = None


def _get_device():
    global _device
    if _device is None:
        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _device


class CellCounting(BaseWorker):
    def __init__(
        self, sample_id: str, input_folder: str, output_folder: str, config: dict | None = None
    ):
        super().__init__()
        self.sample_id = sample_id
        self.input_folder = Path(input_folder)
        self.output_folder = Path(output_folder)
        # Persist config dict for future use
        self.config = config or {}

        # Resolve effective parameters (config takes precedence, then explicit params, then defaults)
        try:
            self.model_weights_path = Path(self.config.get("model_weights_path", ""))
            self.batch_size = int(self.config.get("batch_size", DEFAULT_BATCH_SIZE))
            self.image_size = int(self.config.get("image_size", DEFAULT_IMAGE_SIZE))
            self.confidence_threshold = float(
                self.config.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
            )
            self.use_gpu = bool(self.config.get("use_gpu", DEFAULT_USE_GPU))
            self.use_half_precision = bool(
                self.config.get("use_half_precision", DEFAULT_USE_HALF_PRECISION)
            )
            self.num_workers = int(self.config.get("num_workers", DEFAULT_NUM_WORKERS))
        except Exception:
            self.model_weights_path = None
            self.batch_size = DEFAULT_BATCH_SIZE
            self.image_size = DEFAULT_IMAGE_SIZE
            self.confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD
            self.use_gpu = DEFAULT_USE_GPU
            self.use_half_precision = DEFAULT_USE_HALF_PRECISION
            self.num_workers = DEFAULT_NUM_WORKERS

        self.model = None
        self.device = None
        self.dtype = None

    def _compute_device(self) -> torch.device:
        if self.device is None:
            # Use lazy device getter to avoid CUDA initialization at import time
            self.signals.log.emit(log_format("Initializing Device"))
            self.device = _get_device()
            self.signals.log.emit(log_format(f"Device: {self.device}"))

            # Set dtype based on device and preferences
            if self.device.type == "cuda" and self.use_half_precision:
                self.dtype = torch.float16
            else:
                self.dtype = torch.float32

            # Log device information
            self.signals.log.emit(
                log_format(
                    f"PyTorch version: {torch.__version__}, Built with CUDA: {torch.version.cuda}, CUDA available: {torch.cuda.is_available()}, CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}"
                )
            )
            self.signals.log.emit(log_format(f"CUDA is available: {torch.cuda.is_available()}"))

            if self.device.type == "cuda":
                self.signals.log.emit(
                    log_format(
                        f"Device count: {torch.cuda.device_count()}, Device 0: {torch.cuda.get_device_name(0)}"
                    )
                )
                if self.use_half_precision:
                    self.signals.log.emit(
                        log_format("Using half precision (FP16) for faster inference")
                    )
            else:
                self.signals.log.emit(log_format("Using CPU for inference"))

            # Initialize CUDA if needed
            if self.device.type == "cuda":
                try:
                    torch.cuda.init()
                except Exception as e:
                    print("Init error:", e)

        return self.device

    def _get_dtype(self) -> torch.dtype:
        if self.dtype is None:
            self._compute_device()
        return self.dtype

    def load_model(self):
        """Load the trained model for cell counting with optimizations"""
        try:
            # Validate path presence and existence
            if not self.model_weights_path:
                raise FileNotFoundError(
                    "Model weights path is empty. Please set 'ai_model_weights_path' in settings."
                )
            if not self.model_weights_path.exists():
                raise FileNotFoundError(f"Model weights not found: {self.model_weights_path}")

            self.signals.log.emit(log_format(f"Loading model from: {self.model_weights_path}"))

            self.model = CellCountingRegressor(pretrained=False)
            target_device = self._compute_device()
            target_dtype = self._get_dtype()

            # Log device information
            if target_device.type == "cuda":
                self.signals.log.emit(log_format(f"Using GPU: {torch.cuda.get_device_name(0)}"))
                self.signals.log.emit(
                    log_format(
                        f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB"
                    )
                )
                if self.use_half_precision:
                    self.signals.log.emit(
                        log_format("Using half precision (FP16) for faster inference")
                    )
            else:
                self.signals.log.emit(log_format("Using CPU for inference"))

            # Load model weights
            state_dict = torch.load(
                self.model_weights_path, weights_only=True, map_location=target_device
            )

            # Handle compiled model state dict (remove _orig_mod prefix if present)
            def clean_state_dict(state_dict):
                """Remove _orig_mod prefix from compiled model state dict keys."""
                cleaned_dict = {}
                for key, value in state_dict.items():
                    if key.startswith("_orig_mod."):
                        # Remove _orig_mod. prefix
                        clean_key = key[10:]  # Remove '_orig_mod.' (10 characters)
                        cleaned_dict[clean_key] = value
                    else:
                        cleaned_dict[key] = value
                return cleaned_dict

            # Clean the state dict before loading
            cleaned_state_dict = clean_state_dict(state_dict)

            # Log information about state dict cleaning
            original_keys = len(state_dict.keys())
            cleaned_keys = len(cleaned_state_dict.keys())
            if original_keys != cleaned_keys:
                self.signals.log.emit(
                    log_format(
                        f"Cleaned state dict: {original_keys} -> {cleaned_keys} keys (removed _orig_mod prefix)"
                    )
                )

            try:
                self.model.load_state_dict(cleaned_state_dict)
                self.signals.log.emit(log_format("Model state dict loaded successfully"))
            except Exception as load_error:
                self.signals.log.emit(
                    log_format(f"Failed to load cleaned state dict: {load_error}")
                )
                # Try loading with strict=False as fallback
                missing_keys, unexpected_keys = self.model.load_state_dict(
                    cleaned_state_dict, strict=False
                )
                if missing_keys:
                    self.signals.log.emit(
                        log_format(f"Missing keys (ignored): {len(missing_keys)}")
                    )
                if unexpected_keys:
                    self.signals.log.emit(
                        log_format(f"Unexpected keys (ignored): {len(unexpected_keys)}")
                    )
                self.signals.log.emit(
                    log_format("Model loaded with strict=False (some keys ignored)")
                )
            self.model.eval()  # Set to evaluation mode

            # Move model to device and convert to appropriate dtype
            self.model.to(target_device, dtype=target_dtype)

            # Optimize model for inference
            if target_device.type == "cuda":
                # Enable cuDNN benchmark for consistent input sizes
                torch.backends.cudnn.benchmark = True
                # Disable max_autotune_gemm to avoid SM warning on low-end GPUs
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True

                # Detect Triton availability without importing it
                try:
                    from importlib.util import find_spec

                    triton_available = find_spec("triton") is not None
                except Exception:
                    triton_available = False

                # Ensure dynamo errors don't crash runtime; fallback to eager if needed
                try:
                    import torch._dynamo as torch_dynamo  # type: ignore

                    torch_dynamo.config.suppress_errors = True
                except Exception:
                    pass

                if triton_available:
                    try:
                        self.model = torch.compile(self.model, mode="reduce-overhead")
                        self.signals.log.emit(
                            log_format("Model compiled for optimized inference (inductor)")
                        )
                    except Exception as compile_error:
                        self.signals.log.emit(
                            log_format(f"Model compilation failed, using eager: {compile_error}")
                        )
                else:
                    self.signals.log.emit(
                        log_format(
                            "Triton not available. Skipping torch.compile and using eager mode."
                        )
                    )

            self.signals.log.emit(log_format("Model loaded and optimized successfully"))

        except Exception as e:
            self.signals.error.emit(log_format(f"Failed to load model: {str(e)}", level="Error"))
            raise

    def _load_single_image(self, img_path):
        """Load and preprocess a single image - optimized for threading"""
        try:
            img = Image.open(img_path).convert("RGB")
            img = transform_batch(img)

            # Extract well and tile numbers from filename
            img_name = os.path.basename(img_path).split("Well_")[1].split(".")[0]
            well_number = int(img_name.split("_")[0])
            tile_number = int(img_name.split("_")[1])

            return img, well_number, tile_number, os.path.basename(img_path)
        except Exception as e:
            self.signals.log.emit(log_format(f"Skip unreadable image {img_path}: {e}"))
            return None, None, None, None

    def load_images_from_folder(self, dir_path):
        """Load and preprocess images from a folder - optimized with threading"""
        try:
            # Get all image files first
            image_files = [
                os.path.join(dir_path, f)
                for f in os.listdir(dir_path)
                if f.lower().endswith(("png", "jpg", "jpeg", "bmp", "tiff"))
            ]

            if len(image_files) == 0:
                raise ValueError("No valid images found in the folder!")

            # Use ThreadPoolExecutor for parallel image loading
            images = []
            well_numbers = []
            tile_numbers = []
            image_names = []

            with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                results = list(executor.map(self._load_single_image, image_files))

                for result in results:
                    img, well_num, tile_num, name = result
                    if img is not None:
                        images.append(img)
                        well_numbers.append(well_num)
                        tile_numbers.append(tile_num)
                        image_names.append(name)

            if len(images) == 0:
                raise ValueError("No valid images could be loaded!")

            # Stack images into a batch tensor
            images_tensor = torch.stack(images)
            return images_tensor, image_names, well_numbers, tile_numbers

        except Exception as e:
            self.signals.error.emit(
                log_format(f"Failed to load images from {dir_path}: {str(e)}", level="Error")
            )
            raise

    def predict_cell_count(self, dir_path: str):
        """Predict cell count for images in a directory - optimized version"""
        try:
            start_time = time.time()

            self.signals.log.emit(log_format(f"Processing directory: {dir_path}"))

            # Log current device being used
            current_device = self._compute_device()
            current_dtype = self._get_dtype()
            if current_device.type == "cuda":
                self.signals.log.emit(
                    log_format(f"Starting inference on GPU: {torch.cuda.get_device_name(0)}")
                )
                if self.use_half_precision:
                    self.signals.log.emit(
                        log_format("Using half precision (FP16) for faster inference")
                    )
            else:
                self.signals.log.emit(log_format("Starting inference on CPU"))

            # Enumerate images first
            image_files = [
                os.path.join(dir_path, f)
                for f in os.listdir(dir_path)
                if f.lower().endswith(("png", "jpg", "jpeg", "bmp", "tiff"))
            ]
            image_files.sort()
            total_images = len(image_files)
            if total_images == 0:
                raise ValueError("No valid images found in the folder!")

            self.signals.log.emit(log_format(f"Found {total_images} images"))

            all_well_numbers = []
            all_tile_numbers = []
            all_pred_values = []

            batch_size = self.batch_size
            processed_images = 0

            # Pre-allocate lists for better memory management
            all_well_numbers = []
            all_tile_numbers = []
            all_pred_values = []

            for start_idx in range(0, total_images, batch_size):
                # Check for cancellation before processing each batch
                self.check_abort()

                end_idx = min(start_idx + batch_size, total_images)
                batch_files = image_files[start_idx:end_idx]

                # Load batch with threading
                batch_imgs = []
                batch_well_numbers = []
                batch_tile_numbers = []

                with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                    results = list(executor.map(self._load_single_image, batch_files))

                    for result in results:
                        img, well_num, tile_num, name = result
                        if img is not None:
                            batch_imgs.append(img)
                            batch_well_numbers.append(well_num)
                            batch_tile_numbers.append(tile_num)

                if not batch_imgs:
                    # Update progress and continue
                    processed_images += len(batch_files)
                    self.signals.progress.emit(int(processed_images / total_images * 100))
                    continue

                # Stack and move to device
                batch_tensor = torch.stack(batch_imgs)

                # Convert to appropriate dtype and move to device
                try:
                    batch_tensor = batch_tensor.to(device=current_device, dtype=current_dtype)
                except Exception as te:
                    self.signals.log.emit(log_format(f"Falling back to CPU for this batch: {te}"))
                    batch_tensor = batch_tensor.cpu().float()
                    current_device = torch.device("cpu")
                    current_dtype = torch.float32

                # Inference with optimizations
                with torch.no_grad():
                    try:
                        # Use autocast for mixed precision if using half precision
                        if self.use_half_precision and current_device.type == "cuda":
                            with torch.amp.autocast("cuda"):
                                batch_out = self.model(batch_tensor)
                        else:
                            batch_out = self.model(batch_tensor)

                        batch_out = torch.clamp(batch_out, min=0)

                    except RuntimeError as re:
                        if "out of memory" in str(re).lower():
                            self.signals.log.emit(
                                log_format(
                                    "CUDA OOM detected. Switching to CPU for remaining batches."
                                )
                            )
                            self.model.to("cpu").float()
                            current_device = torch.device("cpu")
                            current_dtype = torch.float32
                            batch_tensor = batch_tensor.cpu().float()
                            batch_out = self.model(batch_tensor)
                            if self.use_gpu and torch.cuda.is_available():
                                self.signals.log.emit(
                                    log_format("GPU available but continuing on CPU to avoid OOM")
                                )
                        else:
                            raise

                # Convert predictions to numpy efficiently
                batch_preds = batch_out.detach().cpu().numpy().flatten().tolist()

                all_well_numbers.extend(batch_well_numbers)
                all_tile_numbers.extend(batch_tile_numbers)
                all_pred_values.extend(batch_preds)

                processed_images += len(batch_imgs)

                # Check for cancellation after processing each batch
                self.check_abort()

                # Update progress less frequently to reduce overhead
                if processed_images % (batch_size * 2) == 0 or processed_images == total_images:
                    self.signals.progress.emit(int(processed_images / total_images * 100))
                    self.signals.log.emit(
                        log_format(f"Processed {processed_images} / {total_images} images")
                    )

            # Check for cancellation before final data processing
            self.check_abort()

            # Create DataFrame with results - optimized
            self.signals.log.emit(log_format("Processing results..."))

            # Use numpy arrays for faster operations
            well_numbers = np.array(all_well_numbers, dtype=np.int32)
            tile_numbers = np.array(all_tile_numbers, dtype=np.int32)
            pred_values = np.array(all_pred_values, dtype=np.float32)

            # Create DataFrame efficiently
            result_df = pd.DataFrame(
                {
                    "Absolute Well Number": well_numbers,
                    "Tile Number": tile_numbers,
                    "Cell Count Score": pred_values,
                }
            )

            # Sort by Absolute Well Number using numpy for speed
            sort_indices = np.argsort(well_numbers)
            result_df = result_df.iloc[sort_indices].reset_index(drop=True)

            # Save Raw data CSV file
            raw_csv_output_path = self.output_folder / "Raw_Predicted_Cell_Count.csv"
            result_df.to_csv(raw_csv_output_path, index=False)
            self.signals.log.emit(log_format(f"Saved raw CSV file to {raw_csv_output_path}"))

            # Check for cancellation before computing averages
            self.check_abort()

            # Optimized groupby and aggregation
            self.signals.log.emit(log_format("Computing averages..."))

            # Use numpy for faster groupby operations
            unique_wells = np.unique(well_numbers)
            avg_scores = np.zeros(len(unique_wells), dtype=np.float32)

            for i, well in enumerate(unique_wells):
                mask = well_numbers == well
                avg_scores[i] = np.mean(pred_values[mask])

            # Create average DataFrame
            avg_df = pd.DataFrame(
                {"Absolute Well Number": unique_wells, "Average Cell Count Score": avg_scores}
            )

            # Round to 2 decimal places
            avg_df["Average Cell Count Score"] = np.round(avg_df["Average Cell Count Score"], 2)

            # Handle non-finite values efficiently
            finite_mask = np.isfinite(avg_df["Average Cell Count Score"])
            if not finite_mask.all():
                non_finite_count = np.sum(~finite_mask)
                self.signals.log.emit(
                    log_format(
                        f"Warning: Found {non_finite_count} non-finite values, replacing with 0"
                    )
                )
                avg_df.loc[~finite_mask, "Average Cell Count Score"] = 0.0

            # Calculate Cell Count using vectorized operations
            scores = avg_df["Average Cell Count Score"].values
            cell_counts = np.floor(scores).astype(np.int32) + (
                scores % 1 >= self.confidence_threshold
            ).astype(np.int32)
            avg_df["Cell Count"] = cell_counts

            # Save final CSV file
            csv_output_path = self.output_folder / "Predicted_Cell_Count.csv"
            avg_df.to_csv(csv_output_path, index=False)
            self.signals.log.emit(log_format(f"Saved final CSV file to {csv_output_path}"))

            end_time = time.time()
            elapsed_time = end_time - start_time

            self.signals.log.emit(
                log_format(
                    f"Cell count prediction completed for {dir_path}. Elapsed time: {elapsed_time:.2f} sec"
                )
            )

            return {
                "output_folder": self.output_folder,
                "image_count": len(all_well_numbers),
                "csv_path": str(csv_output_path),
                "elapsed_time": elapsed_time,
            }

        except Exception as e:
            self.signals.error.emit(
                log_format(f"Failed to predict cell count for {dir_path}: {str(e)}", level="Error")
            )
            raise

    def run(self):
        """Main execution method for the worker"""
        try:
            self.signals.log.emit(
                log_format(f"Starting cell counting for sample: {self.sample_id}")
            )

            # Check if input folder exists
            if not self.input_folder.exists():
                self.signals.error.emit(
                    log_format(f"Input folder does not exist: {self.input_folder}", level="Error")
                )
                return

            # Create output folder
            self.output_folder.mkdir(parents=True, exist_ok=True)

            # Load model
            self.load_model()

            self.check_abort()  # Check for cancellation

            dir_path = self.input_folder
            result = self.predict_cell_count(dir_path)

            # Create summary results
            summary_result = {
                "sample_id": self.sample_id,
                "result": result,
                "output_folder": str(self.output_folder),
            }

            self.signals.done.emit(summary_result)

        except Exception as e:
            self.signals.error.emit(log_format(f"Cell counting failed: {str(e)}", level="Error"))
