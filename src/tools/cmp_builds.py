"""Run the engine flow for two builds (each with its own ENGMOD) and compare outputs, masks and
voice records block by block. usage: cmp_builds.py modA prgA modB prgB semis [--loop] [--rate R]"""
import sys, os, random, importlib
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here); sys.path.insert(0, os.path.join(here, '..'))
import test_engine as te, test_engine2 as t2
EP = te.EP

def run(mod, prg, semi, loop, voices, blocks, stop_at):
    e2 = importlib.import_module(mod); t2.e2 = e2
    m = te.make_mem(prg); t2.install(m, prg)
    if os.environ.get('UNITY') and semi:
        m.w(e2.STEPTAB + 4 * (semi - e2.SEMIS[0]), 4, 0x10000)
    vs = [2, 5, 7, 0][:voices]
    stag = int(os.environ.get('STAGGER', '0')); normk = int(os.environ.get('NORMALK', '-1'))
    later = {}
    for k, v in enumerate(vs):
        te.V = v; te.RING = 0x500000 + k * 0x10000
        keep = {x: m.r(EP + x, 1) for x in (4021, 4023, 4030)}
        te.setup_voice(m, random.Random(v), nchunks=60 + 7 * k, loop=loop, pan=k % 3, send=k & 1)
        if os.environ.get('STRETCH'):
            rec = EP + 1020 + v * 208; m.w(rec + 148, 1, 2); m.w(rec + 187, 1, 2)
        bits = {x: m.r(EP + x, 1) & ~keep[x] for x in (4021, 4023, 4030)}
        if stag and k:
            later[k * stag] = bits
            for x in (4021, 4023, 4030): m.w(EP + x, 1, keep[x])
        else:
            for x in (4021, 4023, 4030): m.w(EP + x, 1, keep[x] | m.r(EP + x, 1))
        pad = 10 if (os.environ.get('PAIR') and k < 2) else 10 + k
        m.w(t2.GP + 0x30000 + 13928 + v * 64 + 10, 2, pad)
        sv = (0 if k == normk else semi) & 0xFF; fv = (0 if k == normk else int(os.environ.get('FINE', '0'))) & 0xFF
        m.w(t2.GP + 15312 + 48 * pad + 0x2D, 1, sv); m.w(t2.GP + 15312 + 48 * pad + 0x2E, 1, fv)   # v29+: record
        m.w(e2.VTAB + pad * 4, 4, (0x5AC3 << 16) | ((0 if k == normk else semi) & 0xFF) | ((0 if k == normk else int(os.environ.get('FINE', '0'))) & 0xFF) << 8)
    res = []
    for b in range(blocks):
        if stop_at and b == stop_at:
            m.w(EP + 4022, 1, m.r(EP + 4022, 1) | sum(1 << v for v in vs))
        if b in later:
            for x, bt in later[b].items(): m.w(EP + x, 1, m.r(EP + x, 1) | bt)
        te.clear_out(m)
        m.w(EP + 876, 4, 0xABCD0); m.w(EP + 880, 4, 0)
        t2.run(m, e2.HOOK, {0x1B345C}, lp=0x6AF8)
        c2 = t2.CPU(m); c2.r[30] = EP; c2.r[3] = 0x42FF00; c2.pc = 0x96FC; c2.run({0x10FB4})
        if m.r(EP + 876, 4) != 0xABCD0:
            c3 = t2.run(m, m.r(EP + 876, 4), id_=1)
            assert c3.sr[0] == 0xABCD0 and c3.r[3] == 0x42FF00
        out = te.read_out(m); mk = te.masks(m)
        if os.environ.get('OUTONLY'): mk = None; recs = None
        else:
            ign = set(range(8, 12)) if os.environ.get('IGNREC8') else set()   # v31: +8 = copy of patched +36
            recs = [tuple(m.r(EP + 1020 + v * 208 + i, 1) for i in range(208) if i not in ign) for v in vs]
        if os.environ.get('TRACE'): print(b, 'owned %02x active %02x' % (m.r(0x428000, 1), m.r(EP + 4021, 1)))
        te.epilogue(m)
        res.append((out, mk, recs))
    return res

if __name__ == '__main__':
    ma, pa, mb, pb, semi = sys.argv[1:6]
    loop = '--loop' in sys.argv
    voices = int(os.environ.get('VOICES', '1')); blocks = int(os.environ.get('BLOCKS', '300'))
    stop_at = int(os.environ.get('STOPAT', '0'))
    A = run(ma, pa, int(semi), loop, voices, blocks, stop_at)
    B = run(mb, pb, int(semi), loop, voices, blocks, stop_at)
    bad = [b for b in range(blocks) if A[b] != B[b]]
    print('semi %s loop %s voices %d rate %s: %d/%d blocks differ %s' % (semi, loop, voices, os.environ.get('RATE', '0'), len(bad), blocks, bad[:5]))
