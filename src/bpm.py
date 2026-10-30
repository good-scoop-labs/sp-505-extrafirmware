"""BPM rule: a sample's BPM always follows its own settings.

Stock invariant (v1.02): a sample's BPM (param 44, BPM x 10) is always the "natural" BPM that
0x15BF84(sample) computes from start/end, rate, format, Measure and Beat: every stock path that
writes param 44 passes either that value or the current param 44 (post-sampling init 0x1A0BE8,
Measure 0x1A2E10 / 0x1A3Axx, Beat 0x193D40 -> 0x1A296C, start/end 0x1A3B26 / 0x1A3BC2).

EXTRAfirmware keeps the same kind of invariant with varispeed:

    BPM = natural                                      Varispeed and Fine Tune both 0
    BPM = clamp(round(natural * ratio(semis, cents)))  otherwise (40.0 .. 200.0)

and enforces it in three places (UI side only):

1. BPMWRAP (generic value edit, 0x183B06), Varispeed / Fine Tune edits: computes the new BPM from
   natural and the new setting. The new setting and BPM are also written straight into the
   sample record, so the record is consistent at once whatever order the posted parameter
   messages are processed in. Play Type: a non-zero setting switches Phrase to Single, and Phrase
   is refused while either setting is non-zero.
2. SETWRAP (entry of the parameter setter 0x1C34B4, all callers):
   - param 44 set to exactly natural (Measure, Beat, start / end edits, sampling): the value is
     replaced by the varispeed BPM when the sample has a setting;
   - param 58 set by stock code (post-sampling init sets it to 0): Fine Tune (59) is reset too
     (otherwise a new recording would inherit the old sample's Fine Tune).
3. REPGET (BPM read for the sample header line, 0x183B60; shown by the sample parameter menu and
   two other screens): if the stored BPM doesn't match the rule, it is corrected (setter + record)
   and the corrected value is displayed. This repairs samples whose BPM was carried over without
   their setting, e.g. a CLIPBOARD copy of a varispeed sample (the copy gets the BPM but not the
   Varispeed / Fine Tune bytes, so it plays at normal speed and now shows the original BPM).

Samples whose natural BPM is outside 10.0..1600.0 (empty pads, degenerate lengths) are never
touched, and REPGET leaves values the getter can't show (above 200.9) alone.
"""
import layout as L
from layout import (GETTER, SETTER, SETTER_FIRST, SETTER_BODY, NATURAL, UI_REDRAW, REC_GPOFF,
                    OFF_SEMI, OFF_FINE, OFF_BPM, PARAM_VARI, PARAM_FINE, PARAM_BPM, PARAM_PLAYTYPE,
                    STEPTAB, FINETAB, SEMIS, FINE, NSAMPLES)
from sp505fw import put
from v850asm import *

BPMWRAP = L.BPM_CODE
NAT_MIN, NAT_MAX = 100, 16000       # plausible natural BPM x 10 (0 = empty / degenerate); keeps natural * ratio < 2^32
BPM_MIN, BPM_MAX = 400, 2000        # 40.0 .. 200.0
DESC_BPM_MAX = 2009                 # the getter returns param 44 clamped to its descriptor range


def recptr(a, s, out, tmp):
    """out = gp + 15312 + 48 * s"""
    a.emit(mov_rr, s, out); a.emit(shl_i, 5, out)
    a.emit(mov_rr, s, tmp); a.emit(shl_i, 4, tmp); a.emit(add_rr, tmp, out)
    a.emit(movea, REC_GPOFF, 'gp', tmp); a.emit(add_rr, tmp, out)


def range_s(a, s, lbl):
    """branch to lbl unless 0 <= s < NSAMPLES (clobbers r1)"""
    a.emit(cmp_rr, 'r0', s); a.bfar('lt', lbl)
    a.emit(movea, NSAMPLES - 1, 'r0', 'r1'); a.emit(cmp_rr, 'r1', s); a.bfar('gt', lbl)


def put_bpm(a, s, v, t1, t2):
    """record BPM (big-endian halfword at +0x1C) = v"""
    recptr(a, s, t1, t2)
    a.emit(mov_rr, v, t2); a.emit(shr_i, 8, t2); a.emit(st_b, t2, OFF_BPM, t1)
    a.emit(st_b, v, OFF_BPM + 1, t1)


