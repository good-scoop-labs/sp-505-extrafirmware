"""Check engine output at 0.5x against ideal linear interpolation of the ROM's own decoded stream."""
import sys, os, random
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here); sys.path.insert(0, os.path.join(here, '..'))
from v850emu import CPU, Halt
import test_engine as te, test_engine2 as t2
e2 = t2.e2
VARI = int(os.environ.get('VARI', '2'))
SPEED = float(os.environ.get('SPEED', '0.5'))

prg = sys.argv[1]
# reference stream: ROM at 1:1, volume 128 -> output word = decoded sample
mr = te.make_mem(prg); te.V = 2; te.RING = 0x500000
te.setup_voice(mr, random.Random(2), nchunks=200, vol=128, pan=1)
s = []
for b in range(120):
    te.clear_out(mr); te.rom_block(mr); s += te.read_out(mr)[0::4]; te.epilogue(mr)
# engine 0.5x
me = te.make_mem(prg); t2.install(me, prg)
te.setup_voice(me, random.Random(2), nchunks=200, vol=128, pan=1)
me.w(t2.GP + 0x30000 + 13928 + 2 * 64 + 10, 2, 10); me.w(t2.GP + 15312 + 480 + 0x2D, 1, VARI & 0xFF); me.w(t2.GP + 15312 + 480 + 0x2E, 1, int(os.environ.get('FINE', '0')) & 0xFF)
me.w(e2.VTAB + 40, 4, (0x5AC3 << 16) | (VARI & 0xFF) | ((int(os.environ.get('FINE', '0')) & 0xFF) << 8))
out = []
for b in range(200):
    te.clear_out(me)
    c = t2.run(me, e2.HOOK, {0x1B345C}, lp=0x6AF8)
    c = CPU(me); c.r[30] = te.EP; c.r[3] = 0x42FF00; c.pc = 0x96FC; c.run({0x10FB4})
    t2.run(me, me.r(te.EP + 876, 4))
    out += te.read_out(me)[0::4]; te.epilogue(me)
# steady region: ROM blocks 4.., i.e. stream samples >= 64; engine frames k with k/2 >= 64
if os.environ.get('EXACT'):      # speed = the engine's own step (semitone x cents tables)
    st = me.r(e2.STEPTAB + 4 * (VARI - e2.SEMIS[0]), 4)
    fn = int(os.environ.get('FINE', '0'))
    ft = me.r(e2.FINETAB + 4 * (fn + 50), 4) if hasattr(e2, 'FINETAB') else 65536
    SPEED = (st * ft >> 16) / 65536
worst = 0
for k in range(int(70 / SPEED) + 70, 3000):
    p = k * SPEED
    n = int(p); f = p - n
    if n + 1 >= len(s) or n < 70: continue
    want = s[n] + (s[n + 1] - s[n]) * f
    worst = max(worst, abs(out[k] - want))
print('speed', SPEED, 'max |engine - ideal| over steady region: %.1f (of 32768)' % worst)
