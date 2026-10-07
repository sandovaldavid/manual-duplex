from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pypdf import PageObject, PdfReader, PdfWriter

from .errors import ManualDuplexError
from .models import BackOrder, LayoutSettings, PassPlan


def compose_pdf(
    source: Path,
    destination: Path,
    settings: LayoutSettings,
) -> int:
    """Normalize source pages into physical printable sides.

    The output PDF already has the requested paper size and orientation.
    Multiple logical pages are fitted into each physical side before the
    document is split into duplex passes.
    """

    try:
        reader = PdfReader(str(source))
    except Exception as exc:
        raise ManualDuplexError(f"Cannot read PDF: {source}") from exc

    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise ManualDuplexError(
                "Encrypted PDFs are not supported without a password."
            ) from exc
        if not unlocked:
            raise ManualDuplexError("Encrypted PDFs are not supported without a password.")

    if not reader.pages:
        raise ManualDuplexError("The PDF has no pages.")

    width, height = settings.page_size
    writer = PdfWriter()
    pages_per_side = settings.pages_per_side

    for offset in range(0, len(reader.pages), pages_per_side):
        destination_page = writer.add_blank_page(width=width, height=height)
        source_pages = reader.pages[offset : offset + pages_per_side]
        slots = _slots(settings, len(source_pages))
        for source_page, slot in zip(source_pages, slots, strict=True):
            _normalize_rotation(source_page)
            _merge_page_into_slot(destination_page, source_page, slot)

    destination.parent.mkdir(parents=True, exist_ok=True)
    writer.write(str(destination))
    return len(writer.pages)


def split_duplex_passes(
    composed: Path,
    fronts: Path,
    backs: Path,
    back_order: BackOrder,
    back_rotation: int = 0,
) -> PassPlan:
    """Split physical sides into first-pass fronts and second-pass backs.

    When the physical side count is odd, the back pass receives an explicit
    blank page. That blank consumes the unmatched sheet during the second pass
    and keeps the paper stack aligned.
    """

    if back_rotation not in (0, 180):
        raise ValueError("back_rotation must be 0 or 180")

    reader = PdfReader(str(composed))
    side_count = len(reader.pages)
    if side_count == 0:
        raise ManualDuplexError("The prepared PDF has no physical sides.")

    pairs: list[tuple[int, int | None]] = []
    for front_index in range(0, side_count, 2):
        back_index = front_index + 1 if front_index + 1 < side_count else None
        pairs.append((front_index, back_index))

    front_indices = [front for front, _ in pairs]
    back_indices = [back for _, back in pairs]
    if back_order is BackOrder.REVERSE:
        back_indices.reverse()

    fronts.parent.mkdir(parents=True, exist_ok=True)
    backs.parent.mkdir(parents=True, exist_ok=True)
    _write_pass(reader, front_indices, fronts, rotation=0)
    _write_pass(reader, back_indices, backs, rotation=back_rotation)

    return PassPlan(
        physical_sides=side_count,
        sheet_count=len(pairs),
        front_sides=tuple(index + 1 for index in front_indices),
        back_sides=tuple(None if index is None else index + 1 for index in back_indices),
    )


def _slots(
    settings: LayoutSettings,
    source_page_count: int,
) -> list[tuple[float, float, float, float]]:
    width, height = settings.page_size
    margin = settings.margin_pt
    gutter = settings.gutter_pt

    usable_width = width - (2 * margin)
    usable_height = height - (2 * margin)
    if usable_width <= 0 or usable_height <= 0:
        raise ManualDuplexError("Margins leave no printable area.")

    if settings.pages_per_side == 1:
        return [(margin, margin, usable_width, usable_height)]

    if settings.pages_per_side == 4:
        slot_width = (usable_width - gutter) / 2
        slot_height = (usable_height - gutter) / 2
        if slot_width <= 0 or slot_height <= 0:
            raise ManualDuplexError("Gutter leaves no printable area.")

        right_x = margin + slot_width + gutter
        top_y = margin + slot_height + gutter
        slots = [
            (margin, top_y, slot_width, slot_height),
            (right_x, top_y, slot_width, slot_height),
            (margin, margin, slot_width, slot_height),
            (right_x, margin, slot_width, slot_height),
        ]
        return slots[:source_page_count]

    if settings.orientation.value == "landscape":
        slot_width = (usable_width - gutter) / 2
        if slot_width <= 0:
            raise ManualDuplexError("Gutter leaves no printable area.")
        slots = [
            (margin, margin, slot_width, usable_height),
            (margin + slot_width + gutter, margin, slot_width, usable_height),
        ]
    else:
        slot_height = (usable_height - gutter) / 2
        if slot_height <= 0:
            raise ManualDuplexError("Gutter leaves no printable area.")
        slots = [
            (margin, margin + slot_height + gutter, usable_width, slot_height),
            (margin, margin, usable_width, slot_height),
        ]

    return slots[:source_page_count]


def _normalize_rotation(page: PageObject) -> None:
    if page.rotation:
        page.transfer_rotation_to_content()


def _merge_page_into_slot(
    destination: PageObject,
    source: PageObject,
    slot: tuple[float, float, float, float],
) -> None:
    x, y, slot_width, slot_height = slot
    box = source.cropbox
    source_width = float(box.width)
    source_height = float(box.height)

    if source_width <= 0 or source_height <= 0:
        raise ManualDuplexError("A source page has invalid dimensions.")

    scale = min(slot_width / source_width, slot_height / source_height)
    rendered_width = source_width * scale
    rendered_height = source_height * scale

    translate_x = x + (slot_width - rendered_width) / 2 - float(box.left) * scale
    translate_y = y + (slot_height - rendered_height) / 2 - float(box.bottom) * scale

    destination.merge_transformed_page(
        source,
        (scale, 0, 0, scale, translate_x, translate_y),
        expand=False,
    )


def _write_pass(
    reader: PdfReader,
    indices: Iterable[int | None],
    destination: Path,
    rotation: int,
) -> None:
    writer = PdfWriter()
    reference_page = reader.pages[0]
    width = float(reference_page.mediabox.width)
    height = float(reference_page.mediabox.height)

    for index in indices:
        if index is None:
            writer.add_blank_page(width=width, height=height)
            continue

        added_page = writer.add_page(reader.pages[index])
        if rotation:
            added_page.rotate(rotation)

    writer.write(str(destination))
