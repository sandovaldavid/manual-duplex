import pytest

from manual_duplex.cups import (
    _resolve_media,
    _resolve_monochrome,
    _resolve_quality,
    parse_capabilities,
    parse_job_id,
)
from manual_duplex.errors import ConfigurationError
from manual_duplex.models import Paper, Quality


def test_parse_capabilities_strips_default_marker() -> None:
    parsed = parse_capabilities(
        """
PageSize/Media Size: Letter Legal *A4 Folio
ColorModel/Color Model: *RGB Gray
cupsPrintQuality/Print Quality: Draft *Normal High
"""
    )

    assert parsed["PageSize"] == ("Letter", "Legal", "A4", "Folio")
    assert parsed["ColorModel"] == ("RGB", "Gray")
    assert parsed["cupsPrintQuality"] == ("Draft", "Normal", "High")


def test_parse_job_id() -> None:
    assert parse_job_id("request id is Brother_DCP_T310-42 (1 file(s))") == (
        "Brother_DCP_T310-42"
    )


def test_resolve_folio_uses_driver_choice() -> None:
    option, value = _resolve_media(
        {"PageSize": ("A4", "Folio", "Legal")},
        Paper.FOLIO,
    )
    assert (option, value) == ("PageSize", "Folio")


def test_resolve_media_fails_when_driver_exposes_option_but_not_requested_size() -> None:
    with pytest.raises(ConfigurationError):
        _resolve_media({"PageSize": ("A4", "Letter")}, Paper.FOLIO)


def test_quality_is_capability_driven() -> None:
    option, value = _resolve_quality(
        {"cupsPrintQuality": ("Draft", "Normal", "High")},
        Quality.HIGH,
    )
    assert (option, value) == ("cupsPrintQuality", "High")


def test_monochrome_uses_all_recognized_driver_options() -> None:
    result = _resolve_monochrome(
        {
            "ColorModel": ("Color", "Gray"),
            "BRMonoColor": ("Color", "Mono"),
        }
    )
    assert result == {"ColorModel": "Gray", "BRMonoColor": "Mono"}
