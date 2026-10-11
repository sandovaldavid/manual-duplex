import subprocess
from pathlib import Path

import pytest

from manual_duplex.errors import CommandError
from manual_duplex.models import (
    BackOrder,
    FeedEdge,
    PassOrder,
    PrintedFace,
    PrinterProfile,
    Quality,
)
from manual_duplex.refeed import refeed_guide_text
from manual_duplex.ui import (
    Zenity,
    build_refeed_instruction,
    layout_preview_text,
    parse_calibration_form,
    parse_print_form,
    print_summary_text,
    quality_labels,
)


def test_print_form_maps_spanish_labels_to_internal_values() -> None:
    result = parse_print_form(
        (
            "A4",
            "Vertical",
            "1 página por cara",
            "Normal",
            "Color",
            "No",
        ),
        printer="Brother_DCP_T310",
    )

    assert result == {
        "printer": "Brother_DCP_T310",
        "paper": "a4",
        "orientation": "portrait",
        "pages_per_side": "1",
        "quality": "normal",
        "color": "color",
        "preview": "no",
    }


def test_print_form_maps_two_pages_per_side() -> None:
    result = parse_print_form(
        (
            "A4",
            "Horizontal",
            "2 páginas por cara",
            "Normal",
            "Blanco y negro",
            "Sí",
        ),
        printer="Brother_DCP_T310",
    )

    assert result["orientation"] == "landscape"
    assert result["pages_per_side"] == "2"
    assert result["color"] == "monochrome"
    assert result["preview"] == "yes"


def test_print_form_maps_four_pages_per_side() -> None:
    result = parse_print_form(
        (
            "A4",
            "Vertical",
            "4 páginas por cara (8 por hoja)",
            "Normal",
            "Color",
            "Sí",
        ),
        printer="Brother_DCP_T310",
    )

    assert result["pages_per_side"] == "4"
    assert result["preview"] == "yes"


def test_print_summary_is_human_readable() -> None:
    text = print_summary_text(
        Path("/tmp/clase.pdf"),
        "DCP-T310",
        {
            "paper": "a4",
            "orientation": "landscape",
            "pages_per_side": "4",
            "quality": "normal",
            "color": "color",
            "preview": "yes",
        },
    )

    assert "Archivo: clase.pdf" in text
    assert "Orientación: Horizontal" in text
    assert "Páginas por cara: 4 páginas por cara (8 por hoja)" in text
    assert "Vista previa: Sí" in text


def test_quality_labels_only_show_supported_modes() -> None:
    assert quality_labels((Quality.NORMAL,)) == ("Normal",)
    assert quality_labels((Quality.NORMAL, Quality.HIGH)) == ("Normal", "Alta")


def test_calibration_form_requires_explicit_choices() -> None:
    with pytest.raises(CommandError):
        parse_calibration_form(
            (
                "Seleccionar...",
                "Imprimir reversos desde la última hoja",
                "Sin giro adicional",
                "Cara impresa hacia abajo",
                "Borde superior entra primero",
            )
        )


def test_calibration_form_builds_human_refeed_instruction() -> None:
    result = parse_calibration_form(
        (
            "Reversos primero",
            "Imprimir reversos desde la última hoja",
            "Girar reversos 180°",
            "Cara impresa hacia abajo",
            "Borde superior entra primero",
        )
    )

    assert result == {
        "pass_order": "backs_first",
        "back_order": "reverse",
        "back_rotation": 180,
        "refeed_instruction": (
            "Coloca el bloque con la cara ya impresa hacia abajo y "
            "el borde superior entrando primero."
        ),
        "printed_face": "down",
        "feed_edge": "top",
    }


def test_build_refeed_instruction_covers_other_orientation() -> None:
    assert build_refeed_instruction("up", "bottom") == (
        "Coloca el bloque con la cara ya impresa hacia arriba y "
        "el borde inferior entrando primero."
    )


def test_two_up_landscape_preview_shows_front_back_and_pass_order() -> None:
    text = layout_preview_text(
        page_count=8,
        pages_per_side=2,
        orientation="landscape",
        pass_order=PassOrder.BACKS_FIRST,
    )

    assert "Primera pasada: reversos." in text
    assert "Segunda pasada: caras delanteras." in text
    assert "HOJA 1" in text
    assert "│    1    │    2    │" in text
    assert "│    3    │    4    │" in text
    assert "HOJA 2" in text
    assert "│    5    │    6    │" in text
    assert "│    7    │    8    │" in text


