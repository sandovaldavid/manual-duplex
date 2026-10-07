import json
from pathlib import Path

from manual_duplex.config import get_profile, save_profile
from manual_duplex.models import BackOrder, PassOrder, PrinterProfile


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
