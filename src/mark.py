"""Mark button: [L/R] marks START / END of the last pressed pad's sample while it plays, and
clears the marks again, like the Mark button of an SP-303. The SP-505 has no LED behind L/R, so
a marked sample is shown on the PATTERN PLAY / SONG PLAY screens instead: an inverted "MARK"
tag at the right end of the PAD BANK box, solid when START and END are set, flashing while a START
is set and the END is still due (as the SP-303's Mark button lights / flashes).

Key path. The UI's key dispatcher (0x1A065A) sends every key through a key-class table; L/R (21)
is class 3 with ZOOM IN / OUT, whose handler 0x19BDF8 only calls the current screen's slot +28.
Only the WAVE EDIT screen and the sample screens with a waveform use L/R there (held, ZOOM changes
the vertical zoom); everywhere else the key did nothing. MARKKEY replaces the class 3 entry of
the handler table: ZOOM keys, and L/R on a screen whose slot +28 uses it, go to the stock handler
unchanged; otherwise a press of L/R is a mark press for the sample of the last pressed pad
(system params 184 / 185, as the sample menu uses them):

  protected bank        "Protected!", nothing changed
  END due               (a START was set with Mark) END = play position (if at least MIN_LEN
                        after START, else this press moves START)
  sample marked         clear: START / END = the whole recorded sample (params 37 / 42, the
                        limits WAVE EDIT uses); works whether or not the sample plays
  reverse sample        nothing
  not playing           nothing
  otherwise             START = play position (if at least MIN_LEN before END); END due

"Marked" means the sample's START or END isn't at the edge of its recorded data, however they
were set (Mark, WAVE EDIT, a CLIPBOARD copy, ...), so the tag always tells whether the sample
plays in full.

Holding L/R while hitting a pad sets START to the very beginning of the recorded data (PADW,
before the note starts, so it plays from the beginning); the next L/R press sets END. The held
state comes from L/R's press / release events (MARK_RAM +12).

The play position is voice +24 of a playing voice of the sample (active, not fading, stopping or
just starting; the earliest position if there are several), in the units of the stock START /
END positions. START / END are set with WAVE EDIT's commits (0x1A3BB0 / 0x1A3B14: parameter,
Measure, BPM, project changed), so the EXTRAfirmware BPM rule applies as usual. Setting the END
restarts playback at once from the new START, like the SP-303 (RETRIG: the pad's note is sent
again the way a pad hit is, and the audio task's note-on replaces the playing note as for a second
hit); a START press leaves the note playing, and if playback stops there the sample keeps the new
START with its old END.

Whether an END press is due (a START was set with Mark) is kept in RAM (MARK_RAM); the idle loop
ends it when the sample stops playing.

The tag is redrawn after the two play screens' enter (frame) and draw slots, after every pad key
(the last pressed pad decides what it shows) and after each mark press. Preset banks are
skipped: they can't be marked and their bank names reach the tag's area.
"""
import struct
import layout as L
from layout import GETTER, UI_REDRAW, VOICE_REC, SLOTS, NSAMPLES, MARK_RAM, MARK_MAGIC, MIN_LEN
from sp505fw import put
from v850asm import *

SAVED = ('lp', 'r20', 'r21', 'r22', 'r23')
FRAME = 4 + 4 * len(SAVED)              # 0[sp]: outgoing 5th argument


def prologue(a):
    a.emit(addi, -FRAME, 'sp', 'sp')
    for i, r in enumerate(SAVED):
        a.emit(st_w, r, 4 + 4 * i, 'sp')


def epilogue(a):
    for i, r in enumerate(SAVED):
        a.emit(ld_w, 4 + 4 * i, 'sp', r)
    a.emit(addi, FRAME, 'sp', 'sp')
    a.emit(jmp_reg, 'lp')


