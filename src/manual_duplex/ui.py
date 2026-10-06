from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from .errors import CommandError

_PRINT_ACTION = "Imprimir un PDF"
_CONFIGURE_ACTION = "Configurar impresora"

_PAPER_LABELS = {
    "A4": "a4",
    "Carta": "letter",
    "Legal": "legal",
    "Oficio (Folio 8.5 x 13)": "folio",
}
_ORIENTATION_LABELS = {
    "Vertical": "portrait",
    "Horizontal": "landscape",
}
_QUALITY_LABELS = {
    "Normal": "normal",
    "Borrador": "draft",
    "Alta": "high",
}
_COLOR_LABELS = {
    "Color": "color",
    "Blanco y negro": "monochrome",
}
_PREVIEW_LABELS = {
    "No": "no",
    "Sí": "yes",
}

_ORDER_LABELS = {
    "Imprimir reversos desde la última hoja": "reverse",
    "Imprimir reversos en el mismo orden": "normal",
}
_ROTATION_LABELS = {
    "Sin giro adicional": 0,
    "Girar reversos 180°": 180,
}
_FACE_LABELS = {
    "Cara impresa hacia arriba": "up",
    "Cara impresa hacia abajo": "down",
}
_EDGE_LABELS = {
    "Borde superior entra primero": "top",
    "Borde inferior entra primero": "bottom",
}


