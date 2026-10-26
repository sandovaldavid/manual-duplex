from __future__ import annotations

from html import escape

from .models import FeedEdge, PassOrder, PrintedFace, PrinterProfile
from .refeed import resolve_refeed_orientation

WIDTH = 1040

# All output is vector artwork. The paper path is illustrative, never an
# assumed mechanical layout for any particular Brother/CUPS printer.


def _text(
    x: int,
    y: int,
    value: str,
    *,
    size: int = 18,
    weight: int = 400,
    color: str = "#253247",
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}"'
        f' fill="{color}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def _rect(
    x: int, y: int, width: int, height: int, *,
    fill: str = "#ffffff", stroke: str = "#cbd5e1", radius: int = 12,
) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}"'
        f' rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    )


def _svg(content: list[str], *, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}"'
        ' role="img">'
        + _rect(0, 0, WIDTH, height, fill="#f4f7fb", stroke="#f4f7fb", radius=0)
        + "".join(content)
        + "</svg>"
    )


def _page_grid(
    x: int, y: int, pages: tuple[int | None, ...], *,
    pages_per_side: int, orientation: str,
) -> list[str]:
    grid_width = 220 if orientation == "landscape" else 145
    grid_height = 138 if orientation == "landscape" else 165
    columns = 2 if pages_per_side == 4 or (
        pages_per_side == 2 and orientation == "landscape"
    ) else 1
    rows = (pages_per_side + columns - 1) // columns
    cell_width = grid_width // columns
    cell_height = grid_height // rows
    items = [_rect(x, y, grid_width, grid_height, radius=5)]
    for index, page in enumerate(pages):
        col, row = index % columns, index // columns
        left, top = x + col * cell_width, y + row * cell_height
        items.append(
            _rect(
                left + 5, top + 5, cell_width - 10, cell_height - 10,
                fill="#e8f1fc" if page is not None else "#f0f1f4",
                stroke="#a1b7d0" if page is not None else "#cbd5e1",
                radius=4,
            )
        )
        items.append(
            _text(
                left + cell_width // 2, top + cell_height // 2 + 6,
                str(page) if page is not None else "Vacío",
                size=24 if page is not None else 15,
                weight=700 if page is not None else 400,
                anchor="middle",
            )
        )
    return items


def print_plan_svg(
    *,
    source_name: str,
    printer: str,
    page_count: int,
    pages_per_side: int,
    orientation: str,
    pass_order: PassOrder,
) -> str:
    """Illustrate logical pages on front/back before the first CUPS submission."""
    if page_count < 1 or pages_per_side not in (1, 2, 4):
        raise ValueError("invalid page count or pages-per-side")
    if orientation not in ("portrait", "landscape"):
        raise ValueError("invalid print orientation")

    per_sheet = 2 * pages_per_side
    sheets = (page_count + per_sheet - 1) // per_sheet
    physical_sides = (page_count + pages_per_side - 1) // pages_per_side
    visible_sheets = min(sheets, 3)
    height = 230 + 226 * visible_sheets + 95

    parts = [
        _text(44, 58, "ANTES DE IMPRIMIR", size=31, weight=700),
        _text(44, 96, f"Documento: {source_name}", size=18),
        _text(44, 127, f"Impresora: {printer}", size=18),
        _text(
            44, 158,
            f"{page_count} páginas • {sheets} hojas • "
            f"{pages_per_side} página(s) por cara",
            size=18,
        ),
        _rect(36, 180, 968, 54, fill="#e0efff", stroke="#b9d8fc"),
    ]
    if physical_sides == 1:
        description = "Una sola pasada: no necesitas reinsertar papel."
    else:
        first = "reversos" if pass_order is PassOrder.BACKS_FIRST else "frentes"
        second = "frentes" if pass_order is PassOrder.BACKS_FIRST else "reversos"
        description = f"Primera pasada: {first}.  Segunda pasada: {second}."
    parts.append(_text(54, 215, description, size=19, weight=700))

    for sheet_index in range(visible_sheets):
        y = 250 + sheet_index * 226
        first_number = sheet_index * per_sheet + 1
        front = tuple(
            value if value <= page_count else None
            for value in range(first_number, first_number + pages_per_side)
        )
        back = tuple(
            value if value <= page_count else None
            for value in range(
                first_number + pages_per_side, first_number + per_sheet
            )
        )
        parts.append(_rect(36, y, 968, 208))
        parts.append(_text(60, y + 35, f"HOJA {sheet_index + 1}", size=20, weight=700))
        for side_index, (side_name, pages) in enumerate(
            (("FRENTE", front), ("REVERSO", back))
        ):
            base_x = 70 + side_index * 475
            parts.append(_text(base_x, y + 66, side_name, size=16, weight=700))
            parts.extend(
                _page_grid(
                    base_x + 180, y + 28, pages,
                    pages_per_side=pages_per_side, orientation=orientation,
                )
            )
    footer = 250 + 226 * visible_sheets + 33
    if sheets > visible_sheets:
        parts.append(
            _text(46, footer, f"Y {sheets - visible_sheets} hoja(s) más.", size=18)
        )
        footer += 30
    parts.append(
        _text(
            46, footer + 30,
            "Esquema de páginas, no una fotografía ni una instrucción para girar hojas.",
            size=16, color="#526277",
        )
    )
    return _svg(parts, height=height)


