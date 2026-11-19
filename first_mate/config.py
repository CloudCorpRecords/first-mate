"""Configuration loaded from environment variables and a local .env file.

No keys are hardcoded, and no keys or credits are needed to run the
demo. Every sponsor key in .env is an optional upgrade only. See
.env.example for the full list.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load simple KEY=value lines from .env, if present. Stdlib only."""
    candidates = []
    if path is not None:
        candidates.append(path)
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path(__file__).resolve().parent.parent / ".env")
    for candidate in candidates:
        if candidate.is_file():
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            break


@dataclass
class Config:
    context_dev_api_key: str = ""
    context_dev_base_url: str = "https://api.context.dev"
    nyte_api_key: str = ""
    trustedrouter_api_key: str = ""
    # Base URL is configurable on purpose. First Mate does not guess or
    # hardcode a NYTE or TrustedRouter endpoint as fact. Set it only if
    # you choose to use that optional route, from its published docs.
    nyte_base_url: str = ""
    nyte_model: str = ""
    data_dir: Path = Path("data/ship-logs")
    host: str = "0.0.0.0"
    port: int = 8000
    fetch_timeout: float = 8.0
    # Set FIRST_MATE_ON_BOAT=1 (or BOAT_VM=1) when running on a Boat.dev
    # VM, so the All accesses record can say so plainly.
    on_boat_vm: bool = False

    @property
    def inference_api_key(self) -> str:
        return self.nyte_api_key or self.trustedrouter_api_key

    @property
    def inference_configured(self) -> bool:
        # Both a key and a base URL are required for a live private call.
        return bool(self.inference_api_key and self.nyte_base_url and self.nyte_model)

    @property
    def context_dev_configured(self) -> bool:
        return bool(self.context_dev_api_key)


def load_config() -> Config:
    load_dotenv()
    data_dir = os.environ.get("FIRST_MATE_DATA_DIR", "data/ship-logs")
    return Config(
        context_dev_api_key=os.environ.get("CONTEXT_DEV_API_KEY", ""),
        context_dev_base_url=os.environ.get(
            "CONTEXT_DEV_BASE_URL", "https://api.context.dev"
        ),
        nyte_api_key=os.environ.get("NYTE_API_KEY", ""),
        trustedrouter_api_key=os.environ.get("TRUSTEDROUTER_API_KEY", ""),
        nyte_base_url=os.environ.get("NYTE_BASE_URL", "")
        or os.environ.get("TRUSTEDROUTER_BASE_URL", ""),
        nyte_model=os.environ.get("NYTE_MODEL", "")
        or os.environ.get("TRUSTEDROUTER_MODEL", ""),
        data_dir=Path(data_dir),
        on_boat_vm=os.environ.get("FIRST_MATE_ON_BOAT", "") in ("1", "true", "yes")
        or os.environ.get("BOAT_VM", "") in ("1", "true", "yes"),
        host=os.environ.get("FIRST_MATE_HOST", "0.0.0.0"),
        port=int(os.environ.get("FIRST_MATE_PORT", "8000")),
        fetch_timeout=float(os.environ.get("FIRST_MATE_FETCH_TIMEOUT", "8")),
    )
