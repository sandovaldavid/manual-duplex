from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .config import get_profile, save_profile
from .cups import CupsClient
from .desktop import install_desktop_entry
from .errors import CommandError, ConfigurationError, ManualDuplexError
from .models import (
    BackOrder,
    LayoutSettings,
    Orientation,
    Paper,
    PrinterProfile,
    PrintSettings,
    Quality,
)
from .ui import Zenity
from .workflow import PrintResult, print_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manual-duplex",
        description=(
            "Guided manual duplex printing for CUPS printers without automatic duplex support."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    printers = subparsers.add_parser("printers", help="List CUPS printers.")
    printers.set_defaults(handler=_cmd_printers)

    capabilities = subparsers.add_parser(
        "capabilities",
        help="Show driver options exposed by CUPS.",
    )
    capabilities.add_argument("--printer")
    capabilities.set_defaults(handler=_cmd_capabilities)

    calibrate = subparsers.add_parser(
        "calibrate",
        help="Save the validated paper refeed behavior for one printer.",
    )
    calibrate.add_argument("--printer")
    calibrate.add_argument("--back-order", choices=[item.value for item in BackOrder])
    calibrate.add_argument(
        "--back-rotation",
        type=int,
        choices=(0, 180),
        default=None,
        help="Rotate every back side by 180 degrees if required by the validated refeed.",
    )
    calibrate.add_argument(
        "--refeed-instruction",
        help="Human-readable instruction shown after the first pass.",
    )
    calibrate.set_defaults(handler=_cmd_calibrate)

    print_parser = subparsers.add_parser("print", help="Print a PDF using manual duplex.")
    print_parser.add_argument("file", type=Path)
    print_parser.add_argument("--printer")
    _add_print_options(print_parser)
    print_parser.set_defaults(handler=_cmd_print)

    gui = subparsers.add_parser(
        "gui",
        help="Open the graphical print workflow, optionally for a specific PDF.",
    )
    gui.add_argument("file", nargs="?", type=Path)
    gui.add_argument(
        "--configure",
        action="store_true",
        help="Open printer configuration directly.",
    )
    gui.set_defaults(handler=_cmd_gui)

    desktop = subparsers.add_parser(
        "install-desktop",
        help="Install a per-user PDF desktop entry for GNOME and other desktops.",
    )
    desktop.set_defaults(handler=_cmd_install_desktop)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.handler(args))
    except ManualDuplexError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


