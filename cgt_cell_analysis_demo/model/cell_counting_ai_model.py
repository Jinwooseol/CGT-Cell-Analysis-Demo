import logging

logger = logging.getLogger(__name__)

# Import required packages with error handling
try:
    import torch
    import torch.nn as nn
except ImportError as e:
    logger.error(f"Failed to import PyTorch: {e}")
    logger.error("Please install PyTorch: pip install torch")
    raise

try:
    from timm import create_model
except ImportError as e:
    logger.error(f"Failed to import timm: {e}")
    logger.error("Please install timm: pip install timm")
    raise


class CellCountingRegressor(nn.Module):
    """Enhanced model for well image analysis with improved architecture.

    Mirrors the training-time classifier head to ensure weights are compatible
    across training and inference.
    """

    def __init__(
        self, model_name: str = "efficientnet_b4", pretrained: bool = False, num_classes: int = 1
    ):
        super().__init__()
        self.model = create_model(model_name, pretrained=pretrained, num_classes=num_classes)

        if torch.cuda.device_count() > 1:
            self.model = nn.DataParallel(self.model)
            logger.info("Using %d GPUs", torch.cuda.device_count())
        else:
            logger.info("Using a single device (1 GPU or CPU)")

        if hasattr(self.model, "classifier"):
            in_features = self.model.classifier.in_features
            self.model.classifier = nn.Sequential(
                nn.AdaptiveAvgPool2d((1, 1)) if hasattr(self.model, "avgpool") else nn.Identity(),
                nn.Flatten(),
                nn.BatchNorm1d(in_features),
                nn.Dropout(0.4),
                nn.Linear(in_features, 1024),
                nn.ReLU(),
                nn.BatchNorm1d(1024),
                nn.Dropout(0.3),
                nn.Linear(1024, 512),
                nn.ReLU(),
                nn.BatchNorm1d(512),
                nn.Dropout(0.2),
                nn.Linear(512, 256),
                nn.ReLU(),
                nn.BatchNorm1d(256),
                nn.Dropout(0.1),
                nn.Linear(256, num_classes),
            )
        elif hasattr(self.model, "head"):
            in_features = self.model.head.in_features
            self.model.head = nn.Sequential(
                nn.BatchNorm1d(in_features),
                nn.Dropout(0.4),
                nn.Linear(in_features, 1024),
                nn.ReLU(),
                nn.BatchNorm1d(1024),
                nn.Dropout(0.3),
                nn.Linear(1024, 512),
                nn.ReLU(),
                nn.BatchNorm1d(512),
                nn.Dropout(0.2),
                nn.Linear(512, 256),
                nn.ReLU(),
                nn.BatchNorm1d(256),
                nn.Dropout(0.1),
                nn.Linear(256, num_classes),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)
