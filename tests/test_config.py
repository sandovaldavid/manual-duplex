import json
from pathlib import Path

import pytest

from manual_duplex.config import get_profile, save_profile
from manual_duplex.errors import ConfigurationError
from manual_duplex.models import (
    BackOrder,
    FeedEdge,
    PassOrder,
    PrintedFace,
    PrinterProfile,
)


def test_profile_round_trip(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    profile = PrinterProfile(
        printer="Brother_DCP_T310",
        back_order=BackOrder.REVERSE,
        pass_order=PassOrder.BACKS_FIRST,
        back_rotation=180,
        refeed_instruction="Blank side down.",
    )

    save_profile(profile, config)
    loaded = get_profile("Brother_DCP_T310", config)

    assert loaded == profile


def test_legacy_profile_without_pass_order_defaults_to_fronts_first(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "printers": {
                    "Brother_DCP_T310": {
                        "back_order": "reverse",
                        "back_rotation": 0,
                        "refeed_instruction": "Blank side down.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = get_profile("Brother_DCP_T310", config)

    assert loaded is not None
    assert loaded.pass_order is PassOrder.FRONTS_FIRST



@pytest.mark.parametrize(
    ("face", "edge"),
    [
        (PrintedFace.UP, FeedEdge.TOP),
        (PrintedFace.UP, FeedEdge.BOTTOM),
        (PrintedFace.DOWN, FeedEdge.TOP),
        (PrintedFace.DOWN, FeedEdge.BOTTOM),
    ],
)
def test_reinsert_calibration_round_trip(
    tmp_path: Path, face: PrintedFace, edge: FeedEdge
) -> None:
    config = tmp_path / "config.json"
    profile = PrinterProfile(
        printer="Brother_DCP_T310",
        back_order=BackOrder.REVERSE,
        pass_order=PassOrder.BACKS_FIRST,
        refeed_instruction="Calibrated.",
        printed_face=face,
        feed_edge=edge,
    )
    save_profile(profile, config)

    loaded = get_profile("Brother_DCP_T310", config)
    assert loaded == profile
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["printers"]["Brother_DCP_T310"]["printed_face"] == face.value
    assert data["printers"]["Brother_DCP_T310"]["feed_edge"] == edge.value


def test_profile_cannot_store_partial_paper_orientation() -> None:
    with pytest.raises(ValueError, match="must be set together"):
        PrinterProfile(
            printer="printer",
            back_order=BackOrder.NORMAL,
            printed_face=PrintedFace.UP,
        )


def test_invalid_stored_paper_orientation_fails_closed(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "printers": {
                    "printer": {
                        "back_order": "normal",
                        "refeed_instruction": "Custom instruction.",
                        "printed_face": "up",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="Invalid profile"):
        get_profile("printer", config)
