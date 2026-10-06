# Development tools

Standalone scripts, run by hand from a shell. Nothing here is imported by the
addon: `device_gps/tools/` has no `__init__.py` that reaches into this
directory, and nothing in `__manifest__.py` references it.

They live under `dev/` so that is obvious. `gps_simulator.py` used to sit
directly in `tools/`, where it read as module code — 479 lines of it, importing
`requests` and `argparse`, next to files the addon actually loads.

## gps_simulator.py

Generates GPS device movement, either pushed live at a running instance or
written out as demo data.

```bash
python3 device_gps/tools/dev/gps_simulator.py --help
```
