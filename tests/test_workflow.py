from pathlib import Path

from pypdf import PdfWriter

from manual_duplex.models import (
    BackOrder,
    LayoutSettings,
    PassOrder,
    PrinterProfile,
    PrintSettings,
)
from manual_duplex.workflow import print_document


class FakeCups:
    def __init__(self) -> None:
        self.submitted: list[Path] = []
        self.waited: list[str] = []

    def build_options(self, **_: object) -> dict[str, str]:
        return {"PageSize": "A4"}

    def submit(self, printer: str, pdf: Path, options: dict[str, str]) -> str:
        assert printer == "printer"
        assert options == {"PageSize": "A4"}
        self.submitted.append(pdf)
        return f"printer-{len(self.submitted)}"

    def wait_for_job(self, printer: str, job_id: str, timeout_seconds: float) -> None:
        assert printer == "printer"
        assert timeout_seconds == 900
        self.waited.append(job_id)


def _make_pdf(path: Path, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=300, height=500)
    writer.write(path)


def test_second_pass_only_starts_after_confirmation(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_pdf(source, 4)
    cups = FakeCups()
    confirmations: list[int] = []

    result = print_document(
        source=source,
        printer="printer",
        settings=PrintSettings(layout=LayoutSettings()),
        profile=PrinterProfile(
            printer="printer",
            back_order=BackOrder.REVERSE,
            refeed_instruction="Reinsert now.",
        ),
        cups=cups,  # type: ignore[arg-type]
        confirm_refeed=lambda instruction, sheets: (
            confirmations.append(sheets) or instruction == "Reinsert now."
        ),
    )

    assert [path.name for path in cups.submitted] == ["fronts.pdf", "backs.pdf"]
    assert cups.waited == ["printer-1", "printer-2"]
    assert confirmations == [2]
    assert result.back_job_id == "printer-2"


def test_single_physical_side_never_prompts_for_refeed(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_pdf(source, 1)
    cups = FakeCups()

    result = print_document(
        source=source,
        printer="printer",
        settings=PrintSettings(layout=LayoutSettings()),
        profile=PrinterProfile(
            printer="printer",
            back_order=BackOrder.NORMAL,
        ),
        cups=cups,  # type: ignore[arg-type]
        confirm_refeed=lambda _instruction, _sheets: (_ for _ in ()).throw(
            AssertionError("must not prompt")
        ),
    )

    assert len(cups.submitted) == 1
    assert result.back_job_id is None


def test_backs_first_submits_back_pass_before_fronts_for_two_up(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_pdf(source, 8)
    cups = FakeCups()

    result = print_document(
        source=source,
        printer="printer",
        settings=PrintSettings(layout=LayoutSettings(pages_per_side=2)),
        profile=PrinterProfile(
            printer="printer",
            back_order=BackOrder.REVERSE,
            pass_order=PassOrder.BACKS_FIRST,
            refeed_instruction="Reinsert now.",
        ),
        cups=cups,  # type: ignore[arg-type]
        confirm_refeed=lambda instruction, sheets: (
            instruction == "Reinsert now." and sheets == 2
        ),
    )

    assert [path.name for path in cups.submitted] == ["backs.pdf", "fronts.pdf"]
    assert cups.waited == ["printer-1", "printer-2"]
    assert result.back_job_id == "printer-1"
    assert result.front_job_id == "printer-2"
