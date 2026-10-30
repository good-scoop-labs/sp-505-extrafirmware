"""v11 engine test: full per-block flow in the emulator (hook stub -> RAM hook -> ROM voice
loop -> POST stub -> RAM POST) against the ROM alone.

usage: test_engine2.py built.prg [--vari 1|2] [--loop] [--pan N] [--send] [--blocks N]
                                 [--stop-at B] [--voices N] [--overrun-at B]
"""
import sys, os, random, argparse
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here); sys.path.insert(0, os.path.join(here, '..'))
from v850emu import Mem, CPU, Halt
import test_engine as te
import importlib
e2 = importlib.import_module(os.environ.get('ENGMOD', 'extrafirmware'))

EP = te.EP
GP = 0x437000


def install(m, prg):
    """engine RAM as after the idle-task init (READY set)"""
    m.w(e2.ENG + 4, 4, e2.READY)


class SafeCPU(CPU):
    """interrupts can arrive whenever ID == 0: ep must then be the system ep (the ROM's ISRs
    use it), and nothing may be stored below sp."""
    def step(self):
        if not self.id and self.r[30] != EP:
            raise Halt('ep moved with interrupts enabled at %x' % self.pc)
        super().step()


def run(m, pc, stop=None, lp=0, r4=GP, id_=0):
    c = SafeCPU(m); c.r[30] = EP; c.r[3] = 0x42FF00; c.r[4] = r4; c.r[31] = lp; c.pc = pc; c.id = id_
    try:
        c.run(stop or set(), limit=3_000_000)
    except Halt as e:
        if str(e) != 'reti':
            raise
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('prg')
    ap.add_argument('--vari', type=int, default=1)
    ap.add_argument('--loop', action='store_true')
    ap.add_argument('--pan', type=int, default=0)
    ap.add_argument('--send', action='store_true')
    ap.add_argument('--blocks', type=int, default=90)
    ap.add_argument('--stop-at', type=int, default=0)
    ap.add_argument('--voices', type=int, default=1)
    ap.add_argument('--overrun-at', type=int, default=-1)
    ap.add_argument('--overrun-len', type=int, default=0)
    ap.add_argument('--fmt', type=int, default=6)
    ap.add_argument('--mixed', action='store_true')
    ap.add_argument('--nbytes', type=int, default=12)
    ap.add_argument('--unity', action='store_true', help='v19+: make setting -1 play at exactly 1.0x (identity test)')
    a = ap.parse_args()
    exact = a.vari in (0, 25) or a.unity
    mr, me = te.make_mem(a.prg), te.make_mem(a.prg)
    install(me, a.prg)
    voices = [2, 5, 7, 0, 3, 1, 4, 6][:a.voices]
    mask = 0
    for k, v in enumerate(voices):
        for m in (mr, me):
            te.V = v; te.RING = 0x500000 + k * 0x10000
            keep = {x: m.r(EP + x, 1) for x in (4021, 4023, 4030)}
            te.setup_voice(m, random.Random(v), fmt=a.fmt, nbytes=a.nbytes, nchunks=50 + 7 * k, loop=a.loop, pan=(k % 3) if a.mixed else a.pan,
                           send=(k & 1) if a.mixed else (1 if a.send else 0))
            for x in (4021, 4023, 4030):
                m.w(EP + x, 1, keep[x] | m.r(EP + x, 1))
        mask |= 1 << v
        # pad k for voice v, VTAB[pad] = engine setting
        me.w(GP + 0x30000 + 13928 + v * 64 + 10, 2, 10 if os.environ.get('SAMEPAD') else 10 + k)
        pad = 10 if os.environ.get('SAMEPAD') else 10 + k
        me.w(e2.VTAB + pad * 4, 4, (0x5AC3 << 16) | (a.vari & 0xFF))
        me.w(GP + 15312 + 48 * pad + 0x2D, 1, a.vari & 0xFF); me.w(GP + 15312 + 48 * pad + 0x2E, 1, 0)   # v29+: record
    if a.unity:
        me.w(e2.STEPTAB + 4 * (a.vari - e2.SEMIS[0]), 4, 0x10000)
    diffs = 0; steps = []; rsteps = []
    for b in range(a.blocks):
        if a.stop_at and b == a.stop_at:
            for m in (mr, me):
                m.w(EP + 4022, 1, m.r(EP + 4022, 1) | mask)
        te.clear_out(mr); te.clear_out(me)
        rsteps.append(te.rom_block(mr))
        # engine side
        me.w(EP + 876, 4, 0xABCD0); me.w(EP + 880, 4, 0)
        c1 = run(me, e2.HOOK, {te.EP and 0x1B345C}, lp=0x6AF8)
        assert c1.r[31] == 0x6AF8, 'lp lost'
        c2 = CPU(me); c2.r[30] = EP; c2.r[3] = 0x42FF00; c2.pc = 0x96FC; c2.run({0x10FB4})
        if b == a.overrun_at or (a.overrun_at >= 0 and a.overrun_len and a.overrun_at <= b < a.overrun_at + a.overrun_len):
            me.w(EP + 2976, 4, te.OUT + 0x100)          # pretend the DMA already swapped
        if me.r(EP + 876, 4) != 0xABCD0:            # (redirect may be undone when idle)
            c3 = run(me, me.r(EP + 876, 4), id_=1)
            assert c3.sr[0] == 0xABCD0, hex(c3.sr[0])
            assert c3.r[3] == 0x42FF00
        else:
            c3 = c1; c3.steps = 0
        if me.r(EP + 2976, 4) != te.OUT:
            me.w(EP + 2976, 4, te.OUT)
        steps.append(c1.steps + c3.steps)
        if os.environ.get('RECCMP') and exact:
            for v in voices:
                ra = [mr.r(EP + 1020 + v * 208 + i, 1) for i in range(208)]
                ea = [me.r(EP + 1020 + v * 208 + i, 1) for i in range(208)]
                if ra != ea:
                    print('block %d voice %d record differs at' % (b, v), [i for i in range(208) if ra[i] != ea[i]])
        orr, oe = te.read_out(mr), te.read_out(me)
        mkr, mke = te.masks(mr), te.masks(me)
        if os.environ.get('IGN4025'):
            mkr.pop(4025); mke.pop(4025)
        if os.environ.get('OUTONLY'):
            mkr = mke = {}
        te.epilogue(mr); te.epilogue(me)
        if exact and a.overrun_at < 0 and (orr != oe or mkr != mke):
            diffs += 1
            if diffs <= 4:
                print('block %d differs' % b)
                if orr != oe: print('  rom', orr[:16]); print('  eng', oe[:16])
                if mkr != mke: print('  masks rom', mkr, '\n  masks eng', mke)
        if a.vari in (2, 4) and b in (6, 7):
            print('block %d eng L:' % b, oe[0::4][:16])
    print('blocks %d, differing %d, final 4021 rom %d eng %d, overruns %d, owned %d' % (
        a.blocks, diffs, mr.r(EP + 4021, 1), me.r(EP + 4021, 1), me.r(e2.ENG + 12, 4), me.r(e2.ENG, 1)))
    act = [s for s in steps if s > 60]
    print('engine steps/block (hook+post, blocks with engine work): avg %.0f max %d ; ROM loop avg %.0f' % (
        sum(act) / max(1, len(act)), max(steps), sum(rsteps) / len(rsteps)))


if __name__ == '__main__':
    main()
