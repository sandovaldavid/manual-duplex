from pathlib import Path

import pytest

from manual_duplex.errors import CommandError
from manual_duplex.models import Quality
from manual_duplex.ui import (
    build_refeed_instruction,
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


def test_print_summary_is_human_readable() -> None:
    text = print_summary_text(
        Path("/tmp/clase.pdf"),
        "DCP-T310",
        {
            "paper": "a4",
            "orientation": "landscape",
            "pages_per_side": "2",
            "quality": "normal",
            "color": "color",
            "preview": "yes",
        },
    )

    assert "Archivo: clase.pdf" in text
    assert "Orientación: Horizontal" in text
    assert "Páginas por cara: 2 páginas por cara" in text
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
    }


def test_build_refeed_instruction_covers_other_orientation() -> None:
    assert build_refeed_instruction("up", "bottom") == (
        "Coloca el bloque con la cara ya impresa hacia arriba y "
        "el borde inferior entrando primero."
    )