def _printer(x: int, y: int) -> list[str]:
    """Generic printer icon, deliberately not a DCP-T310 paper-path claim."""
    return [
        _rect(x, y + 65, 300, 145, fill="#b8cadb", stroke="#6686a5"),
        _rect(x + 32, y + 12, 237, 92, fill="#ffffff", stroke="#7699b7"),
        _rect(x + 65, y + 160, 173, 20, fill="#344b63", stroke="#344b63"),
        _rect(x + 245, y + 100, 18, 13, fill="#4fd4aa", stroke="#2b9977"),
    ]


def refeed_svg(profile: PrinterProfile, sheet_count: int) -> str:
    """Illustrate an unverified exit and a calibrated incoming stack."""
    if sheet_count < 1:
        raise ValueError("sheet_count must be positive")

    orientation = resolve_refeed_orientation(profile)
    parts = [
        _text(36, 57, "CÓMO VOLVER A COLOCAR EL PAPEL", size=29, weight=700),
        _text(
            36, 94,
            f"La primera pasada terminó. Retira el bloque completo ({sheet_count} hojas).",
            size=18,
        ),
        _rect(30, 120, 475, 484),
        _rect(535, 120, 475, 484),
        _text(52, 162, "1. RECOGER DE LA SALIDA", size=20, weight=700),
        _text(554, 162, "2. INTRODUCIR EL BLOQUE", size=20, weight=700),
        *_printer(108, 210),
        '<path d="M 253 412 L 253 484" stroke="#268fce" '
        'stroke-width="8" stroke-linecap="round"/>',
        '<path d="M 236 469 L 253 489 L 270 469" stroke="#268fce" '
        'stroke-width="8" stroke-linejoin="round" fill="none"/>',
        _rect(182, 445, 142, 68, fill="#ffffff", stroke="#2b8ac4", radius=3),
        _text(252, 468, "PAPEL", size=16, weight=700, anchor="middle"),
        _text(252, 497, "SALIENTE", size=14, anchor="middle"),
        _text(54, 552, "Salida ilustrativa, no calibrada.", size=16, weight=700),
        _text(54, 577, "Observa cómo sale realmente el papel.", size=15),
    ]

    if orientation is None:
        parts.extend(
            [
                _rect(
                    570, 206, 405, 318, fill="#fff5e2", stroke="#e0b25b",
                ),
                _text(590, 248, "ORIENTACIÓN NO VERIFICADA", size=19, weight=700),
                _text(590, 295, "No podemos dibujar el giro correcto.", size=16),
                _text(590, 327, "Utiliza la instrucción que guardaste", size=16),
                _text(590, 354, "o vuelve a configurar la impresora.", size=16),
            ]
        )
    else:
        face, edge = orientation
        face_text = (
            "CARA IMPRESA HACIA ARRIBA"
            if face is PrintedFace.UP
            else "CARA IMPRESA HACIA ABAJO"
        )
        visible_text = (
            "IMPRESIÓN VISIBLE"
            if face is PrintedFace.UP
            else "CARA SIN IMPRIMIR VISIBLE"
        )
        first_edge = (
            "BORDE SUPERIOR"
            if edge is FeedEdge.TOP
            else "BORDE INFERIOR"
        )
        other_edge = (
            "BORDE INFERIOR"
            if edge is FeedEdge.TOP
            else "BORDE SUPERIOR"
        )
        parts.extend(
            [
                _rect(595, 231, 350, 72, fill="#bed2e3", stroke="#7293ae"),
                _text(770, 270, "ENTRADA A IMPRESORA", size=17, weight=700,
                      anchor="middle"),
                '<path d="M 770 461 L 770 331" stroke="#169769" '
                'stroke-width="9" stroke-linecap="round"/>',
                '<path d="M 747 353 L 770 327 L 793 353" stroke="#169769" '
                'stroke-width="9" stroke-linejoin="round" fill="none"/>',
                _rect(628, 414, 285, 120, fill="#e5f0fe", stroke="#4286c9"),
                _text(770, 455, visible_text, size=15, weight=700,
                      anchor="middle"),
                _text(770, 483, "BLOQUE COMPLETO", size=16, anchor="middle"),
                _text(770, 389, f"Entra: {first_edge}", size=17, weight=700,
                      anchor="middle"),
                _text(770, 560, f"Hacia ti: {other_edge}", size=16,
                      anchor="middle"),
                _text(770, 587, face_text, size=16, weight=700,
                      anchor="middle"),
            ]
        )

    parts.extend(
        [
            _rect(30, 622, 980, 110, fill="#fff4dc", stroke="#e6c071"),
            _text(51, 658, "NO reordenes las hojas una por una.", size=19,
                  weight=700),
            _text(51, 686, "El dibujo de salida NO representa el trayecto real de",
                  size=16),
            _text(51, 708, "la Brother. Reintroduce siguiendo la calibración física validada.",
                  size=16),
        ]
    )
    if orientation is None:
        parts.append(
            _text(36, 769, f"Instrucción guardada: {profile.refeed_instruction}",
                  size=16),
        )
    return _svg(parts, height=790 if orientation is None else 750)