def emit_cursample(a, lbl_none):
    """r20 = sample of the last pressed pad, r21 = bank; lbl_none if no sample (pad 16)"""
    a.emit(movea, L.PARAM_CURPAD, 'r0', 'r6'); a.emit(mov_i, -1, 'r7'); a.call(GETTER)
    a.emit(mov_rr, 'r10', 'r20')
    a.emit(movea, L.PARAM_CURBANK, 'r0', 'r6'); a.emit(mov_i, -1, 'r7'); a.call(GETTER)
    a.emit(mov_rr, 'r10', 'r21')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(mov_rr, 'r21', 'r7'); a.call(L.PADSAMPLE)
    a.emit(mov_rr, 'r10', 'r20')
    a.emit(cmp_rr, 'r0', 'r20'); a.bfar('lt', lbl_none)
    a.emit(movea, NSAMPLES - 1, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r20'); a.bfar('gt', lbl_none)


def emit_playing(a, n):
    # idle loop: r13 = 1 if a voice of the sample at MARK_RAM+4 is active (r21 MARK_RAM, r25 ep,
    # r26 voice slot 0); clobbers r9, r11, r12, r14
    a.emit(ld_w, 4, 'r21', 'r9')
    a.emit(ld_bu, 4021, 'r25', 'r11'); a.emit(mov_rr, 'r26', 'r12'); a.emit(mov_i, 0, 'r13')
    a.label(n)
    a.emit(cmp_rr, 'r0', 'r11'); a.branch('z', n + 'd')
    a.emit(shr_i, 1, 'r11'); a.branch('nc', n + 'n')
    a.emit(ld_h, 10, 'r12', 'r14'); a.emit(cmp_rr, 'r9', 'r14'); a.branch('nz', n + 'n')
    a.emit(mov_i, 1, 'r13')
    a.label(n + 'n')
    a.emit(addi, 64, 'r12', 'r12'); a.branch('r', n)
    a.label(n + 'd')


def emit_wrapper(a, name, target):
    """name(r6, r7): target(r6, r7), then TAG; keeps the target's r10"""
    a.label(name)
    a.emit(addi, -8, 'sp', 'sp'); a.emit(st_w, 'lp', 0, 'sp')
    a.call(target)
    a.emit(st_w, 'r10', 4, 'sp')
    a.calll('TAG')
    a.emit(ld_w, 4, 'sp', 'r10'); a.emit(ld_w, 0, 'sp', 'lp'); a.emit(addi, 8, 'sp', 'sp')
    a.emit(jmp_reg, 'lp')


def build_mark():
    a = Asm(L.MARK)
    # ---------------------------------------------------------------- MARKKEY (class 3 entry)
    a.label('MARKKEY')
    a.emit(ld_bu, 4, 'r7', 'r10')
    a.emit(movea, L.KEY_LR, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.branch('nz', 'stock')
    # every L/R event: held state (press 1 / release 0; repeat keeps it), RAM state valid
    a.emit(mov32, MARK_RAM, 'r11')
    a.emit(ld_w, 0, 'r11', 'r12'); a.emit(mov32, MARK_MAGIC, 'r13'); a.emit(cmp_rr, 'r13', 'r12')
    a.branch('z', 'mk_ok')
    a.emit(st_w, 'r13', 0, 'r11'); a.emit(mov_i, -1, 'r12'); a.emit(st_w, 'r12', 4, 'r11')
    a.emit(st_w, 'r0', 8, 'r11'); a.emit(st_w, 'r0', 12, 'r11'); a.emit(st_w, 'r0', 16, 'r11')
    a.label('mk_ok')
    a.emit(ld_w, 8, 'r7', 'r10'); a.emit(cmp_i, 1, 'r10'); a.branch('h', 'mk_rep')
    a.emit(st_w, 'r10', 12, 'r11')
    a.label('mk_rep')
    a.emit(ld_w, L.SCREEN_ZOOM_SLOT, 'r6', 'r10')
    for user in L.LR_USERS:
        a.emit(mov32, user, 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.branch('z', 'stock')
    a.emit(ld_w, 8, 'r7', 'r10'); a.emit(cmp_i, 1, 'r10'); a.branch('z', 'MARK')
    a.emit(jmp_reg, 'lp')                                               # release / repeat
    a.label('stock')
    a.jump(L.LR_STOCK)

    # ---------------------------------------------------------------- MARK (a press)
    a.label('MARK')
    prologue(a)
    emit_cursample(a, 'out')
    a.emit(mov_rr, 'r21', 'r6'); a.call(L.PROTECTED)
    a.emit(cmp_rr, 'r0', 'r10'); a.branch('z', 'unprot')
    a.emit(mov_i, L.ERR_PROTECTED, 'r6'); a.call(L.POST_ERROR)
    a.jumpl('out')
    a.label('unprot')
    a.emit(mov32, MARK_RAM, 'r23')                                      # state for this sample
    a.emit(ld_w, 0, 'r23', 'r10'); a.emit(mov32, MARK_MAGIC, 'r11'); a.emit(cmp_rr, 'r11', 'r10')
    a.branch('nz', 'fresh')
    a.emit(ld_w, 4, 'r23', 'r10'); a.emit(cmp_rr, 'r20', 'r10'); a.branch('z', 'same')
    a.label('fresh')
    a.emit(st_w, 'r11', 0, 'r23'); a.emit(st_w, 'r20', 4, 'r23'); a.emit(st_w, 'r0', 8, 'r23')
    a.label('same')
    # END due (a START was set with Mark): this press is the END press
    a.emit(ld_w, 8, 'r23', 'r10'); a.emit(cmp_i, 1, 'r10'); a.branch('z', 'notm')
    # marked (START / END not the whole sample, however they were set) -> clear
    a.emit(mov_rr, 'r20', 'r6'); a.calll('ISMARKED')
    a.emit(cmp_rr, 'r0', 'r10'); a.branch('z', 'notm')
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.WAVE_START_POS); a.emit(mov_rr, 'r10', 'r22')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(mov_rr, 'r22', 'r7'); a.call(L.SET_START)
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.WAVE_END_POS); a.emit(mov_rr, 'r10', 'r22')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(mov_rr, 'r22', 'r7'); a.call(L.SET_END)
    a.emit(st_w, 'r0', 8, 'r23')
    a.jumpl('redraw')
    a.label('notm')
    a.emit(movea, L.PARAM_REVERSE, 'r0', 'r6'); a.emit(mov_rr, 'r20', 'r7'); a.call(GETTER)
    a.emit(cmp_rr, 'r0', 'r10'); a.bfar('nz', 'out')

    # r22 = position: candidates = active and not fading / starting / stopping
    a.emit(ld_bu, 4021, 'ep', 'r11')
    a.emit(ld_bu, 4022, 'ep', 'r12')
    for m in (4023, 4026, 4027):
        a.emit(ld_bu, m, 'ep', 'r13'); a.emit(or_rr, 'r13', 'r12')
    a.emit(not_rr, 'r12', 'r12'); a.emit(and_rr, 'r12', 'r11')
    a.emit(mov_i, -1, 'r22')
    a.emit(movhi, 3, 'gp', 'r1'); a.emit(movea, SLOTS, 'r1', 'r14')    # slot of voice 0
    a.emit(movea, VOICE_REC, 'ep', 'r15')                               # record of voice 0
    a.label('vl')
    a.emit(cmp_rr, 'r0', 'r11'); a.branch('z', 'vdone')
    a.emit(shr_i, 1, 'r11'); a.branch('nc', 'vn')
    a.emit(ld_h, 10, 'r14', 'r16'); a.emit(cmp_rr, 'r20', 'r16'); a.branch('nz', 'vn')
    a.emit(ld_w, 24, 'r15', 'r16')
    a.emit(ld_w, 28, 'r15', 'r17'); a.emit(cmp_rr, 'r17', 'r16'); a.branch('l', 'vn')
    a.emit(ld_w, 32, 'r15', 'r17'); a.emit(cmp_rr, 'r17', 'r16'); a.branch('nl', 'vn')
    a.emit(cmp_rr, 'r22', 'r16'); a.branch('nl', 'vn')
    a.emit(mov_rr, 'r16', 'r22')
    a.label('vn')
    a.emit(addi, 64, 'r14', 'r14'); a.emit(addi, 208, 'r15', 'r15')
    a.branch('r', 'vl')
    a.label('vdone')
    a.emit(cmp_i, -1, 'r22'); a.bfar('z', 'out')

    a.emit(ld_w, 8, 'r23', 'r10'); a.emit(cmp_rr, 'r0', 'r10'); a.branch('z', 'tstart')
    # END press: needs position >= START + MIN_LEN, else it moves START
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.START_POS)
    a.emit(movea, MIN_LEN, 'r10', 'r10'); a.emit(cmp_rr, 'r10', 'r22'); a.branch('l', 'tstart')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(mov_rr, 'r22', 'r7'); a.call(L.SET_END)
    a.emit(st_w, 'r0', 8, 'r23')
    a.emit(mov_rr, 'r20', 'r6'); a.calll('RETRIG')                      # play the marked range now
    a.branch('r', 'redraw')
    # START press: needs position + MIN_LEN <= END
    a.label('tstart')
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.END_POS)
    a.emit(movea, MIN_LEN, 'r22', 'r11'); a.emit(cmp_rr, 'r10', 'r11'); a.bfar('h', 'out')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(mov_rr, 'r22', 'r7'); a.call(L.SET_START)
    a.emit(mov_i, 1, 'r10'); a.emit(st_w, 'r10', 8, 'r23'); a.emit(st_w, 'r10', 24, 'r23')  # playing
    a.emit(mov_rr, 'r20', 'r6'); a.calll('ISMARKED'); a.emit(st_w, 'r10', 28, 'r23')  # if it stops
    a.label('redraw')
    a.emit(mov_i, -1, 'r6'); a.call(UI_REDRAW)
    a.calll('TAG')
    a.label('out')
    epilogue(a)

    # ---------------------------------------------------------------- RETRIG(r6 sample)
    # SP-303 style: when the END is set, playback goes straight back to the new START. A note-on
    # message goes straight into the audio task's ring (AUDIO_POST 0x1B3394, as the START / END
    # editor's preview notes do), right after the END commit, whose parameter message task 0 has
    # already put into the same ring (it runs at once: highest priority). So the old note stops
    # within a block of the press instead of running on past the END until a note through the
    # sequencer arrives (2.1d). (2.1e posted it through 0x1C284C, which routes type 4 messages to
    # ROM 0x1393C, not to the audio task: no restart at all.) The audio task's note-on cuts the sample's playing
    # voices itself (0x1BD184, with the allocator's bookkeeping), as for a second hit of the pad.
    # Part, velocity, flags and extra are those of the audio task's last note-on when it was this
    # sample (the pad hit being marked), else part 0 / flags 1 / the PAD ACCENT level / 0 as the
    # panel sends them. Not through the sequencer: no MIDI OUT, not recorded.
    a.label('RETRIG')
    a.emit(addi, -16, 'sp', 'sp'); a.emit(st_w, 'lp', 12, 'sp')
    a.emit(mov_i, 0, 'r10'); a.emit(mov_i, 1, 'r11'); a.emit(mov_i, 0, 'r13')
    a.emit(movhi, 1, 'gp', 'r1'); a.emit(ld_w, L.PAD_VELOCITY - 0x10000, 'r1', 'r12')
    a.emit(movhi, 3, 'gp', 'r1'); a.emit(movea, L.LAST_NOTE - 0x30000, 'r1', 'r14')
    a.emit(ld_h, 2, 'r14', 'r15'); a.emit(cmp_rr, 'r6', 'r15'); a.branch('nz', 'rt_send')
    a.emit(ld_h, 0, 'r14', 'r13'); a.emit(ld_b, 4, 'r14', 'r10')
    a.emit(ld_b, 5, 'r14', 'r12'); a.emit(ld_b, 6, 'r14', 'r11')
    a.label('rt_send')
    a.emit(mov_i, 4, 'r15'); a.emit(st_b, 'r15', 0, 'sp')
    a.emit(st_b, 'r11', 1, 'sp'); a.emit(st_b, 'r10', 2, 'sp')
    a.emit(movea, L.NOTE_ON, 'r0', 'r15'); a.emit(st_b, 'r15', 3, 'sp')
    a.emit(st_h, 'r6', 4, 'sp'); a.emit(st_h, 'r12', 6, 'sp'); a.emit(st_h, 'r13', 8, 'sp')
    a.emit(mov_rr, 'sp', 'r6'); a.call(L.AUDIO_POST)
    a.emit(ld_w, 12, 'sp', 'lp'); a.emit(addi, 16, 'sp', 'sp')
    a.emit(jmp_reg, 'lp')

    # ---------------------------------------------------------------- ISMARKED(r6 sample) -> r10
    # marked = START or END isn't at the edge of the recorded data (params 37 / 42), compared as
    # positions with the routines WAVE EDIT uses for its limits; an empty sample is never marked
    a.label('ISMARKED')
    a.emit(addi, -12, 'sp', 'sp'); a.emit(st_w, 'lp', 0, 'sp'); a.emit(st_w, 'r20', 4, 'sp')
    a.emit(st_w, 'r21', 8, 'sp')
    a.emit(mov_rr, 'r6', 'r20')
    a.call(L.START_POS); a.emit(mov_rr, 'r10', 'r21')
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.WAVE_START_POS)
    a.emit(cmp_rr, 'r10', 'r21'); a.branch('nz', 'im_yes')
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.END_POS); a.emit(mov_rr, 'r10', 'r21')
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.WAVE_END_POS)
    a.emit(cmp_rr, 'r10', 'r21'); a.branch('nz', 'im_yes')
    a.emit(mov_i, 0, 'r10'); a.branch('r', 'im_out')
    a.label('im_yes')
    a.emit(mov_i, 1, 'r10')
    a.label('im_out')
    a.emit(ld_w, 0, 'sp', 'lp'); a.emit(ld_w, 4, 'sp', 'r20'); a.emit(ld_w, 8, 'sp', 'r21')
    a.emit(addi, 12, 'sp', 'sp')
    a.emit(jmp_reg, 'lp')

    # ---------------------------------------------------------------- TAG (play screens only)
    x0, y0, x1, y1 = L.TAG_BOX
    a.label('TAG')
    prologue(a)
    a.emit(movhi, 1, 'gp', 'r1'); a.emit(ld_w, L.CUR_SCREEN - 0x10000, 'r1', 'r10')
    for desc, _, _ in L.PLAY_SCREENS:
        a.emit(mov32, desc, 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.branch('z', 'tg_play')
    a.jumpl('tg_out')
    a.label('tg_play')
    emit_cursample(a, 'tg_out')
    a.emit(cmp_i, L.PRESET_BANKS, 'r21'); a.bfar('lt', 'tg_out')
    a.emit(mov_i, 0, 'r22')                                             # 0 none, 1 flashing, 2 solid
    # START set with Mark, END due: flashing (comes first)
    a.emit(mov32, MARK_RAM, 'r23')
    a.emit(ld_w, 0, 'r23', 'r10'); a.emit(mov32, MARK_MAGIC, 'r11'); a.emit(cmp_rr, 'r11', 'r10')
    a.branch('nz', 'tg_mk')
    a.emit(ld_w, 4, 'r23', 'r10'); a.emit(cmp_rr, 'r20', 'r10'); a.branch('nz', 'tg_mk')
    a.emit(ld_w, 8, 'r23', 'r22'); a.emit(cmp_i, 1, 'r22'); a.branch('z', 'tg_draw')
    a.emit(mov_i, 0, 'r22')
    # START / END not the whole sample (Mark, WAVE EDIT, a copy, ...): solid
    a.label('tg_mk')
    a.emit(mov_rr, 'r20', 'r6'); a.calll('ISMARKED')
    a.emit(cmp_rr, 'r0', 'r10'); a.branch('z', 'tg_draw')
    a.emit(mov_i, 2, 'r22')
    a.label('tg_draw')
    a.emit(mov32, MARK_RAM, 'r23')
    a.emit(st_w, 'r0', 16, 'r23')                                       # no flashing while drawing
    a.emit(st_w, 'r0', 0, 'sp')
    a.emit(movea, x0, 'r0', 'r6'); a.emit(movea, y0, 'r0', 'r7')
    a.emit(movea, x1, 'r0', 'r8'); a.emit(movea, y1, 'r0', 'r9'); a.call(L.LCD_FILL)
    a.emit(cmp_rr, 'r0', 'r22'); a.branch('z', 'tg_out')
    a.emit(movea, x0 + 2, 'r0', 'r6'); a.emit(movea, y0 + 1, 'r0', 'r7'); a.emit(mov_i, 1, 'r8')
    a.mov32l('S_MARK', 'r9'); a.call(L.LCD_TEXT)
    a.emit(movea, x0, 'r0', 'r6'); a.emit(movea, y0, 'r0', 'r7')
    a.emit(movea, x1, 'r0', 'r8'); a.emit(movea, y1, 'r0', 'r9'); a.call(L.LCD_INVERT)
    a.emit(cmp_i, 2, 'r22'); a.branch('z', 'tg_out')                    # marked: solid
    # START set, END due: the idle loop flashes it; keep the tag's bytes (rows 48-54)
    a.emit(mov32, L.TAG_FB, 'r11'); a.emit(movea, 0x20, 'r23', 'r12'); a.emit(movea, L.TAG_BYTES, 'r0', 'r13')
    a.label('tg_save')
    a.emit(ld_bu, 0, 'r11', 'r14'); a.emit(andi, 0x7F, 'r14', 'r14'); a.emit(st_b, 'r14', 0, 'r12')
    a.emit(add_i, 1, 'r11'); a.emit(add_i, 1, 'r12'); a.emit(add_i, -1, 'r13'); a.branch('nz', 'tg_save')
    a.emit(mov_i, 1, 'r10'); a.emit(st_w, 'r10', 20, 'r23')                # shown
    a.emit(st_w, 'r10', 16, 'r23')                                      # flash
    a.label('tg_out')
    epilogue(a)

    # ---------------------------------------------------------------- PADW (class 6 entry)
    # A pad press while L/R is held (on a screen that doesn't use L/R): START = the beginning of
    # the recorded data, committed before the stock handler starts the note, so the parameter
    # message is ahead of the note start in the audio task's queue and the note plays from the
    # beginning; the next L/R press sets END. Then the stock handler, then the tag.
    a.label('PADW')
    a.emit(addi, -32, 'sp', 'sp')
    for i, r in enumerate(('lp', 'r20', 'r21', 'r22', 'r23', 'r6', 'r7')):
        a.emit(st_w, r, 4 + 4 * i, 'sp')
    a.emit(ld_w, 8, 'r7', 'r10'); a.emit(cmp_i, 1, 'r10'); a.bfar('nz', 'pw_stock')
    a.emit(ld_bu, 4, 'r7', 'r22'); a.emit(addi, -L.KEY_PAD1, 'r22', 'r22')      # pad 0..15
    a.emit(cmp_i, 15, 'r22'); a.bfar('h', 'pw_stock')
    a.emit(mov32, MARK_RAM, 'r23')
    a.emit(ld_w, 0, 'r23', 'r10'); a.emit(mov32, MARK_MAGIC, 'r11'); a.emit(cmp_rr, 'r11', 'r10')
    a.bfar('nz', 'pw_stock')
    a.emit(ld_w, 12, 'r23', 'r10'); a.emit(cmp_i, 1, 'r10'); a.bfar('nz', 'pw_stock')   # held?
    a.emit(ld_w, L.SCREEN_ZOOM_SLOT, 'r6', 'r10')
    for user in L.LR_USERS:
        a.emit(mov32, user, 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.bfar('z', 'pw_stock')
    a.emit(movea, L.PARAM_CURBANK, 'r0', 'r6'); a.emit(mov_i, -1, 'r7'); a.call(GETTER)
    a.emit(mov_rr, 'r10', 'r21')
    a.emit(mov_rr, 'r22', 'r6'); a.emit(mov_rr, 'r21', 'r7'); a.call(L.PADSAMPLE)
    a.emit(mov_rr, 'r10', 'r20')
    a.emit(cmp_rr, 'r0', 'r20'); a.bfar('lt', 'pw_stock')
    a.emit(movea, NSAMPLES - 1, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r20'); a.bfar('gt', 'pw_stock')
    a.emit(mov_rr, 'r21', 'r6'); a.call(L.PROTECTED)
    a.emit(cmp_rr, 'r0', 'r10'); a.branch('z', 'pw_unprot')
    a.emit(mov_i, L.ERR_PROTECTED, 'r6'); a.call(L.POST_ERROR)
    a.jumpl('pw_stock')
    a.label('pw_unprot')
    a.emit(movea, L.PARAM_REVERSE, 'r0', 'r6'); a.emit(mov_rr, 'r20', 'r7'); a.call(GETTER)
    a.emit(cmp_rr, 'r0', 'r10'); a.bfar('nz', 'pw_stock')
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.WAVE_START_POS); a.emit(mov_rr, 'r10', 'r22')
    a.emit(mov_rr, 'r20', 'r6'); a.call(L.END_POS)
    a.emit(movea, MIN_LEN, 'r22', 'r11'); a.emit(cmp_rr, 'r10', 'r11'); a.bfar('h', 'pw_stock')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(mov_rr, 'r22', 'r7'); a.call(L.SET_START)
    a.emit(st_w, 'r20', 4, 'r23'); a.emit(mov_i, 1, 'r10'); a.emit(st_w, 'r10', 8, 'r23')
    a.emit(st_w, 'r0', 24, 'r23')                                       # its note not seen yet
    a.emit(mov_rr, 'r20', 'r6'); a.calll('ISMARKED'); a.emit(st_w, 'r10', 28, 'r23')  # if it stops
    a.label('pw_stock')
    a.emit(ld_w, 24, 'sp', 'r6'); a.emit(ld_w, 28, 'sp', 'r7')
    a.call(L.PAD_STOCK)
    a.emit(st_w, 'r10', 24, 'sp')
    a.calll('TAG')
    a.emit(ld_w, 24, 'sp', 'r10')
    for i, r in enumerate(('lp', 'r20', 'r21', 'r22', 'r23')):
        a.emit(ld_w, 4 + 4 * i, 'sp', r)
    a.emit(addi, 32, 'sp', 'sp')
    a.emit(jmp_reg, 'lp')

    # ---------------------------------------------------------------- MIDLE (idle task loop)
    # Flashes the tag, and ends the "END due" state once the sample, seen playing, has stopped
    # (the tag goes out; START stays, END is the old one; the next press is a START). Runs in the
    # idle task (lowest priority, so the UI task is waiting and its
    # drawing is complete whenever this runs); it never calls UI or LCD code (the LCD lock is a
    # spin lock), it only rewrites the tag's 22 framebuffer bytes (rows 48-54, the box's line in
    # bit 7 kept) every 2^BLINK_SHIFT ticks, with interrupts off from the check to the last byte.
    a.label('MIDLE')
    a.emit(mov32, L.TICK, 'r20'); a.emit(mov32, MARK_RAM, 'r21')
    a.emit(mov32, L.GP_VALUE + L.CUR_SCREEN, 'r22'); a.emit(mov32, MARK_MAGIC, 'r24')
    a.emit(mov32, L.EP, 'r25'); a.emit(mov32, L.GP_VALUE + 0x30000 + SLOTS, 'r26')
    a.label('mi_l')
    a.emit(ld_w, 8, 'r21', 'r10'); a.emit(cmp_i, 1, 'r10'); a.bfar('nz', 'mi_l')   # END due
    # is the sample still playing? (a voice of it active)
    emit_playing(a, 'mi_v')
    a.emit(cmp_rr, 'r0', 'r13'); a.branch('z', 'mi_np')
    a.emit(st_w, 'r13', 24, 'r21')                                      # seen playing
    a.jumpl('mi_fl')
    a.label('mi_np')
    a.emit(ld_w, 24, 'r21', 'r10'); a.emit(cmp_rr, 'r0', 'r10'); a.bfar('z', 'mi_fl')
    # it played and has stopped: the START stays, the END wait ends (SP-303: Mark stops flashing)
    a.emit(di)
    a.emit(ld_w, 0, 'r21', 'r10'); a.emit(cmp_rr, 'r24', 'r10'); a.bfar('nz', 'mi_x')
    a.emit(ld_w, 8, 'r21', 'r10'); a.emit(cmp_i, 1, 'r10'); a.bfar('nz', 'mi_x')
    a.emit(ld_w, 24, 'r21', 'r10'); a.emit(cmp_rr, 'r0', 'r10'); a.bfar('z', 'mi_x')
    emit_playing(a, 'mi_w2')                                            # again, uninterrupted
    a.emit(cmp_rr, 'r0', 'r13'); a.bfar('nz', 'mi_x')
    a.emit(ld_w, 16, 'r21', 'r18')
    a.emit(st_w, 'r0', 16, 'r21'); a.emit(st_w, 'r0', 8, 'r21'); a.emit(st_w, 'r0', 24, 'r21')
    a.emit(cmp_i, 1, 'r18'); a.bfar('nz', 'mi_x')                     # tag wasn't flashing
    a.emit(ld_w, 28, 'r21', 'r11')                                      # marked now: steady, else out
    a.jumpl('mi_scr')
    # flashing
    a.label('mi_fl')
    a.emit(ld_w, 16, 'r21', 'r10'); a.emit(cmp_i, 1, 'r10'); a.bfar('nz', 'mi_l')
    a.emit(ld_w, 0, 'r20', 'r11'); a.emit(shr_i, L.BLINK_SHIFT, 'r11'); a.emit(andi, 1, 'r11', 'r11')
    a.emit(ld_w, 20, 'r21', 'r12'); a.emit(cmp_rr, 'r12', 'r11'); a.bfar('z', 'mi_l')
    a.emit(di)
    a.emit(ld_w, 0, 'r21', 'r10'); a.emit(cmp_rr, 'r24', 'r10'); a.bfar('nz', 'mi_x')
    a.emit(ld_w, 16, 'r21', 'r10'); a.emit(cmp_i, 1, 'r10'); a.bfar('nz', 'mi_x')
    a.label('mi_scr')
    a.emit(ld_w, 0, 'r22', 'r10')
    for desc, _, _ in L.PLAY_SCREENS:
        a.emit(mov32, desc, 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.branch('z', 'mi_w')
    a.jumpl('mi_x')
    a.label('mi_w')
    a.emit(st_w, 'r11', 20, 'r21')
    a.emit(mov32, L.TAG_FB, 'r13'); a.emit(movea, 0x20, 'r21', 'r14')
    a.emit(movea, L.TAG_BYTES, 'r0', 'r15')
    a.label('mi_b')
    a.emit(ld_bu, 0, 'r13', 'r16'); a.emit(andi, 0x80, 'r16', 'r16')
    a.emit(cmp_rr, 'r0', 'r11'); a.branch('z', 'mi_off')
    a.emit(ld_bu, 0, 'r14', 'r17'); a.emit(or_rr, 'r17', 'r16')
    a.label('mi_off')
    a.emit(st_b, 'r16', 0, 'r13')
    a.emit(add_i, 1, 'r13'); a.emit(add_i, 1, 'r14'); a.emit(add_i, -1, 'r15'); a.branch('nz', 'mi_b')
    a.label('mi_x')
    a.emit(ei)
    a.jumpl('mi_l')

    # ---------------------------------------------------------------- wrappers
    for k, (desc, enter, draw) in enumerate(L.PLAY_SCREENS):
        emit_wrapper(a, 'ENTER%d' % k, enter)
        emit_wrapper(a, 'DRAW%d' % k, draw)
    a.label('S_MARK'); a.emit(raw, b'MARK\0\0')
    return a.assemble(), a.labels


def install(d):
    code, labels = build_mark()
    assert labels['MARKKEY'] == L.MARK and L.MARK + len(code) <= L.MARK_END, hex(L.MARK + len(code))
    put(d, L.MARK, code, b'\xff' * len(code))
    w = lambda v: struct.pack('<I', v)
    put(d, L.CLASS_HANDLERS + 4 * L.LR_CLASS, w(L.MARK), w(L.LR_STOCK))
    put(d, L.CLASS_HANDLERS + 4 * L.PAD_CLASS, w(labels['PADW']), w(L.PAD_STOCK))
    # the idle task's endless loop (engine.build_idle: 'br .', then free space) -> MIDLE
    import engine
    hang = L.IDLE + len(engine.build_idle()) - 2
    put(d, hang, jr(labels['MIDLE'], hang), bcond('r', hang, hang) + bytes([0xFF, 0xFF]))
    for k, (desc, enter, draw) in enumerate(L.PLAY_SCREENS):
        put(d, desc + L.SCREEN_ENTER, w(labels['ENTER%d' % k]), w(enter))
        put(d, desc + L.SCREEN_DRAW, w(labels['DRAW%d' % k]), w(draw))
    return labels
