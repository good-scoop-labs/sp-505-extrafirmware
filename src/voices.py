"""Polyphony weighting: while varispeed notes play, the pad voice allocator sees fewer free voices,
so it fades out other voices earlier and the SP-505 stays out of "Too Busy!" overloads.

The allocator 0x1BDCDC computes  steal = needed - free - releasing  and asks 0x1BC3C4 to steal that
many of the oldest stealable voices. The load of the free count at 0x1BDD28 is replaced by a call
to VOICEHELP, which returns  free - reserve:

  reserve = sum over engine voices of (WEIGHT[rate code] - 1)
            capped at  CAP - engine voices                      (at least 2 other voices)
            and at     others + max(0, free + releasing - needed)
                       (others = stealable playing voices that aren't engine voices), so the
                       reserve can only make the allocator steal other voices, never a varispeed
                       note when nothing else is playing (e.g. two Long loops while resampling).

  mono Standard counts as 6 voices, mono Long as 4, mono lowest grade as 3, stereo as 6.
"""
import layout as L
from sp505fw import put
from v850asm import *

WEIGHT = {0: 6, 1: 4, 2: 3}
CAP = 6


def build_voicehelp():
    """r10 = free voice count - reserve (r19 = voices needed). Keeps every register except r1, r10."""
    a = Asm(L.VOICEHELP)
    a.emit(addi, -16, 'sp', 'sp')
    for i, r in enumerate(('r11', 'r12', 'r13', 'r14')):
        a.emit(st_w, r, 4 * i, 'sp')
    a.emit(movhi, 3, 'gp', 'r1'); a.emit(ld_w, L.FREE_COUNT, 'r1', 'r10')
    a.emit(mov32, L.ENG, 'r1')
    a.emit(ld_w, 4, 'r1', 'r11'); a.emit(mov32, L.READY, 'r12'); a.emit(cmp_rr, 'r12', 'r11')
    a.branch('nz', 'out')
    a.emit(ld_bu, 0, 'r1', 'r11'); a.emit(cmp_rr, 'r0', 'r11'); a.branch('z', 'out')
    a.emit(addi, L.VS - L.ENG, 'r1', 'r1')
    a.emit(mov_i, 0, 'r12')                                             # reserve
    a.emit(mov_i, 0, 'r13')                                             # engine voices
    a.label('wl')
    a.emit(shr_i, 1, 'r11'); a.branch('nc', 'nx')
    a.emit(add_i, 1, 'r13')
    a.emit(ld_bu, 8, 'r1', 'r10')
    a.emit(cmp_i, 0, 'r10'); a.branch('z', 'w0')
    a.emit(cmp_i, 1, 'r10'); a.branch('z', 'w1')
    a.emit(add_i, WEIGHT[2] - 1, 'r12'); a.branch('r', 'nx')
    a.label('w0')
    a.emit(add_i, WEIGHT[0] - 1, 'r12'); a.branch('r', 'nx')
    a.label('w1')
    a.emit(add_i, WEIGHT[1] - 1, 'r12')
    a.label('nx')
    a.emit(addi, 64, 'r1', 'r1')
    a.emit(cmp_rr, 'r0', 'r11'); a.branch('nz', 'wl')
    # cap 1: CAP - engine voices
    a.emit(mov_i, CAP, 'r14'); a.emit(sub_rr, 'r13', 'r14')
    a.emit(cmp_rr, 'r14', 'r12'); a.branch('le', 'c1')
    a.emit(mov_rr, 'r14', 'r12')
    a.label('c1')
    # cap 2: others + max(0, free + releasing - needed)
    a.emit(movhi, 3, 'gp', 'r1')
    a.emit(ld_w, L.LIST1_COUNT, 'r1', 'r11'); a.emit(sub_rr, 'r13', 'r11')  # others
    a.emit(cmp_rr, 'r0', 'r11'); a.branch('ge', 'c2')
    a.emit(mov_i, 0, 'r11')
    a.label('c2')
    a.emit(ld_w, L.FREE_COUNT, 'r1', 'r10'); a.emit(ld_w, L.REL_COUNT, 'r1', 'r14')
    a.emit(add_rr, 'r14', 'r10'); a.emit(sub_rr, 'r19', 'r10')
    a.emit(cmp_rr, 'r0', 'r10'); a.branch('ge', 'c3')
    a.emit(mov_i, 0, 'r10')
    a.label('c3')
    a.emit(add_rr, 'r10', 'r11')
    a.emit(cmp_rr, 'r11', 'r12'); a.branch('le', 'c4')
    a.emit(mov_rr, 'r11', 'r12')
    a.label('c4')
    a.emit(ld_w, L.FREE_COUNT, 'r1', 'r10'); a.emit(sub_rr, 'r12', 'r10')
    a.label('out')
    for i, r in enumerate(('r11', 'r12', 'r13', 'r14')):
        a.emit(ld_w, 4 * i, 'sp', r)
    a.emit(addi, 16, 'sp', 'sp')
    a.emit(jmp_reg, 'lp')
    return a.assemble()


def install(d):
    vh = build_voicehelp()
    assert L.VOICEHELP + len(vh) <= L.VARI_NAMES
    put(d, L.VOICEHELP, vh, b'\xff' * len(vh))
    put(d, L.ALLOC_SITE, jarl(L.VOICEHELP, L.ALLOC_SITE) + h(0, 0), L.ALLOC_ORIG)
