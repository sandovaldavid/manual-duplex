from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Paper(StrEnum):
    A4 = "a4"
    LETTER = "letter"
    LEGAL = "legal"
    FOLIO = "folio"


class Orientation(StrEnum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class BackOrder(StrEnum):
    NORMAL = "normal"
    REVERSE = "reverse"


class Quality(StrEnum):
    NORMAL = "normal"
    DRAFT = "draft"
    HIGH = "high"


PAPER_POINTS: dict[Paper, tuple[float, float]] = {
    Paper.A4: (595.2756, 841.8898),
    Paper.LETTER: (612.0, 792.0),
    Paper.LEGAL: (612.0, 1008.0),
    Paper.FOLIO: (612.0, 936.0),
}

PAPER_CUPS_CANDIDATES: dict[Paper, tuple[str, ...]] = {
    Paper.A4: ("A4", "iso_a4_210x297mm"),
    Paper.LETTER: ("Letter", "na_letter_8.5x11in"),
    Paper.LEGAL: ("Legal", "na_legal_8.5x14in"),
    Paper.FOLIO: ("Folio", "na_foolscap_8.5x13in", "8.5x13"),
}


@dataclass(frozen=True, slots=True)
class LayoutSettings:
    paper: Paper = Paper.A4
    orientation: Orientation = Orientation.PORTRAIT
    pages_per_side: int = 1
    margin_pt: float = 12.0
    gutter_pt: float = 12.0

    def __post_init__(self) -> None:
        if self.pages_per_side not in (1, 2):
            raise ValueError("pages_per_side must be 1 or 2")
        if self.margin_pt < 0 or self.gutter_pt < 0:
            raise ValueError("margins cannot be negative")

    @property
    def page_size(self) -> tuple[float, float]:
        width, height = PAPER_POINTS[self.paper]
        if self.orientation is Orientation.LANDSCAPE:
            return height, width
        return width, height


@dataclass(frozen=True, slots=True)
class PrinterProfile:
    printer: str
    back_order: BackOrder
    back_rotation: int = 0
    refeed_instruction: str = (
        "Reinsert the printed stack using the orientation validated for this printer."
    )

    def __post_init__(self) -> None:
        if self.back_rotation not in (0, 180):
            raise ValueError("back_rotation must be 0 or 180")


@dataclass(frozen=True, slots=True)
class PassPlan:
    physical_sides: int
    sheet_count: int
    front_sides: tuple[int, ...]
    back_sides: tuple[int | None, ...]


@dataclass(frozen=True, slots=True)
class PrintSettings:
    layout: LayoutSettings
    quality: Quality = Quality.NORMAL
    monochrome: bool = False
    raw_cups_options: tuple[str, ...] = ()
    timeout_seconds: float = 900.0
