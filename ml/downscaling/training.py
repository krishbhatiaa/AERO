"""Training loop and dataset for the U-Net downscaler.

Includes physics-informed loss (conservation + MSE), spectral loss component, and
evaluation against baselines.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, Dataset

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from ml.core.grid import GridSpec
from ml.downscaling.baseline import BaselineDownscaler


def _load_split_json(split_path: Path) -> list[dict[str, Any]]:
    with open(split_path, encoding="utf-8") as fh:
        return json.load(fh)


class DownscalingDataset(Dataset):
    """Dataset of (coarse, fine) precipitation pairs for downscaling training."""

    def __init__(self, training_root: str | Path, split: str = "train") -> None:
        if not HAS_TORCH:
            raise ImportError("PyTorch is required for DownscalingDataset. Install with: pip install torch")
        self.root = Path(training_root)
        split_path = self.root / "splits" / f"{split}.json"
        self.entries = _load_split_json(split_path)

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        entry = self.entries[idx]
        coarse = np.load(entry["input_path"])
        fine = np.load(entry["target_path"])
        coarse_t = torch.tensor(coarse, dtype=torch.float32).unsqueeze(0)
        fine_t = torch.tensor(fine, dtype=torch.float32).unsqueeze(0)
        return {"coarse": coarse_t, "fine": fine_t, "entry": entry}


def _spectral_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    pred_fft = torch.fft.rfft2(pred)
    target_fft = torch.fft.rfft2(target)
    mag_pred = torch.abs(pred_fft)
    mag_target = torch.abs(target_fft)
    return F.l1_loss(mag_pred, mag_target)


def _conservation_loss(pred: torch.Tensor, target: torch.Tensor, block_factor: int) -> torch.Tensor:
    b, c, h, w = pred.shape
    if h % block_factor != 0 or w % block_factor != 0:
        return torch.tensor(0.0, device=pred.device)
    pred_coarse = pred.unfold(2, block_factor, block_factor).unfold(3, block_factor, block_factor)
    pred_coarse = pred_coarse.mean(dim=(-2, -1))
    target_coarse = target.unfold(2, block_factor, block_factor).unfold(3, block_factor, block_factor)
    target_coarse = target_coarse.mean(dim=(-2, -1))
    return F.mse_loss(pred_coarse, target_coarse)


def _combined_loss(
    pred: torch.Tensor,
    target: torch.Tensor,
    block_factor: int = 4,
    spectral_weight: float = 0.1,
    conservation_weight: float = 0.5,
) -> torch.Tensor:
    mse = F.mse_loss(pred, target)
    spec = _spectral_loss(pred, target)
    cons = _conservation_loss(pred, target, block_factor)
    return mse + spectral_weight * spec + conservation_weight * cons


@dataclass
class DownscalerTrainConfig:
    epochs: int = 100
    batch_size: int = 2
    lr: float = 1e-3
    weight_decay: float = 1e-5
    base_features: int = 16
    spectral_weight: float = 0.1
    conservation_weight: float = 0.5
    block_factor: int = 4
    val_interval: int = 5
    checkpoint_dir: str = "models/downscaler_checkpoints"
    onnx_export: bool = True
    patience: int = 15
    in_channels: int = 1
    use_mixed_precision: bool = True
    gradient_accumulation_steps: int = 4
    gradient_checkpointing: bool = True


def train_downscaler(
    training_root: str | Path,
    config: DownscalerTrainConfig | None = None,
) -> dict[str, Any]:
    if not HAS_TORCH:
        raise ImportError("PyTorch is required for training. Install with: pip install torch")
    cfg = config or DownscalerTrainConfig()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    from ml.downscaling.unet import UNet

    train_ds = DownscalingDataset(training_root, "train")
    val_ds = DownscalingDataset(training_root, "validation")
    train_loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=0)

    model = UNet(in_channels=cfg.in_channels, out_channels=1, base_features=cfg.base_features).to(device)
    if cfg.gradient_checkpointing and hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.epochs)

    scaler = torch.amp.GradScaler("cuda", enabled=cfg.use_mixed_precision and device.type == "cuda")

    ckpt_dir = Path(cfg.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    best_val_loss = float("inf")
    patience_counter = 0
    history: dict[str, list[float]] = {"train_loss": [], "val_loss": []}

    for epoch in range(cfg.epochs):
        model.train()
        train_losses = []
        optimizer.zero_grad()
        for step, batch in enumerate(train_loader):
            coarse = batch["coarse"].to(device)
            fine_gt = batch["fine"].to(device)
            with torch.amp.autocast("cuda", enabled=cfg.use_mixed_precision and device.type == "cuda"):
                fine_pred = model(coarse)
                loss = _combined_loss(
                    fine_pred, fine_gt,
                    block_factor=cfg.block_factor,
                    spectral_weight=cfg.spectral_weight,
                    conservation_weight=cfg.conservation_weight,
                ) / cfg.gradient_accumulation_steps
            scaler.scale(loss).backward()
            if (step + 1) % cfg.gradient_accumulation_steps == 0:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
            train_losses.append(float(loss) * cfg.gradient_accumulation_steps)
        scheduler.step()
        avg_train = float(np.mean(train_losses)) if train_losses else 0.0
        history["train_loss"].append(avg_train)

        if (epoch + 1) % cfg.val_interval == 0:
            model.eval()
            val_losses = []
            with torch.no_grad():
                for batch in val_loader:
                    coarse = batch["coarse"].to(device)
                    fine_gt = batch["fine"].to(device)
                    with torch.amp.autocast("cuda", enabled=cfg.use_mixed_precision and device.type == "cuda"):
                        fine_pred = model(coarse)
                        loss = _combined_loss(fine_pred, fine_gt, cfg.block_factor, cfg.spectral_weight, cfg.conservation_weight)
                    val_losses.append(float(loss))
            avg_val = float(np.mean(val_losses)) if val_losses else 0.0
            history["val_loss"].append(avg_val)

            if avg_val < best_val_loss:
                best_val_loss = avg_val
                patience_counter = 0
                torch.save({
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "val_loss": avg_val,
                    "config": {
                        "base_features": cfg.base_features,
                        "in_channels": cfg.in_channels,
                    },
                }, ckpt_dir / "best.pt")
            else:
                patience_counter += cfg.val_interval
                if patience_counter >= cfg.patience:
                    break

    torch.save({
        "model_state_dict": model.state_dict(),
        "epoch": epoch,
        "config": {
            "base_features": cfg.base_features,
            "in_channels": cfg.in_channels,
        },
    }, ckpt_dir / "final.pt")

    onnx_path = ckpt_dir / "model.onnx"
    if cfg.onnx_export:
        dummy = torch.randn(1, cfg.in_channels, 32, 32, device=device)
        torch.onnx.export(
            model, dummy, str(onnx_path),
            input_names=["coarse"],
            output_names=["fine"],
            dynamic_axes={"coarse": {0: "batch"}, "fine": {0: "batch"}},
        )

    return {
        "history": history,
        "best_val_loss": best_val_loss,
        "checkpoint_dir": str(ckpt_dir),
    }


def evaluate_downscaler(
    training_root: str | Path,
    checkpoint_path: str | Path,
    split: str = "test",
) -> dict[str, float]:
    if not HAS_TORCH:
        raise ImportError("PyTorch is required for evaluation.")
    device = torch.device("cpu")
    from ml.downscaling.unet import LearnedDownscaler, UNet

    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    cfg = checkpoint.get("config", {})
    model = UNet(
        in_channels=cfg.get("in_channels", 1),
        out_channels=1,
        base_features=cfg.get("base_features", 32),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    learned = LearnedDownscaler(model=model)
    baseline = BaselineDownscaler("bicubic_conservative")

    ds = DownscalingDataset(training_root, split)
    loader = DataLoader(ds, batch_size=1, shuffle=False, num_workers=0)

    learned_errors: list[float] = []
    baseline_errors: list[float] = []
    learned_extreme_recall: list[float] = []
    baseline_extreme_recall: list[float] = []

    for batch in loader:
        coarse_np = batch["coarse"].squeeze().numpy()
        fine_gt_np = batch["fine"].squeeze().numpy()
        entry = batch["entry"]
        coarse_grid = GridSpec(**entry["coarse_grid"])
        fine_grid = GridSpec(**entry["fine_grid"])

        fine_learned = learned.downscale(coarse_np, coarse_grid, fine_grid)
        fine_baseline = baseline.downscale(coarse_np, coarse_grid, fine_grid)

        learned_errors.append(float(np.sqrt(np.mean((fine_learned - fine_gt_np) ** 2))))
        baseline_errors.append(float(np.sqrt(np.mean((fine_baseline - fine_gt_np) ** 2))))

        threshold = np.percentile(fine_gt_np, 95)
        gt_extreme = fine_gt_np > threshold
        if gt_extreme.sum() > 0:
            learned_recall = float((fine_learned[gt_extreme] > threshold).mean())
            baseline_recall = float((fine_baseline[gt_extreme] > threshold).mean())
            learned_extreme_recall.append(learned_recall)
            baseline_extreme_recall.append(baseline_recall)

    def _safe_mean(vals: list[float]) -> float:
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "learned_rmse": _safe_mean(learned_errors),
        "baseline_rmse": _safe_mean(baseline_errors),
        "learned_extreme_recall": _safe_mean(learned_extreme_recall),
        "baseline_extreme_recall": _safe_mean(baseline_extreme_recall),
    }
