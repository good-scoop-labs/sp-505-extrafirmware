# User guide

Everything the stock SP-505 does still works the same. EXTRAfirmware adds two settings per sample
and changes a few behaviours when they're in use.

## The new settings

Both are at the bottom of a sample's parameter menu, below Measure and Beat.

### Varispeed

`-24 … -1, 0, +1 … +12` (semitones)

Plays the sample faster or slower, so pitch and length change together, like a tape or turntable
speed change. 0 (no change) is in the middle: turn left to go down (slower, lower), right to go up
(faster, higher).

| Setting | Speed |
|---|---|
| −24 | ¼ speed (two octaves down) |
| −12 | ½ speed (one octave down) |
| −7 | 0.67× (a fifth down) |
| 0 | as recorded |
| +7 | 1.5× |
| +12 | 2× (one octave up) |

### Fine Tune

`-50 … 0 … +50` (cents; 100 cents = 1 semitone)

Adds to Varispeed for settings between semitones. Varispeed −7 with Fine Tune +23 plays
6.77 semitones down. Fine Tune works on its own too, with Varispeed at 0.

A sample counts as "varispeed" when either setting isn't zero. With both at 0 it plays
exactly as with the stock firmware.

### When changes take effect

Settings are read when a pad starts playing. A sample that's already playing keeps its speed;
the next trigger uses the new setting.

### Copying and recording samples

Varispeed and Fine Tune are stored with the sample like its other parameters, and playback always
follows the values the sample's own menu shows.

- **CLIPBOARD copies** don't take the two settings along: a copy of a varispeed sample plays at
  normal speed. Its BPM goes back to the original value as soon as it's shown (for example when
  you open the copy's parameter menu), so the BPM always matches the speed you hear.
- **A new recording** on a pad starts with Varispeed and Fine Tune at 0, whatever the pad's
  previous sample used.

## BPM follows the speed

When you change Varispeed or Fine Tune, the sample's BPM is recalculated for the new speed and
the screen updates straight away. A 120.0 BPM loop shows 113.3 at −1, 60.0 at −12 and 123.5 at
+50 cents.

- The SP-505's BPM range is 40.0–200.0. Results outside it stop at the limit (120 BPM at −24
  shows 40.0).
- Turning back returns the exact original BPM, even after hitting a limit.
- Changing **Measure** or **Beat** on a varispeed sample keeps the varispeed: the BPM is the new
  value at the sample's speed (a 120.0 sample at −12 shows 60.0; doubling Measure shows 120.0).
- The rule is always: BPM = the sample's original BPM × its speed. If a BPM doesn't match it (a
  copied sample, for example), the SP-505 corrects it the next time it shows that sample's BPM.

## Play Type

Phrase play type time-stretches a sample to the tempo, which doesn't combine with varispeed.
So:

- Setting Varispeed or Fine Tune to anything other than 0 switches a Phrase sample to
  **Single**.
- While either setting is non-zero, Play Type can't be set to Phrase.
- Going back to 0 leaves Play Type on Single; set Phrase again yourself if you want it.

## Polyphony and sample grade

Varispeed playback takes much more processing than normal playback, more so for higher sampling
grades. To keep the SP-505 out of "Too Busy!" overloads, a playing varispeed note counts as
several of the 8 voices:

| Varispeed sample | Counts as | Other voices that can play |
|---|---|---|
| Mono, Standard grade | 6 | 2 |
| Mono, Long grade | 4 | 4 |
| Mono, lowest grade | 3 | 5 |
| Stereo, any grade | 6 | 2 |

When you hit more pads than that, the SP-505's normal voice stealing fades out the oldest voices,
which can include the varispeed note itself. Once no varispeed note is playing, all 8 voices are
available again.

### How many varispeed notes at once

- **Mono Long or lowest-grade samples:** two varispeed notes can play together. A third one
  replaces the older of the two, which fades out.
- **Standard grade or stereo samples:** one varispeed note at a time. Starting another varispeed
  note fades out the one that's playing.
- Pads started at exactly the same moment (for example on the same pattern step) follow the same
  rules. Extra varispeed notes are dropped silently.
- If only varispeed notes are playing (for example two Long varispeed loops while resampling,
  when the recorder holds some voices), the weighting doesn't cut them to make room for a new
  varispeed note. When other pads are playing too, the oldest voice is faded out as usual, and that
  can be a varispeed note.
- Samples with both settings at 0 are never affected by these limits.

## Limitations

- **Reverse:** a sample with Reverse on plays at normal speed. Varispeed isn't applied to reverse
  playback.
- **Play Type switch:** the switch to Single happens when you edit Varispeed / Fine Tune in the
  sample menu.
- **When the BPM is corrected:** a BPM that doesn't match the rule (a copied sample) is corrected
  when that sample's BPM is shown on screen, not before. Until then, features that use the
  sample's BPM (such as BPM sync) see the old value.
- **Measure edits at the BPM limits:** if a varispeed sample's BPM sits at 40.0 or 200.0, the
  SP-505 may refuse Measure / Beat changes that would push it out of range, as it always does.
- **Sound:** speed changes use linear interpolation. Very low settings sound darker and slightly
  grainy, much like slowing a sampler down.
