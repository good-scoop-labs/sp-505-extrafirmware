# Troubleshooting

## "ERROR!!! Too Busy!"

The SP-505 shows this when its background work (loading sample data) falls behind, and it stops
playback. Varispeed notes are limited to keep this from happening (see
[polyphony](USER_GUIDE.md#polyphony-and-sample-grade)), but very dense playing on top of Standard
grade varispeed loops can still get there.

- Lower-grade samples (Long, lowest) are much cheaper for varispeed.
- Mono samples are half the work of stereo ones.
- Faster settings (+) also read sample data faster, like playing an extra pad.

If you can reproduce it, please open an issue with the sample grade, mono/stereo, the settings and
what you were playing.

## Varispeed seems to have no effect

- Is Reverse on? Reverse playback ignores varispeed.
- Was the sample already playing? Changes apply from the next trigger.
- Is the setting really non-zero in **this** sample's menu?
- Check the version screen (hold EXIT + ENTER at power-on): it should show version `2.00` and SYS checksum `FA9AD007`.

## The menu or effect switching is slower while varispeed loops play

Expected: varispeed runs inside the audio interrupt, which always comes first, so the screen,
buttons and effect changes get the processing time that's left. Faster settings, Standard grade,
stereo and two loops at once cost the most; Long or lowest-grade mono loops are the lightest.
With no varispeed note playing, everything responds as with the stock firmware.

## Play Type won't go to Phrase

That's intended while Varispeed or Fine Tune is non-zero. Set both to 0 first.

## The BPM stopped at 40.0 or 200.0

That's the SP-505's BPM range. Turning back toward 0 returns the original value.

## Update problems

| What you see | What to do |
|---|---|
| The patcher (web or Python) says the input isn't the official v1.02 file | Use the unmodified official `sp505.prg` (MD5 `20bb3983ec3144793deefd34075e7e58`). |
| "Wrong Card !!" on the update screen | The card couldn't be read. Format it in the SP-505, copy both files again. |
| "NOR → CARD" / "Copying…" | You held only two buttons. Power off and hold **SONG + PTN + BPM**. |
| Update refused / checksum error | The file on the card is damaged. Copy it again. Nothing was written to the SP-505. |
| The version screen shows something else | The update didn't run. Repeat the update steps. |

## Going back to stock

See [INSTALL.md → Going back to the stock firmware](INSTALL.md#going-back-to-the-stock-firmware).
