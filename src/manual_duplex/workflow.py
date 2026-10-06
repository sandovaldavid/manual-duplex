from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .cups import CupsClient
from .errors import ManualDuplexError
from .models import PrintSettings, PrinterProfile
from .pdf import compose_pdf, split_duplex_passes


@dataclass(frozen=True, slots=True)
class PrintResult:
    physical_sides: int
    sheet_count: int
    front_job_id: str
    back_job_id: str | None


PreviewCallback = Callable[[Path], bool]
RefedCallback = Callable[[str, int], bool]


def print_document(
    source: Path,
    printer: str,
    settings: PrintSettings,
    profile: PrinterProfile,
    *,
    cups: CupsClient | None = None,
    preview: PreviewCallback | None = None,
    confirm_refeed: RefedCallback | None = None,
) -> PrintResult:
    if not source.is_file():
        raise ManualDuplexError(f"PDF does not exist: {source}")
    if profile.printer != printer:
        raise ManualDuplexError(
            f"Profile printer {profile.printer!r} does not match selected printer {printer!r}."
        )

    cups_client = cups or CupsClient()
    options = cups_client.build_options(
        printer=printer,
        paper=settings.layout.paper,
        quality=settings.quality,
        monochrome=settings.monochrome,
        raw_options=settings.raw_cups_options,
    )

    with tempfile.TemporaryDirectory(prefix="manual-duplex-") as temp_dir:
        workdir = Path(temp_dir)
        composed = workdir / "composed.pdf"
        physical_sides = compose_pdf(source, composed, settings.layout)

        if preview is not None and not preview(composed):
            raise ManualDuplexError("Printing cancelled from preview.")

        if physical_sides == 1:
            job_id = cups_client.submit(printer, composed, options)
            cups_client.wait_for_job(printer, job_id, settings.timeout_seconds)
            return PrintResult(
                physical_sides=1,
                sheet_count=1,
                front_job_id=job_id,
                back_job_id=None,
            )

        if confirm_refeed is None:
            raise ManualDuplexError(
                "A refeed confirmation callback is required before a duplex job starts."
            )

        fronts = workdir / "fronts.pdf"
        backs = workdir / "backs.pdf"
        plan = split_duplex_passes(
            composed,
            fronts,
            backs,
            profile.back_order,
            profile.back_rotation,
        )

        front_job_id = cups_client.submit(printer, fronts, options)
        cups_client.wait_for_job(printer, front_job_id, settings.timeout_seconds)

        if not confirm_refeed(profile.refeed_instruction, plan.sheet_count):
            raise ManualDuplexError(
                "Second pass cancelled. The front sides were already printed."
            )

        back_job_id = cups_client.submit(printer, backs, options)
        cups_client.wait_for_job(printer, back_job_id, settings.timeout_seconds)

        return PrintResult(
            physical_sides=plan.physical_sides,
            sheet_count=plan.sheet_count,
            front_job_id=front_job_id,
            back_job_id=back_job_id,
        )
