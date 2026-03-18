"""Configuration management for stacks."""
import os
from pathlib import Path


def get_stacks_root() -> Path:
    """Return the stacks root directory.

    Uses STACKS_ROOT env var, falls back to current working directory.
    """
    root = os.environ.get("STACKS_ROOT")
    if root:
        return Path(root)
    return Path.cwd()


def get_db_path() -> Path:
    """Return the path to stacks.db."""
    return get_stacks_root() / "stacks.db"


def get_converted_dir() -> Path:
    """Return the path to the converted PDF directory, creating it if needed."""
    d = get_stacks_root() / ".stacks" / "converted"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_filepath(path) -> Path:
    """Resolve a filepath relative to stacks root."""
    return get_stacks_root() / Path(path)
