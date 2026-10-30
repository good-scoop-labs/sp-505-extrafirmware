"""Small NEC V850 / V850E1 disassembler (little-endian).
dis(buf, off, addr) -> (length, text, target_or_None)
CLI: v850.py image.bin file_offset count [base]
"""
import struct, sys

R = ['r0', 'r1', 'r2', 'sp', 'gp', 'tp', 'r6', 'r7', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14',
     'r15', 'r16', 'r17', 'r18', 'r19', 'r20', 'r21', 'r22', 'r23', 'r24', 'r25', 'r26', 'r27',
     'r28', 'r29', 'ep', 'lp']
COND = ['v', 'l', 'z', 'nh', 'n', 'r', 'lt', 'le', 'nv', 'nl', 'nz', 'h', 'p', 'sa', 'ge', 'gt']
SREG = {0: 'eipc', 1: 'eipsw', 2: 'fepc', 3: 'fepsw', 4: 'ecr', 5: 'psw', 16: 'ctpc', 17: 'ctpsw',
        18: 'dbpc', 19: 'dbpsw', 20: 'ctbp', 21: 'dir'}

def sx(v, bits):
    m = 1 << (bits - 1)
    return (v ^ m) - m

def h16(buf, o):
    return struct.unpack_from('<H', buf, o)[0]

