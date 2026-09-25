"""Conditional Diffusion model for extreme weather downscaling (EDM style).

Provides probabilistic downscaling by sampling fine-resolution precipitation fields
conditioned on coarse NWP inputs.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    class _DummyModule:
        pass
    class _DummyNN:
        Module = _DummyModule
    nn = _DummyNN()

from ml.core.grid import GridSpec


class SinusoidalTimeEmbedding(nn.Module):
    """Encodes diffusion time step t into a continuous embedding."""

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        device = t.device
        half_dim = self.dim // 2
        emb = math.log(10000) / (half_dim - 1)
        emb = torch.exp(torch.arange(half_dim, device=device) * -emb)
        emb = t.unsqueeze(1) * emb.unsqueeze(0)
        emb = torch.cat([torch.sin(emb), torch.cos(emb)], dim=1)
        return emb


class ResBlock(nn.Module):
    """Residual block with time step embedding conditioning."""

    def __init__(self, in_ch: int, out_ch: int, time_dim: int) -> None:
        super().__init__()
        self.time_mlp = nn.Sequential(
            nn.SiLU(),
            nn.Linear(time_dim, out_ch),
        )
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1)
        self.act = nn.SiLU()
        self.norm1 = nn.BatchNorm2d(out_ch)
        self.norm2 = nn.BatchNorm2d(out_ch)
        self.shortcut = nn.Conv2d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()

    def forward(self, x: torch.Tensor, time_emb: torch.Tensor) -> torch.Tensor:
        h = self.act(self.norm1(self.conv1(x)))
        h = h + self.time_mlp(time_emb).unsqueeze(-1).unsqueeze(-1)
        h = self.act(self.norm2(self.conv2(h)))
        return h + self.shortcut(x)


class ConditionalDiffusionUNet(nn.Module):
    """U-Net architecture for denoising score-based diffusion model."""

    def __init__(self, in_channels: int = 2, out_channels: int = 1, base_dim: int = 32) -> None:
        super().__init__()
        time_dim = base_dim * 4
        self.time_embed = nn.Sequential(
            SinusoidalTimeEmbedding(base_dim),
            nn.Linear(base_dim, time_dim),
            nn.SiLU(),
            nn.Linear(time_dim, time_dim),
        )
        self.inc = nn.Conv2d(in_channels, base_dim, 3, padding=1)
        self.down1 = ResBlock(base_dim, base_dim * 2, time_dim)
        self.down2 = ResBlock(base_dim * 2, base_dim * 4, time_dim)
        self.bot = ResBlock(base_dim * 4, base_dim * 4, time_dim)
        self.up2 = ResBlock(base_dim * 4 + base_dim * 2, base_dim * 2, time_dim)
        self.up1 = ResBlock(base_dim * 2 + base_dim, base_dim, time_dim)
        self.outc = nn.Conv2d(base_dim, out_channels, 1)

    def forward(self, x_noisy: torch.Tensor, coarse_cond: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        t_emb = self.time_embed(t)
        x_in = torch.cat([x_noisy, coarse_cond], dim=1)
        h0 = self.inc(x_in)
        h1 = self.down1(h0, t_emb)
        h2 = self.down2(h1, t_emb)
        b = self.bot(h2, t_emb)
        
        # Upsample h2 size match
        b_up = F.interpolate(b, size=h1.shape[2:], mode="nearest")
        u2 = self.up2(torch.cat([b_up, h1], dim=1), t_emb)
        
        u2_up = F.interpolate(u2, size=h0.shape[2:], mode="nearest")
        u1 = self.up1(torch.cat([u2_up, h0], dim=1), t_emb)
        return self.outc(u1)


class ConditionalDiffusionDownscaler:
    """Diffusion-based probabilistic downscaler for high-resolution precipitation fields."""

    def __init__(
        self,
        model: ConditionalDiffusionUNet | None = None,
        base_dim: int = 32,
        num_steps: int = 20,
        device: str = "cpu",
    ) -> None:
        if not HAS_TORCH:
            raise ImportError("PyTorch is required for ConditionalDiffusionDownscaler.")
        self.name = "conditional_diffusion"
        self.device = torch.device(device)
        self._model = (model or ConditionalDiffusionUNet(base_dim=base_dim)).to(self.device)
        self._model.eval()
        self.num_steps = num_steps
        self.beta_start = 1e-4
        self.beta_end = 0.02
        self.betas = torch.linspace(self.beta_start, self.beta_end, num_steps, device=self.device)
        self.alphas = 1.0 - self.betas
        self.alphas_cumprod = torch.cumprod(self.alphas, dim=0)

    def downscale(
        self, coarse: np.ndarray, coarse_grid: GridSpec, fine_grid: GridSpec, num_samples: int = 1
    ) -> np.ndarray:
        """Sample fine-resolution precipitation fields given coarse input."""
        from scipy import ndimage

        fi = (fine_grid.lats - coarse_grid.lat_min) / coarse_grid.dlat
        fj = (fine_grid.lons - coarse_grid.lon_min) / coarse_grid.dlon
        ii, jj = np.meshgrid(fi, fj, indexing="ij")
        upsampled = ndimage.map_coordinates(np.asarray(coarse, float), [ii, jj], order=3, mode="nearest")

        cond = torch.tensor(upsampled, dtype=torch.float32, device=self.device).unsqueeze(0).unsqueeze(0)

        samples = []
        with torch.no_grad():
            for _ in range(num_samples):
                x = torch.randn_like(cond, device=self.device)
                for t_idx in reversed(range(self.num_steps)):
                    t = torch.tensor([t_idx], device=self.device, dtype=torch.float32)
                    pred_noise = self._model(x, cond, t)
                    alpha = self.alphas[t_idx]
                    alpha_hat = self.alphas_cumprod[t_idx]
                    beta = self.betas[t_idx]

                    if t_idx > 0:
                        noise = torch.randn_like(x)
                    else:
                        noise = torch.zeros_like(x)

                    x = (1 / torch.sqrt(alpha)) * (x - ((1 - alpha) / torch.sqrt(1 - alpha_hat)) * pred_noise) + torch.sqrt(beta) * noise
                
                fine_field = (cond + x).squeeze().cpu().numpy()
                samples.append(np.clip(fine_field, 0.0, None))

        if num_samples == 1:
            return samples[0]
        return np.stack(samples, axis=0)

    def load_state_dict(self, state_dict: dict[str, Any]) -> None:
        self._model.load_state_dict(state_dict)
