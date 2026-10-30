"""Small V850E assembler for the EXTRAfirmware patches.

Each instruction function returns its encoding (little-endian halfwords). Asm collects
instructions, labels and label references and assembles them in two passes; every item has a fixed
size, so label addresses from the first pass are final.
"""
import struct

REG = {'r%d' % i: i for i in range(32)}
REG.update({'sp': 3, 'gp': 4, 'tp': 5, 'ep': 30, 'lp': 31})
COND = {'v': 0, 'l': 1, 'c': 1, 'z': 2, 'e': 2, 'nh': 3, 'n': 4, 'r': 5, 'lt': 6, 'le': 7,
        'nv': 8, 'nl': 9, 'nc': 9, 'nz': 10, 'ne': 10, 'h': 11, 'p': 12, 'sa': 13, 'ge': 14, 'gt': 15}
INV = {'z': 'nz', 'nz': 'z', 'e': 'ne', 'ne': 'e', 'l': 'nl', 'nl': 'l', 'c': 'nc', 'nc': 'c',
       'lt': 'ge', 'ge': 'lt', 'le': 'gt', 'gt': 'le', 'h': 'nh', 'nh': 'h', 'n': 'p', 'p': 'n'}
SREG = {'eipc': 0, 'eipsw': 1, 'fepc': 2, 'fepsw': 3, 'ecr': 4, 'psw': 5}


def h(*hw):
    return b''.join(struct.pack('<H', x & 0xFFFF) for x in hw)


def fmt1(op, r1, r2):                                   # reg, reg
    return h((REG[r2] << 11) | (op << 5) | REG[r1])


def fmt2(op, imm5, r2):                                 # imm5, reg
    return h((REG[r2] << 11) | (op << 5) | (imm5 & 0x1F))


def raw(bs): return bytes(bs)

# ---- register / immediate arithmetic and logic
def mov_rr(r1, r2): return fmt1(0x00, r1, r2)
def not_rr(r1, r2): return fmt1(0x01, r1, r2)
def mulh_rr(r1, r2): return fmt1(0x07, r1, r2)          # r2 = lo16(r2) * lo16(r1), signed
def or_rr(r1, r2): return fmt1(0x08, r1, r2)
def xor_rr(r1, r2): return fmt1(0x09, r1, r2)
def and_rr(r1, r2): return fmt1(0x0A, r1, r2)
def tst_rr(r1, r2): return fmt1(0x0B, r1, r2)
def sub_rr(r1, r2): return fmt1(0x0D, r1, r2)           # r2 = r2 - r1
def add_rr(r1, r2): return fmt1(0x0E, r1, r2)
def cmp_rr(r1, r2): return fmt1(0x0F, r1, r2)           # flags of r2 - r1
def mov_i(imm, r2): assert -16 <= imm <= 15; return fmt2(0x10, imm, r2)
def add_i(imm, r2): assert -16 <= imm <= 15; return fmt2(0x12, imm, r2)
def cmp_i(imm, r2): assert -16 <= imm <= 15; return fmt2(0x13, imm, r2)
def shr_i(imm, r2): assert 0 <= imm <= 31; return fmt2(0x14, imm, r2)
def sar_i(imm, r2): assert 0 <= imm <= 31; return fmt2(0x15, imm, r2)
def shl_i(imm, r2): assert 0 <= imm <= 31; return fmt2(0x16, imm, r2)
def addi(imm, r1, r2): return h((REG[r2] << 11) | (0x30 << 5) | REG[r1], imm & 0xFFFF)
def ori(imm, r1, r2): return h((REG[r2] << 11) | (0x34 << 5) | REG[r1], imm & 0xFFFF)
def xori(imm, r1, r2): return h((REG[r2] << 11) | (0x35 << 5) | REG[r1], imm & 0xFFFF)
def andi(imm, r1, r2): return h((REG[r2] << 11) | (0x36 << 5) | REG[r1], imm & 0xFFFF)


def movea(imm, r1, r2):
    assert -32768 <= imm <= 32767
    return h((REG[r2] << 11) | (0x31 << 5) | REG[r1], imm)


def movhi(imm, r1, r2): return h((REG[r2] << 11) | (0x32 << 5) | REG[r1], imm & 0xFFFF)
def mov32(imm, r1): return h((0x31 << 5) | REG[r1]) + struct.pack('<I', imm & 0xFFFFFFFF)
def mul_rr(r1, r2, r3): return h((REG[r2] << 11) | (0x3F << 5) | REG[r1], (REG[r3] << 11) | 0x220)
def mulu(r1, r2, r3): return h((REG[r2] << 11) | (0x3F << 5) | REG[r1], (REG[r3] << 11) | 0x222)  # r3:r2 = r2 * r1
def divu(r1, r2, r3): return h((REG[r2] << 11) | (0x3F << 5) | REG[r1], (REG[r3] << 11) | 0x2C2)  # r2 /= r1, r3 = rem
def shr_rr(r1, r2): return h((REG[r2] << 11) | (0x3F << 5) | REG[r1], 0x0080)
def sar_rr(r1, r2): return h((REG[r2] << 11) | (0x3F << 5) | REG[r1], 0x00A0)
def shl_rr(r1, r2): return h((REG[r2] << 11) | (0x3F << 5) | REG[r1], 0x00C0)

