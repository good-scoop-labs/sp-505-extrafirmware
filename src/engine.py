"""The varispeed engine: plays the notes of samples whose Varispeed / Fine Tune isn't 0.

The SP-505 renders audio in blocks of 16 frames in an interrupt routine in the CPU's mask ROM; the
flash firmware only sets voices up. The ROM calls a hook (pointer at ep+4004) at the start of every
block. EXTRAfirmware installs its own hook stub there:

- Take-over: when a note starts on a pad whose sample has a setting, the engine owns that voice.
- Every block, for each owned voice, the engine streams the sample with the ROM's own decoder and
  bookkeeping on the voice's real fields, resamples it (linear interpolation, 16.16 step) and writes
  the 16 >> c samples the ROM's kernel expects (c = sample rate code) into the voice's ROM buffer.
- ROM-mix: the voice's format is set to NOOP_FMT (decode does nothing) and the fields the ROM's
  bookkeeping would advance are neutralised, so the ROM does requests, fades, volume, pan, effect
  send and mixing for that voice as usual.
- POST: the interrupt's return address is redirected, so that after the ROM's interrupt (interrupts
  still off, before any task runs) the patched record words are restored from an undo list.
- Polyphony limits (one Standard / stereo note, or two mono lower-grade notes) are applied when
  notes start; older engine notes go back to the ROM with a fade-out.

The engine runs in place from flash, which is slow, so its cost is counted in flash halfwords
fetched per block (tools/prof30.py). Full history and reasoning: docs/DEV_NOTES.md.
"""
import layout as L
from layout import ENG, VS, XB, UNDO, CURSOR, SAVEPC, VTAB, TAG, SEMIS, FINE
from sp505fw import put
from v850asm import *

UNDO_LONG = (16, 148, 32, 36, 136)      # Standard (rate code 0): rec + these words (24 bytes)
UNDO_SHORT = (16, 148)                  # rate code >= 1: rec + these words (12 bytes)


# ---------------------------------------------------------------- small emitters
def emit_rec(a, vreg, out, tmp):
    """out = ep + 1020 + v * 208 (voice record)"""
    a.emit(mov_rr, vreg, out); a.emit(shl_i, 4, out)
    a.emit(mov_rr, out, tmp); a.emit(shl_i, 2, tmp); a.emit(add_rr, tmp, out)
    a.emit(add_rr, tmp, out); a.emit(add_rr, tmp, out)
    a.emit(movea, L.VOICE_REC, 'ep', tmp); a.emit(add_rr, tmp, out)


def or_mask(a, off, rm='r29', t='r6'):
    a.emit(ld_bu, off, 'ep', t); a.emit(or_rr, rm, t); a.emit(st_b, t, off, 'ep')


def andnot_mask(a, off, rnot, t='r6'):
    a.emit(ld_bu, off, 'ep', t); a.emit(and_rr, rnot, t); a.emit(st_b, t, off, 'ep')


def emit_bitloop_head(a, maskreg, vreg, name):
    """iterate the set bits of maskreg (destroyed): the body runs with vreg = bit index and must
    end with jumpl(name + '_next'); when no bit is left it goes to name + '_done'."""
    a.emit(mov_i, -1, vreg)
    a.label(name + '_next')
    a.emit(add_i, 1, vreg)
    a.emit(cmp_rr, 'r0', maskreg); a.bfar('z', name + '_done')
    a.emit(shr_i, 1, maskreg); a.branch('nc', name + '_next')


def emit_interp(a):
    """r15 = x[i] + (x[i+1] - x[i]) * frac, i = P >> 16 (P in r17, x base r9)"""
    a.emit(mov_rr, 'r17', 'r14'); a.emit(shr_i, 16, 'r14'); a.emit(shl_i, 1, 'r14')
    a.emit(add_rr, 'r9', 'r14')
    a.emit(ld_h, 0, 'r14', 'r22'); a.emit(ld_h, 2, 'r14', 'r15')
    a.emit(mov_rr, 'r17', 'r13'); a.emit(shl_i, 16, 'r13'); a.emit(shr_i, 17, 'r13')
    a.emit(sub_rr, 'r22', 'r15'); a.emit(sar_i, 1, 'r15'); a.emit(mulh_rr, 'r13', 'r15')
    a.emit(sar_i, 14, 'r15'); a.emit(add_rr, 'r22', 'r15')


