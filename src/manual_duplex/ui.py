from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from .errors import CommandError
from .models import Quality

_PRINT_ACTION = "Imprimir un PDF"
_CONFIGURE_ACTION = "Configurar impresora"
_HELP_ACTION = "Ayuda y solución de problemas"

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
_PAGES_PER_SIDE_LABELS = {
    "1 página por cara": "1",
    "2 páginas por cara": "2",
    "4 páginas por cara (8 por hoja)": "4",
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

_PASS_ORDER_LABELS = {
    "Caras delanteras primero": "fronts_first",
    "Reversos primero": "backs_first",
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

_HELP_TOPICS = {
    "Las páginas quedan en otro orden": (
        "Abre “Configurar impresora” y revisa qué caras se imprimen primero y el "
        "orden de los reversos. Haz una prueba corta de 4 u 8 páginas antes de "
        "imprimir un documento largo."
    ),
    "El reverso queda de cabeza": (
        "Abre “Configurar impresora” y cambia “Giro del reverso”. Si ya estaba "
        "activado, desactívalo; si estaba desactivado, prueba con 180°."
    ),
    "La impresión queda corrida o cerca del borde": (
        "Comprueba que el tamaño de papel elegido coincida con las hojas reales y "
        "que la orientación sea correcta. Alinea las guías de la bandeja con el "
        "papel sin apretarlas. Si solo ocurre en una segunda pasada, alisa las hojas "
        "antes de volver a colocarlas."
    ),
    "La impresora no aparece": (
        "Comprueba que la impresora esté encendida y conectada. Abre Configuración "
        "de Fedora > Impresoras y verifica que aparezca allí. Cuando CUPS la detecte, "
        "vuelve a abrir Dúplex manual."
    ),
    "La impresión se detuvo": (
        "Revisa papel, tinta y avisos de la impresora. En Configuración de Fedora > "
        "Impresoras puedes ver si hay un trabajo detenido. Corrige el problema y "
        "vuelve a imprimir; la aplicación nunca inicia la segunda pasada sin tu "
        "confirmación."
    ),
    "Quiero cambiar cómo se imprime": (
        "En “Imprimir un PDF” puedes elegir papel, orientación, páginas por cara, "
        "color, calidad disponible y vista previa. La configuración física de cómo "
        "se reinserta el papel se cambia por separado en “Configurar impresora”."
    ),
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
                "--text=Selecciona lo que quieres hacer.",
                "--column=Acción",
                "--column=Descripción",
                "--print-column=1",
                _PRINT_ACTION,
                "Selecciona un PDF y sigue la impresión paso a paso.",
                _CONFIGURE_ACTION,
                "Corrige el orden, giro o forma de volver a colocar las hojas.",
                _HELP_ACTION,
                "Resuelve problemas comunes sin usar la consola.",
                "--height=340",
                "--width=700",
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
        if value == _HELP_ACTION:
            return "help"
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
                "--title=Seleccionar impresora",
                "--text=Selecciona dónde quieres imprimir.",
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
        printer: str,
        qualities: Sequence[Quality],
    ) -> dict[str, str] | None:
        quality_values = quality_labels(qualities)
        if not quality_values:
            raise CommandError("La impresora no tiene una calidad de impresión utilizable.")

        result = self._run(
            (
                "zenity",
                "--forms",
                "--title=Configurar impresión",
                f"--text=Impresora: {printer}\n"
                "Elige cómo quieres que quede el documento. Puedes revisar todo antes de imprimir.",
                "--add-combo=Tamaño de papel",
                f"--combo-values={'|'.join(_PAPER_LABELS)}",
                "--add-combo=Orientación",
                f"--combo-values={'|'.join(_ORIENTATION_LABELS)}",
                "--add-combo=Páginas por cara",
                f"--combo-values={'|'.join(_PAGES_PER_SIDE_LABELS)}",
                "--add-combo=Calidad",
                f"--combo-values={'|'.join(quality_values)}",
                "--add-combo=Color",
                f"--combo-values={'|'.join(_COLOR_LABELS)}",
                "--add-combo=Vista previa",
                f"--combo-values={'|'.join(_PREVIEW_LABELS)}",
                "--separator=|",
                "--width=620",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None

        values = result.stdout.rstrip("\n").split("|")
        return parse_print_form(values, printer=printer)

    def calibration_form(self, printer: str) -> dict[str, str | int] | None:
        result = self._run(
            (
                "zenity",
                "--forms",
                "--title=Configurar impresora",
                f"--text=Estas opciones describen cómo {printer} mueve y apila las hojas.\n"
                "Cámbialas solo cuando una prueba corta muestre que el orden u orientación "
                "no son correctos.",
                "--add-combo=Qué caras se imprimen primero",
                f"--combo-values=Seleccionar...|{'|'.join(_PASS_ORDER_LABELS)}",
                "--add-combo=Orden de los reversos",
                f"--combo-values=Seleccionar...|{'|'.join(_ORDER_LABELS)}",
                "--add-combo=Giro del reverso",
                f"--combo-values=Seleccionar...|{'|'.join(_ROTATION_LABELS)}",
                "--add-combo=Cómo colocar la cara ya impresa",
                f"--combo-values=Seleccionar...|{'|'.join(_FACE_LABELS)}",
                "--add-combo=Qué borde entra primero",
                f"--combo-values=Seleccionar...|{'|'.join(_EDGE_LABELS)}",
                "--separator=|",
                "--width=700",
            ),
            check=False,
        )
        if result.returncode != 0:
            return None

        values = result.stdout.rstrip("\n").split("|")
        return parse_calibration_form(values)

    def ask_first_configuration(self, printer: str) -> bool:
        return self.question(
            "Preparar impresora",
            f"Es la primera vez que usas {printer} con Dúplex manual.\n\n"
            "Necesitamos guardar cómo esta impresora apila y vuelve a recibir las hojas. "
            "Se hace una sola vez y después puedes corregirlo desde “Configurar impresora”.\n\n"
            "Usa pocas hojas para esta primera prueba.",
            ok_label="Configurar impresora",
            cancel_label="Cancelar",
        )

    def confirm_print(
        self,
        source: Path,
        printer: str,
        form: Mapping[str, str],
    ) -> bool:
        return self.question(
            "Revisar impresión",
            print_summary_text(source, printer, form)
            + "\n\nLa impresión a doble cara se realiza en dos pasadas. "
            "La aplicación te avisará exactamente cuándo volver a colocar las hojas.",
            ok_label="Empezar impresión",
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
            "Se abrió el PDF preparado en el visor de documentos.\n\n"
            "Comprueba orientación, tamaño y distribución de las páginas. "
            "Después vuelve a esta ventana.",
            ok_label="Se ve bien, imprimir",
            cancel_label="Cancelar",
        )

    def confirm_refeed(self, instruction: str, sheet_count: int) -> bool:
        return self.question(
            "Volver a colocar las hojas",
            f"La primera pasada terminó ({sheet_count} hoja(s)).\n\n"
            "1. Espera a que hayan salido todas las hojas.\n"
            "2. Mantén el bloque en el mismo orden; no reordenes hojas individualmente.\n"
            f"3. {instruction}\n"
            "4. Ajusta las guías de la bandeja sin doblar ni apretar el papel.\n\n"
            "Cuando el bloque esté listo, continúa con la segunda pasada.",
            ok_label="Continuar impresión",
            cancel_label="Cancelar",
        )

    def help_menu(self) -> None:
        topics = tuple(_HELP_TOPICS)
        rows: list[str] = []
        for topic in topics:
            rows.extend((topic, _HELP_TOPICS[topic]))

        result = self._run(
            (
                "zenity",
                "--list",
                "--title=Ayuda de Dúplex manual",
                "--text=Selecciona el problema que más se parece a lo que ocurrió.",
                "--column=Problema",
                "--column=Qué revisar",
                "--print-column=1",
                *rows,
                "--height=430",
                "--width=860",
            ),
            check=False,
        )
        if result.returncode != 0:
            return

        topic = result.stdout.strip()
        detail = _HELP_TOPICS.get(topic)
        if detail is not None:
            self.info(topic, detail)

    def print_complete(self, sheet_count: int, physical_sides: int) -> None:
        if physical_sides == 1:
            text = "La página se imprimió correctamente."
        else:
            text = (
                f"La impresión a doble cara terminó correctamente en {sheet_count} hoja(s).\n\n"
                "Comprueba que la primera página quede al frente y que el documento avance "
                "en el orden esperado."
            )
        self.info("Impresión terminada", text)

    def print_error(self, detail: str) -> None:
        self.error(
            "No se pudo completar la impresión",
            "La impresión no terminó correctamente.\n\n"
            f"Detalle: {detail}\n\n"
            "Puedes abrir “Ayuda y solución de problemas” desde Dúplex manual para revisar "
            "los casos más comunes.",
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


def quality_labels(qualities: Sequence[Quality]) -> tuple[str, ...]:
    supported = set(qualities)
    return tuple(
        label
        for label, value in _QUALITY_LABELS.items()
        if Quality(value) in supported
    )


def parse_print_form(
    values: Sequence[str],
    *,
    printer: str,
) -> dict[str, str]:
    if len(values) != 6:
        raise CommandError("La ventana devolvió una configuración de impresión inesperada.")

    paper, orientation, pages_per_side, quality, color, preview = values
    try:
        return {
            "printer": printer,
            "paper": _PAPER_LABELS[paper],
            "orientation": _ORIENTATION_LABELS[orientation],
            "pages_per_side": _PAGES_PER_SIDE_LABELS[pages_per_side],
            "quality": _QUALITY_LABELS[quality],
            "color": _COLOR_LABELS[color],
            "preview": _PREVIEW_LABELS[preview],
        }
    except KeyError as exc:
        raise CommandError("La configuración gráfica contiene un valor no reconocido.") from exc


def parse_calibration_form(values: Sequence[str]) -> dict[str, str | int]:
    if len(values) != 5:
        raise CommandError("La ventana devolvió una calibración inesperada.")

    pass_order, order, rotation, face, edge = values
    if "Seleccionar..." in values:
        raise CommandError(
            "Debes seleccionar las cinco opciones de configuración de la impresora."
        )

    try:
        face_value = _FACE_LABELS[face]
        edge_value = _EDGE_LABELS[edge]
        return {
            "pass_order": _PASS_ORDER_LABELS[pass_order],
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


def print_summary_text(
    source: Path,
    printer: str,
    form: Mapping[str, str],
) -> str:
    return (
        f"Archivo: {source.name}\n"
        f"Impresora: {printer}\n"
        f"Papel: {_display_label(_PAPER_LABELS, form['paper'])}\n"
        f"Orientación: {_display_label(_ORIENTATION_LABELS, form['orientation'])}\n"
        f"Páginas por cara: {_display_label(_PAGES_PER_SIDE_LABELS, form['pages_per_side'])}\n"
        f"Calidad: {_display_label(_QUALITY_LABELS, form['quality'])}\n"
        f"Color: {_display_label(_COLOR_LABELS, form['color'])}\n"
        f"Vista previa: {_display_label(_PREVIEW_LABELS, form['preview'])}"
    )


def _display_label(mapping: Mapping[str, str], value: str) -> str:
    for label, internal in mapping.items():
        if internal == value:
            return label
    return value


def _ordered_printers(
    printers: Sequence[str],
    default_printer: str | None,
) -> list[str]:
    ordered = list(printers)
    if default_printer in ordered:
        ordered.remove(default_printer)
        ordered.insert(0, default_printer)
    return ordered