# ---- loads / stores
def ld_b(disp, r1, r2): return h((REG[r2] << 11) | (0x38 << 5) | REG[r1], disp & 0xFFFF)


def ld_h(disp, r1, r2):
    assert disp % 2 == 0
    return h((REG[r2] << 11) | (0x39 << 5) | REG[r1], disp & 0xFFFE)


def ld_w(disp, r1, r2):
    assert disp % 2 == 0
    return h((REG[r2] << 11) | (0x39 << 5) | REG[r1], (disp & 0xFFFE) | 1)


def ld_bu(disp, r1, r2):
    assert REG[r2] != 0
    return h((REG[r2] << 11) | ((0x3C | (disp & 1)) << 5) | REG[r1], (disp & 0xFFFE) | 1)


def ld_hu(disp, r1, r2):
    assert disp % 2 == 0 and REG[r2] != 0
    return h((REG[r2] << 11) | (0x3F << 5) | REG[r1], (disp & 0xFFFE) | 1)


def st_b(r2, disp, r1): return h((REG[r2] << 11) | (0x3A << 5) | REG[r1], disp & 0xFFFF)


def st_h(r2, disp, r1):
    assert disp % 2 == 0
    return h((REG[r2] << 11) | (0x3B << 5) | REG[r1], disp & 0xFFFE)


def st_w(r2, disp, r1):
    assert disp % 2 == 0
    return h((REG[r2] << 11) | (0x3B << 5) | REG[r1], (disp & 0xFFFE) | 1)


def _bitop(sub, bit, disp, r1): return h((sub << 14) | (bit << 11) | (0x3E << 5) | REG[r1], disp & 0xFFFF)
def set1(bit, disp, r1): return _bitop(0, bit, disp, r1)
def clr1(bit, disp, r1): return _bitop(2, bit, disp, r1)

# ---- control
def jarl(target, here, r2='lp'):
    d = target - here
    assert -(1 << 21) <= d < (1 << 21) and d % 2 == 0
    d &= 0x3FFFFF
    return h((REG[r2] << 11) | (0x1E << 6) | (d >> 16), d & 0xFFFE)


def jr(target, here): return jarl(target, here, 'r0')
def jmp_reg(r1): return h((0x03 << 5) | REG[r1])


def bcond(cond, target, here):
    d = target - here
    assert -256 <= d <= 254 and d % 2 == 0, d
    d &= 0x1FF
    return h(((d >> 4) & 0x1F) << 11 | (0xB << 7) | ((d >> 1) & 7) << 4 | COND[cond])


def prepare_lp(stack):                                  # prepare {lp}, stack
    assert stack % 4 == 0 and stack < 128
    return h(0x0780 | ((stack // 4) << 1), 0x0021)


def dispose_lp(stack):                                  # dispose stack, {lp}, [lp]
    assert stack % 4 == 0 and stack < 128
    return h(0x0640 | ((stack // 4) << 1), 0x003F)


def ldsr(r, sreg): return h((SREG[sreg] << 11) | (0x3F << 5) | REG[r], 0x0020)
def stsr(sreg, r): return h((REG[r] << 11) | (0x3F << 5) | SREG[sreg], 0x0040)
def di(): return h(0x07E0, 0x0160)
def ei(): return h(0x87E0, 0x0160)
def reti(): return h(0x07E0, 0x0140)


class Asm:
    """Collects code for one address. Label references: branch (short conditional), bfar (any
    distance: inverted short branch over a jr), jumpl / calll (jr / jarl to a label), mov32l (a
    label's address); call / jump take absolute targets."""
    def __init__(self, base):
        self.base = base; self.items = []; self.labels = {}; self._n = 0

    def label(self, name): self.items.append(('label', name))
    def emit(self, fn, *args): self.items.append(('ins', fn, args))
    def branch(self, cond, lbl): self.items.append(('br', cond, lbl))
    def call(self, target): self.items.append(('call', target))
    def jump(self, target): self.items.append(('jump', target))
    def jumpl(self, lbl): self.items.append(('jumpl', lbl))
    def calll(self, lbl): self.items.append(('calll', lbl))
    def mov32l(self, lbl, reg): self.items.append(('mov32l', lbl, reg))

    def bfar(self, cond, lbl):
        self._n += 1
        skip = '__bfar%d' % self._n
        self.branch(INV[cond], skip); self.jumpl(lbl); self.label(skip)

    def assemble(self):
        for _ in (1, 2):
            pc = self.base; out = bytearray()
            for it in self.items:
                k = it[0]
                if k == 'label':
                    self.labels[it[1]] = pc; continue
                if k == 'ins': b = it[1](*it[2])
                elif k == 'br': b = bcond(it[1], self.labels.get(it[2], pc), pc)
                elif k == 'call': b = jarl(it[1], pc)
                elif k == 'jump': b = jarl(it[1], pc, 'r0')
                elif k == 'jumpl': b = jarl(self.labels.get(it[1], pc), pc, 'r0')
                elif k == 'calll': b = jarl(self.labels.get(it[1], pc), pc)
                elif k == 'mov32l': b = mov32(self.labels.get(it[1], 0), it[2])
                out += b; pc += len(b)
        return bytes(out)