def _add_print_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--paper", choices=[item.value for item in Paper], default="a4")
    parser.add_argument(
        "--orientation",
        choices=[item.value for item in Orientation],
        default="portrait",
    )
    parser.add_argument("--pages-per-side", type=int, choices=(1, 2), default=1)
    parser.add_argument(
        "--quality",
        choices=[item.value for item in Quality],
        default="normal",
    )
    parser.add_argument("--monochrome", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--back-order", choices=[item.value for item in BackOrder])
    parser.add_argument("--back-rotation", type=int, choices=(0, 180))
    parser.add_argument(
        "--cups-option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pass a driver-specific CUPS option. Can be repeated.",
    )
    parser.add_argument("--timeout", type=float, default=900.0)


def _cmd_printers(_: argparse.Namespace) -> int:
    cups = CupsClient()
    printers = cups.list_printers()
    default = cups.default_printer()
    for printer in printers:
        marker = " *" if printer == default else ""
        print(f"{printer}{marker}")
    if not printers:
        print("No CUPS printers found.")
    return 0


def _cmd_capabilities(args: argparse.Namespace) -> int:
    cups = CupsClient()
    printer = _resolve_printer(cups, args.printer)
    capabilities = cups.capabilities(printer)
    print(f"Printer: {printer}")
    for option, choices in capabilities.items():
        print(f"{option}: {' '.join(choices)}")
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    cups = CupsClient()
    printer = _resolve_printer(cups, args.printer)

    back_order = args.back_order
    if back_order is None:
        back_order = _prompt_choice(
            "Back-side order after your physical refeed test",
            ("normal", "reverse"),
            default="reverse",
        )

    back_rotation = args.back_rotation
    if back_rotation is None:
        back_rotation = int(
            _prompt_choice(
                "Back-side rotation",
                ("0", "180"),
                default="0",
            )
        )

    instruction = args.refeed_instruction
    if instruction is None:
        print(
            "Enter the exact paper refeed instruction that worked in your physical test.\n"
            "Example: Reinsert the stack blank-side down, top edge entering first."
        )
        instruction = input("Refeed instruction: ").strip()
        if not instruction:
            raise ConfigurationError("A refeed instruction is required.")

    profile = PrinterProfile(
        printer=printer,
        back_order=BackOrder(back_order),
        back_rotation=back_rotation,
        refeed_instruction=instruction,
    )
    destination = save_profile(profile)
    print(f"Saved calibration for {printer} in {destination}")
    return 0


def _cmd_print(args: argparse.Namespace) -> int:
    cups = CupsClient()
    printer = _resolve_printer(cups, args.printer)
    profile = _profile_for_print(
        printer,
        back_order=args.back_order,
        back_rotation=args.back_rotation,
    )
    settings = _settings_from_args(args)

    preview = _cli_preview if args.preview else None
    result = print_document(
        source=args.file.expanduser().resolve(),
        printer=printer,
        settings=settings,
        profile=profile,
        cups=cups,
        preview=preview,
        confirm_refeed=_cli_confirm_refeed,
    )
    _print_result(result)
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    ui = Zenity()
    cups = CupsClient()
    printers = cups.list_printers()
    if not printers:
        ui.error("Dúplex manual", "No se encontraron impresoras configuradas en CUPS.")
        return 2

    if args.configure:
        return _configure_printer_gui(ui, cups, printers)

    source = args.file.expanduser().resolve() if args.file else None
    if source is None:
        action = ui.choose_action()
        if action is None:
            return 0
        if action == "configure":
            return _configure_printer_gui(ui, cups, printers)
        source = ui.choose_pdf()

    if source is None:
        return 0

    printer = _select_gui_printer(ui, cups, printers)
    if printer is None:
        return 0

    form = ui.print_form(printer, cups.supported_qualities(printer))
    if form is None:
        return 0

    profile = get_profile(printer)
    if profile is None:
        if not ui.ask_first_configuration(printer):
            return 0
        profile = _configure_profile_gui(ui, printer)
        if profile is None:
            return 0

    settings = PrintSettings(
        layout=LayoutSettings(
            paper=Paper(form["paper"]),
            orientation=Orientation(form["orientation"]),
            pages_per_side=int(form["pages_per_side"]),
        ),
        quality=Quality(form["quality"]),
        monochrome=form["color"] == "monochrome",
    )

    try:
        result = print_document(
            source=source,
            printer=printer,
            settings=settings,
            profile=profile,
            cups=cups,
            preview=ui.preview if form["preview"] == "yes" else None,
            confirm_refeed=ui.confirm_refeed,
        )
    except ManualDuplexError as exc:
        ui.error("Dúplex manual", str(exc))
        return 2

    ui.info(
        "Dúplex manual",
        f"Impresión finalizada.\nHojas: {result.sheet_count}\n"
        f"Trabajo de frentes: {result.front_job_id}\n"
        f"Trabajo de reversos: {result.back_job_id or 'no fue necesario'}",
    )
    return 0


def _select_gui_printer(
    ui: Zenity,
    cups: CupsClient,
    printers: tuple[str, ...],
) -> str | None:
    if len(printers) == 1:
        return printers[0]
    return ui.choose_printer(printers, cups.default_printer())


def _configure_printer_gui(
    ui: Zenity,
    cups: CupsClient,
    printers: tuple[str, ...],
) -> int:
    printer = ui.choose_printer(printers, cups.default_printer())
    if printer is None:
        return 0

    profile = _configure_profile_gui(ui, printer)
    return 0 if profile is not None else 0


def _configure_profile_gui(ui: Zenity, printer: str) -> PrinterProfile | None:
    while True:
        try:
            calibration = ui.calibration_form(printer)
            if calibration is None:
                return None
        except CommandError as exc:
            ui.error("Configuración de impresora", str(exc))
            continue

        profile = PrinterProfile(
            printer=printer,
            back_order=BackOrder(str(calibration["back_order"])),
            back_rotation=int(calibration["back_rotation"]),
            refeed_instruction=str(calibration["refeed_instruction"]),
        )
        save_profile(profile)
        ui.info(
            "Impresora configurada",
            f"La configuración de {printer} quedó guardada.\n\n"
            "Antes de imprimir muchas hojas, haz una prueba corta de 2 hojas. "
            "Si el reverso queda mal orientado o en otro orden, abre Dúplex manual "
            "y selecciona “Configurar impresora” para corregirlo.",
        )
        return profile


def _cmd_install_desktop(_: argparse.Namespace) -> int:
    destination = install_desktop_entry()
    print(f"Installed desktop entry: {destination}")
    return 0


def _resolve_printer(cups: CupsClient, requested: str | None) -> str:
    printers = cups.list_printers()
    if requested is not None:
        if requested not in printers:
            available = ", ".join(printers) or "none"
            raise ConfigurationError(
                f"Printer {requested!r} was not found. Available printers: {available}"
            )
        return requested

    default = cups.default_printer()
    if default in printers:
        return default
    if len(printers) == 1:
        return printers[0]
    if not printers:
        raise ConfigurationError("No CUPS printers were found.")
    raise ConfigurationError(
        "More than one printer is available and no default is configured. "
        "Use --printer NAME."
    )


def _profile_for_print(
    printer: str,
    *,
    back_order: str | None,
    back_rotation: int | None,
) -> PrinterProfile:
    saved = get_profile(printer)
    if saved is None and back_order is None:
        raise ConfigurationError(
            f"No calibration exists for {printer!r}. Run "
            f"`manual-duplex calibrate --printer {printer}` first, or pass "
            "`--back-order` for a one-off test."
        )

    resolved_order = BackOrder(back_order) if back_order is not None else saved.back_order
    resolved_rotation = (
        back_rotation
        if back_rotation is not None
        else (saved.back_rotation if saved is not None else 0)
    )
    instruction = (
        saved.refeed_instruction
        if saved is not None
        else "Reinsert the stack using the orientation validated for this printer."
    )
    return PrinterProfile(
        printer=printer,
        back_order=resolved_order,
        back_rotation=resolved_rotation,
        refeed_instruction=instruction,
    )


def _settings_from_args(args: argparse.Namespace) -> PrintSettings:
    if args.timeout <= 0:
        raise ConfigurationError("--timeout must be greater than zero.")
    return PrintSettings(
        layout=LayoutSettings(
            paper=Paper(args.paper),
            orientation=Orientation(args.orientation),
            pages_per_side=args.pages_per_side,
        ),
        quality=Quality(args.quality),
        monochrome=args.monochrome,
        raw_cups_options=tuple(args.cups_option),
        timeout_seconds=args.timeout,
    )


def _cli_preview(pdf: Path) -> bool:
    opener = shutil.which("xdg-open")
    if opener is None:
        raise ConfigurationError("xdg-open is required for preview mode.")
    subprocess.Popen(
        [opener, str(pdf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    answer = input("Review the prepared PDF. Continue printing? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _cli_confirm_refeed(instruction: str, sheet_count: int) -> bool:
    print(f"First pass complete: {sheet_count} sheet(s).")
    print(instruction)
    answer = input("Paper reinserted and ready for the back pass? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _print_result(result: PrintResult) -> None:
    print(f"Printed {result.physical_sides} physical side(s) on {result.sheet_count} sheet(s).")
    print(f"Front job: {result.front_job_id}")
    if result.back_job_id is not None:
        print(f"Back job: {result.back_job_id}")


def _prompt_choice(label: str, choices: tuple[str, ...], *, default: str) -> str:
    options = "/".join(choices)
    while True:
        value = input(f"{label} [{options}] (default {default}): ").strip().lower()
        if not value:
            return default
        if value in choices:
            return value
        print(f"Choose one of: {options}")
