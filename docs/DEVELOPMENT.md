# Development

## Repository layout

```
patch.py                 user-facing patcher: official v1.02 sp505.prg -> EXTRAfirmware sp505.prg
docs/index.html          web patcher (GitHub Pages); data in docs/extrafirmware-patch.js
src/
  extrafirmware.py       the build: applies the parts below to the official file, sets VERSION
  layout.py              every address used: stock firmware locations, our flash and RAM map
  menu.py                Varispeed / Fine Tune menu rows, descriptors, speed tables
  engine.py              the varispeed engine (audio-block hook, POST), idle-task init,
                         pad set-up and parameter-handler hooks
  voices.py              polyphony weighting (pad voice allocator)
  bpm.py                 BPM rule and Play Type rules (value edit, setter, header line)
  v850asm.py             small V850E assembler used by the modules above
  sp505fw.py             .prg container: load / verify / fix checksums (also a small CLI)
  tools/                 V850 disassembler and emulator, the test suite, the web-patch generator
docs/DEV_NOTES.md        full reverse-engineering and development log
```

## How it works (short version)

The SP-505 renders audio in blocks of 16 frames in an interrupt routine that lives in the CPU's
internal mask ROM. The firmware in flash only sets voices up. The varispeed engine
(`src/engine.py`) hooks in like this:

1. **Start-of-block hook** (the ROM calls a function pointer at `ep+4004`; installed at
   `0x1BB672`). The stub at `0x1D1600` goes straight back to the ROM unless a varispeed voice is
   playing or a note is starting.
2. **Take-over**: when a note starts on a pad whose Varispeed/Fine Tune isn't zero, the engine
   owns that voice. It streams the sample itself with the ROM's own decoder and bookkeeping,
   resamples it (linear interpolation, 16.16 step) and writes the 16 output samples into the
   voice's ROM decode buffer.
3. **ROM-mix**: the voice's format field is temporarily set to a value whose decoder `switch`
   entry is a bare return, and the fields the ROM's bookkeeping would advance are neutralised.
   The ROM then does volume, envelope, pan, effect send and mixing for that voice as usual.
4. **POST**: the interrupt's return address is redirected so that, with interrupts off and before
   any task runs, the patched fields are restored from an undo list.

Other patches: the pad voice allocator (varispeed notes count as several voices), the sample menu
(two rows, signed parameter descriptors), the audio task's parameter handler and the pad set-up
(per-pad settings table), the UI's generic value edit (BPM recalculation, Play Type rules), the
parameter setter's entry (BPM rule for Measure / Beat / trim edits, Fine Tune reset on a new
recording) and the BPM read of the sample header line (repairs copied samples).

Memory used: DRAM `0x428000–0x42A000` (unreferenced by the stock firmware). Flash: free space in
block 13 (`0x1D0000–0x1DFFFF`), plus a few call sites. Block 14 (the card updater) is never
touched. `src/layout.py` lists every address; `docs/DEV_NOTES.md` has the reasoning behind them.

## Building

```
python3 patch.py official/sp505.prg -o out/sp505.prg      # release build, checked against the release MD5
python3 src/extrafirmware.py official/sp505.prg out.prg    # same build, no MD5 check (for development)
```

## Tests

The tests run the real audio code in a V850 emulator (`src/tools/v850emu.py`) and compare the
engine against the ROM's own playback. They need a dump of the SP-505's **CPU mask ROM**, which
isn't distributed. Put it at `rom_dump/cpu_mask_rom_v1.00.bin` (or set `SP505_MASK_ROM`).

```
cd src/tools
./regress.sh ../../out/sp505.prg extrafirmware   # 40 checks, all must print "ok"
MULTI=1 python3 fuzz.py ../../out/sp505.prg extrafirmware 3000 1
python3 test_bpm.py ../../out/sp505.prg extrafirmware ../../official/sp505.prg
```

What `regress.sh` covers:

- Normal pads are bit-identical to the ROM.
- The engine at exactly 1.0x is bit-identical to the ROM for all three sample grades, with loops,
  stops, multi-voice notes, all formats, pan and send.
- Two staggered lower-grade notes match the ROM.
- The time-stretch override works.
- Interpolation accuracy, including Fine Tune.

`fuzz.py` does random starts, stops and retriggers, several per block. It checks that no voice is
left patched, that POST returns correctly and that the note limits hold.

`test_bpm.py` runs the UI-side BPM code (the edit wrapper, the setter wrapper and the header
repair) with the real getter and natural-BPM routine, in both message orders, and compares the
BPM rule with a Python model for every setting.

Other tools: `test_speed.py` (accuracy at a setting), `prof30.py` (flash halfwords fetched per
block, the main cost metric, with a hot-spot list),
`cmp_builds.py` (two builds block by block), `difffuzz.py` (the fuzz scenario on two builds in
lockstep; use it to prove an optimisation changes nothing), `unity_vs_rom.py`.

## Making a release

1. Make the change in the module it belongs to (addresses go in `src/layout.py`).
2. Set `SYSTEM_VERSION` in `src/extrafirmware.py` (exactly 4 characters, e.g. `b'2.01'`). It's
   written into the image header (shown on the EXIT + ENTER screen and by the card updater) and
   into the `EXT Ver.` text of an internal test screen.
3. Build it (`python3 src/extrafirmware.py ...` prints the version-screen checksum), run `regress.sh`,
   `fuzz.py` and `test_bpm.py` (and `difffuzz.py` against the previous build for changes that
   shouldn't alter the sound), and test on hardware.
4. In `patch.py` update `RELEASE`, `VERSION_SCREEN`, `OUTPUT_MD5` and `CHECKSUM`.
5. Regenerate the web patcher data:
   `python3 src/tools/make_web_patch.py official/sp505.prg out/sp505.prg docs/extrafirmware-patch.js X.Y.Z 2.01 CHECKSUM`
   It stores only the changed bytes and the SHA-256 of the official input and of the result.
6. Update `CHANGELOG.md`, the README's "Current release" line and the user docs (version string
   and checksum appear in INSTALL and TROUBLESHOOTING).
7. Commit, tag `vX.Y.Z`, and create a GitHub release from the tag with the changelog entry as the
   notes. Don't attach `.prg` files.

## Web patcher / GitHub Pages

`docs/index.html` + `docs/extrafirmware-patch.js` are a self-contained page (no server code, no
uploads). To publish it: repository **Settings → Pages → Build and deployment → Deploy from a
branch → `main` / `/docs`**. The site is then at `https://<user>.github.io/<repo>/`, and the
Markdown docs in `docs/` are served next to it (`INSTALL.html`, `USER_GUIDE.html`, ...).
To try it locally: `cd docs && python3 -m http.server`, then open http://localhost:8000.

The page checks the input's SHA-256 against the official v1.02 file, applies the changed-byte runs
and checks the result's SHA-256 before offering the download. It also recognises zip files and
already-patched files.
