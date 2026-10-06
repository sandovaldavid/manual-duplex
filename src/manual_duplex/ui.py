from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .errors import CommandError


class Zenity:
    def __init__(self) -> None:
        if shutil.which("zenity") is None:
            raise CommandError(
                "Zenity is required for GUI mode. On Fedora install it with "
                "`sudo dnf install zenity`."
            )

    def choose_pdf(self) -> Path | None:
        result = self._run(
            (
                "zenity",
                "--file-selection",
                "--title=Select PDF",
                "--file-filter=PDF files | *.pdf",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return Path(value) if value else None

    def print_form(
        self,
        printers: Sequence[str],
        default_printer: str | None = None,
    ) -> dict[str, str] | None:
        ordered_printers = list(printers)
        if default_printer in ordered_printers:
            ordered_printers.remove(default_printer)
            ordered_printers.insert(0, default_printer)

        printer_values = "|".join(ordered_printers)
        result = self._run(
            (
                "zenity",
                "--forms",
                "--title=Manual Duplex",
                "--text=Configure the print job",
                "--add-combo=Printer",
                f"--combo-values={printer_values}",
                "--add-combo=Paper",
                "--combo-values=a4|letter|legal|folio",
                "--add-combo=Orientation",
                "--combo-values=portrait|landscape",
                "--add-combo=Pages per side",
                "--combo-values=1|2",
                "--add-combo=Quality",
                "--combo-values=normal|draft|high",
                "--add-combo=Color",
                "--combo-values=color|monochrome",
                "--add-combo=Preview",
                "--combo-values=yes|no",
                "--separator=|",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None

        values = result.stdout.rstrip("\n").split("|")
        if len(values) != 7:
            raise CommandError("Zenity returned an unexpected print configuration.")
        keys = (
            "printer",
            "paper",
            "orientation",
            "pages_per_side",
            "quality",
            "color",
            "preview",
        )
        return dict(zip(keys, values, strict=True))

    def preview(self, pdf: Path) -> bool:
        opener = shutil.which("xdg-open")
        if opener is None:
            raise CommandError("xdg-open is required for preview mode.")
        subprocess.Popen(
            [opener, str(pdf)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return self.question(
            "Preview",
            "Review the prepared PDF in your document viewer.\n\n"
            "Continue with printing?",
            ok_label="Print",
            cancel_label="Cancel",
        )

    def confirm_refeed(self, instruction: str, sheet_count: int) -> bool:
        return self.question(
            "Reinsert paper",
            f"The first pass is complete ({sheet_count} sheet(s)).\n\n"
            f"{instruction}\n\n"
            "Only continue after the full first pass has finished and the stack "
            "has been reinserted.",
            ok_label="Print backs",
            cancel_label="Cancel",
        )

    def info(self, title: str, text: str) -> None:
        self._run(("zenity", "--info", f"--title={title}", f"--text={text}"))

    def error(self, title: str, text: str) -> None:
        self._run(
            ("zenity", "--error", f"--title={title}", f"--text={text}"),
            check=False,
        )

    def question(
        self,
        title: str,
        text: str,
        *,
        ok_label: str = "OK",
        cancel_label: str = "Cancel",
    ) -> bool:
        result = self._run(
            (
                "zenity",
                "--question",
                f"--title={title}",
                f"--text={text}",
                f"--ok-label={ok_label}",
                f"--cancel-label={cancel_label}",
            ),
            check=False,
        )
        return result.returncode == 0

    @staticmethod
    def _run(
        args: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise CommandError(f"Zenity failed: {detail}")
        return result
