"""U-Net CNN for precipitation downscaling.

Maps coarse-resolution precipitation (and optional static features) to fine-resolution
precipitation fields. Implements the Downscaler protocol from ml/downscaling/baseline.py.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np

try:
    import torch
    import torch.nn as nn

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    class _DummyModule:
        pass
    class _DummyNN:
        Module = _DummyModule
    nn = _DummyNN()

from ml.core.grid import GridSpec

try:
    from ml.downscaling.baseline import Downscaler
except ImportError:
    class Downscaler(Protocol):
        name: str
        def downscale(self, coarse: np.ndarray, coarse_grid: GridSpec, fine_grid: GridSpec) -> np.ndarray: ...


class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class Downsample(nn.Module):
    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.pool = nn.MaxPool2d(2)
        self.conv = ConvBlock(in_ch, out_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(self.pool(x))


class Upsample(nn.Module):
    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.up = nn.ConvTranspose2d(in_ch, out_ch, 2, stride=2)
        self.conv = ConvBlock(out_ch * 2, out_ch)

    def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        x = self.up(x)
        dy = skip.size(2) - x.size(2)
        dx = skip.size(3) - x.size(3)
        x = nn.functional.pad(x, [dx // 2, dx - dx // 2, dy // 2, dy - dy // 2])
        x = torch.cat([skip, x], dim=1)
        return self.conv(x)


class UNet(nn.Module):
    """U-Net for precipitation downscaling.

    Args:
        in_channels: Number of input channels (precipitation + optional static features).
        out_channels: Number of output channels (typically 1 for precipitation).
        base_features: Number of features in the first encoder layer.
    """

    def __init__(self, in_channels: int = 1, out_channels: int = 1, base_features: int = 64) -> None:
        super().__init__()
        f = base_features
        self.enc1 = ConvBlock(in_channels, f)
        self.enc2 = Downsample(f, f * 2)
        self.enc3 = Downsample(f * 2, f * 4)
        self.enc4 = Downsample(f * 4, f * 8)

        self.bottleneck = nn.Sequential(
            nn.Conv2d(f * 8, f * 16, 3, padding=1, bias=False),
            nn.BatchNorm2d(f * 16),
            nn.ReLU(inplace=True),
            nn.Conv2d(f * 16, f * 16, 3, padding=1, bias=False),
            nn.BatchNorm2d(f * 16),
            nn.ReLU(inplace=True),
        )

        self.dec4 = Upsample(f * 16, f * 8)
        self.dec3 = Upsample(f * 8, f * 4)
        self.dec2 = Upsample(f * 4, f * 2)
        self.dec1 = Upsample(f * 2, f)

        self.out_conv = nn.Conv2d(f, out_channels, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)

        b = self.bottleneck(e4)

        d4 = self.dec4(b, e4)
        d3 = self.dec3(d4, e3)
        d2 = self.dec2(d3, e2)
        d1 = self.dec1(d2, e1)

        return self.out_conv(d1)


class LearnedDownscaler:
    """Wrapper that exposes the UNet as a Downscaler-compatible object.

    Uses bicubic upsampling of the coarse field to the fine grid as the input to the U-Net,
    which then learns a residual correction.
    """

    def __init__(
        self,
        model: UNet | None = None,
        in_channels: int = 1,
        base_features: int = 64,
        nonneg: bool = True,
    ) -> None:
        if not HAS_TORCH:
            raise ImportError("PyTorch is required for LearnedDownscaler. Install with: pip install torch")
        self.name = "learned_unet"
        self._model = model or UNet(in_channels=in_channels, base_features=base_features)
        self._model.eval()
        self._nonneg = nonneg

    def downscale(self, coarse: np.ndarray, coarse_grid: GridSpec, fine_grid: GridSpec) -> np.ndarray:
        from scipy import ndimage

        if coarse.shape != coarse_grid.shape:
            raise ValueError(f"coarse shape {coarse.shape} != grid {coarse_grid.shape}")

        fi = (fine_grid.lats - coarse_grid.lat_min) / coarse_grid.dlat
        fj = (fine_grid.lons - coarse_grid.lon_min) / coarse_grid.dlon
        ii, jj = np.meshgrid(fi, fj, indexing="ij")
        upsampled = ndimage.map_coordinates(np.asarray(coarse, float), [ii, jj], order=3, mode="nearest")

        upsampled_tensor = torch.tensor(upsampled, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

        with torch.no_grad():
            correction = self._model(upsampled_tensor)
            fine = (upsampled_tensor + correction).squeeze().numpy()

        if self._nonneg:
            fine = np.clip(fine, 0.0, None)
        return fine

    def load_state_dict(self, state_dict: dict) -> None:
        self._model.load_state_dict(state_dict)

    def eval(self) -> None:
        self._model.eval()