def test_two_up_portrait_preview_uses_vertical_stack() -> None:
    text = layout_preview_text(
        page_count=4,
        pages_per_side=2,
        orientation="portrait",
        pass_order=PassOrder.FRONTS_FIRST,
    )

    assert "Primera pasada: caras delanteras." in text
    assert "│    1    │\n├─────────┤\n│    2    │" in text


def test_four_up_preview_shows_two_by_two_grid_and_blank_cells() -> None:
    text = layout_preview_text(
        page_count=6,
        pages_per_side=4,
        orientation="portrait",
        pass_order=PassOrder.BACKS_FIRST,
    )

    assert "│    1    │    2    │" in text
    assert "│    3    │    4    │" in text
    assert "│    5    │    6    │" in text
    assert "│  vacío  │  vacío  │" in text


def test_layout_preview_limits_long_documents_to_three_sheets() -> None:
    text = layout_preview_text(
        page_count=40,
        pages_per_side=2,
        orientation="landscape",
        pass_order=PassOrder.BACKS_FIRST,
    )

    assert "HOJA 1" in text
    assert "HOJA 3" in text
    assert "HOJA 4" not in text
    assert "... y 7 hoja(s) más." in text



@pytest.mark.parametrize(
    ("face", "edge", "visible_text", "first_edge", "opposite_edge"),
    [
        (
            PrintedFace.UP,
            FeedEdge.TOP,
            "CARA YA IMPRESA VISIBLE",
            "BORDE SUPERIOR",
            "BORDE INFERIOR",
        ),
        (
            PrintedFace.UP,
            FeedEdge.BOTTOM,
            "CARA YA IMPRESA VISIBLE",
            "BORDE INFERIOR",
            "BORDE SUPERIOR",
        ),
        (
            PrintedFace.DOWN,
            FeedEdge.TOP,
            "CARA NO IMPRESA VISIBLE",
            "BORDE SUPERIOR",
            "BORDE INFERIOR",
        ),
        (
            PrintedFace.DOWN,
            FeedEdge.BOTTOM,
            "CARA NO IMPRESA VISIBLE",
            "BORDE INFERIOR",
            "BORDE SUPERIOR",
        ),
    ],
)


def test_refeed_guide_matches_saved_orientation(
    face: PrintedFace,
    edge: FeedEdge,
    visible_text: str,
    first_edge: str,
    opposite_edge: str,
) -> None:
    profile = PrinterProfile(
        printer="printer",
        back_order=BackOrder.REVERSE,
        pass_order=PassOrder.BACKS_FIRST,
        refeed_instruction=build_refeed_instruction(face.value, edge.value),
        printed_face=face,
        feed_edge=edge,
    )
    text = refeed_guide_text(profile, 2)

    assert "Primera pasada completada: 2 hoja(s)." in text
    assert f"{first_edge} ENTRA PRIMERO" in text
    assert f"{opposite_edge} queda hacia ti" in text
    assert visible_text in text
    assert "Mantén el bloque en el mismo orden" in text
    assert "┌──────────────────────────┐" in text


@pytest.mark.parametrize(
    ("face", "edge"),
    [
        (
            PrintedFace.UP, FeedEdge.TOP,
        ),
        (
            PrintedFace.UP, FeedEdge.BOTTOM,
        ),
        (
            PrintedFace.DOWN, FeedEdge.TOP,
        ),
        (
            PrintedFace.DOWN, FeedEdge.BOTTOM,
        ),
    ],
)
def test_old_gui_calibration_has_accurate_diagram_without_migration(
    face: PrintedFace, edge: FeedEdge
) -> None:
    profile = PrinterProfile(
        printer="printer",
        back_order=BackOrder.REVERSE,
        refeed_instruction=build_refeed_instruction(face.value, edge.value),
    )
    text = refeed_guide_text(profile, 2)
    label = "BORDE SUPERIOR" if edge is FeedEdge.TOP else "BORDE INFERIOR"

    assert f"{label} ENTRA PRIMERO" in text
    assert "No hay un dibujo verificado" not in text


def test_legacy_custom_instruction_does_not_guess_paper_orientation() -> None:
    profile = PrinterProfile(
        printer="printer",
        back_order=BackOrder.REVERSE,
        refeed_instruction="Reinsert using the orientation previously tested.",
    )
    text = refeed_guide_text(profile, 2)

    assert "No hay un dibujo verificado" in text
    assert "Reinsert using the orientation previously tested." in text
    assert "CARA YA IMPRESA VISIBLE" not in text
    assert "CARA NO IMPRESA VISIBLE" not in text


