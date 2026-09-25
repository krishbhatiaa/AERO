"""Chunking helpers (lazy, memory-aware)."""
from __future__ import annotations

import xarray as xr

DEFAULT_CHUNKS = {"time": 1, "latitude": 256, "longitude": 256}


def chunk_dataset(ds: xr.Dataset, chunks: dict[str, int] | None = None) -> xr.Dataset:
    """Chunk along the dimensions present in ``ds``; unknown dimensions are ignored."""
    spec = {k: v for k, v in (chunks or DEFAULT_CHUNKS).items() if k in ds.dims}
    return ds.chunk(spec) if spec else ds