def emit_record_step(a):
    """take-over: r17 = pad * 4 (checked 0..511) -> r19 = step (16.16) from the sample's record
    bytes Varispeed / Fine Tune, or branch to 'hno' (the ROM plays it). Free: r1, r18, r19, r22,
    r24, r26, r28, r29."""
    a.emit(mov_rr, 'r17', 'r22'); a.emit(shl_i, 3, 'r22')             # pad * 32
    a.emit(mov_rr, 'r17', 'r24'); a.emit(shl_i, 2, 'r24')             # pad * 16
    a.emit(add_rr, 'r24', 'r22')
    a.emit(movea, L.REC_GPOFF, 'gp', 'r24'); a.emit(add_rr, 'r24', 'r22')   # sample record
    a.emit(ld_b, L.OFF_SEMI, 'r22', 'r18'); a.emit(ld_b, L.OFF_FINE, 'r22', 'r22')
    a.emit(mov_rr, 'r18', 'r19'); a.emit(or_rr, 'r22', 'r19'); a.bfar('z', 'hno')     # both 0
    a.emit(cmp_i, SEMIS[-1], 'r18'); a.bfar('gt', 'hno')
    a.emit(addi, -SEMIS[0], 'r18', 'r18'); a.bfar('lt', 'hno')
    a.emit(movea, FINE[-1], 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r22'); a.bfar('gt', 'hno')
    a.emit(addi, -FINE[0], 'r22', 'r22'); a.bfar('lt', 'hno')
    a.emit(shl_i, 2, 'r18'); a.emit(mov32, L.STEPTAB, 'r19')
    a.emit(add_rr, 'r18', 'r19'); a.emit(ld_w, 0, 'r19', 'r19')
    a.emit(shl_i, 2, 'r22'); a.emit(mov32, L.FINETAB, 'r24')
    a.emit(add_rr, 'r22', 'r24'); a.emit(ld_w, 0, 'r24', 'r24')
    a.emit(mulu, 'r24', 'r19', 'r22')                                   # r22:r19 = semis * cents
    a.emit(shr_i, 16, 'r19'); a.emit(shl_i, 16, 'r22'); a.emit(or_rr, 'r22', 'r19')


def emit_cap(a):
    """note limits, after the take-over scan: r20 = ENG, r21 = owned (incl. new), r25 = new engine
    voices. Keeps note1 = the newest new note (its voices: stereo = 2); if note1 is mono and not
    Standard, also the newest other note when that is mono and not Standard. Every other engine
    voice goes back to the ROM with a fade-out (a voice handed back in its start block never
    sounds). Ends by jumping to 'nonew'. Free: r1, r6-r19, r22-r24, r26-r29."""
    a.emit(cmp_rr, 'r0', 'r25'); a.bfar('z', 'nonew')
    a.emit(mov_rr, 'r25', 'r6'); a.calll('NEWEST')                     # r7 = newest new voice
    a.calll('PADOF')                                                    # r9 = its pad
    a.emit(mov_rr, 'r25', 'r6'); a.calll('SAMEPAD')                    # r10 = note1
    a.emit(mov_rr, 'r10', 'r22')                                        # keep = note1
    a.emit(mov_rr, 'r10', 'r6'); a.emit(add_i, -1, 'r6'); a.emit(and_rr, 'r10', 'r6')
    a.bfar('nz', 'c_fin')                                               # stereo: alone
    a.calll('RATEOF'); a.bfar('z', 'c_fin')                             # Standard: alone
    a.emit(not_rr, 'r22', 'r23'); a.emit(and_rr, 'r21', 'r23')         # other engine voices
    a.emit(cmp_rr, 'r0', 'r23'); a.bfar('z', 'c_fin')
    a.emit(mov_rr, 'r23', 'r6'); a.calll('NEWEST'); a.calll('PADOF')
    a.emit(mov_rr, 'r23', 'r6'); a.calll('SAMEPAD')                    # r10 = note2
    a.emit(mov_rr, 'r10', 'r6'); a.emit(add_i, -1, 'r6'); a.emit(and_rr, 'r10', 'r6')
    a.bfar('nz', 'c_fin')
    a.calll('RATEOF'); a.bfar('z', 'c_fin')
    a.emit(or_rr, 'r10', 'r22')                                         # keep note2 as well
    a.label('c_fin')
    a.emit(not_rr, 'r22', 'r17'); a.emit(and_rr, 'r21', 'r17')         # handed back
    a.emit(and_rr, 'r22', 'r21')
    a.emit(ld_bu, 4022, 'ep', 'r15'); a.emit(or_rr, 'r17', 'r15'); a.emit(st_b, 'r15', 4022, 'ep')
    a.emit(ld_bu, 4028, 'ep', 'r15'); a.emit(or_rr, 'r17', 'r15'); a.emit(st_b, 'r15', 4028, 'ep')
    a.jumpl('nonew')
    # NEWEST(r6 mask, destroyed) -> r7 = voice with the highest start serial. clobbers r11-r14
    a.label('NEWEST')
    a.emit(mov_i, -1, 'r7'); a.emit(mov_i, 0, 'r13'); a.emit(mov_i, 0, 'r11'); a.emit(mov32, VS, 'r12')
    a.label('nw_l')
    a.emit(shr_i, 1, 'r6'); a.branch('nc', 'nw_n')
    a.emit(ld_w, 12, 'r12', 'r14'); a.emit(cmp_rr, 'r13', 'r14'); a.branch('nh', 'nw_n')
    a.emit(mov_rr, 'r14', 'r13'); a.emit(mov_rr, 'r11', 'r7')
    a.label('nw_n')
    a.emit(add_i, 1, 'r11'); a.emit(addi, 64, 'r12', 'r12')
    a.emit(cmp_rr, 'r0', 'r6'); a.branch('nz', 'nw_l')
    a.emit(jmp_reg, 'lp')
    # PADOF(r7 voice) -> r9 = pad of its slot. clobbers r1, r14
    a.label('PADOF')
    a.emit(movhi, 3, 'gp', 'r1'); a.emit(movea, L.SLOTS, 'r1', 'r9')
    a.emit(mov_rr, 'r7', 'r14'); a.emit(shl_i, 6, 'r14'); a.emit(add_rr, 'r14', 'r9')
    a.emit(ld_h, 10, 'r9', 'r9')
    a.emit(jmp_reg, 'lp')
    # SAMEPAD(r6 mask, destroyed; r9 pad) -> r10 = voices of the mask playing that pad. clobbers r1, r12, r14, r15
    a.label('SAMEPAD')
    a.emit(mov_i, 0, 'r10'); a.emit(mov_i, 1, 'r15')
    a.emit(movhi, 3, 'gp', 'r1'); a.emit(movea, L.SLOTS, 'r1', 'r12')
    a.label('sp_l')
    a.emit(shr_i, 1, 'r6'); a.branch('nc', 'sp_n')
    a.emit(ld_h, 10, 'r12', 'r14'); a.emit(cmp_rr, 'r9', 'r14'); a.branch('nz', 'sp_n')
    a.emit(or_rr, 'r15', 'r10')
    a.label('sp_n')
    a.emit(shl_i, 1, 'r15'); a.emit(addi, 64, 'r12', 'r12')
    a.emit(cmp_rr, 'r0', 'r6'); a.branch('nz', 'sp_l')
    a.emit(jmp_reg, 'lp')
    # RATEOF(r7 voice) -> Z set if its output rate shift c (VS+8) is 0 (Standard). clobbers r14
    a.label('RATEOF')
    a.emit(mov_rr, 'r7', 'r14'); a.emit(shl_i, 6, 'r14'); a.emit(mov32, VS, 'r1')
    a.emit(add_rr, 'r1', 'r14'); a.emit(ld_bu, 8, 'r14', 'r14'); a.emit(cmp_rr, 'r0', 'r14')
    a.emit(jmp_reg, 'lp')


def emit_book(a):
    """per-chunk bookkeeping on the real voice fields, as the ROM's 0xADBE..0xB0EA does it.
    r10 voice record, r29 voice bit, r11 voice index, r26 VS. out: r21 = 1 if the voice finished.
    clobbers r6, r7, r12..r15."""
    a.label('BOOK')
    a.emit(mov_i, 0, 'r21')
    a.emit(ld_w, 24, 'r10', 'r12'); a.emit(ld_b, 137, 'r10', 'r13'); a.emit(add_rr, 'r13', 'r12')
    a.emit(st_w, 'r12', 24, 'r10')
    a.emit(ld_w, 32, 'r10', 'r14'); a.emit(addi, -4, 'r14', 'r15')
    a.emit(cmp_rr, 'r15', 'r12'); a.branch('l', 'bseg'); a.branch('z', 'beq')
    a.emit(cmp_rr, 'r14', 'r12'); a.branch('l', 'bseg')
    a.jumpl('bend')
    a.label('beq')
    a.emit(ld_bu, 4030, 'ep', 'r6'); a.emit(and_rr, 'r29', 'r6'); a.branch('nz', 'bseg')
    or_mask(a, 4028)
    a.label('bseg')
    a.emit(ld_w, 36, 'r10', 'r12'); a.emit(ld_b, 143, 'r10', 'r13'); a.emit(add_rr, 'r13', 'r12')
    a.emit(ld_bu, 145, 'r10', 'r13')
    a.emit(cmp_i, 10, 'r13'); a.branch('gt', 'bwrap')
    a.emit(mov_rr, 'r13', 'r14'); a.emit(shl_i, 2, 'r14'); a.emit(add_rr, 'r10', 'r14')
    a.emit(ld_w, 60, 'r14', 'r14')
    a.emit(cmp_rr, 'r14', 'r12'); a.branch('nz', 'bst')
    a.emit(mov_rr, 'r10', 'r15'); a.emit(add_rr, 'r13', 'r15')
    a.emit(st_b, 'r0', 116, 'r15'); a.emit(mov_i, 2, 'r6'); a.emit(st_b, 'r6', 117, 'r15')
    a.emit(add_i, 1, 'r13'); a.emit(st_b, 'r13', 145, 'r10')
    or_mask(a, 4025)
    a.branch('r', 'bst')
    a.label('bwrap')
    a.emit(ld_w, 104, 'r10', 'r14'); a.emit(cmp_rr, 'r14', 'r12'); a.branch('l', 'bst')
    a.emit(st_b, 'r0', 127, 'r10'); a.emit(mov_i, 2, 'r6')
    a.emit(st_b, 'r6', 118, 'r10'); a.emit(st_b, 'r6', 145, 'r10')
    or_mask(a, 4025)
    a.emit(ld_w, 64, 'r10', 'r12')
    a.label('bst')
    a.emit(st_w, 'r12', 36, 'r10')
    a.emit(jmp_reg, 'lp')
    a.label('bend')
    a.emit(ld_b, 4020, 'ep', 'r6'); a.emit(cmp_rr, 'r11', 'r6'); a.branch('nz', 'be1')
    a.emit(st_b, 'r29', 4019, 'ep')
    a.label('be1')
    a.emit(ld_bu, 4030, 'ep', 'r6'); a.emit(and_rr, 'r29', 'r6'); a.branch('nz', 'bloop')
    # sample end while still audible: hold the last sample (P = 0, step = 0), request the fade-out
    a.emit(ld_bu, 133, 'r10', 'r6'); a.emit(cmp_rr, 'r0', 'r6'); a.branch('z', 'bfin')
    a.emit(mov_i, 0, 'r17'); a.emit(mov_i, 0, 'r18'); a.emit(st_w, 'r0', 4, 'r26')
    or_mask(a, 4028)
    a.emit(mov_i, 0, 'r21')
    a.emit(jmp_reg, 'lp')
    a.label('bfin')
    or_mask(a, 4029)
    a.emit(not_rr, 'r29', 'r7')
    andnot_mask(a, 4022, 'r7'); andnot_mask(a, 4021, 'r7'); andnot_mask(a, 4028, 'r7')
    a.emit(mov_i, 1, 'r21')
    a.emit(jmp_reg, 'lp')
    a.label('bloop')
    a.emit(ld_w, 40, 'r10', 'r6'); a.emit(st_w, 'r6', 36, 'r10')
    a.emit(mov32, 0x7FFFFFFF, 'r6'); a.emit(st_w, 'r6', 44, 'r10')
    a.emit(ld_w, 28, 'r10', 'r6'); a.emit(st_w, 'r6', 24, 'r10')
    a.emit(st_b, 'r0', 151, 'r10')
    a.emit(ld_bu, 145, 'r10', 'r13'); a.emit(cmp_i, 2, 'r13'); a.branch('l', 'bl2')
    a.label('bl1')
    a.emit(mov_rr, 'r10', 'r15'); a.emit(add_rr, 'r13', 'r15'); a.emit(st_b, 'r0', 116, 'r15')
    a.emit(add_i, 1, 'r13'); a.emit(cmp_i, 13, 'r13'); a.branch('le', 'bl1')
    a.label('bl2')
    a.emit(mov_i, 2, 'r6'); a.emit(st_b, 'r6', 116, 'r10'); a.emit(st_b, 'r0', 145, 'r10')
    a.emit(mov_i, 1, 'r6'); a.emit(st_b, 'r6', 117, 'r10')
    or_mask(a, 4025)
    a.emit(jmp_reg, 'lp')


# ---------------------------------------------------------------- the engine
def build_engine(base=L.ENGINE):
    a = Asm(base)
    # =============== HOOK (from the stub; lp = ROM return; r12 = ENG; r1, r6-r29 free) =========
    a.emit(mov_rr, 'r12', 'r20'); a.emit(st_w, 'lp', 16, 'r20')
    a.emit(ld_bu, 4021, 'ep', 'r15'); a.emit(ld_bu, 4026, 'ep', 'r16')
    a.emit(ld_bu, 4027, 'ep', 'r17'); a.emit(or_rr, 'r17', 'r16'); a.emit(not_rr, 'r16', 'r16')
    a.emit(and_rr, 'r16', 'r15')                                        # cand = active & normal
    a.emit(ld_bu, 0, 'r20', 'r21'); a.emit(and_rr, 'r15', 'r21')       # owned &= cand
    a.emit(ld_bu, 4023, 'ep', 'r27'); a.emit(and_rr, 'r15', 'r27')     # note starts pending
    a.bfar('nz', 'scan')                                                # (rare) take-over scan
    a.label('nonew_main')
    a.emit(st_b, 'r21', 0, 'r20')
    a.emit(mov32, UNDO, 'r6'); a.emit(st_w, 'r6', CURSOR, 'r20')        # undo list empty
    # ---- every owned voice: stream, interpolate raw samples into the ROM's buffer, patch ----
    a.emit(mov_rr, 'r21', 'r27')
    a.label('v_next')
    a.emit(cmp_rr, 'r0', 'r27'); a.bfar('z', 'v_done')
    a.mov32l('LSB', 'r11'); a.emit(add_rr, 'r27', 'r11'); a.emit(ld_bu, 0, 'r11', 'r11')   # voice
    a.emit(mov_rr, 'r27', 'r6'); a.emit(add_i, -1, 'r6'); a.emit(and_rr, 'r6', 'r27')       # done
    a.emit(mov_rr, 'r11', 'r26'); a.emit(shl_i, 6, 'r26'); a.emit(mov32, VS, 'r16')
    a.emit(add_rr, 'r16', 'r26')                                        # r26 = VS (kept by decoder)
    a.emit(ld_w, 32, 'r26', 'r10'); a.emit(ld_w, 36, 'r26', 'r9'); a.emit(ld_w, 40, 'r26', 'r28')
    a.emit(ld_bu, 142, 'r10', 'r29')
    a.emit(ld_w, 0, 'r26', 'r17'); a.emit(ld_w, 4, 'r26', 'r18')
    a.emit(movhi, 0x10, 'r0', 'r23')                                    # 16.0
    a.emit(mov_rr, 'r17', 'r6'); a.emit(shl_i, 2, 'r6'); a.branch('nc', 'nf')   # bit30 (CY)
    a.emit(shl_i, 2, 'r17'); a.emit(shr_i, 2, 'r17')
    a.calll('DECW')                                                     # first chunk
    a.branch('r', 'go')
    a.label('nf')
    a.emit(cmp_rr, 'r0', 'r17'); a.branch('ge', 'go')                   # bit31?
    a.emit(shl_i, 1, 'r17'); a.emit(shr_i, 1, 'r17')
    a.calll('ADV')                                                      # deferred chunk advance
    a.emit(cmp_rr, 'r0', 'r21'); a.bfar('nz', 'v_next')                 # sample ended
    a.label('go')
    a.emit(ld_bu, 8, 'r26', 'r6'); a.emit(cmp_rr, 'r0', 'r6'); a.branch('z', 'g16')
    a.emit(cmp_i, 1, 'r6'); a.bfar('z', 'g8')
    a.jumpl('g4')
    for n, sh in ((16, 4), (8, 3), (4, 2)):
        # no chunk crossing possible in this block (P + n * step <= 16.0): no crossing test
        a.label('g%d' % n)
        a.emit(mov_rr, 'r18', 'r6'); a.emit(shl_i, sh, 'r6'); a.emit(add_rr, 'r17', 'r6')
        a.emit(cmp_rr, 'r23', 'r6'); a.bfar('h', 'n%d' % n)
        for k in range(n):
            emit_interp(a)
            a.emit(st_h, 'r15', 2 * k, 'r28')
            a.emit(add_rr, 'r18', 'r17')
        a.jumpl('patch')
        a.label('n%d' % n)
        for k in range(n):
            emit_interp(a)
            a.emit(st_h, 'r15', 2 * k, 'r28')
            a.emit(add_rr, 'r18', 'r17')
            a.emit(cmp_rr, 'r23', 'r17'); a.branch('nh', 'f%d_%d' % (n, k))
            if k < n - 1:
                a.calll('ADV')
                a.emit(cmp_rr, 'r0', 'r21'); a.bfar('nz', 'v_next')        # sample ended
            else:
                a.emit(movhi, 0x8000, 'r0', 'r6'); a.emit(or_rr, 'r6', 'r17')  # advance next block
            a.label('f%d_%d' % (n, k))
        a.jumpl('patch')
    # ---- patch the fields the ROM's pass would use; the undo list lets POST put them back ----
    a.label('patch')
    a.emit(st_w, 'r17', 0, 'r26')
    a.emit(mov32, ENG, 'r6'); a.emit(ld_w, CURSOR, 'r6', 'r7')
    a.emit(st_w, 'r10', 0, 'r7')
    for i, off in enumerate(UNDO_SHORT):
        a.emit(ld_w, off, 'r10', 'r8'); a.emit(st_w, 'r8', 4 + 4 * i, 'r7')
    a.emit(movea, L.NOOP_FMT, 'r0', 'r8'); a.emit(st_w, 'r8', 16, 'r10')  # decode = no-op
    a.emit(st_b, 'r0', 151, 'r10')                                      # phase 0
    a.emit(ld_bu, 8, 'r26', 'r8'); a.emit(cmp_rr, 'r0', 'r8'); a.branch('nz', 'pshort')
    for i, off in enumerate(UNDO_LONG[2:]):                             # Standard (1:1)
        a.emit(ld_w, off, 'r10', 'r8'); a.emit(st_w, 'r8', 12 + 4 * i, 'r7')
    a.emit(mov_i, -1, 'r8'); a.emit(shr_i, 1, 'r8'); a.emit(st_w, 'r8', 32, 'r10')   # end: never
    a.emit(st_w, 'r0', 36, 'r10')                                       # pointer: no segment match
    a.emit(st_b, 'r0', 137, 'r10')                                      # position step 0
    a.emit(addi, 4 * (1 + len(UNDO_LONG)), 'r7', 'r7'); a.emit(st_w, 'r7', CURSOR, 'r6')
    a.jumpl('v_next')
    a.label('pshort')
    a.emit(addi, 4 * (1 + len(UNDO_SHORT)), 'r7', 'r7'); a.emit(st_w, 'r7', CURSOR, 'r6')
    a.jumpl('v_next')
    a.label('v_done')
    a.emit(mov32, ENG, 'r20'); a.emit(ld_w, 16, 'r20', 'lp')
    a.emit(ld_w, CURSOR, 'r20', 'r6'); a.emit(addi, UNDO - ENG, 'r20', 'r7'); a.emit(cmp_rr, 'r7', 'r6')
    a.branch('z', 'noredir')
    a.emit(st_w, 'r0', 0, 'r6')                                         # terminate the undo list
    # something patched: redirect the interrupt's return into POST
    a.emit(ld_w, 876, 'ep', 'r10'); a.emit(st_w, 'r10', SAVEPC, 'r20')
    a.emit(ld_w, 880, 'ep', 'r10'); a.emit(st_w, 'r10', SAVEPC + 4, 'r20')
    a.emit(ori, 0x20, 'r10', 'r10'); a.emit(st_w, 'r10', 880, 'ep')
    a.mov32l('POST', 'r10'); a.emit(st_w, 'r10', 876, 'ep')
    a.label('noredir')
    a.jump(L.MONO_HOOK)

    # ---- take-over scan of pending note starts (out of line) ----
    a.label('scan')
    a.emit(mov_i, 0, 'r25')                                             # new engine notes
    emit_bitloop_head(a, 'r27', 'r14', 'h')
    emit_rec(a, 'r14', 'r12', 'r16')
    a.emit(ld_bu, 142, 'r12', 'r13')
    a.emit(movhi, 3, 'gp', 'r1'); a.emit(movea, L.SLOTS, 'r1', 'r16')
    a.emit(mov_rr, 'r14', 'r17'); a.emit(shl_i, 6, 'r17'); a.emit(add_rr, 'r17', 'r16')
    a.emit(ld_h, 10, 'r16', 'r17')                                      # pad (sample)
    a.emit(cmp_rr, 'r0', 'r17'); a.bfar('lt', 'hno')
    a.emit(movea, L.NSAMPLES - 1, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r17'); a.bfar('gt', 'hno')
    a.emit(shl_i, 2, 'r17'); a.emit(mov32, VTAB, 'r18'); a.emit(add_rr, 'r17', 'r18')
    emit_record_step(a)
    a.emit(st_b, 'r0', 148, 'r12'); a.emit(st_b, 'r0', 187, 'r12')    # no time stretch (Phrase)
    a.emit(mov_rr, 'r14', 'r17'); a.emit(shl_i, 6, 'r17'); a.emit(mov32, VS, 'r1')
    a.emit(add_rr, 'r1', 'r17')                                         # r17 = VS for voice
    a.emit(ld_bu, 139, 'r12', 'r18'); a.emit(cmp_i, 2, 'r18'); a.branch('le', 'hc')
    a.emit(mov_i, 2, 'r18')
    a.label('hc')
    a.emit(st_b, 'r18', 8, 'r17')                                       # output rate shift c
    a.emit(movhi, 0x4001, 'r0', 'r1')                                   # P = 1.0, first decode due
    a.emit(st_w, 'r1', 0, 'r17'); a.emit(st_w, 'r19', 4, 'r17')
    a.emit(ld_w, 8, 'r20', 'r1'); a.emit(add_i, 1, 'r1'); a.emit(st_w, 'r1', 8, 'r20')
    a.emit(st_w, 'r1', 12, 'r17')                                       # start serial
    a.emit(st_w, 'r12', 32, 'r17')                                      # voice record
    a.emit(mov_rr, 'r14', 'r1'); a.emit(shl_i, 6, 'r1'); a.emit(mov32, XB, 'r16')
    a.emit(add_rr, 'r16', 'r1'); a.emit(st_w, 'r1', 36, 'r17'); a.emit(st_h, 'r0', 0, 'r1')  # x, x[0]=0
    a.emit(mov_rr, 'r14', 'r1'); a.emit(shl_i, 5, 'r1'); a.emit(movea, L.ROM_BUF, 'ep', 'r16')
    a.emit(add_rr, 'r16', 'r1'); a.emit(st_w, 'r1', 40, 'r17')         # ROM buffer of the voice
    a.emit(st_w, 'r14', 44, 'r17')                                      # voice index
    a.emit(st_b, 'r0', 9, 'r17')                                        # not a 2nd-note candidate
    a.emit(or_rr, 'r13', 'r21'); a.emit(or_rr, 'r13', 'r25')
    a.jumpl('h_next')
    a.label('hno')
    a.emit(not_rr, 'r13', 'r15'); a.emit(and_rr, 'r15', 'r21')
    a.jumpl('h_next')
    a.label('h_done')
    emit_cap(a)
    a.label('nonew')
    a.jumpl('nonew_main')

    # ---- ADV: while P > 16: next chunk (bookkeeping + decode). out: r21 = 1 if finished
    a.label('ADV')
    a.emit(mov_rr, 'lp', 'r1')
    a.label('a1')
    a.emit(sub_rr, 'r23', 'r17')
    a.emit(ld_h, 32, 'r9', 'r6'); a.emit(st_h, 'r6', 0, 'r9')           # x[0] = x[16]
    a.calll('BOOK')
    a.emit(cmp_rr, 'r0', 'r21'); a.branch('nz', 'a9')
    a.calll('DECW')
    a.emit(mov_i, 0, 'r21')
    a.emit(cmp_rr, 'r23', 'r17'); a.branch('h', 'a1')
    a.label('a9')
    a.emit(jmp_reg, 'r1')
    # ---- DECW: the ROM decoder into x[1..16] with the real fields. The decoder clobbers r7-r25
    # and keeps r1, r6, r26-r29: the loop state is put back from VS afterwards.
    a.label('DECW')
    a.emit(st_w, 'r17', 0, 'r26'); a.emit(st_w, 'lp', 48, 'r26')
    a.emit(addi, 2, 'r9', 'r12'); a.emit(st_w, 'r12', 0, 'r10')
    a.emit(ld_w, 36, 'r10', 'r12'); a.emit(st_w, 'r12', 8, 'r10')
    a.emit(mov_rr, 'r10', 'r6')
    a.call(L.DECODE)
    a.emit(mov_rr, 'r6', 'r10')
    a.emit(ld_w, 0, 'r26', 'r17'); a.emit(ld_w, 4, 'r26', 'r18')
    a.emit(ld_w, 36, 'r26', 'r9'); a.emit(ld_w, 44, 'r26', 'r11')
    a.emit(movhi, 0x10, 'r0', 'r23')
    a.emit(ld_w, 48, 'r26', 'lp'); a.emit(jmp_reg, 'lp')
    emit_book(a)

    # =============== POST (after the ROM's reti; interrupts off; every register live) ===============
    a.label('POST')
    a.emit(addi, -12, 'sp', 'sp')
    a.emit(st_w, 'r1', 0, 'sp'); a.emit(st_w, 'r10', 4, 'sp'); a.emit(st_w, 'r11', 8, 'sp')
    a.emit(mov32, UNDO, 'r10')
    a.label('pl')
    a.emit(ld_w, 0, 'r10', 'r11'); a.emit(cmp_rr, 'r0', 'r11'); a.branch('z', 'pend')
    for i, off in enumerate(UNDO_SHORT):
        a.emit(ld_w, 4 + 4 * i, 'r10', 'r1'); a.emit(st_w, 'r1', off, 'r11')
    a.emit(ld_bu, 139, 'r11', 'r1'); a.emit(cmp_rr, 'r0', 'r1'); a.branch('nz', 'pls')  # rate code
    for i, off in enumerate(UNDO_LONG[2:]):
        a.emit(ld_w, 12 + 4 * i, 'r10', 'r1'); a.emit(st_w, 'r1', off, 'r11')
    a.emit(addi, 4 * (1 + len(UNDO_LONG)), 'r10', 'r10'); a.branch('r', 'pl')
    a.label('pls')
    a.emit(addi, 4 * (1 + len(UNDO_SHORT)), 'r10', 'r10'); a.branch('r', 'pl')
    a.label('pend')
    a.emit(mov32, ENG + SAVEPC, 'r1')                                   # back to the interrupted code
    a.emit(ld_w, 0, 'r1', 'r10'); a.emit(ldsr, 'r10', 'eipc')
    a.emit(ld_w, 4, 'r1', 'r10'); a.emit(ldsr, 'r10', 'eipsw')
    a.emit(stsr, 'psw', 'r10'); a.emit(ori, 0x40, 'r10', 'r10'); a.emit(ldsr, 'r10', 'psw')
    a.emit(ld_w, 8, 'sp', 'r11'); a.emit(ld_w, 4, 'sp', 'r10'); a.emit(ld_w, 0, 'sp', 'r1')
    a.emit(addi, 12, 'sp', 'sp')
    a.emit(reti)
    # ---- LSB[m] = index of the lowest set bit of m (m = 1..255)
    a.label('LSB')
    a.emit(raw, bytes([0] + [((m & -m).bit_length() - 1) for m in range(1, 256)]))
    return a.assemble(), a.labels


def build_hook_stub():
    """at the start of every audio block: straight back to the stock hook unless an engine voice
    plays or a note start is pending (and the engine RAM has been initialised)."""
    a = Asm(L.HOOK)
    a.emit(mov32, ENG, 'r12')                                           # (the engine expects r12 = ENG)
    a.emit(ld_bu, 0, 'r12', 'r10'); a.emit(ld_bu, 4023, 'ep', 'r11'); a.emit(or_rr, 'r11', 'r10')
    a.branch('nz', 'act')
    a.jump(L.MONO_HOOK)
    a.label('act')
    a.emit(ld_w, 4, 'r12', 'r10'); a.emit(mov32, L.READY, 'r11'); a.emit(cmp_rr, 'r11', 'r10')
    a.branch('nz', 'mono')
    a.jump(L.ENGINE)
    a.label('mono')
    a.jump(L.MONO_HOOK)
    return a.assemble()


def build_idle():
    """idle task start-up: the original call, engine RAM init (READY last), then the original
    endless loop."""
    a = Asm(L.IDLE)
    a.call(L.SET_FLG)
    a.emit(mov32, ENG, 'r20')
    for off in (0, 4, 8, 12, 0x14, 0x18, 0x1C):
        a.emit(st_w, 'r0', off, 'r20')
    a.emit(mov32, L.READY, 'r24'); a.emit(st_w, 'r24', 4, 'r20')
    a.label('hang')
    a.branch('r', 'hang')
    return a.assemble()


def build_padsetup():
    """replaces get_param(46, pad) at the 3 pad set-up sites (r6 = 46, r7 = pad -> r10 = rate);
    also records the pad's settings in VTAB[pad]."""
    a = Asm(L.PADSETUP)
    a.emit(prepare_lp, 12)
    a.emit(st_w, 'r7', 0, 'sp')
    a.call(L.GETTER)                                                    # rate
    a.emit(st_w, 'r10', 4, 'sp')
    a.emit(movea, L.PARAM_VARI, 'r0', 'r6'); a.emit(ld_w, 0, 'sp', 'r7'); a.call(L.GETTER)
    a.emit(st_w, 'r10', 8, 'sp')
    a.emit(movea, L.PARAM_FINE, 'r0', 'r6'); a.emit(ld_w, 0, 'sp', 'r7'); a.call(L.GETTER)
    a.emit(ld_w, 0, 'sp', 'r11')
    a.emit(cmp_rr, 'r0', 'r11'); a.branch('lt', 'done')
    a.emit(movea, L.NSAMPLES - 1, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r11'); a.branch('gt', 'done')
    a.emit(shl_i, 2, 'r11'); a.emit(mov32, VTAB, 'r12'); a.emit(add_rr, 'r11', 'r12')
    a.emit(andi, 0xFF, 'r10', 'r10'); a.emit(shl_i, 8, 'r10')
    a.emit(ld_w, 8, 'sp', 'r13'); a.emit(andi, 0xFF, 'r13', 'r13'); a.emit(or_rr, 'r13', 'r10')
    a.emit(movhi, TAG, 'r10', 'r10')
    a.emit(st_w, 'r10', 0, 'r12')
    a.label('done')
    a.emit(ld_w, 4, 'sp', 'r10')
    a.emit(dispose_lp, 12)
    return a.assemble()


def build_paramhook():
    """audio task on_param_change(pad r6, id r7, value r8): Varispeed / Fine Tune changes update
    their VTAB byte; everything else continues into the stock handler."""
    a = Asm(L.PARAMHOOK)
    a.emit(movea, L.PARAM_VARI, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.branch('z', 'mine')
    a.emit(movea, L.PARAM_FINE, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.branch('z', 'mine')
    a.emit(raw, L.HANDLER_FIRST)
    a.jump(L.PARAM_HANDLER + 4)
    a.label('mine')
    a.emit(cmp_rr, 'r0', 'r6'); a.branch('lt', 'out')
    a.emit(movea, L.NSAMPLES - 1, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r6'); a.branch('gt', 'out')
    a.emit(mov_rr, 'r6', 'r11'); a.emit(shl_i, 2, 'r11')
    a.emit(mov32, VTAB, 'r12'); a.emit(add_rr, 'r11', 'r12')
    a.emit(ld_w, 0, 'r12', 'r10')
    a.emit(mov_rr, 'r10', 'r13'); a.emit(shr_i, 16, 'r13')
    a.emit(movea, TAG, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r13'); a.branch('z', 'tagged')
    a.emit(mov_i, 0, 'r10')                                             # not set up yet: other = 0
    a.label('tagged')
    a.emit(andi, 0xFF, 'r8', 'r8')
    a.emit(movea, L.PARAM_VARI, 'r0', 'r1'); a.emit(cmp_rr, 'r1', 'r7'); a.branch('nz', 'fine')
    a.emit(andi, 0xFF00, 'r10', 'r10'); a.emit(or_rr, 'r8', 'r10'); a.branch('r', 'st')
    a.label('fine')
    a.emit(andi, 0x00FF, 'r10', 'r10'); a.emit(shl_i, 8, 'r8'); a.emit(or_rr, 'r8', 'r10')
    a.label('st')
    a.emit(movhi, TAG, 'r10', 'r10'); a.emit(st_w, 'r10', 0, 'r12')
    a.label('out')
    a.emit(jmp_reg, 'lp')
    return a.assemble()


def install(d):
    ff = lambda b: b'\xff' * len(b)
    code, labels = build_engine()
    assert L.ENGINE + len(code) <= L.ENGINE_END, hex(L.ENGINE + len(code))
    put(d, L.ENGINE, code, ff(code))
    stub = build_hook_stub(); assert L.HOOK + len(stub) <= L.VOICEHELP
    put(d, L.HOOK, stub, ff(stub))
    put(d, L.HOOK_INSTALL, movhi(L.HOOK >> 16, 'tp', 'r1') + movea(L.HOOK & 0xFFFF, 'r1', 'r12'),
        movhi(0x1B, 'tp', 'r1') + movea(13404, 'r1', 'r12'))
    idle = build_idle(); put(d, L.IDLE, idle, ff(idle))
    put(d, L.IDLE_CALL_SITE, jarl(L.IDLE, L.IDLE_CALL_SITE), jarl(L.SET_FLG, L.IDLE_CALL_SITE))
    ps = build_padsetup(); put(d, L.PADSETUP, ps, ff(ps))
    for site in L.PAD_SETUP_SITES:
        put(d, site, jarl(L.PADSETUP, site), jarl(L.GETTER, site))
    ph = build_paramhook(); put(d, L.PARAMHOOK, ph, ff(ph))
    put(d, L.PARAM_HANDLER, jr(L.PARAMHOOK, L.PARAM_HANDLER), L.HANDLER_FIRST)
    return labels