def build_bpmx():
    a = Asm(BPMWRAP)

    # ---------------------------------------------------------------- BPMWRAP (0x183B06)
    a.label('BPMWRAP')
    a.emit(movea, PARAM_VARI, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.bfar('z', 'go')
    a.emit(movea, PARAM_FINE, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.bfar('z', 'go')
    # Play Type -> Phrase refused while Varispeed / Fine Tune is set (v27)
    a.emit(movea, PARAM_PLAYTYPE, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.bfar('nz', 'pass')
    a.emit(cmp_rr, 'r0', 'r8'); a.bfar('z', 'pass')
    a.emit(prepare_lp, 16)
    a.emit(st_w, 'r6', 0, 'sp'); a.emit(st_w, 'r7', 4, 'sp'); a.emit(st_w, 'r8', 8, 'sp')
    a.emit(mov_rr, 'r6', 'r7'); a.emit(movea, PARAM_VARI, 'r0', 'r6'); a.call(GETTER)
    a.emit(st_w, 'r10', 12, 'sp')
    a.emit(movea, PARAM_FINE, 'r0', 'r6'); a.emit(ld_w, 0, 'sp', 'r7'); a.call(GETTER)
    a.emit(ld_w, 12, 'sp', 'r11'); a.emit(or_rr, 'r10', 'r11')
    a.emit(ld_w, 0, 'sp', 'r6'); a.emit(ld_w, 4, 'sp', 'r7'); a.emit(ld_w, 8, 'sp', 'r8')
    a.branch('nz', 'refuse')
    a.calll('RAWSET')
    a.label('refuse')
    a.emit(dispose_lp, 16)
    a.label('pass')
    a.jumpl('RAWSET')

    a.label('go')                       # r6 sample, r7 58 / 59, r8 new value
    a.emit(prepare_lp, 40)
    for i in range(10):
        a.emit(st_w, 'r%d' % (20 + i), 4 * i, 'sp')
    a.emit(mov_rr, 'r6', 'r20'); a.emit(mov_rr, 'r7', 'r21'); a.emit(mov_rr, 'r8', 'r22')
    for pid, reg in ((PARAM_VARI, 'r23'), (PARAM_FINE, 'r24')):          # old setting
        a.emit(movea, pid, 'r0', 'r6'); a.emit(mov_rr, 'r20', 'r7'); a.call(GETTER)
        a.emit(mov_rr, 'r10', reg)
    a.emit(mov_rr, 'r20', 'r6'); a.emit(mov_rr, 'r21', 'r7'); a.emit(mov_rr, 'r22', 'r8')
    a.calll('RAWSET')                                                   # the edit itself
    a.emit(mov_rr, 'r23', 'r26'); a.emit(mov_rr, 'r24', 'r27')          # new semis / cents
    a.emit(movea, PARAM_VARI, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r21'); a.branch('nz', 'isf')
    a.emit(mov_rr, 'r22', 'r26'); a.branch('r', 'cnt')
    a.label('isf')
    a.emit(mov_rr, 'r22', 'r27')
    a.label('cnt')
    a.emit(cmp_rr, 'r23', 'r26'); a.branch('nz', 'chg')
    a.emit(cmp_rr, 'r24', 'r27'); a.bfar('z', 'done')
    a.label('chg')
    range_s(a, 'r20', 'done')
    recptr(a, 'r20', 'r28', 'r1')                                       # record now, not later
    a.emit(st_b, 'r26', OFF_SEMI, 'r28'); a.emit(st_b, 'r27', OFF_FINE, 'r28')
    a.emit(mov_i, 0, 'r29')                                             # redraw needed
    a.emit(mov_rr, 'r20', 'r6'); a.call(NATURAL)
    a.emit(movea, NAT_MIN, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.bfar('lt', 'nobpm')
    a.emit(movea, NAT_MAX, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.bfar('gt', 'nobpm')
    a.emit(mov_rr, 'r10', 'r6'); a.emit(mov_rr, 'r26', 'r7'); a.emit(mov_rr, 'r27', 'r8')
    a.calll('TARGET'); a.emit(mov_rr, 'r10', 'r25')
    a.emit(movea, PARAM_BPM, 'r0', 'r6'); a.emit(mov_rr, 'r20', 'r7'); a.call(GETTER)
    a.emit(cmp_rr, 'r10', 'r25'); a.bfar('z', 'nobpm')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(movea, PARAM_BPM, 'r0', 'r7'); a.emit(mov_rr, 'r25', 'r8')
    a.calll('RAWSET')
    put_bpm(a, 'r20', 'r25', 'r28', 'r1')
    a.emit(mov_i, 1, 'r29')
    a.label('nobpm')
    # (v26) Play Type Phrase -> Single when a setting is non-zero
    a.emit(mov_rr, 'r26', 'r6'); a.emit(or_rr, 'r27', 'r6'); a.bfar('z', 'rd')
    a.emit(movea, PARAM_PLAYTYPE, 'r0', 'r6'); a.emit(mov_rr, 'r20', 'r7'); a.call(GETTER)
    a.emit(cmp_rr, 'r0', 'r10'); a.bfar('z', 'rd')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(movea, PARAM_PLAYTYPE, 'r0', 'r7'); a.emit(mov_i, 0, 'r8')
    a.calll('RAWSET')
    a.emit(mov_i, 1, 'r29')
    a.label('rd')
    a.emit(cmp_rr, 'r0', 'r29'); a.bfar('z', 'done')
    a.emit(mov_i, -1, 'r6'); a.call(UI_REDRAW)
    a.label('done')
    for i in range(10):
        a.emit(ld_w, 4 * i, 'sp', 'r%d' % (20 + i))
    a.emit(dispose_lp, 40)

    # ---------------------------------------------------------------- SETWRAP (0x1C34B4 entry)
    a.label('SETWRAP')
    a.emit(movea, PARAM_BPM, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.bfar('z', 'sbpm')
    a.emit(movea, PARAM_VARI, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.bfar('z', 'svari')
    a.label('RAWSET')                   # the original setter
    a.emit(raw, SETTER_FIRST)
    a.jump(SETTER_BODY)

    a.label('sbpm')                     # param 44 := natural -> varispeed BPM
    a.emit(prepare_lp, 16)
    for i in range(3):
        a.emit(st_w, 'r%d' % (20 + i), 4 * i, 'sp')
    a.emit(mov_rr, 'r6', 'r20'); a.emit(mov_rr, 'r8', 'r22')
    range_s(a, 'r20', 'sbset')
    a.call(NATURAL)                                                     # r6 = sample
    a.emit(cmp_rr, 'r10', 'r22'); a.bfar('nz', 'sbset')
    a.emit(movea, NAT_MIN, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.bfar('lt', 'sbset')
    a.emit(movea, NAT_MAX, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.bfar('gt', 'sbset')
    recptr(a, 'r20', 'r21', 'r1')
    a.emit(mov_rr, 'r10', 'r6'); a.emit(ld_b, OFF_SEMI, 'r21', 'r7'); a.emit(ld_b, OFF_FINE, 'r21', 'r8')
    a.calll('TARGET'); a.emit(mov_rr, 'r10', 'r22')
    a.label('sbset')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(movea, PARAM_BPM, 'r0', 'r7'); a.emit(mov_rr, 'r22', 'r8')
    a.calll('RAWSET')
    for i in range(3):
        a.emit(ld_w, 4 * i, 'sp', 'r%d' % (20 + i))
    a.emit(dispose_lp, 16)

    a.label('svari')                    # stock code sets 58 (init): Fine Tune follows
    a.emit(prepare_lp, 16)
    for i in range(3):
        a.emit(st_w, 'r%d' % (20 + i), 4 * i, 'sp')
    a.emit(mov_rr, 'r6', 'r20'); a.emit(mov_rr, 'r8', 'r22')
    a.calll('RAWSET')                                                   # 58 as asked
    a.emit(mov_rr, 'r20', 'r6'); a.emit(movea, PARAM_FINE, 'r0', 'r7'); a.emit(mov_i, 0, 'r8')
    a.calll('RAWSET')                                                   # 59 = 0
    range_s(a, 'r20', 'svout')
    recptr(a, 'r20', 'r21', 'r1')
    a.emit(st_b, 'r22', OFF_SEMI, 'r21'); a.emit(st_b, 'r0', OFF_FINE, 'r21')
    a.label('svout')
    for i in range(3):
        a.emit(ld_w, 4 * i, 'sp', 'r%d' % (20 + i))
    a.emit(dispose_lp, 16)

    # ---------------------------------------------------------------- REPGET (0x183B60)
    a.label('REPGET')                   # r6 = 44, r7 = sample -> r10 = BPM (corrected)
    a.emit(prepare_lp, 16)
    for i in range(3):
        a.emit(st_w, 'r%d' % (20 + i), 4 * i, 'sp')
    a.emit(mov_rr, 'r7', 'r20')
    a.call(GETTER); a.emit(mov_rr, 'r10', 'r21')
    range_s(a, 'r20', 'rgout')
    a.emit(mov_rr, 'r20', 'r6'); a.call(NATURAL)
    a.emit(movea, NAT_MIN, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.bfar('lt', 'rgout')
    a.emit(movea, NAT_MAX, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.bfar('gt', 'rgout')
    recptr(a, 'r20', 'r22', 'r1')
    a.emit(mov_rr, 'r10', 'r6'); a.emit(ld_b, OFF_SEMI, 'r22', 'r7'); a.emit(ld_b, OFF_FINE, 'r22', 'r8')
    a.calll('TARGET')
    a.emit(movea, DESC_BPM_MAX, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.bfar('gt', 'rgout')
    a.emit(cmp_rr, 'r10', 'r21'); a.bfar('z', 'rgout')
    a.emit(mov_rr, 'r10', 'r21')
    a.emit(mov_rr, 'r20', 'r6'); a.emit(movea, PARAM_BPM, 'r0', 'r7'); a.emit(mov_rr, 'r21', 'r8')
    a.calll('RAWSET')
    put_bpm(a, 'r20', 'r21', 'r22', 'r1')
    a.label('rgout')
    a.emit(mov_rr, 'r21', 'r10')
    for i in range(3):
        a.emit(ld_w, 4 * i, 'sp', 'r%d' % (20 + i))
    a.emit(dispose_lp, 16)

    # ---------------------------------------------------------------- TARGET
    # (natural r6, semis r7, cents r8) -> r10 = BPM for that setting. Leaf; clobbers r1, r6-r11.
    # Out-of-range settings count as Normal, as in the engine.
    a.label('TARGET')
    a.emit(mov_rr, 'r6', 'r10')
    a.emit(mov_rr, 'r7', 'r9'); a.emit(or_rr, 'r8', 'r9'); a.branch('z', 'tret')
    a.emit(movea, SEMIS[-1], 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.branch('gt', 'tret')
    a.emit(movea, SEMIS[0], 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.branch('lt', 'tret')
    a.emit(movea, FINE[-1], 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r8'); a.branch('gt', 'tret')
    a.emit(movea, FINE[0], 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r8'); a.branch('lt', 'tret')
    a.emit(addi, -SEMIS[0], 'r7', 'r7'); a.emit(shl_i, 2, 'r7'); a.emit(mov32, STEPTAB, 'r1')
    a.emit(add_rr, 'r1', 'r7'); a.emit(ld_w, 0, 'r7', 'r7')
    a.emit(addi, -FINE[0], 'r8', 'r8'); a.emit(shl_i, 2, 'r8'); a.emit(mov32, FINETAB, 'r1')
    a.emit(add_rr, 'r1', 'r8'); a.emit(ld_w, 0, 'r8', 'r8')
    a.emit(mulu, 'r8', 'r7', 'r9')                                      # r9:r7 = semi * fine
    a.emit(shr_i, 16, 'r7'); a.emit(shl_i, 16, 'r9'); a.emit(or_rr, 'r9', 'r7')   # ratio 16.16
    a.emit(mulu, 'r7', 'r10', 'r11')                                    # natural * ratio (< 2^29)
    a.emit(mov32, 0x8000, 'r1'); a.emit(add_rr, 'r1', 'r10'); a.emit(shr_i, 16, 'r10')
    a.emit(movea, BPM_MIN, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.branch('ge', 'tc1')
    a.emit(mov_rr, 'r1', 'r10')
    a.label('tc1')
    a.emit(movea, BPM_MAX, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r10'); a.branch('le', 'tret')
    a.emit(mov_rr, 'r1', 'r10')
    a.label('tret')
    a.emit(jmp_reg, 'lp')
    code = a.assemble()
    return code, dict(a.labels)


def install(d):
    code, labels = build_bpmx()
    assert labels['BPMWRAP'] == BPMWRAP and BPMWRAP + len(code) <= L.BPM_END, hex(BPMWRAP + len(code))
    put(d, BPMWRAP, code, b'\xff' * len(code))
    put(d, L.EDIT_SET_SITE, jarl(BPMWRAP, L.EDIT_SET_SITE), jarl(SETTER, L.EDIT_SET_SITE))
    put(d, SETTER, jr(labels['SETWRAP'], SETTER), SETTER_FIRST)
    put(d, L.HDR_GET_SITE, jarl(labels['REPGET'], L.HDR_GET_SITE), jarl(GETTER, L.HDR_GET_SITE))
    return labels