def dis(buf, o, addr):
    if o + 2 > len(buf):
        return 2, '??', None
    w = h16(buf, o)
    r2 = w >> 11; op = (w >> 5) & 0x3f; r1 = w & 0x1f
    rr1, rr2 = R[r1], R[r2]
    imm5 = sx(r1, 5)
    # 16-bit formats
    if op < 0x10:
        if op == 0:
            if w == 0: return 2, 'nop', None
            if r2 == 0: return 2, 'callt? %s' % rr1, None
            return 2, 'mov %s, %s' % (rr1, rr2), None
        if op == 2 and r2 == 0:
            if r1 == 0: return 2, 'fetrap?', None
            return 2, 'switch %s' % rr1, None
        if op == 3:
            if r2 == 0: return 2, 'jmp [%s]' % rr1, None
            if r1 & 0x10: return 2, 'sld.hu %d[ep], %s' % ((r1 & 0xf) * 2, rr2), None
            return 2, 'sld.bu %d[ep], %s' % (r1 & 0xf, rr2), None
        if r2 == 0 and op in (4, 5, 6, 7):
            return 2, ['zxb', 'sxb', 'zxh', 'sxh'][op - 4] + ' ' + rr1, None
        names = {1: 'not', 2: 'divh', 4: 'satsubr', 5: 'satsub', 6: 'satadd', 7: 'mulh', 8: 'or',
                 9: 'xor', 10: 'and', 11: 'tst', 12: 'subr', 13: 'sub', 14: 'add', 15: 'cmp'}
        return 2, '%s %s, %s' % (names[op], rr1, rr2), None
    if op < 0x18:
        if op == 0x10 and r2 == 0:
            return 2, 'callt %d' % (w & 0x3f), None
        names = {0x10: 'mov', 0x11: 'satadd', 0x12: 'add', 0x13: 'cmp', 0x14: 'shr', 0x15: 'sar',
                 0x16: 'shl', 0x17: 'mulh'}
        v = r1 if op in (0x14, 0x15, 0x16) else imm5
        return 2, '%s %d, %s' % (names[op], v, rr2), None
    top4 = (w >> 7) & 0xf
    if top4 == 0x6: return 2, 'sld.b %d[ep], %s' % (w & 0x7f, rr2), None
    if top4 == 0x7: return 2, 'sst.b %s, %d[ep]' % (rr2, w & 0x7f), None
    if top4 == 0x8: return 2, 'sld.h %d[ep], %s' % ((w & 0x7f) * 2, rr2), None
    if top4 == 0x9: return 2, 'sst.h %s, %d[ep]' % (rr2, (w & 0x7f) * 2), None
    if top4 == 0xa:
        d = (w & 0x7e) * 2
        if w & 1: return 2, 'sst.w %s, %d[ep]' % (rr2, d), None
        return 2, 'sld.w %d[ep], %s' % (d, rr2), None
    if top4 == 0xb:
        disp = sx((((w >> 11) & 0x1f) << 4) | (((w >> 4) & 7) << 1), 9)
        t = (addr + disp) & 0xffffffff
        return 2, 'b%s 0x%x' % (COND[w & 0xf], t), t
    # 32-bit formats
    if o + 4 > len(buf):
        return 2, '??', None
    w2 = h16(buf, o + 2)
    s16 = sx(w2, 16)
    if op == 0x31 and r2 == 0:  # mov imm32
        v = struct.unpack_from('<I', buf, o + 2)[0]
        return 6, 'mov 0x%x, %s' % (v, rr1), None
    if op == 0x32 and r2 == 0 or op == 0x33 and r2 == 0:  # dispose
        imm = (w >> 1) & 0x1f
        lst = ((w & 1) << 11) | (w2 >> 5)
        rr = w2 & 0x1f
        return 4, 'dispose %d, {0x%x}%s' % (imm * 4, lst, (', [%s]' % R[rr]) if rr else ''), None
    if op in range(0x30, 0x38):
        names = ['addi', 'movea', 'movhi', 'satsubi', 'ori', 'xori', 'andi', 'mulhi']
        if op in (0x34, 0x35, 0x36, 0x32):
            return 4, '%s 0x%x, %s, %s' % (names[op - 0x30], w2, rr1, rr2), None
        return 4, '%s %d, %s, %s' % (names[op - 0x30], s16, rr1, rr2), None
    if op == 0x38: return 4, 'ld.b %d[%s], %s' % (s16, rr1, rr2), None
    if op == 0x39:
        return 4, ('ld.w' if w2 & 1 else 'ld.h') + ' %d[%s], %s' % (sx(w2 & ~1, 16), rr1, rr2), None
    if op == 0x3a: return 4, 'st.b %s, %d[%s]' % (rr2, s16, rr1), None
    if op == 0x3b:
        return 4, ('st.w' if w2 & 1 else 'st.h') + ' %s, %d[%s]' % (rr2, sx(w2 & ~1, 16), rr1), None
    if op in (0x3c, 0x3d):
        if w2 & 1:
            if r2 == 0 and op == 0x3c:  # prepare
                imm = (w >> 1) & 0x1f
                lst = ((w & 1) << 11) | (w2 >> 5)
                return 4, 'prepare {0x%x}, %d (sub=%d)' % (lst, imm * 4, (w2 >> 1) & 0xf), None
            if op == 0x3d and r2 == 0:
                imm = (w >> 1) & 0x1f
                return 4, 'prepare? %x %x' % (w, w2), None
            # ld.bu
            disp = sx(((w2 & ~1) | ((w >> 5) & 1)), 16)
            return 4, 'ld.bu %d[%s], %s' % (disp, rr1, rr2), None
        disp = sx(((w & 0x3f) << 16) | w2, 22)
        t = (addr + disp) & 0xffffffff
        if r2 == 0: return 4, 'jr 0x%x' % t, t
        return 4, 'jarl 0x%x, %s' % (t, rr2), t
    if op == 0x3e:
        sub = w >> 14; bit = (w >> 11) & 7
        return 4, '%s %d, %d[%s]' % (['set1', 'not1', 'clr1', 'tst1'][sub], bit, s16, rr1), None
    # op == 0x3f extended
    if w2 & 1:
        return 4, 'ld.hu %d[%s], %s' % (sx(w2 & ~1, 16), rr1, rr2), None
    x = w2 & 0x7e0
    r3 = R[w2 >> 11]
    if x == 0x000: return 4, 'setf %s, %s' % (COND[r1 & 0xf], rr2), None
    if x == 0x020: return 4, 'ldsr %s, %s' % (rr1, SREG.get(r2, 'sr%d' % r2)), None
    if x == 0x040: return 4, 'stsr %s, %s' % (SREG.get(r1, 'sr%d' % r1), rr2), None
    if x == 0x080: return 4, 'shr %s, %s' % (rr1, rr2), None
    if x == 0x0a0: return 4, 'sar %s, %s' % (rr1, rr2), None
    if x == 0x0c0: return 4, 'shl %s, %s' % (rr1, rr2), None
    if x == 0x0e0:
        return 4, '%s %s, [%s]' % (['set1', 'not1', 'clr1', 'tst1'][(w2 >> 1) & 3], rr2, rr1), None
    if x == 0x100: return 4, 'trap %d' % r1, None
    if x == 0x120: return 4, 'halt', None
    if x == 0x140:
        return 4, {0: 'reti', 4: 'ctret', 6: 'dbret'}.get(w2 & 0x1f, 'reti?'), None
    if x == 0x160: return 4, 'ei' if w & 0x8000 else 'di', None
    if x == 0x200: return 4, 'sasf %s, %s' % (COND[r1 & 0xf], rr2), None
    if x == 0x220:
        return 4, '%s %s, %s, %s' % ('mulu' if w2 & 2 else 'mul', rr1, rr2, r3), None
    if x in (0x240, 0x260):
        imm9 = r1 | (((w2 >> 2) & 0xf) << 5)
        return 4, '%s %d, %s, %s' % ('mulu' if w2 & 2 else 'mul', sx(imm9, 9), rr2, r3), None
    if x == 0x280:
        return 4, '%s %s, %s, %s' % ('divhu' if w2 & 2 else 'divh', rr1, rr2, r3), None
    if x == 0x2c0:
        return 4, '%s %s, %s, %s' % ('divu' if w2 & 2 else 'div', rr1, rr2, r3), None
    if x == 0x300:
        return 4, 'cmov %s, %d, %s, %s' % (COND[(w2 >> 1) & 0xf], imm5, rr2, r3), None
    if x == 0x320:
        return 4, 'cmov %s, %s, %s, %s' % (COND[(w2 >> 1) & 0xf], rr1, rr2, r3), None
    if x == 0x340:
        return 4, {0: 'bsw', 2: 'bsh', 4: 'hsw'}.get(w2 & 6, 'bs?') + ' %s, %s' % (rr2, r3), None
    return 4, '.ext %04x %04x' % (w, w2), None

def listing(buf, start, count, base):
    o = start; out = []
    for _ in range(count):
        n, t, _ = dis(buf, o, base + o)
        raw = buf[o:o + n].hex()
        out.append('%08x: %-12s %s' % (base + o, raw, t))
        o += n
    return '\n'.join(out)

if __name__ == '__main__':
    buf = open(sys.argv[1], 'rb').read()
    base = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0
    print(listing(buf, int(sys.argv[2], 0), int(sys.argv[3], 0), base))
