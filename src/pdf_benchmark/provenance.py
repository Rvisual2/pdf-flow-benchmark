"""Capture source identity without claiming that publication regenerated old artifacts."""

import hashlib
import subprocess

from .files import ROOT


def repository_provenance() -> dict:
    def git(*arguments: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(ROOT), *arguments], capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else None

    try:
        commit = git("rev-parse", "HEAD")
        changed = git("status", "--porcelain")
    except FileNotFoundError:
        commit, changed = None, None
    lock = ROOT / "uv.lock"
    return {
        "commit": commit,
        "dirty": bool(changed) if changed is not None else None,
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None,
    }
