from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import subprocess
import yaml


@dataclass(frozen=True)
class IO3Config:
    config_dir: Path
    providers: Dict[str, Any]
    logging: Dict[str, Any]
    routing: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_dir": str(self.config_dir),
            "providers": self.providers,
            "logging": self.logging,
            "routing": self.routing,
        }


def _repo_root() -> Optional[Path]:
    """
    Returns the git repo root if available, else None.
    """
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if p.returncode != 0:
            return None
        root = (p.stdout or "").strip()
        return Path(root) if root else None
    except Exception:
        return None


def default_config_dir() -> Path:
    """
    Portable default config dir resolver.

    Strategy:
    - Resolve repo root relative to this file location.
    - Return <repo_root>/IO-III/runtime/config
    """
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / "IO-III" / "runtime" / "config"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must be a YAML mapping/dict: {path}")
    return data


def load_io3_config(config_dir: Optional[Path] = None) -> IO3Config:
    """
    Load IO-III runtime configuration from YAML files in config_dir.
    """
    cfg_dir = config_dir or default_config_dir()

    providers = _load_yaml(cfg_dir / "providers.yaml")
    logging = _load_yaml(cfg_dir / "logging.yaml")
    routing = _load_yaml(cfg_dir / "routing_table.yaml")

    return IO3Config(
        config_dir=cfg_dir,
        providers=providers,
        logging=logging,
        routing=routing,
    )
