"""Per-block cost of the engine (hook stub + engine + POST), split by memory, with a hot-spot list.

usage: [ENGMOD=extrafirmware] prof30.py prg [--semi S] [--fine C] [--rate R] [--voices N]
                                             [--stereo] [--hot N] [--blocks N]
  rate: voice +139 rate code (0 Standard, 1 Long, 2 lowest).  voices: engine voices (mono, own pads)
  stereo: one stereo note = two voices on the same pad.
Cost metric: flash halfwords fetched per block (code runs from flash, which is slow).
"""
import sys, os, random, collections, argparse
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here); sys.path.insert(0, os.path.join(here, '..'))
from v850emu import CPU, Halt
import test_engine as te, test_engine2 as t2


def ilen(m, pc):
    """length in bytes of the V850E instruction at pc"""
    w = m.r(pc, 2); op = (w >> 5) & 0x3f
    if op < 0x18: return 2
    top4 = (w >> 7) & 0xf
    if op < 0x30 and top4 in (6, 7, 8, 9, 0xa, 0xb): return 2
    if op == 0x31 and (w >> 11) == 0: return 6
    return 4
import v850
e2 = t2.e2
EP = te.EP


class PC(t2.SafeCPU):
    def __init__(s, m, stats): super().__init__(m); s.stats = stats
    def step(s):
        pc = s.pc; n = ilen(s.m, pc)
        k = 'rom' if pc < 0x100000 else 'flash' if pc < 0x400000 else 'dram'
        s.stats[k] += 1; s.stats[k + '_hw'] += n // 2
        if k == 'flash':
            s.stats[('pc', pc)] += 1; s.stats[('hw', pc)] += n // 2
        super().step()


def runc(m, pc, stats, stop, lp=0, id_=0):
    c = PC(m, stats); c.r[30] = EP; c.r[3] = 0x42FF00; c.r[4] = t2.GP; c.r[31] = lp; c.pc = pc; c.id = id_
    try: c.run(stop, limit=3_000_000)
    except Halt as e:
        if str(e) != 'reti': raise
    return c


def prof(prg, semi=-7, fine=0, rate=0, voices=1, stereo=False, blocks=160, fmt=6, nbytes=12, seed=2):
    m = te.make_mem(prg); t2.install(m, prg)
    vlist = [2, 5][:2 if stereo else voices] if (stereo or voices > 1) else [2]
    for k, v in enumerate(vlist):
        te.V = v; te.RING = 0x500000 + k * 0x10000
        keep = {x: m.r(EP + x, 1) for x in (4021, 4023, 4030)}
        os.environ['RATE'] = str(rate)
        te.setup_voice(m, random.Random(seed + k), fmt=fmt, nbytes=nbytes, nchunks=400, loop=True)
        for x in (4021, 4023, 4030):
            m.w(EP + x, 1, keep[x] | m.r(EP + x, 1))
        pad = 10 if stereo else 10 + k
        m.w(t2.GP + 0x30000 + 13928 + v * 64 + 10, 2, pad)
        m.w(e2.VTAB + pad * 4, 4, (0x5AC3 << 16) | ((fine & 0xFF) << 8) | (semi & 0xFF))
        m.w(t2.GP + 15312 + 48 * pad + 0x2D, 1, semi & 0xFF); m.w(t2.GP + 15312 + 48 * pad + 0x2E, 1, fine & 0xFF)
    tot = collections.Counter(); rom = collections.Counter()
    for b in range(blocks):
        te.clear_out(m)
        st = collections.Counter()
        m.w(EP + 876, 4, 0xABCD0); m.w(EP + 880, 4, 0)
        runc(m, e2.HOOK, st, {0x1B345C}, lp=0x6AF8)
        c2 = PC(m, rom); c2.r[30] = EP; c2.r[3] = 0x42FF00; c2.pc = 0x96FC; c2.run({0x10FB4})
        if m.r(EP + 876, 4) != 0xABCD0:
            runc(m, m.r(EP + 876, 4), st, set(), id_=1)
        te.epilogue(m)
        if b >= 20: tot.update(st)
    n = blocks - 20
    owned = m.r(e2.ENG, 1)
    return {k: v / n for k, v in tot.items()}, rom['rom'] / blocks, owned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('prg'); ap.add_argument('--semi', type=int, default=-7); ap.add_argument('--fine', type=int, default=0)
    ap.add_argument('--rate', type=int, default=0); ap.add_argument('--voices', type=int, default=1)
    ap.add_argument('--stereo', action='store_true'); ap.add_argument('--hot', type=int, default=0)
    ap.add_argument('--blocks', type=int, default=160)
    a = ap.parse_args()
    t, r, owned = prof(a.prg, a.semi, a.fine, a.rate, a.voices, a.stereo, a.blocks)
    print('semi %+d fine %+d rate %d voices %d%s: flash %5.0f ins %5.0f hw | dram %4.0f | rom %5.0f | owned %s' % (
        a.semi, a.fine, a.rate, a.voices, ' stereo' if a.stereo else '', t.get('flash', 0), t.get('flash_hw', 0),
        t.get('dram', 0), t.get('rom', 0), bin(owned)))
    if a.hot:
        img = open(a.prg, 'rb').read()
        pcs = sorted(((v, k[1]) for k, v in t.items() if isinstance(k, tuple) and k[0] == 'pc'), key=lambda x: x[1])
        # group consecutive PCs into runs with the same execution count (basic blocks)
        runs = []
        for v, pc in pcs:
            hw = t[('hw', pc)]
            if runs and abs(runs[-1][2] - v) < 1e-9 and pc - runs[-1][1] <= 6:
                runs[-1][1] = pc; runs[-1][3] += hw
            else:
                runs.append([pc, pc, v, hw])
        runs.sort(key=lambda x: -x[3])
        for s, e, per, totv in runs[:a.hot]:
            print('  %06x-%06x  x%6.2f/block  %6.1f hw/block' % (s, e, per, totv))


if __name__ == '__main__':
    main()
