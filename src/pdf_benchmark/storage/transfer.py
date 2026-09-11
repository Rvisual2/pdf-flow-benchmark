"""Small GCS transport: authenticated immutable uploads and anonymous downloads."""

import base64
import hashlib
import json
import mimetypes
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

import httpx


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def public_url(bucket: str, name: str) -> str:
    return f"https://storage.googleapis.com/{quote(bucket, safe='')}/{quote(name, safe='/')}"


def checked_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "storage.googleapis.com" or parsed.fragment:
        raise ValueError("Artifact URLs must use https://storage.googleapis.com")
    return url


class BucketPublisher:
    """Reuse a gcloud user token and HTTP connection pool; never persist credentials."""

    def __init__(self, bucket: str, client: httpx.Client, token: str):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket):
            raise ValueError("Provide a bucket name, without gs:// or a path")
        self.bucket = bucket
        self.client = client
        self._token = token

    @classmethod
    def from_gcloud(cls, bucket: str, client: httpx.Client, account: str | None = None):
        command = ["gcloud", "auth", "print-access-token", "--quiet"]
        if account:
            command += ["--account", account]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except FileNotFoundError as error:
            raise ValueError(
                "Uploads require gcloud. Install it and run 'gcloud auth login'."
            ) from error
        if result.returncode or not result.stdout.strip():
            raise ValueError("Google Cloud authentication failed. Run 'gcloud auth login'.")
        return cls(bucket, client, result.stdout.strip())

    def upload(self, filename: str, content: bytes) -> dict:
        checksum = digest(content)
        name = f"objects/{checksum}/{Path(filename).name}"
        response = self.client.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o",
            params={"uploadType": "media", "name": name, "ifGenerationMatch": "0"},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            },
            content=content,
        )
        url = public_url(self.bucket, name)
        if response.status_code == 412:
            existing = self.client.get(url)
            existing.raise_for_status()
            if digest(existing.content) != checksum:
                raise ValueError(f"Remote object conflicts with its content hash: {name}")
        else:
            response.raise_for_status()
            expected_md5 = base64.b64encode(hashlib.md5(content).digest()).decode()
            if response.json().get("md5Hash") != expected_md5:
                raise ValueError(f"Cloud Storage checksum mismatch for {filename}")
        return {"url": url, "sha256": checksum, "size": len(content)}


def read_manifest(reference: dict | str, client: httpx.Client, depth: int = 0) -> dict:
    if depth > 2:
        raise ValueError("Too many manifest redirects")
    expected_hash = reference.get("sha256") if isinstance(reference, dict) else None
    location = checked_url(reference["url"]) if isinstance(reference, dict) else reference
    if location.startswith("https://"):
        response = client.get(checked_url(location))
        response.raise_for_status()
        content = response.content
    else:
        content = Path(location).read_bytes()
    if expected_hash and digest(content) != expected_hash:
        raise ValueError("Manifest checksum does not match the pinned release")
    manifest = json.loads(content)
    # Upload receipts are small pointers to the immutable manifest.
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be a JSON object")
    if "manifest" in manifest:
        return read_manifest(manifest["manifest"], client, depth + 1)
    if manifest.get("schema_version") != 1 or manifest.get("kind") not in {
        "dataset",
        "results",
        "thumbnails",
    }:
        raise ValueError("Unsupported artifact manifest")
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise ValueError("Manifest has no files")
    return manifest


def validated_targets(manifest: dict, directory: Path) -> list[tuple[dict, Path]]:
    root = directory.resolve()
    targets = []
    seen = set()
    for entry in manifest["files"]:
        path = PurePosixPath(entry["path"])
        if path.is_absolute() or not path.parts or ".." in path.parts or "\\" in entry["path"]:
            raise ValueError(f"Unsafe manifest path: {entry['path']}")
        target = root.joinpath(*path.parts)
        if target in seen or not target.resolve().is_relative_to(root):
            raise ValueError(f"Duplicate or escaping destination: {entry['path']}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("Invalid SHA-256 checksum")
        if type(entry["size"]) is not int or entry["size"] < 0:
            raise ValueError("Invalid file size")
        checked_url(entry["url"])
        seen.add(target)
        targets.append((entry, target))
    return targets


def download_file(entry: dict, target: Path, client: httpx.Client) -> bool:
    if target.is_file() and digest(target.read_bytes()) == entry["sha256"]:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
            temporary_path = Path(output.name)
            checksum = hashlib.sha256()
            count = 0
            with client.stream("GET", entry["url"]) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    count += len(chunk)
                    if count > entry["size"]:
                        raise ValueError(f"Downloaded file exceeds expected size: {entry['path']}")
                    checksum.update(chunk)
                    output.write(chunk)
        if count != entry["size"] or checksum.hexdigest() != entry["sha256"]:
            raise ValueError(f"Download checksum mismatch: {entry['path']}")
        temporary_path.chmod(0o644)
        temporary_path.replace(target)
        return True
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
