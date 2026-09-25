import os

import pytest

from data_pipeline.storage.base import StorageError
from data_pipeline.storage.factory import storage_from_env
from data_pipeline.storage.keys import InvalidKeyError, build_key, validate_key
from data_pipeline.storage.local import LocalStorageProvider
from data_pipeline.storage.s3 import S3StorageProvider


@pytest.mark.parametrize("bad", ["", "/abs", "../x", "a/../b", "a//b", "a\\b", "a b", "a/b\x00", "x" * 600, ".hidden", "a/.."])
def test_invalid_keys_are_rejected(bad):
    with pytest.raises(InvalidKeyError):
        validate_key(bad)


@pytest.mark.parametrize("good", ["a", "staged/era5/x.zarr", "jobs/abc-123.json", "climatology/1991-2020/tp.zarr"])
def test_valid_keys_accepted(good):
    assert validate_key(good) == good
    assert build_key("staged", "era5", "x.zarr") == "staged/era5/x.zarr"


def test_local_roundtrip_listing_delete_and_health(tmp_path):
    s = LocalStorageProvider(tmp_path)
    obj = s.put_bytes("a/b/c.bin", b"hello")
    assert obj.size == 5 and len(obj.sha256) == 64
    assert s.get_bytes("a/b/c.bin") == b"hello" and s.exists("a/b/c.bin")
    assert s.list_keys("a/") == ["a/b/c.bin"] and s.list_keys("z") == []
    s.delete("a/b/c.bin")
    assert not s.exists("a/b/c.bin")
    assert s.healthcheck() == (True, "writable")
    with pytest.raises(StorageError):
        s.get_bytes("missing.bin")


def test_local_provider_blocks_path_traversal_and_symlink_escape(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    s = LocalStorageProvider(root)
    with pytest.raises(InvalidKeyError):
        s.get_bytes("../outside/secret.txt")
    os.symlink(outside, root / "link")
    with pytest.raises(StorageError):
        s.get_bytes("link/secret.txt")


def test_s3_provider_against_moto(monkeypatch):
    moto = pytest.importorskip("moto")
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "testing")
    with moto.mock_aws():
        s = S3StorageProvider("ewai-test-bucket", region="us-east-1", access_key="testing", secret_key="testing", create_bucket=True)
        assert s.healthcheck()[0]
        s.put_bytes("jobs/j1.json", b"{}")
        s.put_bytes("staged/x", b"1")
        assert s.get_bytes("jobs/j1.json") == b"{}" and s.exists("staged/x") and not s.exists("nope")
        assert s.list_keys("jobs/") == ["jobs/j1.json"]
        s.delete("staged/x")
        assert not s.exists("staged/x")
        target, opts = s.zarr_target("staged/a.zarr")
        assert target == "s3://ewai-test-bucket/staged/a.zarr" and opts["key"] == "testing"
        with pytest.raises(StorageError):
            s.get_bytes("absent")
        with pytest.raises(InvalidKeyError):
            s.put_bytes("../x", b"")


def test_s3_requires_bucket_and_factory_reads_environment(tmp_path):
    with pytest.raises(ValueError):
        S3StorageProvider("")
    assert storage_from_env({"STORAGE_BACKEND": "local", "DATA_PATH": str(tmp_path)}).name == "local"
    with pytest.raises(ValueError):
        storage_from_env({"STORAGE_BACKEND": "ftp"})
    with pytest.raises(ValueError):
        storage_from_env({"STORAGE_BACKEND": "s3"})  # bucket missing: never a hard-coded default