def test_visual_refeed_modal_requires_explicit_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[tuple[str, ...], str | None]] = []

    def fake_run(
        args: tuple[str, ...],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check
        captured.append((args, input_text))
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(Zenity, "_run", staticmethod(fake_run))
    monkeypatch.setattr(
        Zenity, "_illustrated_question", staticmethod(lambda *_args, **_kwargs: None)
    )
    ui = object.__new__(Zenity)
    profile = PrinterProfile(
        printer="printer",
        back_order=BackOrder.NORMAL,
        refeed_instruction=build_refeed_instruction("up", "top"),
        printed_face=PrintedFace.UP,
        feed_edge=FeedEdge.TOP,
    )
    accepted = ui.confirm_refeed(profile.refeed_instruction, 2, profile=profile)

    assert not accepted
    command, instructions = captured[0]
    assert command[1] == "--text-info"
    assert "--ok-label=Ya coloqué las hojas, continuar" in command
    assert "--cancel-label=Cancelar" in command
    assert instructions is not None
    assert "BORDE SUPERIOR ENTRA PRIMERO" in instructions


def test_visual_refeed_modal_continue_on_explicit_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        args: tuple[str, ...],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, input_text
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(Zenity, "_run", staticmethod(fake_run))
    monkeypatch.setattr(
        Zenity, "_illustrated_question", staticmethod(lambda *_args, **_kwargs: None)
    )
    ui = object.__new__(Zenity)
    profile = PrinterProfile(
        printer="printer",
        back_order=BackOrder.NORMAL,
        refeed_instruction=build_refeed_instruction("down", "bottom"),
        printed_face=PrintedFace.DOWN,
        feed_edge=FeedEdge.BOTTOM,
    )
    assert ui.confirm_refeed(profile.refeed_instruction, 2, profile=profile)



def test_one_up_preview_shows_front_back_and_one_page_per_side() -> None:
    text = layout_preview_text(
        page_count=3,
        pages_per_side=1,
        orientation="portrait",
        pass_order=PassOrder.BACKS_FIRST,
    )

    assert "VISTA ESQUEMÁTICA ANTES DE IMPRIMIR" in text
    assert "Total: 3 página(s) lógica(s) en 2 hoja(s) física(s)." in text
    assert "Primera pasada: reversos." in text
    assert "Segunda pasada: caras delanteras." in text
    assert "Frente\n┌─────────┐\n│    1    │\n└─────────┘" in text
    assert "Reverso\n┌─────────┐\n│    2    │\n└─────────┘" in text
    assert "HOJA 2" in text
    assert "│    3    │" in text
    assert "│  vacío  │" in text


@pytest.mark.parametrize("pages_per_side", [1, 2, 4])
def test_single_physical_side_preview_does_not_claim_duplex(
    pages_per_side: int,
) -> None:
    text = layout_preview_text(
        page_count=pages_per_side,
        pages_per_side=pages_per_side,
        orientation="landscape",
        pass_order=PassOrder.BACKS_FIRST,
    )

    assert "Una sola pasada: únicamente la cara delantera." in text
    assert "No será necesario volver a colocar las hojas." in text
    assert "Primera pasada: reversos." not in text
    assert "Segunda pasada:" not in text
    assert "HOJA 1" in text
    assert "Reverso" in text
    assert "vacío" in text
    assert "Después de la primera pasada se mostrará" not in text


@pytest.mark.parametrize("pages_per_side", [1, 2, 4])
def test_layout_preview_dialog_used_for_all_print_modes(
    monkeypatch: pytest.MonkeyPatch,
    pages_per_side: int,
) -> None:
    captured: list[tuple[tuple[str, ...], str | None]] = []

    def fake_run(
        args: tuple[str, ...],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check
        captured.append((args, input_text))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(Zenity, "_run", staticmethod(fake_run))
    monkeypatch.setattr(
        Zenity, "_illustrated_question", staticmethod(lambda *_args, **_kwargs: None)
    )
    ui = object.__new__(Zenity)
    form = {
        "paper": "a4",
        "orientation": "portrait",
        "pages_per_side": str(pages_per_side),
        "quality": "normal",
        "color": "color",
        "preview": "no",
    }

    assert ui.confirm_layout_preview(
        Path("/tmp/guia.pdf"), "Brother_DCP_T310", form,
        page_count=pages_per_side * 2,
        pass_order=PassOrder.BACKS_FIRST,
    )
    assert len(captured) == 1
    command, preview_text = captured[0]
    assert "--text-info" in command
    assert "--cancel-label=Cancelar" in command
    assert "--ok-label=Se ve bien, imprimir" in command
    assert preview_text is not None
    assert "Archivo: guia.pdf" in preview_text
    assert "Frente" in preview_text
    assert "Reverso" in preview_text
    assert "Primera pasada: reversos." in preview_text
