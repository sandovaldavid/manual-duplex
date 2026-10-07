from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from manual_duplex.models import BackOrder, LayoutSettings, Orientation, Paper
from manual_duplex.pdf import _slots, compose_pdf, logical_page_count, split_duplex_passes


def _make_pdf(path: Path, page_count: int, width: float = 300, height: float = 500) -> None:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=width, height=height)
    writer.write(path)


def test_default_layout_uses_safe_compact_margin() -> None:
    assert LayoutSettings().margin_pt == 12.0


def test_layout_rejects_unsupported_pages_per_side() -> None:
    with pytest.raises(ValueError, match="1, 2 or 4"):
        LayoutSettings(pages_per_side=3)


def test_logical_page_count_uses_validated_pdf_reader(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_pdf(source, 7)

    assert logical_page_count(source) == 7


def test_compose_one_up_preserves_side_count_and_target_size(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _make_pdf(source, 3)

    side_count = compose_pdf(
        source,
        output,
        LayoutSettings(paper=Paper.A4, orientation=Orientation.PORTRAIT),
    )

    reader = PdfReader(output)
    assert side_count == 3
    assert len(reader.pages) == 3
    assert round(float(reader.pages[0].mediabox.width), 1) == 595.3
    assert round(float(reader.pages[0].mediabox.height), 1) == 841.9


def test_landscape_a4_has_expected_physical_side_size(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _make_pdf(source, 1)

    compose_pdf(
        source,
        output,
        LayoutSettings(paper=Paper.A4, orientation=Orientation.LANDSCAPE),
    )

    page = PdfReader(output).pages[0]
    assert round(float(page.mediabox.width), 1) == 841.9
    assert round(float(page.mediabox.height), 1) == 595.3


def test_compose_two_up_groups_logical_pages_into_physical_sides(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _make_pdf(source, 5)

    side_count = compose_pdf(
        source,
        output,
        LayoutSettings(
            paper=Paper.A4,
            orientation=Orientation.LANDSCAPE,
            pages_per_side=2,
        ),
    )

    reader = PdfReader(output)
    assert side_count == 3
    assert len(reader.pages) == 3
    assert float(reader.pages[0].mediabox.width) > float(reader.pages[0].mediabox.height)


def test_compose_four_up_groups_four_logical_pages_per_physical_side(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _make_pdf(source, 10)

    side_count = compose_pdf(
        source,
        output,
        LayoutSettings(
            paper=Paper.A4,
            orientation=Orientation.PORTRAIT,
            pages_per_side=4,
        ),
    )

    reader = PdfReader(output)
    assert side_count == 3
    assert len(reader.pages) == 3
    assert round(float(reader.pages[0].mediabox.width), 1) == 595.3
    assert round(float(reader.pages[0].mediabox.height), 1) == 841.9


@pytest.mark.parametrize("orientation", (Orientation.PORTRAIT, Orientation.LANDSCAPE))
def test_four_up_slots_use_row_major_two_by_two_grid(
    orientation: Orientation,
) -> None:
    settings = LayoutSettings(
        paper=Paper.A4,
        orientation=orientation,
        pages_per_side=4,
    )

    slots = _slots(settings, 4)

    assert len(slots) == 4
    top_left, top_right, bottom_left, bottom_right = slots

    assert top_left[0] < top_right[0]
    assert bottom_left[0] < bottom_right[0]
    assert top_left[1] > bottom_left[1]
    assert top_right[1] > bottom_right[1]
    assert top_left[2:] == top_right[2:] == bottom_left[2:] == bottom_right[2:]


def test_four_up_partial_side_keeps_remaining_grid_cells_blank() -> None:
    settings = LayoutSettings(pages_per_side=4)

    slots = _slots(settings, 3)

    assert len(slots) == 3
    assert slots[0][1] == slots[1][1]
    assert slots[2][1] < slots[0][1]


def test_split_pads_odd_side_count_with_blank_back(tmp_path: Path) -> None:
    composed = tmp_path / "composed.pdf"
    fronts = tmp_path / "fronts.pdf"
    backs = tmp_path / "backs.pdf"
    _make_pdf(composed, 3)

    plan = split_duplex_passes(
        composed,
        fronts,
        backs,
        back_order=BackOrder.NORMAL,
    )

    assert plan.physical_sides == 3
    assert plan.sheet_count == 2
    assert plan.front_sides == (1, 3)
    assert plan.back_sides == (2, None)
    assert len(PdfReader(fronts).pages) == 2
    assert len(PdfReader(backs).pages) == 2


def test_split_reverse_order_moves_blank_with_unmatched_sheet(tmp_path: Path) -> None:
    composed = tmp_path / "composed.pdf"
    fronts = tmp_path / "fronts.pdf"
    backs = tmp_path / "backs.pdf"
    _make_pdf(composed, 5)

    plan = split_duplex_passes(
        composed,
        fronts,
        backs,
        back_order=BackOrder.REVERSE,
    )

    assert plan.front_sides == (1, 3, 5)
    assert plan.back_sides == (None, 4, 2)


def test_split_can_rotate_back_pages(tmp_path: Path) -> None:
    composed = tmp_path / "composed.pdf"
    fronts = tmp_path / "fronts.pdf"
    backs = tmp_path / "backs.pdf"
    _make_pdf(composed, 2)

    split_duplex_passes(
        composed,
        fronts,
        backs,
        back_order=BackOrder.NORMAL,
        back_rotation=180,
    )

    back_page = PdfReader(backs).pages[0]
    assert back_page.rotation == 180
