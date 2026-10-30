"""Find movhi/movea(addi/ld/st) address pairs and calls in a V850 image.
Usage: xrefs.py img.bin base  -> writes xrefs.txt (target, from) pairs and calls.txt"""
import sys, struct, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v850 import dis, sx

img = open(sys.argv[1], 'rb').read(); B = int(sys.argv[2], 0)
outdir = os.path.dirname(os.path.abspath(sys.argv[1]))
consts = []; calls = []
o = 0
hi = {}  # reg -> (value, offset)
N = len(img)
while o < N - 1:
    n, t, tgt = dis(img, o, B + o)
    w = struct.unpack_from('<H', img, o)[0]
    op = (w >> 5) & 0x3f; r1 = w & 0x1f; r2 = w >> 11
    if op == 0x32 and r2 != 0 and o + 4 <= N:  # movhi imm, r1, r2
        w2 = struct.unpack_from('<H', img, o + 2)[0]
        base = 0 if r1 == 0 else None
        if base is not None:
            hi[r2] = ((w2 << 16), o)
    elif op in (0x30, 0x31, 0x38, 0x39, 0x3a, 0x3b) and o + 4 <= N and r1 in hi:
        w2 = struct.unpack_from('<H', img, o + 2)[0]
        v, ho = hi[r1]
        if o - ho < 24:
            d = sx(w2 & ~1, 16) if op in (0x39, 0x3b) else sx(w2, 16)
            consts.append(((v + d) & 0xffffffff, o))
    if tgt is not None and ('jarl' in t):
        calls.append((tgt, o))
    if n == 6 and t.startswith('mov 0x'):
        consts.append((int(t.split()[1].rstrip(','), 16), o))
    o += n
with open(os.path.join(outdir, 'xrefs.txt'), 'w') as f:
    for v, o in consts:
        f.write('%08x %08x\n' % (v, B + o))
with open(os.path.join(outdir, 'calls.txt'), 'w') as f:
    for v, o in calls:
        f.write('%08x %08x\n' % (v, B + o))
print(len(consts), len(calls))
