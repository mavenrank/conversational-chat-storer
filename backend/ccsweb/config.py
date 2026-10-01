"""Runtime configuration.

Every storage root can be overridden with an environment variable, which is what
makes the app testable against fixtures and usable on machines where a tool
stores data somewhere non-standard (WSL, portable installs, relocated
``globalStorage``).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

_ENV_PREFIX = "CCSWEB_"


class Settings(BaseModel):
    """Resolved paths and tunables."""

    claude_root: Path
    gemini_root: Path
    opencode_root: Path
    kilocode_root: Path
    codex_root: Path

    #: Where normalised session snapshots are kept. Owned by this app, so
    #: history survives a source tool pruning or being reinstalled.
    archive_root: Path

    #: Payloads at or above this size are elided from session responses and
    #: fetched on demand when the user expands the block.
    elide_threshold_bytes: int = 2_000

    #: Sessions whose index entry is older than this are re-read from disk.
    index_ttl_seconds: int = 5

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.environ.get(f"{_ENV_PREFIX}{name}")
    return Path(raw).expanduser() if raw else default


def _windows_appdata() -> Path:
    raw = os.environ.get("APPDATA")
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Roaming"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    home = Path.home()
    return Settings(
        claude_root=_path_from_env("CLAUDE_ROOT", home / ".claude"),
        gemini_root=_path_from_env("GEMINI_ROOT", home / ".gemini"),
        opencode_root=_path_from_env(
            "OPENCODE_ROOT", home / ".local" / "share" / "opencode"
        ),
        kilocode_root=_path_from_env(
            "KILOCODE_ROOT",
            _windows_appdata() / "Code" / "User" / "globalStorage" / "kilocode.kilo-code",
        ),
        codex_root=_path_from_env("CODEX_ROOT", home / ".codex"),
        archive_root=_path_from_env("ARCHIVE_ROOT", home / ".ccsweb" / "archive"),
        elide_threshold_bytes=int(
            os.environ.get(f"{_ENV_PREFIX}ELIDE_THRESHOLD", "2000")
        ),
    )
