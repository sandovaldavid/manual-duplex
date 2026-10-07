from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .errors import ConfigurationError
from .models import BackOrder, PassOrder, PrinterProfile

_CONFIG_VERSION = 1


def default_config_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "manual-duplex" / "config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    if not config_path.exists():
        return {"version": _CONFIG_VERSION, "printers": {}}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read configuration: {config_path}") from exc

    if data.get("version") != _CONFIG_VERSION or not isinstance(data.get("printers"), dict):
        raise ConfigurationError(
            f"Unsupported or malformed configuration file: {config_path}"
        )
    return data


def get_profile(printer: str, path: Path | None = None) -> PrinterProfile | None:
    data = load_config(path)
    raw = data["printers"].get(printer)
    if raw is None:
        return None

    try:
        return PrinterProfile(
            printer=printer,
            back_order=BackOrder(raw["back_order"]),
            pass_order=PassOrder(raw.get("pass_order", PassOrder.FRONTS_FIRST.value)),
            back_rotation=int(raw.get("back_rotation", 0)),
            refeed_instruction=str(
                raw.get(
                    "refeed_instruction",
                    "Reinsert the printed stack using the orientation validated for this printer.",
                )
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid profile for printer {printer!r}") from exc


def save_profile(profile: PrinterProfile, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    data = load_config(config_path)
    data["printers"][profile.printer] = {
        "back_order": profile.back_order.value,
        "pass_order": profile.pass_order.value,
        "back_rotation": profile.back_rotation,
        "refeed_instruction": profile.refeed_instruction,
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = config_path.with_suffix(".tmp")
    try:
        temp_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, config_path)
    except OSError as exc:
        raise ConfigurationError(f"Cannot write configuration: {config_path}") from exc
    finally:
        temp_path.unlink(missing_ok=True)

    return config_path
