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

### Mark button (test build 2.1g)

Passes the emulator tests (`test_mark.py`), not yet tried on an SP-505:

- [ ] Version screen: version 2.1g, SYS checksum FA9FB088.
- [ ] (2.1g) MARK shows steady for samples trimmed in WAVE EDIT (START or END), and not for
      untrimmed ones, freshly recorded samples included; [L/R] on a trimmed sample clears it.
      After START + stop: MARK goes steady.
- [ ] (2.1e, hardware) END press didn't restart at all (played to the sample's end before looping
      the marks): the restart note was posted to the wrong queue. 2.1f posts it into the audio
      task's ring. Check the immediate restart, and that no audio past END is heard.
- [ ] (2.1d, hardware) after a START press, stopping the sample left MARK flashing; 2.1e stops
      the flashing when the sample stops (START kept, old END). Check gate pads (release), loops
      stopped with the pad / STOP, one-shots running to their end.
- [ ] (2.1d, hardware) a little audio past the END before the restart; 2.1e sends the restart
      straight to the audio task. Check the loop point is clean; the restart level matches the hit.
- [ ] (2.1c, hardware) random distortion and level changes during playback. 2.1d removes the
      END press's direct fade request (it bypassed the voice allocator); check playback after
      many marks / clears, with loops and other pads playing. If it remains, compare with 2.0.0.
- [ ] MARK flashes after the START press, is steady after the END press, disappears after a
      clear; flashing rate is comfortable (assumed 1 ms ticks: about twice a second).
- [ ] (2.1b, hardware) END press: the note kept playing to the original end before looping the
      marked range. 2.1c restarts it at the END press: check a loop now loops the marked part at
      once, a one-shot plays it once, at the same level as a pad hit, without a click or a double
      note; also with Gate pad play while holding the pad, and with a varispeed sample.
- [ ] PATTERN PLAY / SONG PLAY: hit a pad, press [L/R] during playback (MARK flashes), press
      again later (MARK steady); the next hit plays from the first press to the second.
      WAVE EDIT shows the same points.
- [ ] Press [L/R] on the marked sample: MARK disappears, the whole sample plays again.
- [ ] Hold [L/R], hit the pad: the note plays from the very beginning, MARK flashes; release,
      press at the end point -> MARK.
- [ ] The tag follows the last pressed pad (marked pad -> MARK, other pad -> nothing), survives
      leaving and re-entering the screen, and doesn't disturb the rest of the PAD BANK line
      (try a PITCH / CHOP / CARD bank). Check it stays after the screen updates itself (pattern
      running, tempo changes).
- [ ] The marked point is where you heard it (no noticeable lag), Standard / Long / lowest grade.
- [ ] Looping sample, Gate pad play (release before pressing [L/R] -> nothing), stereo sample,
      varispeed sample, Phrase play type, a pattern playing the pad.
- [ ] WAVE EDIT and the sample parameter screen: [L/R] + ZOOM still changes the vertical zoom, no
      mark is made; holding L/R there and hitting a pad changes nothing.
- [ ] A WAVE EDIT change of START / END on a marked sample removes MARK.
- [ ] Marked state after saving and a power cycle; a CLIPBOARD copy of a marked sample.
- [ ] Protected bank -> "Protected!"; the BPM shown afterwards matches WAVE EDIT's.

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
