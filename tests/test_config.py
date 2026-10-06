from pathlib import Path

from manual_duplex.config import get_profile, save_profile
from manual_duplex.models import BackOrder, PrinterProfile


def test_profile_round_trip(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    profile = PrinterProfile(
        printer="Brother_DCP_T310",
        back_order=BackOrder.REVERSE,
        back_rotation=180,
        refeed_instruction="Blank side down.",
    )

    save_profile(profile, config)
    loaded = get_profile("Brother_DCP_T310", config)

    assert loaded == profile
