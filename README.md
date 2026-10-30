# SP-505 EXTRAfirmware

**SP-505 EXTRAfirmware** is custom system firmware for the **BOSS SP-505** sampler. It adds
tape-style **varispeed** to every sample: pitch and speed change together, like slowing down or
speeding up a turntable or tape. The setting is saved with the sample.

- **Varispeed**: −24 to +12 semitones per sample, with 0 (no change) in the middle
- **Fine Tune**: −50 to +50 cents on top of Varispeed
- **BPM follows**: the sample's BPM is recalculated as you turn either knob
- Samples with Varispeed and Fine Tune at 0 play exactly as with the stock firmware
- Built on the official v1.02 system program; every stock feature stays

> **Current release: 2.0.0** (version screen: version `2.00`, SYS checksum `FA9AD007`).
> See [CHANGELOG.md](CHANGELOG.md).

## How it is distributed

This repository contains **no BOSS/Roland code**. You supply the official SP-505 system update
v1.02 file (`sp505.prg`), which BOSS still offers on its
[SP-505 support page](https://www.boss.info/us/support/by_product/sp-505/) ("SP-505 System Update
v1.02 SmartMedia"). The included patcher checks that it's the right file, adds the
EXTRAfirmware code, fixes the checksums and writes a new `sp505.prg` that you install with the
SP-505's normal card update.

Two ways to do that, with identical results:

- **In the browser (easiest):** open the
  [web patcher](https://good-scoop-labs.github.io/sp-505-extrafirmware/) (this repository's
  GitHub Pages site) and drop the official `sp505.prg` onto it. Nothing is uploaded; it all runs
  locally in the page.
- **With Python:**
  ```
  python3 patch.py path/to/official/sp505.prg
  # -> out/sp505.prg
  ```

Full instructions: **[docs/INSTALL.md](docs/INSTALL.md)**

## Documentation

| | |
|---|---|
| [Installing (and going back to stock)](docs/INSTALL.md) | step by step, with how to check the install |
| [User guide](docs/USER_GUIDE.md) | the new settings, polyphony rules, limitations |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | "Too Busy!", update errors, common questions |
| [Changelog](CHANGELOG.md) | what changed in each release |
| [Development](docs/DEVELOPMENT.md) | how the firmware works, building, tests, releasing |
| [Status](docs/STATUS.md) | what's confirmed on hardware, what still needs testing |

## Compatibility

- BOSS SP-505 only. The update replaces the whole system program with the modified v1.02, so the
  unit's previous system version doesn't matter.
- Input must be the official v1.02 `sp505.prg` (MD5 `20bb3983ec3144793deefd34075e7e58`).
  The patcher refuses anything else.

## Disclaimer

Unofficial, not affiliated with or endorsed by BOSS / Roland. Updating system firmware always
carries some risk: a power cut while the SP-505 is writing its flash memory can leave it unable
to start, exactly as with an official update. You can return to the stock firmware at any time
with the official file (see [INSTALL](docs/INSTALL.md#going-back-to-the-stock-firmware)).
Use at your own risk.

Please don't upload `.prg` files (official or patched) to this repository, its issues or its
releases. Share the patcher instead.

## License

The code in this repository is released under the MIT License ([LICENSE](LICENSE)).
BOSS and SP-505 are trademarks of Roland Corporation.
