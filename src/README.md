The firmware build. `extrafirmware.py` builds it from the official v1.02 `sp505.prg` (it's what
`../patch.py` runs); each part of the firmware has its own module, and `layout.py` lists every
address used. `tools/` holds the V850 emulator and the test suite. See `../docs/DEVELOPMENT.md`.
