# manual-duplex

`manual-duplex` is a small Linux utility that recreates the useful part of a
proprietary "manual duplex" printer driver: print the front sides, wait until
CUPS has finished, tell the user how to reinsert the paper stack, and only then
print the back sides.

It is intended for printers that **do not have an automatic duplex unit**.
The initial use case is a Brother DCP-T310 on Fedora, but the implementation is
printer-agnostic and discovers media/color/quality options from CUPS instead
of hardcoding Brother-only flags.

## Scope

The MVP deliberately supports:

- PDF input;
- CUPS printers;
- A4, Letter, Legal and Folio physical paper sizes;
- portrait and landscape output;
- 1 or 2 logical pages per physical side;
- guided two-pass printing;
- normal or reverse back-pass ordering;
- optional 180-degree rotation of back sides;
- driver capability discovery for paper, quality and monochrome mode;
- optional preview;
- a Zenity GUI;
- a per-user desktop entry for PDF files.

Multiple copies and automatic physical refeed detection are intentionally out
of scope for v0.1. A printer must be calibrated once because software cannot
infer how a specific output tray stacks sheets or how the user physically
reinserts them.

## Why the PDF is composed first

The source document is first normalized into **physical sides**. For example,
with `--pages-per-side 2`:

```text
physical side 1 -> document pages 1 + 2
physical side 2 -> document pages 3 + 4
physical side 3 -> document pages 5 + 6
physical side 4 -> document pages 7 + 8
```

Only after that composition does `manual-duplex` split odd physical sides into
the front pass and even physical sides into the back pass.

When the number of physical sides is odd, the tool adds an explicit blank side
to the back pass. That blank page deliberately feeds the unmatched last sheet
through the printer so the stack does not drift out of alignment.

## Requirements

- Linux with CUPS
- Python 3.11+
- `lp`, `lpstat` and `lpoptions`
- `zenity` only for GUI mode
- `xdg-open` only for preview mode

On Fedora:

```bash
sudo dnf install cups-client zenity
```

Install the project in an isolated environment:

```bash
git clone https://github.com/sandovaldavid/manual-duplex.git
cd manual-duplex
pipx install .
```

For development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
```

## 1. Inspect the printer

```bash
manual-duplex printers
manual-duplex capabilities --printer Brother_DCP_T310
```

The capability command is the source of truth for driver-specific option names.
`manual-duplex` does not assume that every Brother or CUPS queue exposes
`ColorModel`, `BRMonoColor`, `cupsPrintQuality`, or the same media tokens.

## 2. Calibrate the physical refeed

Before the first real duplex job, perform a small 4-page physical test and note:

1. whether the back pass must run in `normal` or `reverse` sheet order;
2. whether backs need a 180-degree content rotation;
3. exactly how the printed stack must be placed back in the input tray.

Then save that validated behavior:

```bash
manual-duplex calibrate \
  --printer Brother_DCP_T310 \
  --back-order reverse \
  --back-rotation 0 \
  --refeed-instruction \
  'Reinsert the stack blank-side down, top edge entering first.'
```

The profile is stored under:

```text
~/.config/manual-duplex/config.json
```

Do not copy the example refeed instruction blindly. The purpose of calibration
is to record what was physically verified for the actual printer and tray.

## 3. Print

A4, one page per side:

```bash
manual-duplex print document.pdf \
  --printer Brother_DCP_T310 \
  --paper a4 \
  --orientation portrait
```

Two document pages per physical side, for four logical pages per sheet:

```bash
manual-duplex print document.pdf \
  --printer Brother_DCP_T310 \
  --paper a4 \
  --orientation landscape \
  --pages-per-side 2
```

Monochrome draft printing, when the driver exposes compatible options:

```bash
manual-duplex print document.pdf \
  --printer Brother_DCP_T310 \
  --monochrome \
  --quality draft
```

Preview the composed physical sides before sending anything to CUPS:

```bash
manual-duplex print document.pdf --preview
```

If the driver uses a nonstandard option that automatic capability mapping does
not recognize, pass it explicitly:

```bash
manual-duplex print document.pdf \
  --cups-option BRMonoColor=Mono
```

## GUI and GNOME integration

Launch the Zenity interface:

```bash
manual-duplex gui
```

Install a per-user PDF desktop entry:

```bash
manual-duplex install-desktop
```

The generated desktop entry uses the absolute installed executable path and the
standard `%f` local-file field code. It does not misuse `%u` as a Linux
username placeholder.

After installation, "Manual Duplex" can be selected as an application for PDF
files in GNOME Files and other freedesktop-compatible environments.

## Safety properties

`manual-duplex` intentionally:

- waits until the first CUPS job disappears from the active queue before asking
  for paper reinsertion;
- never starts the second pass without explicit user confirmation;
- pads an unmatched sheet with a blank back side;
- keeps printer-specific refeed behavior in a per-printer profile;
- fails instead of silently guessing an unsupported requested quality or
  monochrome option;
- keeps raw driver overrides explicit through `--cups-option KEY=VALUE`.

## License

MIT