class Zenity:
    def __init__(self) -> None:
        if shutil.which("zenity") is None:
            raise CommandError(
                "Zenity es necesario para el modo gráfico. En Fedora se instala con "
                "`sudo dnf install zenity`."
            )

    def choose_action(self) -> str | None:
        result = self._run(
            (
                "zenity",
                "--list",
                "--title=Dúplex manual",
                "--text=¿Qué quieres hacer?",
                "--column=Acción",
                _PRINT_ACTION,
                _CONFIGURE_ACTION,
                "--height=260",
                "--width=440",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        if value == _PRINT_ACTION:
            return "print"
        if value == _CONFIGURE_ACTION:
            return "configure"
        return None

    def choose_pdf(self) -> Path | None:
        result = self._run(
            (
                "zenity",
                "--file-selection",
                "--title=Seleccionar PDF",
                "--file-filter=Archivos PDF | *.pdf",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return Path(value) if value else None

    def choose_printer(
        self,
        printers: Sequence[str],
        default_printer: str | None = None,
    ) -> str | None:
        ordered = _ordered_printers(printers, default_printer)
        result = self._run(
            (
                "zenity",
                "--list",
                "--title=Configurar impresora",
                "--text=Selecciona la impresora que quieres configurar.",
                "--column=Impresora",
                *ordered,
                "--height=320",
                "--width=560",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def print_form(
        self,
        printers: Sequence[str],
        default_printer: str | None = None,
    ) -> dict[str, str] | None:
        ordered_printers = _ordered_printers(printers, default_printer)
        printer_values = "|".join(ordered_printers)
        result = self._run(
            (
                "zenity",
                "--forms",
                "--title=Dúplex manual",
                "--text=Configura la impresión. Los valores habituales ya están seleccionados.",
                "--add-combo=Impresora",
                f"--combo-values={printer_values}",
                "--add-combo=Tamaño de papel",
                f"--combo-values={'|'.join(_PAPER_LABELS)}",
                "--add-combo=Orientación",
                f"--combo-values={'|'.join(_ORIENTATION_LABELS)}",
                "--add-combo=Páginas por cara",
                "--combo-values=1|2",
                "--add-combo=Calidad",
                f"--combo-values={'|'.join(_QUALITY_LABELS)}",
                "--add-combo=Color",
                f"--combo-values={'|'.join(_COLOR_LABELS)}",
                "--add-combo=Vista previa",
                f"--combo-values={'|'.join(_PREVIEW_LABELS)}",
                "--separator=|",
                "--width=560",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None

        values = result.stdout.rstrip("\n").split("|")
        return parse_print_form(values)

    def calibration_form(self, printer: str) -> dict[str, str | int] | None:
        result = self._run(
            (
                "zenity",
                "--forms",
                "--title=Configuración inicial",
                f"--text=Configura una sola vez cómo se vuelve a colocar el papel en {printer}.\n"
                "No se adivinarán estos valores: confírmalos con una prueba corta antes de "
                "imprimir documentos largos.",
                "--add-combo=Orden de los reversos",
                f"--combo-values=Seleccionar...|{'|'.join(_ORDER_LABELS)}",
                "--add-combo=Giro del reverso",
                f"--combo-values=Seleccionar...|{'|'.join(_ROTATION_LABELS)}",
                "--add-combo=Cómo colocar la cara ya impresa",
                f"--combo-values=Seleccionar...|{'|'.join(_FACE_LABELS)}",
                "--add-combo=Qué borde entra primero",
                f"--combo-values=Seleccionar...|{'|'.join(_EDGE_LABELS)}",
                "--separator=|",
                "--width=660",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None

        values = result.stdout.rstrip("\n").split("|")
        return parse_calibration_form(values)

    def ask_first_configuration(self, printer: str) -> bool:
        return self.question(
            "Configuración inicial",
            f"La impresora {printer} todavía no está configurada para impresión a doble cara.\n\n"
            "Esta configuración se realiza una sola vez y después queda guardada.\n"
            "Puedes cambiarla más adelante desde “Configurar impresora”.",
            ok_label="Configurar ahora",
            cancel_label="Cancelar",
        )

    def preview(self, pdf: Path) -> bool:
        opener = shutil.which("xdg-open")
        if opener is None:
            raise CommandError("xdg-open es necesario para la vista previa.")
        subprocess.Popen(
            [opener, str(pdf)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return self.question(
            "Vista previa",
            "Revisa el PDF preparado en el visor de documentos.\n\n"
            "¿Quieres continuar con la impresión?",
            ok_label="Imprimir",
            cancel_label="Cancelar",
        )

    def confirm_refeed(self, instruction: str, sheet_count: int) -> bool:
        return self.question(
            "Volver a colocar las hojas",
            f"La primera pasada terminó ({sheet_count} hoja(s)).\n\n"
            f"{instruction}\n\n"
            "Continúa solo cuando todas las hojas hayan terminado de salir y el bloque "
            "esté colocado nuevamente en la bandeja.",
            ok_label="Imprimir reversos",
            cancel_label="Cancelar",
        )

    def info(self, title: str, text: str) -> None:
        self._run(("zenity", "--info", f"--title={title}", f"--text={text}"))

    def error(self, title: str, text: str) -> None:
        self._run(
            ("zenity", "--error", f"--title={title}", f"--text={text}"),
            check=False,
        )

    def question(
        self,
        title: str,
        text: str,
        *,
        ok_label: str = "Aceptar",
        cancel_label: str = "Cancelar",
    ) -> bool:
        result = self._run(
            (
                "zenity",
                "--question",
                f"--title={title}",
                f"--text={text}",
                f"--ok-label={ok_label}",
                f"--cancel-label={cancel_label}",
            ),
            check=False,
        )
        return result.returncode == 0

    @staticmethod
    def _run(
        args: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "error desconocido"
            raise CommandError(f"Zenity falló: {detail}")
        return result


def parse_print_form(values: Sequence[str]) -> dict[str, str]:
    if len(values) != 7:
        raise CommandError("La ventana devolvió una configuración de impresión inesperada.")

    printer, paper, orientation, pages_per_side, quality, color, preview = values
    try:
        return {
            "printer": printer,
            "paper": _PAPER_LABELS[paper],
            "orientation": _ORIENTATION_LABELS[orientation],
            "pages_per_side": pages_per_side,
            "quality": _QUALITY_LABELS[quality],
            "color": _COLOR_LABELS[color],
            "preview": _PREVIEW_LABELS[preview],
        }
    except KeyError as exc:
        raise CommandError("La configuración gráfica contiene un valor no reconocido.") from exc


def parse_calibration_form(values: Sequence[str]) -> dict[str, str | int]:
    if len(values) != 4:
        raise CommandError("La ventana devolvió una calibración inesperada.")

    order, rotation, face, edge = values
    if "Seleccionar..." in values:
        raise CommandError(
            "Debes seleccionar las cuatro opciones de configuración de la impresora."
        )

    try:
        face_value = _FACE_LABELS[face]
        edge_value = _EDGE_LABELS[edge]
        return {
            "back_order": _ORDER_LABELS[order],
            "back_rotation": _ROTATION_LABELS[rotation],
            "refeed_instruction": build_refeed_instruction(face_value, edge_value),
        }
    except KeyError as exc:
        raise CommandError("La calibración contiene un valor no reconocido.") from exc


def build_refeed_instruction(face: str, edge: str) -> str:
    face_text = {
        "up": "la cara ya impresa hacia arriba",
        "down": "la cara ya impresa hacia abajo",
    }[face]
    edge_text = {
        "top": "el borde superior entrando primero",
        "bottom": "el borde inferior entrando primero",
    }[edge]
    return f"Coloca el bloque con {face_text} y {edge_text}."


def _ordered_printers(
    printers: Sequence[str],
    default_printer: str | None,
) -> list[str]:
    ordered = list(printers)
    if default_printer in ordered:
        ordered.remove(default_printer)
        ordered.insert(0, default_printer)
    return ordered
