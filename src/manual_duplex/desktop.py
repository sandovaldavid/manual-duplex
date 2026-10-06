from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .errors import ConfigurationError


def desktop_entry_content(executable: Path) -> str:
    escaped = str(executable).replace("\\", "\\\\").replace('"', '\\"')
    return f"""[Desktop Entry]
Type=Application
Name=Manual Duplex
Comment=Print PDF files with a guided manual duplex workflow
Exec="{escaped}" gui %f
Icon=printer
Terminal=false
MimeType=application/pdf;
Categories=Utility;Printing;
StartupNotify=true
"""


def install_desktop_entry(
    executable: Path | None = None,
    data_home: Path | None = None,
) -> Path:
    resolved = executable or _resolve_executable()
    root = data_home or Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    applications = root / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    destination = applications / "manual-duplex.desktop"
    destination.write_text(desktop_entry_content(resolved), encoding="utf-8")

    updater = shutil.which("update-desktop-database")
    if updater is not None:
        subprocess.run(
            [updater, str(applications)],
            check=False,
            capture_output=True,
            text=True,
        )
    return destination


def _resolve_executable() -> Path:
    executable = shutil.which("manual-duplex")
    if executable is not None:
        return Path(executable).resolve()

    argv0 = Path(sys.argv[0])
    if argv0.is_file():
        return argv0.resolve()

    raise ConfigurationError(
        "Cannot locate the manual-duplex executable. Install the package first."
    )
