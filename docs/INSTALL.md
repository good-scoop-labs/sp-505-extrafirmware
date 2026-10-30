# Installing SP-505 EXTRAfirmware

The install has three parts: make the firmware file on a computer, copy it to a SmartMedia card,
then run the SP-505's built-in card update.

## What you need

- A BOSS SP-505
- A SmartMedia card the SP-505 can read (format it in the SP-505 if in doubt), and a card reader
- The **official SP-505 system update v1.02** files: `sp505.prg` and `SMPINFO0.SP0`. BOSS still
  offers them on the [SP-505 support page](https://www.boss.info/us/support/by_product/sp-505/):
  download **"SP-505 System Update v1.02 SmartMedia"** (PC or Mac) and unzip it. Its readme also
  has BOSS's own update instructions.
- Only for the Python patcher: **Python 3.8 or newer** (macOS and Linux usually have it; on Windows get it from
  [python.org](https://www.python.org/downloads/))
- For the web patcher: just a browser. For the Python patcher: this repository (the green
  **Code → Download ZIP** button on GitHub, or a release zip)

## 1. Back up

Back up your samples and patterns to a card before updating. The system update doesn't touch
the user data area, but a backup costs nothing.

## 2. Make the firmware file

**Easiest: the web patcher.** Open the project's web patcher page, drop the official `sp505.prg`
onto it and click **Download sp505.prg**. The page checks the file and the result exactly like
the Python patcher, and nothing leaves your computer. Then continue with step 3.

**Or with Python:** open a terminal in the folder you downloaded and run:

```
python3 patch.py path/to/official/sp505.prg
```

(on Windows: `py patch.py path\to\official\sp505.prg`)

You should see:

```
SP-505 EXTRAfirmware 2.0.0 written to out/sp505.prg
After updating, the version screen (hold EXIT + ENTER at power-on) shows
    version 2.00, SYS checksum FA9AD007
```

If it says the input isn't the official v1.02 file, you have a different file (another version,
a damaged download, or an already modified one). Nothing is written in that case.

## 3. Prepare the card

Copy these two files to the card, in the same place the official BOSS update instructions put
them:

- `out/sp505.prg` (the file you just made)
- `SMPINFO0.SP0` from the official update, unchanged

Eject the card safely from the computer.

## 4. Run the update on the SP-505

1. Turn the SP-505 off and insert the card.
2. Hold **SONG + PTN + BPM** (all three) and turn the power on. Keep holding until the update
   starts.
3. Follow the messages on the display. **Don't turn the power off while it's writing.**
4. When it says it's finished, turn the SP-505 off and on again.

Good to know:

- The updater checks the whole file before it writes anything. A damaged or wrong file is
  refused and the flash memory isn't touched.
- Holding only *two* of those buttons runs a different routine that copies the current firmware
  to the card ("NOR → CARD"). If you see that, turn off and try again with all three.
- "Wrong Card !!" means the card couldn't be read. Format it in the SP-505, copy the files again
  and retry.

## 5. Check the installation

Hold **EXIT + ENTER** while turning the power on. The checksum screen should show version
**2.00** and, on the `SYS` line, checksum **FA9AD007**. (The stock firmware shows 1.02 and
FA86B012.)

Then open a sample's parameter menu (where Level, Panpot, Play Type, Measure and Beat are):
there are two new rows at the bottom, **Varispeed** and **Fine Tune**. See the
[user guide](USER_GUIDE.md).

## Going back to the stock firmware

Run the same card update with the **unmodified official** `sp505.prg` and `SMPINFO0.SP0`.
The version screen then shows version 1.02, SYS checksum `FA86B012`.

Your samples keep their Varispeed / Fine Tune values in otherwise unused bytes. The stock
firmware ignores them and plays every sample at normal speed. They come back into effect if you
install EXTRAfirmware again. Sample BPM values that varispeed changed stay as they are.

## Updating to a newer EXTRAfirmware release

Download the new release and repeat steps 2 to 5 with the official v1.02 file. The patcher always
starts from the official file, so you never patch a patched file.
