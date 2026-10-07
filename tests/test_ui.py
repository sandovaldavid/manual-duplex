import pytest

from manual_duplex.errors import CommandError
from manual_duplex.models import Quality
from manual_duplex.ui import (
    build_refeed_instruction,
    parse_calibration_form,
    parse_print_form,
    quality_labels,
)


def test_print_form_maps_spanish_labels_to_internal_values() -> None:
    result = parse_print_form(
        (
            "A4",
            "Vertical",
            "1",
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


def test_quality_labels_only_show_supported_modes() -> None:
    assert quality_labels((Quality.NORMAL,)) == ("Normal",)
    assert quality_labels((Quality.NORMAL, Quality.HIGH)) == ("Normal", "Alta")


def test_calibration_form_requires_explicit_choices() -> None:
    with pytest.raises(CommandError):
        parse_calibration_form(
            (
                "Seleccionar...",
                "Sin giro adicional",
                "Cara impresa hacia abajo",
                "Borde superior entra primero",
            )
        )


def test_calibration_form_builds_human_refeed_instruction() -> None:
    result = parse_calibration_form(
        (
            "Imprimir reversos desde la última hoja",
            "Girar reversos 180°",
            "Cara impresa hacia abajo",
            "Borde superior entra primero",
        )
    )

    assert result == {
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
