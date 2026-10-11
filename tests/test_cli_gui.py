from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from pypdf import PdfWriter

from manual_duplex import cli
from manual_duplex.models import BackOrder, PrinterProfile, Quality
from manual_duplex.workflow import PrintResult


@pytest.mark.parametrize("pages_per_side", (1, 2, 4))
@pytest.mark.parametrize("accepted", (True, False))
def test_gui_always_confirms_print_plan_before_submitting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pages_per_side: int,
    accepted: bool,
) -> None:
    source = tmp_path / "sample.pdf"
    writer = PdfWriter()
    for _ in range(pages_per_side * 2):
        writer.add_blank_page(width=250, height=350)
    writer.write(source)

    events: list[str] = []
    printer = "Brother_DCP_T310"
    profile = PrinterProfile(printer=printer, back_order=BackOrder.REVERSE)

    class FakeCups:
        def list_printers(self) -> tuple[str, ...]:
            return (printer,)

        def supported_qualities(self, chosen_printer: str) -> tuple[Quality, ...]:
            assert chosen_printer == printer
            return (Quality.NORMAL,)

    class FakeUI:
        def print_form(
            self, chosen_printer: str, qualities: tuple[Quality, ...]
        ) -> dict[str, str]:
            assert chosen_printer == printer
            assert qualities == (Quality.NORMAL,)
            return {
                "printer": printer,
                "paper": "a4",
                "orientation": "portrait",
                "pages_per_side": str(pages_per_side),
                "quality": "normal",
                "color": "color",
                "preview": "no",
            }

        def confirm_layout_preview(
            self,
            chosen_source: Path,
            chosen_printer: str,
            form: dict[str, str],
            page_count: int,
            pass_order: object,
        ) -> bool:
            assert chosen_source == source
            assert chosen_printer == printer
            assert form["pages_per_side"] == str(pages_per_side)
            assert page_count == pages_per_side * 2
            assert pass_order == profile.pass_order
            events.append("confirm")
            return accepted

        def print_error(self, detail: str) -> None:
            raise AssertionError(detail)

        def print_complete(self, sheet_count: int, physical_sides: int) -> None:
            assert sheet_count == 1
            assert physical_sides == 2
            events.append("done")

    def fake_print_document(**kwargs: object) -> PrintResult:
        assert kwargs["source"] == source
        assert kwargs["printer"] == printer
        assert kwargs["profile"] == profile
        events.append("print")
        return PrintResult(
            physical_sides=2,
            sheet_count=1,
            front_job_id="printer-1",
            back_job_id="printer-2",
        )

    monkeypatch.setattr(cli, "Zenity", FakeUI)
    monkeypatch.setattr(cli, "CupsClient", FakeCups)
    monkeypatch.setattr(cli, "get_profile", lambda _printer: profile)
    monkeypatch.setattr(cli, "print_document", fake_print_document)

    result = cli._cmd_gui(
        argparse.Namespace(file=source, configure=False, troubleshoot=False)
    )

    assert result == 0
    assert events == (["confirm", "print", "done"] if accepted else ["confirm"])
