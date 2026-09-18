#!/usr/bin/env python3
"""Publish a prepared desktop release to OSS without exposing long-lived keys.

The caller supplies temporary Alibaba Cloud credentials through the standard
ALIBABA_CLOUD_* environment variables.  ZIPs are verified and uploaded before
either manifest is changed, so a failed transfer cannot advertise a broken
release to customers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_file(path: Path) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Missing or empty release file: {path}")
    return path


def object_key_from_url(url: str, bucket: str, prefix: str) -> str:
    parsed = urlparse(url)
    expected_host = f"{bucket}.oss-cn-beijing.aliyuncs.com"
    if parsed.scheme != "https" or parsed.netloc != expected_host:
        raise ValueError(f"Manifest URL must use {expected_host}: {url}")
    key = parsed.path.lstrip("/")
    if not key.startswith(prefix) or not key.endswith(".zip"):
        raise ValueError(f"Manifest update URL is outside {prefix}: {url}")
    return key


def read_release(directory: Path, bucket: str, prefix: str) -> tuple[dict, Path, Path, Path, Path, str, str]:
    manifest_path = require_file(directory / "latest.json")
    latest_js_path = require_file(directory / "latest.js")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = ("version", "url", "sha256", "fullPackageUrl", "fullPackageSha256", "fullPackageName")
    missing = [key for key in required if not isinstance(manifest.get(key), str) or not manifest[key]]
    if missing:
        raise ValueError(f"Manifest fields missing: {', '.join(missing)}")

    update_key = object_key_from_url(manifest["url"], bucket, prefix)
    full_key = object_key_from_url(manifest["fullPackageUrl"], bucket, prefix)
    update_path = require_file(directory / Path(update_key).name)
    full_path = require_file(directory / manifest["fullPackageName"])
    if Path(full_key).name != full_path.name:
        raise ValueError("fullPackageUrl and fullPackageName disagree")
    if update_key == full_key:
        raise ValueError("Update and complete packages must use different immutable object keys")
    if sha256(update_path) != manifest["sha256"].lower():
        raise ValueError("Update package SHA-256 does not match latest.json")
    if sha256(full_path) != manifest["fullPackageSha256"].lower():
        raise ValueError("Complete package SHA-256 does not match latest.json")
    return manifest, update_path, full_path, manifest_path, latest_js_path, update_key, full_key


def build_bucket(bucket_name: str, endpoint: str):
    import oss2

    key_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
    key_secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    security_token = os.environ.get("ALIBABA_CLOUD_SECURITY_TOKEN")
    if not key_id or not key_secret or not security_token:
        raise RuntimeError("Temporary OIDC credentials are unavailable; configure the Alibaba Cloud OIDC role first")
    return oss2.Bucket(oss2.StsAuth(key_id, key_secret, security_token), endpoint, bucket_name)


def upload_and_verify(bucket, local_file: Path, object_key: str, *, manifest: bool = False) -> None:
    import oss2

    content_type, _ = mimetypes.guess_type(local_file.name)
    headers = {"Content-Type": content_type or "application/octet-stream"}
    if manifest:
        headers["Cache-Control"] = "no-cache, no-store, max-age=0"
    oss2.resumable_upload(
        bucket,
        object_key,
        str(local_file),
        multipart_threshold=16 * 1024 * 1024,
        part_size=16 * 1024 * 1024,
        num_threads=4,
        headers=headers,
    )
    remote = bucket.head_object(object_key)
    if remote.content_length != local_file.stat().st_size:
        raise RuntimeError(f"Size verification failed for oss://{bucket.bucket_name}/{object_key}")
    print(f"Verified OSS object: oss://{bucket.bucket_name}/{object_key} ({remote.content_length} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--bucket", default="luotuoqiluotuozhaoma-download")
    parser.add_argument("--endpoint", default="https://oss-cn-beijing.aliyuncs.com")
    parser.add_argument("--prefix", default="updates/")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    prefix = args.prefix.strip("/") + "/"
    manifest, update, full, latest_json, latest_js, update_key, full_key = read_release(
        args.directory.resolve(), args.bucket, prefix
    )
    print(f"Validated release v{manifest['version']}")
    print(f"ZIP upload order: {full_key}, {update_key}")
    print("Manifest upload order: updates/latest.json, updates/latest.js")
    if args.dry_run:
        return 0

    bucket = build_bucket(args.bucket, args.endpoint)
    # Immutable ZIPs first.  Do not advertise the release until both return a
    # matching remote size.
    upload_and_verify(bucket, full, full_key)
    upload_and_verify(bucket, update, update_key)
    upload_and_verify(bucket, latest_json, f"{prefix}latest.json", manifest=True)
    upload_and_verify(bucket, latest_js, f"{prefix}latest.js", manifest=True)
    print(f"Published release v{manifest['version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
