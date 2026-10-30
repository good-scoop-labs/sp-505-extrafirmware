# Status

Where the project stands, what still needs testing and ideas that weren't pursued. For how
things work see [DEVELOPMENT.md](DEVELOPMENT.md); for the full history see
[DEV_NOTES.md](DEV_NOTES.md).

## Confirmed on hardware

Up to development build v28 (all of these still behave the same in 2.0.0):

- Varispeed playback, centred menu, Fine Tune, BPM shown and updated as the settings change.
- Play Type: Phrase switches to Single and stays locked out while a setting is non-zero.
- No "Too Busy!" with many Normal pads; polyphony weighting by grade; two mono Long /
  lowest-grade varispeed loops together, a third one replacing the oldest.
- Normal samples play as with the stock firmware.

## Needs a hardware test (changed after the last hardware test)

Passes the emulator tests, not yet confirmed on an SP-505:

- [ ] Version screen (EXIT + ENTER at power-on): version 2.00, SYS checksum FA9AD007.
- [ ] Varispeed menu shows 0 in the middle, cleanly, when scrolling through it.
- [ ] CLIPBOARD copy of a varispeed sample: the copy plays at normal speed and shows the original
      BPM once its parameter menu is opened.
- [ ] Varispeed / Fine Tune back to 0 returns the exact original BPM.
- [ ] Measure and Beat edits on a varispeed sample keep the varispeed BPM.
- [ ] Recording over a pad whose old sample had Fine Tune set: the new sample's Fine Tune is 0.
- [ ] Resample (Auto) with two Long varispeed loops: neither is cut.
- [ ] Menus / effect switching while varispeed loops play (engine trimmed by 5-14%).

## Known limitations

- Reverse playback ignores varispeed.
- A copied sample's BPM is corrected when its BPM is shown, not at the moment of the copy (the
  CLIPBOARD paste routine wasn't found; it doesn't go through the parameter setter).
- Varispeed playback runs on the main CPU from flash, so it takes processing time from the screen
  and buttons; Standard grade, stereo and fast settings cost the most.

## Ideas not pursued

- **Faster flash timing.** The bus wait-state register (DWC) is never written, so flash runs with
  the reset default (maximum waits). Fewer waits would speed up all flash code, the engine
  included, but the right value depends on the flash chip's timing (Sharp LH28F800BJE, IC36), and
  a wrong value can stop the unit from starting, possibly beyond the card updater's reach.
  Only with the datasheet and a way to recover.
- **Smaller engine trims** (each about 1-2% at most): split blocks at the chunk crossing with a
  computed jump instead of testing every frame; cheaper READY check in the hook stub; `movhi`
  instead of `mov32` for a few RAM addresses.
- **Per-pad table (VTAB).** Pad set-up and the parameter hook still record each pad's settings in
  VTAB, but the engine reads the sample record instead. Could be removed; it's harmless and
  removing it changes live code, so it was left alone.
- **Copying the settings with the sample.** Instead of resetting a copy's BPM, the copy could keep
  Varispeed / Fine Tune; that needs the paste routine to be found.

## Local files you need (never commit them)

| File | What for |
|---|---|
| `official/sp505.prg` | the official v1.02 file (BOSS download): input for every build |
| `rom_dump/cpu_mask_rom_v1.00.bin` | the SP-505's CPU mask ROM (128 KB): needed by the emulator tests |

Both are Roland code and are excluded by `.gitignore`.
