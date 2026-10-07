import subprocess
from collections.abc import Mapping, Sequence

import pytest

from manual_duplex.cups import (
    CupsClient,
    _resolve_media,
    _resolve_monochrome,
    _resolve_quality,
    parse_capabilities,
    parse_job_id,
    supported_qualities,
)
from manual_duplex.errors import CommandError, ConfigurationError
from manual_duplex.models import Orientation, Paper, Quality


class CapabilityCups(CupsClient):
    def __init__(self, capabilities: Mapping[str, Sequence[str]]) -> None:
        super().__init__()
        self._capabilities = {
            key: tuple(values)
            for key, values in capabilities.items()
        }

    def capabilities(self, printer: str) -> dict[str, tuple[str, ...]]:
        assert printer == "printer"
        return dict(self._capabilities)


class FailingStatusCups(CupsClient):
    def _run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del check
        return subprocess.CompletedProcess(
            list(args),
            returncode=1,
            stdout="",
            stderr="scheduler unavailable",
        )


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


def test_supported_qualities_hides_unmappable_driver_modes() -> None:
    assert supported_qualities(
        {
            "PageSize": ("A4", "Letter", "Legal", "Folio"),
            "BRMonoColor": ("Color", "Mono"),
        }
    ) == (Quality.NORMAL,)


def test_supported_qualities_exposes_mappable_modes() -> None:
    assert supported_qualities(
        {"cupsPrintQuality": ("Draft", "Normal", "High")}
    ) == (Quality.NORMAL, Quality.DRAFT, Quality.HIGH)


@pytest.mark.parametrize(
    ("orientation", "expected"),
    (
        (Orientation.PORTRAIT, "3"),
        (Orientation.LANDSCAPE, "4"),
    ),
)
def test_build_options_sends_explicit_cups_orientation(
    orientation: Orientation,
    expected: str,
) -> None:
    cups = CapabilityCups({"PageSize": ("A4",)})

    options = cups.build_options(
        printer="printer",
        paper=Paper.A4,
        orientation=orientation,
        quality=Quality.NORMAL,
        monochrome=False,
    )

    assert options == {
        "PageSize": "A4",
        "orientation-requested": expected,
    }


def test_monochrome_uses_all_recognized_driver_options() -> None:
    result = _resolve_monochrome(
        {
            "ColorModel": ("Color", "Gray"),
            "BRMonoColor": ("Color", "Mono"),
        }
    )
    assert result == {"ColorModel": "Gray", "BRMonoColor": "Mono"}


def test_wait_for_job_does_not_treat_lpstat_failure_as_completion() -> None:
    cups = FailingStatusCups()

    with pytest.raises(CommandError, match="scheduler unavailable"):
        cups.wait_for_job("printer", "printer-1", timeout_seconds=1)
