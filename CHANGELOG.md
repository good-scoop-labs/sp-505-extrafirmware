# Changelog

Releases are numbered like the SP-505's own system versions: `2.10`, `2.20`, ... (the first
release was numbered 2.0.0). The SP-505's version screen (hold EXIT + ENTER at power-on) shows
the version and SYS checksum listed for each release.

## 2.10 (2026-11-09)

Version screen: version `2.10`, SYS checksum `FA9FB0F6`. Built from the official v1.02 system
program.

### Added
- **Mark button** on [L/R], like the Mark button of an SP-303: while the last pressed pad's sample
  plays, the first press sets its START and the second its END at the point you hear; the END
  press restarts playback from the new START at once (a loop then loops the marked part). Holding
  [L/R] while hitting the pad starts the mark at the beginning of the sample. Pressing [L/R] on a
  marked sample clears the marks (START / END back to the whole sample).
- The PATTERN PLAY and SONG PLAY screens show **MARK**, steady whenever the sample's START or END
  differs from the whole recording (however it was set, WAVE EDIT included; [L/R] then clears it)
  and flashing while the END is still to be set (it stops flashing when the sample stops before
  the END), like the SP-303's Mark button (the SP-505 has no light in the [L/R] button).
- [L/R] keeps its vertical-zoom function in WAVE EDIT and on the sample screens with a waveform.

### Notes
- Varispeed and everything else from 2.0.0 is unchanged; normal playback is identical.
- The restart at the END press happens inside the SP-505: it isn't sent to MIDI OUT and isn't
  recorded into a pattern.

Development history (test builds 2.1a–2.1g) is in [docs/DEV_NOTES.md](docs/DEV_NOTES.md).

## 2.0.0 (2026-10-29)

Version screen: version `2.00`, SYS checksum `FA9AD007`. Built from the official v1.02 system
program.

First public release of SP-505 EXTRAfirmware, numbered 2.0 to follow on from the official firmware (v1.02).

### Added
- **Varispeed** sample parameter: −24 to +12 semitones, 0 in the middle; pitch and speed change
  together, like a tape or turntable.
- **Fine Tune** sample parameter: −50 to +50 cents on top of Varispeed.
- **BPM follows the speed**: the sample's BPM is always its original BPM × its speed. It updates
  on screen as you turn either setting, Measure and Beat edits keep it, and turning back to 0
  returns the exact original value. A copied sample (CLIPBOARD copies don't take the two settings
  along) gets its original BPM back as soon as it's shown.
- **Play Type**: a non-zero Varispeed / Fine Tune switches Phrase to Single, and Phrase can't be
  selected while either is set.
- **Polyphony weighting**: a varispeed note counts as 6 (Standard grade, or stereo), 4 (Long) or
  3 (lowest grade) of the 8 voices, to prevent "Too Busy!" overloads. Varispeed notes are never
  cut just to make room when nothing else is playing (for example two Long loops while
  resampling).
- Two mono Long / lowest-grade varispeed notes can play at the same time. Standard-grade and
  stereo varispeed notes play one at a time. Older notes fade out when replaced.
- A new recording on a pad starts with Varispeed and Fine Tune at 0.
- **Web patcher** (`docs/index.html`, for GitHub Pages) and Python patcher (`patch.py`), with
  identical results.

### Notes
- Samples with both settings at 0 play exactly as with the stock firmware.
- Reverse playback ignores varispeed.
- Varispeed playback takes processing time from the screen and buttons, so menus and effect
  switching respond more slowly while varispeed loops play (least with Long / lowest-grade mono).

Development history (internal builds v1–v32) is in [docs/DEV_NOTES.md](docs/DEV_NOTES.md).
