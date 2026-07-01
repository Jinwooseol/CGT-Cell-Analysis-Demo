"""
Model Training Module for CGT Cell Analysis Demo

This module provides functionality for training regression models on image data,
including data loading, model definitions, and Qt-integrated training workers.
"""

import json
import os
import time
from pathlib import Path

import albumentations as A
import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from albumentations.pytorch import ToTensorV2
from torch.utils.data import DataLoader, Dataset

from cgt_cell_analysis_demo.core.workers.base_worker import BaseWorker
from cgt_cell_analysis_demo.model.cell_counting_ai_model import CellCountingRegressor
from cgt_cell_analysis_demo.util.logger import log_format


def GPU_device_check():
    print("=" * 60)
    print("CUDA/GPU CHECK")
    print("=" * 60)

    # PyTorch version
    print(f"PyTorch Version: {torch.__version__}")

    # CUDA availability
    cuda_available = torch.cuda.is_available()
    print(f"CUDA Available: {cuda_available}")

    if cuda_available:
        print(f"CUDA Version (compiled): {torch.version.cuda}")
        print(f"Number of GPUs: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
        try:
            print(f"cuDNN Version: {torch.backends.cudnn.version()}")
            print(f"cuDNN Enabled: {torch.backends.cudnn.enabled}")
        except Exception:
            print("cuDNN: Not available")
    else:
        print(
            f"CUDA Version (compiled): {torch.version.cuda if hasattr(torch.version, 'cuda') and torch.version.cuda else 'None (CPU-only build)'}"
        )

    print("=" * 60)
    print("GPU Device Check Complete")


# ==================== Data Loading Functions ====================
def read_merged_training_report(file_path: str) -> tuple[dict, pd.DataFrame]:
    """
    Read a merged training report file and extract model info and training history.

    Args:
        file_path: Path to the merged CSV file

    Returns:
        tuple: (model_info_dict, training_history_dataframe)
    """
    model_info = {}
    training_data_lines = []

    with open(file_path) as f:
        lines = f.readlines()

    # Parse header comments for model info
    for line in lines:
        line = line.strip()
        if line.startswith("#") and ":" in line:
            # Extract key-value pairs from comment lines
            if line.startswith("# Generated:"):
                model_info["timestamp"] = line.split(":", 1)[1].strip()
            elif line.startswith("# Model Type:"):
                model_info["model_type"] = line.split(":", 1)[1].strip()
            elif line.startswith("# Base Model:"):
                model_info["base_model"] = line.split(":", 1)[1].strip()
            elif line.startswith("# Input Size:"):
                model_info["input_size"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("# Number of Classes:"):
                model_info["num_classes"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("# Training Epochs:"):
                model_info["training_epochs"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("# Final Train Loss:"):
                model_info["final_train_loss"] = float(line.split(":", 1)[1].strip())
            elif line.startswith("# Final Val Loss:"):
                model_info["final_val_loss"] = float(line.split(":", 1)[1].strip())
            elif line.startswith("# Best Epoch:"):
                model_info["best_epoch"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("# Best Val Loss:"):
                model_info["best_val_loss"] = float(line.split(":", 1)[1].strip())
            elif line.startswith("# Total Training Time:"):
                model_info["total_training_time"] = float(line.split(":", 1)[1].strip().split()[0])
            elif line.startswith("# Advanced Loss:"):
                model_info["use_advanced_loss"] = line.split(":", 1)[1].strip().lower() == "true"
            elif line.startswith("# LR Scheduler:"):
                model_info["use_lr_scheduler"] = line.split(":", 1)[1].strip().lower() == "true"
            elif line.startswith("# Early Stopping:"):
                model_info["use_early_stopping"] = line.split(":", 1)[1].strip().lower() == "true"
            elif line.startswith("# Patience:"):
                model_info["patience"] = int(line.split(":", 1)[1].strip())
        elif not line.startswith("#") and line.strip():
            # This is training data
            training_data_lines.append(line)

    # Create DataFrame from training data
    if training_data_lines:
        from io import StringIO

        training_csv = "\n".join(training_data_lines)
        training_df = pd.read_csv(StringIO(training_csv))
    else:
        training_df = pd.DataFrame()

    return model_info, training_df


def load_data(image_dir: str, label_csv: str) -> tuple[list[str], list[float]]:
    """Load well images and labels for model training."""
    image_names = []
    for fname in os.listdir(image_dir):
        if fname.lower().endswith((".png", ".jpg", ".jpeg")):
            # Extract image name without extension
            image_name = fname.replace(".png", "").replace(".jpg", "").replace(".jpeg", "")
            image_names.append([image_name, str(Path(image_dir) / fname)])

    # Load CSV with proper column handling
    df = pd.read_csv(label_csv)

    # Handle different CSV formats
    image_df = pd.DataFrame(image_names, columns=["Image Name", "Image Path"])
    df["Image Name"] = df["Image Name"].astype(str)
    df = df.merge(image_df, on="Image Name", how="left")

    # Validate data before returning
    labels = df["Label"].tolist()
    image_paths = df["Image Path"].tolist()

    # Check for missing or invalid data
    valid_indices = []
    for i, (path, label) in enumerate(zip(image_paths, labels)):
        if pd.isna(path) or pd.isna(label):
            print(f"WARNING: Missing data at index {i}: path={path}, label={label}")
            continue
        if np.isnan(label) or np.isinf(label):
            print(f"WARNING: Invalid label at index {i}: {label}")
            continue
        if not Path(path).exists():
            print(f"WARNING: Image file does not exist: {path}")
            continue
        valid_indices.append(i)

    # Filter out invalid data
    if len(valid_indices) == 0:
        raise ValueError("No valid data found after validation")

    image_paths = [image_paths[i] for i in valid_indices]
    labels = [labels[i] for i in valid_indices]

    print(f"Loaded {len(image_paths)} valid well images out of {len(df)} total")
    print(f"Label range: {min(labels):.4f} to {max(labels):.4f}")
    print(f"Label mean: {np.mean(labels):.4f}, std: {np.std(labels):.4f}")

    return image_paths, labels


# ==================== Dataset Classes ====================


class ImageNumberDataset(Dataset):
    def __init__(self, image_paths, labels, transform=None):
        self.image_paths = image_paths
        self.labels = labels
        self.transform = transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        # Load image with error checking
        image = cv2.imread(self.image_paths[idx])
        if image is None:
            raise ValueError(f"Failed to load image: {self.image_paths[idx]}")

        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if self.transform:
            image = self.transform(image=image)["image"]

        # Check label for NaN/Inf values
        label_value = self.labels[idx]
        if pd.isna(label_value) or np.isnan(label_value) or np.isinf(label_value):
            raise ValueError(
                f"Invalid label value: {label_value} for image: {self.image_paths[idx]}"
            )

        label = torch.tensor(label_value, dtype=torch.float32)
        return image, label


# ==================== Model Definitions ====================


class UNetCNNHybrid(nn.Module):
    def __init__(self):
        super().__init__()
        self.unet = torch.hub.load("pytorch/vision:v0.10.0", "fcn_resnet50", pretrained=True)
        self.unet.classifier[4] = nn.Conv2d(21, 3, kernel_size=1)
        self.cnn = torch.hub.load("pytorch/vision:v0.10.0", "resnet18", pretrained=True)
        self.cnn.fc = nn.Linear(self.cnn.fc.in_features, 1)

    def forward(self, x):
        x = self.unet(x)["out"]
        x = torch.sigmoid(x)
        x = self.unet.classifier[4](x)
        x = self.cnn(x)
        return x


# ==================== Qt Worker for Model Training ====================


class ModelTrainingWorker(BaseWorker):
    """Train a regression model from an image folder and label CSV.

    Exposes progress/log/done via BaseWorker signals to integrate with the app pipeline.
    """

    def __init__(
        self,
        sample_id: str,
        image_dir: str,
        label_csv: str,
        output_dir: str,
        config: dict | None = None,
    ):
        super().__init__()
        self.sample_id = sample_id
        self.image_dir = Path(image_dir)
        self.label_csv = Path(label_csv)
        self.output_dir = Path(output_dir)
        self.config = config or {}

        # Training hyperparameters with sensible defaults
        self.epochs = int(self.config.get("epochs", 50))  # Increased default epochs
        self.learning_rate = float(
            self.config.get("lr", 5e-4)
        )  # Lower learning rate for better convergence
        self.batch_size = int(self.config.get("batch_size", 16))  # Increased batch size
        self.image_size = int(
            self.config.get("image_size", 256)
        )  # Larger image size for better features
        self.model_name = str(self.config.get("model_name", "efficientnet_b4"))
        self.use_gpu = bool(self.config.get("use_gpu", torch.cuda.is_available()))

        # Advanced training options
        self.use_early_stopping = bool(self.config.get("use_early_stopping", True))
        self.patience = int(self.config.get("patience", 10))
        self.use_advanced_loss = bool(self.config.get("use_advanced_loss", True))
        self.use_lr_scheduler = bool(self.config.get("use_lr_scheduler", True))

        # Performance optimization settings
        self.num_workers = int(self.config.get("num_workers", 4))  # Number of data loading workers
        self.pin_memory = bool(
            self.config.get("pin_memory", True)
        )  # Pin memory for faster GPU transfer
        self.persistent_workers = bool(
            self.config.get("persistent_workers", True)
        )  # Keep workers alive
        # Disable AMP by default for stability - can be enabled via config
        self.use_amp = False  # Always disable AMP for maximum stability
        # Check if torch.compile is available and working
        compile_available = hasattr(torch, "compile")
        if compile_available:
            try:
                # Test if compilation works with a simple model using eager backend
                test_model = nn.Linear(1, 1)
                torch.compile(test_model, backend="eager")
                # Only enable compilation if explicitly requested and working
                self.compile_model = bool(self.config.get("compile_model", False))
                if self.compile_model:
                    self.signals.log.emit(log_format("Model compilation enabled"))
                else:
                    self.signals.log.emit(
                        log_format(
                            "Model compilation disabled by default (use compile_model=True to enable)"
                        )
                    )
            except Exception as e:
                self.compile_model = False
                self.signals.log.emit(
                    log_format(f"torch.compile not available, disabling model compilation: {e}")
                )
        else:
            self.compile_model = False
            self.signals.log.emit(
                log_format("torch.compile not available, disabling model compilation")
            )

    def _build_transforms(self, is_training=True):
        """Build transforms optimized for well images with enhanced augmentation."""
        if is_training:
            return A.Compose(
                [
                    A.Resize(self.image_size, self.image_size),
                    # Enhanced augmentation for better generalization
                    A.HorizontalFlip(p=0.5),
                    A.VerticalFlip(p=0.5),
                    A.RandomRotate90(p=0.5),
                    A.Rotate(limit=15, p=0.3),  # Small rotations for well images
                    A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.4),
                    A.HueSaturationValue(
                        hue_shift_limit=20, sat_shift_limit=30, val_shift_limit=20, p=0.3
                    ),
                    A.GaussNoise(var_limit=(10.0, 50.0), p=0.2),
                    A.GaussianBlur(blur_limit=(3, 7), p=0.2),
                    A.ElasticTransform(alpha=1, sigma=50, alpha_affine=50, p=0.2),
                    A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.2),
                    A.OpticalDistortion(distort_limit=0.3, shift_limit=0.1, p=0.2),
                    A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
                    ToTensorV2(),
                ]
            )
        else:
            # Validation transforms - no augmentation
            return A.Compose(
                [
                    A.Resize(self.image_size, self.image_size),
                    A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
                    ToTensorV2(),
                ]
            )

    def _create_model(self) -> nn.Module:
        """Create model optimized for well image analysis."""
        # Default to specialized cell counting model
        if self.model_name.lower().startswith("cell_counting"):
            return CellCountingRegressor(
                model_name="efficientnet_b4", pretrained=True, num_classes=1
            )
        # Default fallback: always return a model
        return CellCountingRegressor(model_name="efficientnet_b4", pretrained=True, num_classes=1)

    def run(self):
        try:
            # Validate paths
            if not self.image_dir.exists() or not self.image_dir.is_dir():
                self.signals.error.emit(
                    log_format(f"Image folder does not exist: {self.image_dir}", level="Error")
                )
                return
            if not self.label_csv.exists():
                self.signals.error.emit(
                    log_format(f"Label CSV does not exist: {self.label_csv}", level="Error")
                )
                return

            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Load data
            self.signals.log.emit(log_format(f"Loading dataset from folder: {self.image_dir}"))
            image_paths, labels = load_data(str(self.image_dir), str(self.label_csv))
            if len(image_paths) == 0:
                self.signals.error.emit(
                    log_format("No images after loading. Check folder and CSV.", level="Error")
                )
                return

            self.signals.log.emit(
                log_format(f"Loaded {len(image_paths)} images and {len(labels)} labels")
            )

            # Build dataset & loaders with performance optimizations
            # Use training transforms for the main dataset
            transform = self._build_transforms(is_training=True)

            # Create dataset and data loaders (following main() pattern)
            dataset = ImageNumberDataset(image_paths, labels, transform=transform)
            # Simple split: 90% train, 10% val
            val_len = max(1, int(0.1 * len(dataset)))
            train_len = len(dataset) - val_len
            train_ds, val_ds = torch.utils.data.random_split(dataset, [train_len, val_len])

            # Optimized data loaders
            train_loader = DataLoader(
                train_ds,
                batch_size=self.batch_size,
                shuffle=True,
                num_workers=self.num_workers,
                pin_memory=self.pin_memory and self.use_gpu,
                persistent_workers=self.persistent_workers and self.num_workers > 0,
                prefetch_factor=2 if self.num_workers > 0 else None,
            )
            val_loader = DataLoader(
                val_ds,
                batch_size=self.batch_size,
                shuffle=False,
                num_workers=self.num_workers,
                pin_memory=self.pin_memory and self.use_gpu,
                persistent_workers=self.persistent_workers and self.num_workers > 0,
                prefetch_factor=2 if self.num_workers > 0 else None,
            )

            # Build model
            model = self._create_model()
            device = "cuda" if (self.use_gpu and torch.cuda.is_available()) else "cpu"

            GPU_device_check()

            # Log training setup
            self.signals.log.emit(
                log_format(f"Starting training for {self.epochs} epochs on {device}")
            )
            self.signals.log.emit(
                log_format(
                    f"Performance optimizations: num_workers={self.num_workers}, pin_memory={self.pin_memory}, persistent_workers={self.persistent_workers}"
                )
            )
            self.signals.log.emit(
                log_format(
                    f"Batch size: {self.batch_size}, Image size: {self.image_size}x{self.image_size}"
                )
            )
            self.signals.progress.emit(0)  # Initial progress

            # Use the standalone train_model function with Qt integration
            self._train_model(model, train_loader, val_loader, device)

        except RuntimeError as e:
            if "canceled" in str(e).lower():
                self.signals.log.emit(log_format("Training canceled by user"))
            else:
                self.signals.error.emit(log_format(f"Training failed: {str(e)}", level="Error"))
        except Exception as e:
            self.signals.error.emit(log_format(f"Training failed: {str(e)}", level="Error"))

    def _train_model(self, model, train_loader, val_loader, device):
        """Qt-integrated version of the train_model function."""
        start_ts = time.time()
        model.to(device)

        # Check model initialization for NaN/Inf weights
        self.signals.log.emit(log_format("Checking model initialization..."))
        for name, param in model.named_parameters():
            if torch.isnan(param).any() or torch.isinf(param).any():
                self.signals.log.emit(
                    log_format(f"WARNING: NaN/Inf detected in {name} - reinitializing")
                )
                nn.init.xavier_uniform_(param)

        # Advanced loss function combining MSE and Huber loss for better regression
        if self.use_advanced_loss:

            class CombinedLoss(nn.Module):
                def __init__(self, mse_weight=0.7, huber_weight=0.3):
                    super().__init__()
                    self.mse_loss = nn.MSELoss()
                    self.huber_loss = nn.SmoothL1Loss()
                    self.mse_weight = mse_weight
                    self.huber_weight = huber_weight

                def forward(self, pred, target):
                    mse = self.mse_loss(pred, target)
                    huber = self.huber_loss(pred, target)
                    return self.mse_weight * mse + self.huber_weight * huber

            criterion = CombinedLoss()
            self.signals.log.emit(log_format("Using advanced combined loss function (MSE + Huber)"))
        else:
            criterion = nn.MSELoss()
            self.signals.log.emit(log_format("Using standard MSE loss function"))

        # Advanced optimizer with weight decay
        optimizer = optim.AdamW(
            model.parameters(),
            lr=self.learning_rate,
            weight_decay=0.01,
            betas=(0.9, 0.999),
            eps=1e-8,
        )

        # Learning rate scheduler for better convergence
        if self.use_lr_scheduler:
            scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
                optimizer,
                T_0=5,  # Restart every 5 epochs
                T_mult=2,  # Double the restart period
                eta_min=1e-6,  # Minimum learning rate
            )
            self.signals.log.emit(
                log_format("Using CosineAnnealingWarmRestarts learning rate scheduler")
            )
        else:
            scheduler = None
            self.signals.log.emit(log_format("Learning rate scheduler disabled"))

        # Test model with a small batch first
        self.signals.log.emit(log_format("Testing model with sample batch..."))
        model.eval()
        with torch.no_grad():
            try:
                sample_batch = next(iter(train_loader))
                sample_images, sample_labels = sample_batch
                sample_images = sample_images.to(device)
                sample_labels = sample_labels.to(device)

                test_outputs = model(sample_images).squeeze()
                test_loss = criterion(test_outputs, sample_labels)

                if torch.isnan(test_loss) or torch.isinf(test_loss):
                    self.signals.log.emit(
                        log_format(
                            "WARNING: Model produces NaN/Inf outputs - reducing learning rate"
                        )
                    )
                    for param_group in optimizer.param_groups:
                        param_group["lr"] *= 0.1
                    self.signals.log.emit(
                        log_format(
                            f"Reduced learning rate to: {optimizer.param_groups[0]['lr']:.6f}"
                        )
                    )

                self.signals.log.emit(
                    log_format(f"Model test successful - Loss: {test_loss.item():.4f}")
                )
            except Exception as e:
                self.signals.log.emit(log_format(f"Model test failed: {e}"))
                raise

        # Add gradient clipping to prevent exploding gradients
        max_grad_norm = 1.0
        self.signals.log.emit(log_format(f"Using gradient clipping with max_norm={max_grad_norm}"))

        # Mixed precision training setup with stability checks
        scaler = None
        if self.use_amp and device == "cuda":
            # Test AMP stability first
            self.signals.log.emit(log_format("Testing AMP stability..."))
            test_scaler = torch.amp.GradScaler("cuda")
            model.train()
            try:
                # Test AMP with a small batch
                sample_batch = next(iter(train_loader))
                sample_images, sample_labels = sample_batch
                sample_images = sample_images.to(device)
                sample_labels = sample_labels.to(device)

                with torch.amp.autocast("cuda"):
                    test_outputs = model(sample_images).squeeze()
                    test_loss = criterion(test_outputs, sample_labels)

                if (
                    torch.isnan(test_loss)
                    or torch.isinf(test_loss)
                    or torch.isnan(test_outputs).any()
                ):
                    self.signals.log.emit(
                        log_format("WARNING: AMP causes NaN/Inf - disabling AMP for stability")
                    )
                    self.use_amp = False
                    scaler = None
                else:
                    scaler = test_scaler
                    self.signals.log.emit(
                        log_format("AMP test successful - using AMP for training")
                    )
            except Exception as e:
                self.signals.log.emit(log_format(f"AMP test failed: {e} - disabling AMP"))
                self.use_amp = False
                scaler = None
        else:
            self.signals.log.emit(log_format("Using full precision training"))

        # Model compilation for PyTorch 2.0+ (significant speedup)
        if self.compile_model and hasattr(torch, "compile"):
            try:
                # Use only the eager backend which is most reliable
                model = torch.compile(model, backend="eager")
                self.signals.log.emit(
                    log_format("Model compiled with torch.compile using eager backend")
                )
            except Exception as e:
                self.signals.log.emit(
                    log_format(f"Model compilation failed, continuing without: {e}")
                )
                self.compile_model = False

        # Training history tracking
        training_history = {
            "epochs": [],
            "train_losses": [],
            "val_losses": [],
            "batch_losses": [],
            "learning_rates": [],
            "epoch_times": [],
        }

        # Early stopping configuration
        best_val_loss = float("inf")
        patience = self.patience if self.use_early_stopping else float("inf")
        patience_counter = 0
        best_epoch = 0

        for epoch in range(self.epochs):
            epoch_start_time = time.time()
            self.check_abort()
            model.train()
            train_loss = 0.0
            batch_count = 0

            for images, labels in train_loader:
                self.check_abort()
                images, labels = images.to(device), labels.to(device)
                optimizer.zero_grad()

                # Forward pass (always use full precision for stability)
                outputs = model(images).squeeze()
                loss = criterion(outputs, labels)

                # Check for NaN before backward pass
                if torch.isnan(outputs).any() or torch.isinf(outputs).any():
                    self.signals.log.emit(
                        log_format(
                            f"WARNING: NaN/Inf in model outputs at Epoch {epoch + 1}, Batch {batch_count + 1} - skipping"
                        )
                    )
                    continue

                # Backward pass
                loss.backward()
                # Apply gradient clipping
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
                optimizer.step()

                # Check for NaN values and handle them
                if torch.isnan(loss) or torch.isinf(loss) or not torch.isfinite(loss):
                    self.signals.log.emit(
                        log_format(
                            f"WARNING: NaN/Inf detected in loss at Epoch {epoch + 1}, Batch {batch_count + 1}"
                        )
                    )
                    self.signals.log.emit(
                        log_format(
                            f"Loss value: {loss.item()}, Outputs range: [{outputs.min().item():.4f}, {outputs.max().item():.4f}]"
                        )
                    )
                    self.signals.log.emit(
                        log_format(
                            f"Labels range: [{labels.min().item():.4f}, {labels.max().item():.4f}]"
                        )
                    )
                    self.signals.log.emit(
                        log_format(f"Learning rate: {optimizer.param_groups[0]['lr']:.6f}")
                    )

                    # Check for NaN in model outputs
                    if torch.isnan(outputs).any() or torch.isinf(outputs).any():
                        self.signals.log.emit(
                            log_format("NaN/Inf detected in model outputs - model may be unstable")
                        )

                        # If using AMP and getting NaN, disable AMP
                        if scaler is not None:
                            self.signals.log.emit(
                                log_format(
                                    "Disabling AMP due to NaN outputs - switching to full precision"
                                )
                            )
                            scaler = None
                            self.use_amp = False

                        # Try to reinitialize the model
                        for name, param in model.named_parameters():
                            if torch.isnan(param).any() or torch.isinf(param).any():
                                self.signals.log.emit(
                                    log_format(f"Reinitializing {name} due to NaN/Inf")
                                )
                                nn.init.xavier_uniform_(param)

                    self.signals.log.emit(
                        log_format("Skipping this batch to prevent training instability")
                    )
                    continue

                train_loss += loss.item()
                batch_count += 1

                # Log batch results every 10 batches
                if batch_count % 10 == 0:
                    avg_batch_loss = train_loss / batch_count
                    self.signals.log.emit(
                        log_format(
                            f"Epoch {epoch + 1}/{self.epochs}, Batch {batch_count} - Loss: {loss.item():.4f}, Avg: {avg_batch_loss:.4f}"
                        )
                    )

                # Update progress within epoch
                epoch_progress = int(batch_count / len(train_loader) * 100)
                overall_progress = int((epoch + epoch_progress / 100) / self.epochs * 100)
                self.signals.progress.emit(overall_progress)

            model.eval()
            val_loss = 0.0
            correct = 0
            total = 0
            val_predictions = []
            val_targets = []

            with torch.no_grad():
                for images, labels in val_loader:
                    self.check_abort()
                    images, labels = images.to(device), labels.to(device)

                    # Validation (always use full precision for stability)
                    outputs = model(images).squeeze()
                    loss = criterion(outputs, labels)

                    # Check for NaN values in validation
                    if torch.isnan(loss) or torch.isinf(loss) or not torch.isfinite(loss):
                        self.signals.log.emit(
                            log_format(
                                f"WARNING: NaN/Inf detected in validation loss at Epoch {epoch + 1}"
                            )
                        )
                        continue

                    # Check for NaN in predictions and targets
                    if torch.isnan(outputs).any() or torch.isinf(outputs).any():
                        self.signals.log.emit(
                            log_format(
                                f"WARNING: NaN/Inf detected in model outputs at Epoch {epoch + 1}"
                            )
                        )
                        continue

                    val_loss += loss.item()
                    predicted = outputs.round()
                    correct += (predicted == labels).sum().item()
                    total += labels.size(0)

                    # Store predictions and targets for metrics
                    val_predictions.extend(outputs.cpu().numpy())
                    val_targets.extend(labels.cpu().numpy())

            # Calculate additional metrics
            if len(val_predictions) > 0 and len(val_targets) > 0:
                val_predictions = np.array(val_predictions)
                val_targets = np.array(val_targets)

                # Check for NaN in the arrays
                if np.isnan(val_predictions).any() or np.isnan(val_targets).any():
                    self.signals.log.emit(
                        log_format(
                            "WARNING: NaN values detected in validation predictions or targets"
                        )
                    )
                    mae, mse, rmse = float("nan"), float("nan"), float("nan")
                else:
                    mae = np.mean(np.abs(val_predictions - val_targets))
                    mse = np.mean((val_predictions - val_targets) ** 2)
                    rmse = np.sqrt(mse)
            else:
                mae, mse, rmse = float("nan"), float("nan"), float("nan")

            accuracy = 100 * correct / total if total > 0 else 0

            end_time = time.time()
            elapsed_time = end_time - epoch_start_time

            # Store training history
            current_train_loss = train_loss / len(train_loader)
            current_val_loss = val_loss / len(val_loader)

            training_history["epochs"].append(epoch + 1)
            training_history["train_losses"].append(current_train_loss)
            training_history["val_losses"].append(current_val_loss)
            training_history["learning_rates"].append(optimizer.param_groups[0]["lr"])
            training_history["epoch_times"].append(elapsed_time)

            # Step the learning rate scheduler
            if scheduler is not None:
                scheduler.step()

            # Early stopping logic
            if current_val_loss < best_val_loss:
                best_val_loss = current_val_loss
                best_epoch = epoch + 1
                patience_counter = 0
                # Save best model
                best_model_state = model.state_dict().copy()
            else:
                patience_counter += 1

            # Detailed epoch logging
            self.signals.log.emit(
                log_format(
                    f"Epoch {epoch + 1}/{self.epochs} - Train Loss: {current_train_loss:.4f}, Val Loss: {current_val_loss:.4f}"
                )
            )
            self.signals.log.emit(
                log_format(
                    f"  Val Accuracy: {accuracy:.2f}%, MAE: {mae:.4f}, MSE: {mse:.4f}, RMSE: {rmse:.4f}"
                )
            )
            self.signals.log.emit(
                log_format(
                    f"  Time: {elapsed_time:.2f}s, LR: {optimizer.param_groups[0]['lr']:.6f}"
                )
            )
            self.signals.log.emit(
                log_format(
                    f"  Best Val Loss: {best_val_loss:.4f} (Epoch {best_epoch}), Patience: {patience_counter}/{patience}"
                )
            )

            # Early stopping check
            if patience_counter >= patience:
                self.signals.log.emit(
                    log_format(
                        f"Early stopping triggered after {epoch + 1} epochs (no improvement for {patience} epochs)"
                    )
                )
                break

            # Check for NaN in epoch metrics and reduce learning rate if needed
            if not torch.isfinite(
                torch.tensor(train_loss / len(train_loader))
            ) or not torch.isfinite(torch.tensor(val_loss / len(val_loader))):
                self.signals.log.emit(
                    log_format(
                        "WARNING: NaN/Inf detected in epoch metrics - reducing learning rate by 50%"
                    )
                )
                for param_group in optimizer.param_groups:
                    param_group["lr"] *= 0.5
                self.signals.log.emit(
                    log_format(f"New learning rate: {optimizer.param_groups[0]['lr']:.6f}")
                )

            # Final progress update for this epoch
            epoch_progress = int((epoch + 1) / self.epochs * 100)
            self.signals.progress.emit(epoch_progress)

        # Calculate final training statistics
        total_training_time = time.time() - start_ts
        best_epoch = np.argmin(training_history["val_losses"]) + 1
        best_val_loss = min(training_history["val_losses"])
        final_train_loss = training_history["train_losses"][-1]
        final_val_loss = training_history["val_losses"][-1]

        # Log comprehensive training results
        self.signals.log.emit(log_format("=" * 60))
        self.signals.log.emit(log_format("TRAINING COMPLETED - FINAL RESULTS"))
        self.signals.log.emit(log_format("=" * 60))
        self.signals.log.emit(log_format(f"Total Training Time: {total_training_time:.2f} seconds"))
        self.signals.log.emit(
            log_format(f"Best Epoch: {best_epoch} (Val Loss: {best_val_loss:.4f})")
        )
        self.signals.log.emit(log_format(f"Final Train Loss: {final_train_loss:.4f}"))
        self.signals.log.emit(log_format(f"Final Val Loss: {final_val_loss:.4f}"))
        self.signals.log.emit(
            log_format(f"Average Epoch Time: {np.mean(training_history['epoch_times']):.2f}s")
        )

        # Save weights to models directory in project
        timestamp = time.strftime("%y%m%d_%H%M%S")

        # Create descriptive filename for well image model
        weight_name = f"cell_counting_model_{timestamp}.pth"
        save_path = self.output_dir / weight_name

        # Load best model state if early stopping was used
        if "best_model_state" in locals():
            model.load_state_dict(best_model_state)
            self.signals.log.emit(log_format(f"Loaded best model from epoch {best_epoch}"))

        # Save model state dict
        torch.save(model.state_dict(), save_path)
        self.signals.log.emit(log_format(f"Saved well image model weights to: {save_path}"))

        # Create merged file with model info as header and training history as body
        training_report_path = self.output_dir / f"model_training_report_{timestamp}.csv"

        # Prepare model information for header
        model_info = {
            "model_type": "CellCountingRegressor",
            "base_model": self.model_name,
            "input_size": int(self.image_size),
            "num_classes": 1,
            "timestamp": timestamp,
            "training_epochs": int(self.epochs),
            "final_train_loss": float(final_train_loss),
            "final_val_loss": float(final_val_loss),
            "best_epoch": int(best_epoch),
            "best_val_loss": float(best_val_loss),
            "total_training_time": float(total_training_time),
            "use_advanced_loss": self.use_advanced_loss,
            "use_lr_scheduler": self.use_lr_scheduler,
            "use_early_stopping": self.use_early_stopping,
            "patience": int(self.patience) if self.use_early_stopping else None,
        }

        # Create training history DataFrame
        history_df = pd.DataFrame(
            {
                "epoch": training_history["epochs"],
                "train_loss": training_history["train_losses"],
                "val_loss": training_history["val_losses"],
                "learning_rate": training_history["learning_rates"],
                "epoch_time": training_history["epoch_times"],
            }
        )

        # Write merged file with model info as header comments
        with open(training_report_path, "w", newline="") as f:
            # Write model information as header comments
            f.write("# Model Training Report\n")
            f.write("# ====================\n")
            f.write(f"# Generated: {timestamp}\n")
            f.write(f"# Model Type: {model_info['model_type']}\n")
            f.write(f"# Base Model: {model_info['base_model']}\n")
            f.write(f"# Input Size: {model_info['input_size']}\n")
            f.write(f"# Number of Classes: {model_info['num_classes']}\n")
            f.write(f"# Training Epochs: {model_info['training_epochs']}\n")
            f.write(f"# Final Train Loss: {model_info['final_train_loss']:.6f}\n")
            f.write(f"# Final Val Loss: {model_info['final_val_loss']:.6f}\n")
            f.write(f"# Best Epoch: {model_info['best_epoch']}\n")
            f.write(f"# Best Val Loss: {model_info['best_val_loss']:.6f}\n")
            f.write(f"# Total Training Time: {model_info['total_training_time']:.2f} seconds\n")
            f.write(f"# Advanced Loss: {model_info['use_advanced_loss']}\n")
            f.write(f"# LR Scheduler: {model_info['use_lr_scheduler']}\n")
            f.write(f"# Early Stopping: {model_info['use_early_stopping']}\n")
            if model_info["patience"] is not None:
                f.write(f"# Patience: {model_info['patience']}\n")
            f.write("#\n")
            f.write("# Training History Data:\n")
            f.write("# =====================\n")

            # Write CSV data
            history_df.to_csv(f, index=False)

        self.signals.log.emit(log_format(f"Saved merged model report to: {training_report_path}"))

        # Also save individual files for backward compatibility
        info_path = self.output_dir / f"cell_counting_model_{timestamp}_info.json"
        with open(info_path, "w") as f:
            json.dump(model_info, f, indent=2)
        self.signals.log.emit(log_format(f"Saved model info to: {info_path}"))

        history_csv_path = self.output_dir / f"training_history_{timestamp}.csv"
        history_df.to_csv(history_csv_path, index=False)
        self.signals.log.emit(log_format(f"Saved training history to: {history_csv_path}"))

        # Convert numpy types to native Python types for JSON serialization
        def convert_numpy_types(obj):
            """Recursively convert numpy types to native Python types."""
            if isinstance(obj, dict):
                return {key: convert_numpy_types(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            else:
                return obj

        # Convert training_history to JSON-serializable format
        serializable_training_history = convert_numpy_types(training_history)

        self.signals.done.emit(
            {
                "output_folder": str(self.output_dir),
                "weights_path": str(save_path),
                "history_path": str(history_csv_path),
                "training_report_path": str(training_report_path),
                "elapsed_time": float(total_training_time),
                "best_epoch": int(best_epoch),
                "best_val_loss": float(best_val_loss),
                "final_train_loss": float(final_train_loss),
                "final_val_loss": float(final_val_loss),
                "training_history": serializable_training_history,
            }
        )
