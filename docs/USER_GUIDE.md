# User guide

Everything the stock SP-505 does still works the same. EXTRAfirmware adds two settings per sample
(and changes a few behaviours when they're in use), and a Mark button on [L/R] (see
[Mark button](#mark-button-lr)).

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

## Mark button ([L/R])

The **[L/R]** button next to the display works like the Mark button of an SP-303: it marks a
sample's start and end while it plays, and clears the marks again.

**Marking**

1. Hit a pad. While it plays, press **[L/R]**: the sample's **START** is set to the point you're
   hearing.
2. Press **[L/R]** again later in the sample: its **END** is set there, and playback jumps
   straight back to the new START, like on an SP-303. A looping sample now loops the marked part;
   a one-shot sample plays the marked part once. The sample is now **marked**.

To start at the very beginning of the sample, **hold [L/R] and then hit the pad**: START is set to
the beginning and the sample plays from there. Let go of [L/R], then press it where the sample
should end.

**Clearing:** press **[L/R]** when the last pad you pressed has a marked sample (steady MARK).
START and END go back to the whole sample. This works whether or not the sample is playing. The
next press marks a new START.

**What the display shows:** the SP-505 has no light in the [L/R] button. Instead, the PATTERN
PLAY and SONG PLAY screens show the state of the last pad you pressed at the right end of the
PAD BANK line:

| Display | Meaning |
|---|---|
| **MARK** steady (white on black) | the sample's START or END isn't at the edge of the recording, however it was set (Mark, WAVE EDIT, a copy); the next press clears them |
| **MARK** flashing | a START was just set with [L/R]; the next press sets END |
| nothing | the sample plays in full; the next press sets START |

If you set a START and then the sample stops before you set an END, MARK stops flashing, as on
the SP-303: the sample keeps the new START and its previous END, so MARK then shows steady (and
the next press clears).

Details:

- Marks are for the **last pad you pressed** (the pad the sample menus show). Setting START or
  END needs the sample to be playing; pressing [L/R] when it isn't playing (and isn't marked)
  does nothing.
- The first press (START) doesn't interrupt the playing sample. The second press (END) restarts
  it from the new START at once, at the level of your pad hit. The restart happens inside the
  SP-505: it isn't sent to MIDI OUT and isn't recorded into a pattern.
- START and END are the same points WAVE EDIT shows and edits. The sample data isn't changed, so
  you can always move them back in WAVE EDIT. The BPM and Measure are recalculated as for a WAVE
  EDIT change (and the BPM still follows Varispeed / Fine Tune).
- "Marked" simply means START or END differs from the whole recording, so MARK also shows for a
  sample trimmed in WAVE EDIT, and [L/R] clears that trim too (as it would on an SP-303, where a
  lit MARK means the next press clears it). A CLIPBOARD copy of a trimmed sample shows MARK as
  well.
- Like WAVE EDIT, marks keep START and END at least about 70 ms apart (193 steps). An END press
  that would be before that (for example right after hitting the pad again) moves START instead,
  and the next press is the END again. A START press too close to END is ignored.
- Hitting a different pad starts over with START for that pad.
- On a protected bank the SP-505 shows "Protected!" and nothing changes (the same protect check
  the SP-505's own edits use). The preset banks are protected, so they never show the tag.
- Reverse samples aren't marked (a marked sample that is later set to Reverse can still be
  cleared).
- **In WAVE EDIT and on the sample screens with a waveform, [L/R] keeps its normal function**
  (hold it and use ZOOM IN / OUT for the vertical zoom). It only marks on screens where it isn't
  used for anything else.

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
