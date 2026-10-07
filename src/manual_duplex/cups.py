from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from .errors import CommandError, ConfigurationError
from .models import PAPER_CUPS_CANDIDATES, Orientation, Paper, Quality

_JOB_ID_PATTERN = re.compile(r"request id is ([^\s]+)")


def parse_capabilities(output: str) -> dict[str, tuple[str, ...]]:
    capabilities: dict[str, tuple[str, ...]] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        left, right = line.split(":", 1)
        option_name = left.split("/", 1)[0].strip()
        choices = tuple(token.lstrip("*") for token in right.split() if token)
        if option_name and choices:
            capabilities[option_name] = choices
    return capabilities


def parse_job_id(output: str) -> str:
    match = _JOB_ID_PATTERN.search(output)
    if not match:
        raise CommandError(f"Could not parse CUPS job id from lp output: {output.strip()}")
    return match.group(1)


class CupsClient:
    def __init__(self, poll_interval: float = 1.0) -> None:
        self.poll_interval = poll_interval

    def list_printers(self) -> tuple[str, ...]:
        result = self._run(("lpstat", "-e"))
        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

    def default_printer(self) -> str | None:
        result = self._run(("lpstat", "-d"), check=False)
        if result.returncode != 0:
            return None
        prefix = "system default destination:"
        line = result.stdout.strip()
        if not line.lower().startswith(prefix):
            return None
        value = line[len(prefix) :].strip()
        return value or None

    def capabilities(self, printer: str) -> dict[str, tuple[str, ...]]:
        result = self._run(("lpoptions", "-p", printer, "-l"))
        return parse_capabilities(result.stdout)

    def supported_qualities(self, printer: str) -> tuple[Quality, ...]:
        return supported_qualities(self.capabilities(printer))

    def build_options(
        self,
        printer: str,
        paper: Paper,
        orientation: Orientation,
        quality: Quality,
        monochrome: bool,
        raw_options: Sequence[str] = (),
    ) -> dict[str, str]:
        capabilities = self.capabilities(printer)
        options: dict[str, str] = {}

        media_option, media_value = _resolve_media(capabilities, paper)
        options[media_option] = media_value
        options["orientation-requested"] = _orientation_requested(orientation)

        if quality is not Quality.NORMAL:
            quality_option, quality_value = _resolve_quality(capabilities, quality)
            options[quality_option] = quality_value

        if monochrome:
            color_options = _resolve_monochrome(capabilities)
            if not color_options:
                raise ConfigurationError(
                    "The selected printer does not expose a recognized monochrome option. "
                    "Inspect it with `manual-duplex capabilities --printer ...` and pass a "
                    "driver-specific value with `--cups-option KEY=VALUE`."
                )
            options.update(color_options)

        for raw_option in raw_options:
            key, value = _parse_raw_option(raw_option)
            options[key] = value

        return options

    def submit(self, printer: str, pdf: Path, options: Mapping[str, str]) -> str:
        args = ["lp", "-d", printer]
        for key, value in options.items():
            args.extend(("-o", f"{key}={value}"))
        args.append(str(pdf))
        result = self._run(tuple(args))
        return parse_job_id(result.stdout)

    def wait_for_job(self, printer: str, job_id: str, timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            result = self._run(
                ("lpstat", "-W", "not-completed", "-o", printer),
                check=False,
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                raise CommandError(
                    f"Could not query CUPS job state for {job_id}: {detail}. "
                    "The second pass was not started."
                )

            active_job_ids = {
                line.split()[0]
                for line in result.stdout.splitlines()
                if line.split()
            }
            if job_id not in active_job_ids:
                return
            if time.monotonic() >= deadline:
                raise CommandError(
                    f"Timed out waiting for CUPS job {job_id}. "
                    "The second pass was not started."
                )
            time.sleep(self.poll_interval)

    def _run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        executable = args[0]
        if shutil.which(executable) is None:
            raise CommandError(
                f"Required command {executable!r} was not found. "
                "Install the CUPS client tools first."
            )

        env = os.environ.copy()
        env["LC_ALL"] = "C"
        result = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise CommandError(f"{' '.join(args)} failed: {detail}")
        return result


def supported_qualities(
    capabilities: Mapping[str, Sequence[str]],
) -> tuple[Quality, ...]:
    qualities = [Quality.NORMAL]
    for quality in (Quality.DRAFT, Quality.HIGH):
        try:
            _resolve_quality(capabilities, quality)
        except ConfigurationError:
            continue
        qualities.append(quality)
    return tuple(qualities)


def _orientation_requested(orientation: Orientation) -> str:
    if orientation is Orientation.LANDSCAPE:
        return "4"
    return "3"


def _resolve_media(
    capabilities: Mapping[str, Sequence[str]],
    paper: Paper,
) -> tuple[str, str]:
    candidates = PAPER_CUPS_CANDIDATES[paper]
    option = _find_option(capabilities, ("PageSize", "PageRegion", "media", "MediaSize"))

    if option is None:
        return "media", candidates[0]

    match = _find_choice(capabilities[option], candidates)
    if match is None:
        available = ", ".join(capabilities[option])
        raise ConfigurationError(
            f"{paper.value} is not exposed by printer option {option}. "
            f"Available values: {available}"
        )
    return option, match


def _resolve_quality(
    capabilities: Mapping[str, Sequence[str]],
    quality: Quality,
) -> tuple[str, str]:
    option = _find_option(
        capabilities,
        ("print-quality", "cupsPrintQuality", "BRPrintQuality"),
    )
    if option is None:
        raise ConfigurationError(
            "The selected printer does not expose a recognized print-quality option."
        )

    candidates = {
        Quality.DRAFT: ("Draft", "draft", "3", "Fast"),
        Quality.HIGH: ("High", "high", "Fine", "Best", "5"),
    }[quality]
    match = _find_choice(capabilities[option], candidates)
    if match is None:
        available = ", ".join(capabilities[option])
        raise ConfigurationError(
            f"Cannot map quality {quality.value!r} to {option}. Available values: {available}"
        )
    return option, match


def _resolve_monochrome(
    capabilities: Mapping[str, Sequence[str]],
) -> dict[str, str]:
    mappings = (
        ("print-color-mode", ("monochrome", "auto-monochrome")),
        ("ColorModel", ("Gray", "Grayscale", "KGray", "Black", "Mono")),
        ("BRMonoColor", ("Mono", "Monochrome", "Black", "ON")),
    )

    resolved: dict[str, str] = {}
    for requested_name, candidates in mappings:
        option = _find_option(capabilities, (requested_name,))
        if option is None:
            continue
        choice = _find_choice(capabilities[option], candidates)
        if choice is not None:
            resolved[option] = choice
    return resolved


def _find_option(
    capabilities: Mapping[str, Sequence[str]],
    candidates: Sequence[str],
) -> str | None:
    by_casefold = {key.casefold(): key for key in capabilities}
    for candidate in candidates:
        match = by_casefold.get(candidate.casefold())
        if match is not None:
            return match
    return None


def _find_choice(choices: Sequence[str], candidates: Sequence[str]) -> str | None:
    by_casefold = {choice.casefold(): choice for choice in choices}
    for candidate in candidates:
        match = by_casefold.get(candidate.casefold())
        if match is not None:
            return match
    return None


def _parse_raw_option(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ConfigurationError(
            f"Invalid CUPS option {value!r}. Expected KEY=VALUE."
        )
    key, option_value = value.split("=", 1)
    if not key or not option_value:
        raise ConfigurationError(
            f"Invalid CUPS option {value!r}. Expected KEY=VALUE."
        )
    return key, option_value
