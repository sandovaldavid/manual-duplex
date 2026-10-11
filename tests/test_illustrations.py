import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from manual_duplex.illustrations import print_plan_svg, refeed_svg
from manual_duplex.models import (
    BackOrder,
    FeedEdge,
    PassOrder,
    PrintedFace,
    PrinterProfile,
)
from manual_duplex.ui import Zenity

SVG_NS = "{http://www.w3.org/2000/svg}"


@pytest.mark.parametrize(("pages_per_side", "orientation"), [
    (1, "portrait"),
    (1, "landscape"),
    (2, "portrait"),
    (2, "landscape"),
    (4, "portrait"),
    (4, "landscape"),
])
def test_print_plan_is_actual_svg_and_dynamic(
    pages_per_side: int, orientation: str
) -> None:
    pages = pages_per_side * 2 + 1
    svg = print_plan_svg(
        source_name="guia&clase.pdf",
        printer="Brother<DCP-T310>",
        page_count=pages,
        pages_per_side=pages_per_side,
        orientation=orientation,
        pass_order=PassOrder.BACKS_FIRST,
    )
    root = ET.fromstring(svg)

    assert root.tag == f"{SVG_NS}svg"
    content = " ".join(text.text or "" for text in root.iter(f"{SVG_NS}text"))
    assert "guia&clase.pdf" in content
    assert "Brother<DCP-T310>" in content
    assert "Primera pasada: reversos" in content
    assert "Segunda pasada: frentes" in content
    assert "HOJA 2" in content
    assert "Vacío" in content
    assert "Esquema de páginas" in content


@pytest.mark.parametrize("pages_per_side", [1, 2, 4])
def test_single_side_diagram_never_invents_a_second_pass(pages_per_side: int) -> None:
    svg = print_plan_svg(
        source_name="una.pdf",
        printer="Brother",
        page_count=pages_per_side,
        pages_per_side=pages_per_side,
        orientation="portrait",
        pass_order=PassOrder.BACKS_FIRST,
    )
    ET.fromstring(svg)
    assert "Una sola pasada: no necesitas reinsertar papel." in svg
    assert "Segunda pasada" not in svg


@pytest.mark.parametrize(("face", "edge", "visible", "feed_edge"), [
    (PrintedFace.UP, FeedEdge.TOP, "IMPRESIÓN VISIBLE", "BORDE SUPERIOR"),
    (PrintedFace.UP, FeedEdge.BOTTOM, "IMPRESIÓN VISIBLE", "BORDE INFERIOR"),
    (PrintedFace.DOWN, FeedEdge.TOP, "CARA SIN IMPRIMIR VISIBLE", "BORDE SUPERIOR"),
    (PrintedFace.DOWN, FeedEdge.BOTTOM, "CARA SIN IMPRIMIR VISIBLE", "BORDE INFERIOR"),
])
def test_refeed_svg_is_dynamic_for_four_calibrated_orientations(
    face: PrintedFace, edge: FeedEdge, visible: str, feed_edge: str
) -> None:
    profile = PrinterProfile(
        printer="Brother",
        back_order=BackOrder.REVERSE,
        printed_face=face,
        feed_edge=edge,
        refeed_instruction="Usar calibración validada.",
    )
    svg = refeed_svg(profile, 3)
    root = ET.fromstring(svg)
    labels = " ".join(item.text or "" for item in root.iter(f"{SVG_NS}text"))

    assert "primera pasada terminó" in labels
    assert visible in labels
    assert f"Entra: {feed_edge}" in labels
    assert "Salida ilustrativa, no calibrada." in labels
    assert "NO reordenes las hojas una por una." in labels
    assert "reintroduce" not in labels.lower() or "calibración" in labels.lower()


def test_custom_legacy_refeed_never_guesses_orientation() -> None:
    profile = PrinterProfile(
        printer="Brother",
        back_order=BackOrder.NORMAL,
        refeed_instruction="Mi instrucción: boca abajo & sin girar <ojo>.",
    )
    svg = refeed_svg(profile, 2)
    root = ET.fromstring(svg)
    labels = " ".join(item.text or "" for item in root.iter(f"{SVG_NS}text"))

    assert "ORIENTACIÓN NO VERIFICADA" in labels
    assert "Mi instrucción: boca abajo & sin girar <ojo>." in labels
    assert "Entra: BORDE" not in labels


@pytest.mark.parametrize(("result_code", "expected"), [
    (0, True),
    (1, False),
    (252, False),
])
def test_picture_dialog_confirmation_is_fail_closed_and_cleans_tmp(
    monkeypatch: pytest.MonkeyPatch,
    result_code: int,
    expected: bool,
) -> None:
    images: list[Path] = []
    arguments: list[str] = []

    monkeypatch.setattr("manual_duplex.ui.shutil.which", lambda exe: "/usr/bin/yad")
    
    def fake_run(
        args: list[str], *,
        check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        assert not check and capture_output and text
        arguments.extend(args)
        path = Path(next(item.split("=", 1)[1] for item in args if
                         item.startswith("--filename=")))
        assert path.is_file()
        assert ET.parse(path).getroot().tag == f"{SVG_NS}svg"
        images.append(path)
        return subprocess.CompletedProcess(args, result_code, "", "")

    monkeypatch.setattr("manual_duplex.ui.subprocess.run", fake_run)
    confirmed = Zenity._illustrated_question(
        print_plan_svg(
            source_name="doc.pdf",
            printer="Brother",
            page_count=2,
            pages_per_side=1,
            orientation="portrait",
            pass_order=PassOrder.FRONTS_FIRST,
        ),
        title="Preflight",
        ok_label="Continuar",
    )

    assert confirmed is expected
    assert "--picture" in arguments
    assert "--button=Cancelar:1" in arguments
    assert "--button=Continuar:0" in arguments
    assert images and not images[0].exists()


def test_picture_dialog_falls_back_if_yad_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("manual_duplex.ui.shutil.which", lambda exe: None)
    assert Zenity._illustrated_question(
        "<svg/>", title="Preflight", ok_label="Continuar"
    ) is None
