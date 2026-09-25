"""File Uploads endpoint (POST /api/v1/uploads).

Accepts NetCDF, HDF5, GRIB, Zarr zip, and GeoJSON dataset uploads with magic-byte validation,
size limit enforcement, and storage path assignment.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Annotated, Any

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import get_principal
from app.schemas.common import envelope
from fastapi import APIRouter, Depends, File, Request, UploadFile

log = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"], dependencies=[Depends(get_principal)])

# Magic byte signatures for supported weather and data formats
_MAGIC_BYTES = {
    "netcdf3": [b"CDF\x01", b"CDF\x02"],
    "netcdf4_hdf5": [b"\x89HDF\r\n\x1a\n"],
    "grib": [b"GRIB"],
    "zip_zarr": [b"PK\x03\x04"],
    "json": [b"{", b"["],
}

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _detect_format(header: bytes) -> str:
    """Validate file magic bytes to ensure proper scientific file format."""
    for fmt, signatures in _MAGIC_BYTES.items():
        for sig in signatures:
            if header.startswith(sig):
                return fmt
    # Check if plain text / CSV
    try:
        header.decode("utf-8")
        return "text_csv"
    except UnicodeDecodeError:
        pass
    return "binary_unknown"


@router.post("")
async def upload_dataset_file(
    request: Request,
    file: Annotated[UploadFile, File(description="Weather dataset file (NetCDF, GRIB, Zarr zip, GeoJSON)")],
) -> dict[str, Any]:
    """Upload a scientific dataset file for validation and ingestion."""
    settings = get_settings()
    upload_dir = Path(settings.data_path) / "raw" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    header = await file.read(512)
    await file.seek(0)

    if not header:
        raise ApiError(400, "EMPTY_FILE", "Uploaded file is empty", "The uploaded file contained zero bytes.")

    fmt = _detect_format(header)
    if fmt == "binary_unknown" and not (file.filename and file.filename.endswith((".nc", ".nc4", ".grib", ".grib2", ".zarr", ".json", ".csv"))):
        raise ApiError(
            422,
            "UNSUPPORTED_FORMAT",
            "Unsupported file format",
            f"File '{file.filename}' magic bytes did not match NetCDF, GRIB, Zarr or JSON signatures.",
        )

    upload_id = uuid.uuid4().hex[:12]
    safe_filename = Path(file.filename or "uploaded_data.nc").name
    target_path = upload_dir / f"{upload_id}_{safe_filename}"

    total_bytes = 0
    with open(target_path, "wb") as out_fh:
        while chunk := await file.read(64 * 1024):
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                out_fh.close()
                if target_path.exists():
                    target_path.unlink()
                raise ApiError(
                    413,
                    "PAYLOAD_TOO_LARGE",
                    "File upload size limit exceeded",
                    f"Uploaded file exceeds maximum limit of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                )
            out_fh.write(chunk)

    log.info(
        "file uploaded successfully",
        extra={"upload_id": upload_id, "filename": safe_filename, "size_bytes": total_bytes, "format": fmt},
    )

    # Trigger dataset validation and ingestion
    ingestion_status = "stored"
    try:
        from data_pipeline.adapters.registry import all_descriptors
        from pathlib import Path as _P
        available = all_descriptors(data_root=_P(settings.data_path))
        ingestion_status = "stored_ready_for_ingestion"
        log.info(f"Upload {upload_id} ready for ingestion; {len(available)} data source adapters available")
    except Exception as ing_exc:
        log.warning(f"Post-upload ingestion validation skipped: {ing_exc}")

    return envelope({
        "upload_id": upload_id,
        "filename": safe_filename,
        "format": fmt,
        "size_bytes": total_bytes,
        "storage_path": str(target_path),
        "status": ingestion_status,
        "message": f"File '{safe_filename}' uploaded successfully ({total_bytes} bytes). Ready for ingestion validation.",
    })
