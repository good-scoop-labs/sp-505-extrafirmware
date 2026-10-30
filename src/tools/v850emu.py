"""Minimal V850E1 emulator for testing patch code against the SP-505 ROM/flash.
Covers the instruction set used by the ROM audio code and our patches."""
import struct

MASK = 0xFFFFFFFF

def s32(v):
    v &= MASK
    return v - (1 << 32) if v & 0x80000000 else v

def sx(v, bits):
    m = 1 << (bits - 1)
    v &= (1 << bits) - 1
    return (v ^ m) - m


class Halt(Exception):
    pass


class Mem:
    def __init__(self):
        self.regions = []   # (base, bytearray)

    def add(self, base, data):
        self.regions.append((base, data if isinstance(data, bytearray) else bytearray(data)))

    def _find(self, a, n):
        a &= MASK
        for base, buf in self.regions:
            if base <= a and a + n <= base + len(buf):
                return buf, a - base
        raise Halt('bad memory access %08x' % a)

    def r(self, a, n, signed=False):
        buf, o = self._find(a, n)
        return int.from_bytes(buf[o:o + n], 'little', signed=signed)

    def w(self, a, n, v):
        buf, o = self._find(a, n)
        buf[o:o + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')


class CPU:
    def __init__(self, mem):
        self.m = mem
        self.r = [0] * 32
        self.pc = 0
        self.z = self.s = self.ov = self.cy = self.sat = 0
        self.id = 0
        self.ep_flag = 0
        self.sr = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
        self.steps = 0

    # flags
    def psw(self):
        return (self.z | self.s << 1 | self.ov << 2 | self.cy << 3 | self.sat << 4 |
                self.id << 5 | self.ep_flag << 6)

    def set_psw(self, v):
        self.z, self.s, self.ov, self.cy, self.sat = v & 1, v >> 1 & 1, v >> 2 & 1, v >> 3 & 1, v >> 4 & 1
        self.id, self.ep_flag = v >> 5 & 1, v >> 6 & 1

    def setr(self, n, v):
        if n: self.r[n] = v & MASK

    def zs(self, v):
        v &= MASK
        self.z = int(v == 0); self.s = v >> 31
        return v

    def add(self, a, b):
        res = (a + b) & MASK
        self.cy = int((a & MASK) + (b & MASK) > MASK)
        self.ov = int(((a ^ res) & (b ^ res) & 0x80000000) != 0)
        return self.zs(res)

    def sub(self, a, b):     # a - b
        res = (a - b) & MASK
        self.cy = int((a & MASK) < (b & MASK))
        self.ov = int(((a ^ b) & (a ^ res) & 0x80000000) != 0)
        return self.zs(res)

    def satv(self, exact, res):
        if exact > 0x7FFFFFFF: self.sat = 1; return self.zs(0x7FFFFFFF)
        if exact < -0x80000000: self.sat = 1; return self.zs(0x80000000)
        return res

    def cond(self, c):
        z, s, ov, cy = self.z, self.s, self.ov, self.cy
        return [ov, cy, z, cy | z, s, 1, s ^ ov, (s ^ ov) | z,
                1 - ov, 1 - cy, 1 - z, 1 - (cy | z), 1 - s, self.sat, 1 - (s ^ ov), 1 - ((s ^ ov) | z)][c]

    def h(self, a):
        return self.m.r(a, 2)

    def step(self):
        pc = self.pc
        w = self.h(pc)
        r2 = w >> 11; op = (w >> 5) & 0x3f; r1 = w & 0x1f
        R = self.r
        npc = pc + 2
        self.steps += 1
        if op < 0x10:
            if op == 0:
                if w == 0: pass
                elif r2 == 0: raise Halt('callt at %x' % pc)
                else: self.setr(r2, R[r1])
            elif op == 1: self.setr(r2, self.zs(~R[r1])); self.ov = 0
            elif op == 2:
                if r2 == 0:   # switch
                    adr = npc + (R[r1] << 1)
                    npc = npc + (sx(self.h(adr), 16) << 1)
                else:         # divh
                    d = sx(R[r1], 16); n = s32(R[r2])
                    if d: q = int(n / d); self.setr(r2, self.zs(q)); self.ov = 0
            elif op == 3:
                if r2 == 0: npc = R[r1] & ~1
                elif r1 & 0x10: self.setr(r2, self.m.r(R[30] + (r1 & 0xf) * 2, 2))
                else: self.setr(r2, self.m.r(R[30] + (r1 & 0xf), 1))
            elif r2 == 0 and op in (4, 5, 6, 7):
                v = R[r1]
                v = [v & 0xff, sx(v, 8), v & 0xffff, sx(v, 16)][op - 4]
                self.setr(r1, v)
            elif op == 7: self.setr(r2, sx(R[r2], 16) * sx(R[r1], 16))
            elif op == 4: self.setr(r2, self.satv(s32(R[r1]) - s32(R[r2]), self.sub(R[r1], R[r2])))
            elif op == 5: self.setr(r2, self.satv(s32(R[r2]) - s32(R[r1]), self.sub(R[r2], R[r1])))
            elif op == 6: self.setr(r2, self.satv(s32(R[r2]) + s32(R[r1]), self.add(R[r2], R[r1])))
            elif op == 8: self.setr(r2, self.zs(R[r2] | R[r1])); self.ov = 0
            elif op == 9: self.setr(r2, self.zs(R[r2] ^ R[r1])); self.ov = 0
            elif op == 10: self.setr(r2, self.zs(R[r2] & R[r1])); self.ov = 0
            elif op == 11: self.zs(R[r2] & R[r1]); self.ov = 0
            elif op == 12: self.setr(r2, self.sub(R[r1], R[r2]))
            elif op == 13: self.setr(r2, self.sub(R[r2], R[r1]))
            elif op == 14: self.setr(r2, self.add(R[r2], R[r1]))
            elif op == 15: self.sub(R[r2], R[r1])
            else: raise Halt('op %x at %x' % (op, pc))
        elif op < 0x18:
            imm = sx(r1, 5)
            if op == 0x10:
                if r2 == 0: raise Halt('callt at %x' % pc)
                self.setr(r2, imm)
            elif op == 0x11: self.setr(r2, self.satv(s32(R[r2]) + imm, self.add(R[r2], imm)))
            elif op == 0x12: self.setr(r2, self.add(R[r2], imm))
            elif op == 0x13: self.sub(R[r2], imm)
            elif op == 0x14:
                v = R[r2]; self.cy = (v >> (r1 - 1)) & 1 if r1 else 0
                self.setr(r2, self.zs(v >> r1)); self.ov = 0
            elif op == 0x15:
                v = s32(R[r2]); self.cy = (v >> (r1 - 1)) & 1 if r1 else 0
                self.setr(r2, self.zs(v >> r1)); self.ov = 0
            elif op == 0x16:
                v = R[r2]; self.cy = (v >> (32 - r1)) & 1 if r1 else 0
                self.setr(r2, self.zs(v << r1)); self.ov = 0
            elif op == 0x17: self.setr(r2, sx(R[r2], 16) * imm)
            else: raise Halt('op %x at %x' % (op, pc))
        else:
            top4 = (w >> 7) & 0xf
            if top4 in (6, 7, 8, 9, 0xa) and op < 0x30:
                ep = R[30]
                if top4 == 6: self.setr(r2, sx(self.m.r(ep + (w & 0x7f), 1), 8))
                elif top4 == 7: self.m.w(ep + (w & 0x7f), 1, R[r2])
                elif top4 == 8: self.setr(r2, sx(self.m.r(ep + (w & 0x7f) * 2, 2), 16))
                elif top4 == 9: self.m.w(ep + (w & 0x7f) * 2, 2, R[r2])
                else:
                    d = (w & 0x7e) * 2
                    if w & 1: self.m.w(ep + d, 4, R[r2])
                    else: self.setr(r2, self.m.r(ep + d, 4))
            elif top4 == 0xb and op < 0x30:
                disp = sx((((w >> 11) & 0x1f) << 4) | (((w >> 4) & 7) << 1), 9)
                if self.cond(w & 0xf): npc = pc + disp
            else:
                w2 = self.h(pc + 2); s16 = sx(w2, 16); npc = pc + 4
                if op == 0x31 and r2 == 0:
                    self.setr(r1, self.m.r(pc + 2, 4)); npc = pc + 6
                elif op in (0x32, 0x33) and r2 == 0:   # dispose
                    imm = (w >> 1) & 0x1f; lst = ((w & 1) << 11) | (w2 >> 5); rr = w2 & 0x1f
                    sp = R[3] + imm * 4
                    for reg in self._list(lst):
                        R[reg] = self.m.r(sp, 4); sp += 4
                    R[3] = sp & MASK
                    if rr: npc = R[rr]
                elif op == 0x30: self.setr(r2, self.add(R[r1], s16))
                elif op == 0x31: self.setr(r2, R[r1] + s16)
                elif op == 0x32: self.setr(r2, R[r1] + (w2 << 16))
                elif op == 0x33: self.setr(r2, self.satv(s32(R[r1]) - s16, self.sub(R[r1], s16)))
                elif op == 0x34: self.setr(r2, self.zs(R[r1] | w2)); self.ov = 0
                elif op == 0x35: self.setr(r2, self.zs(R[r1] ^ w2)); self.ov = 0
                elif op == 0x36: self.setr(r2, self.zs(R[r1] & w2)); self.ov = 0
                elif op == 0x37: self.setr(r2, sx(R[r1], 16) * s16)
                elif op == 0x38: self.setr(r2, sx(self.m.r(R[r1] + s16, 1), 8))
                elif op == 0x39:
                    a = R[r1] + sx(w2 & ~1, 16)
                    self.setr(r2, self.m.r(a, 4) if w2 & 1 else sx(self.m.r(a, 2), 16))
                elif op == 0x3a: self.m.w(R[r1] + s16, 1, R[r2])
                elif op == 0x3b:
                    a = R[r1] + sx(w2 & ~1, 16)
                    if w2 & 1: self.m.w(a, 4, R[r2])
                    else: self.m.w(a, 2, R[r2])
                elif op in (0x3c, 0x3d):
                    if w2 & 1:
                        if r2 == 0 and op == 0x3c:   # prepare
                            imm = (w >> 1) & 0x1f; lst = ((w & 1) << 11) | (w2 >> 5)
                            sub = (w2 >> 1) & 0xf
                            regs = self._list(lst)
                            sp = R[3]
                            for reg in reversed(regs):
                                sp -= 4; self.m.w(sp, 4, R[reg])
                            sp -= imm * 4
                            R[3] = sp & MASK
                            if sub: raise Halt('prepare sub %d' % sub)
                        else:
                            disp = sx(((w2 & ~1) | ((w >> 5) & 1)), 16)
                            self.setr(r2, self.m.r(R[r1] + disp, 1))
                    else:
                        disp = sx(((w & 0x3f) << 16) | w2, 22)
                        self.setr(r2, pc + 4)
                        npc = pc + disp
                elif op == 0x3e:
                    sub = w >> 14; bit = (w >> 11) & 7; a = R[r1] + s16
                    v = self.m.r(a, 1); self.z = int(not (v >> bit) & 1)
                    if sub == 0: v |= 1 << bit
                    elif sub == 1: v ^= 1 << bit
                    elif sub == 2: v &= ~(1 << bit)
                    if sub != 3: self.m.w(a, 1, v)
                else:   # 0x3f
                    if w2 & 1:
                        self.setr(r2, self.m.r(R[r1] + sx(w2 & ~1, 16), 2))
                    else:
                        x = w2 & 0x7e0; r3 = w2 >> 11
                        if x == 0x000: self.setr(r2, self.cond(r1 & 0xf))
                        elif x == 0x020:
                            if r2 == 5: self.set_psw(R[r1])
                            else: self.sr[r2] = R[r1]
                        elif x == 0x040: self.setr(r2, self.psw() if r1 == 5 else self.sr.get(r1, 0))
                        elif x == 0x080:
                            n = R[r1] & 31; v = R[r2]; self.cy = (v >> (n - 1)) & 1 if n else 0
                            self.setr(r2, self.zs(v >> n)); self.ov = 0
                        elif x == 0x0a0:
                            n = R[r1] & 31; v = s32(R[r2]); self.cy = (v >> (n - 1)) & 1 if n else 0
                            self.setr(r2, self.zs(v >> n)); self.ov = 0
                        elif x == 0x0c0:
                            n = R[r1] & 31; v = R[r2]; self.cy = (v >> (32 - n)) & 1 if n else 0
                            self.setr(r2, self.zs(v << n)); self.ov = 0
                        elif x == 0x140:
                            if self.ep_flag: npc = self.sr[0]; self.set_psw(self.sr[1])
                            else: npc = self.sr[0]; self.set_psw(self.sr[1])
                            raise Halt('reti')
                        elif x == 0x160: self.id = 0 if w & 0x8000 else 1
                        elif x == 0x220:
                            a, b = R[r2], R[r1]
                            if w2 & 2: p = a * b
                            else: p = s32(a) * s32(b)
                            p &= (1 << 64) - 1
                            self.setr(r2, p); self.setr(r3, p >> 32)
                        elif x in (0x240, 0x260):
                            imm9 = r1 | (((w2 >> 2) & 0xf) << 5)
                            if w2 & 2: p = R[r2] * (imm9 & 0x1ff)
                            else: p = s32(R[r2]) * sx(imm9, 9)
                            p &= (1 << 64) - 1
                            self.setr(r2, p); self.setr(r3, p >> 32)
                        elif x == 0x2c0:
                            d = R[r1]; n = R[r2]
                            if d:
                                if w2 & 2: q, rem = n // d, n % d
                                else:
                                    q = int(s32(n) / s32(d)); rem = s32(n) - q * s32(d)
                                self.setr(r2, self.zs(q)); self.setr(r3, rem); self.ov = 0
                        elif x == 0x320:
                            c = (w2 >> 1) & 0xf
                            self.setr(r3, R[r1] if self.cond(c) else R[r2])
                        elif x == 0x300:
                            c = (w2 >> 1) & 0xf
                            self.setr(r3, sx(r1, 5) if self.cond(c) else R[r2])
                        elif x == 0x340:
                            v = R[r2]; k = w2 & 6
                            if k == 0: v = int.from_bytes(v.to_bytes(4, 'little'), 'big')
                            elif k == 2: v = ((v & 0x00ff00ff) << 8) | ((v >> 8) & 0x00ff00ff)
                            else: v = ((v & 0xffff) << 16) | (v >> 16)
                            self.setr(r3, v); self.zs(v)
                        else:
                            raise Halt('ext %04x %04x at %x' % (w, w2, pc))
        self.pc = npc & MASK

    @staticmethod
    def _list(lst):
        # prepare/dispose register list bits -> registers (r20..r31 order per V850E spec)
        order = {0: 31, 1: 29, 2: 28, 3: 23, 4: 22, 5: 21, 6: 20, 7: 27, 8: 26, 9: 25, 10: 24, 11: 30}
        regs = [order[b] for b in range(12) if lst >> b & 1]
        return sorted(regs)

    def run(self, until, limit=10_000_000):
        while self.pc not in until:
            self.step()
            if self.steps > limit:
                raise Halt('step limit at %x' % self.pc)
