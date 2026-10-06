# Repository instructions

`manual-duplex` is a bounded Linux/CUPS utility. Keep the implementation small
and capability-driven.

- `main` is the stable branch. Make changes through focused branches and PRs.
- Support Python 3.11+.
- Do not hardcode Brother-specific driver options when CUPS can expose them.
- Treat physical paper order/orientation as calibrated printer behavior, not a
  universal assumption.
- Preserve the invariant that the second pass cannot start before the first
  CUPS job has finished and the user has explicitly confirmed reinsertion.
- Add tests for page ordering, blank-side padding, capability mapping and
  configuration changes.
- Do not expand into printer management, scanning, generic PDF editing, or a
  custom print server without a separate validated need.
