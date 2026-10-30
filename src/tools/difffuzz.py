"""Differential fuzz: the fuzz.py scenario (random starts / stops / retriggers, settings, rate
codes, loops, pan / send, stretch flags) run on two builds in lockstep; every block compares the
output, the voice masks and all voice records (record bytes +8..+11 ignored with IGNREC8=1).
usage: difffuzz.py modA prgA modB prgB [blocks] [seed]"""
import sys, os, random, importlib
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here); sys.path.insert(0, os.path.join(here, '..'))
import test_engine as te, test_engine2 as t2
ma, pa, mb, pb = sys.argv[1:5]
N = int(sys.argv[5]) if len(sys.argv) > 5 else 2000
seed = int(sys.argv[6]) if len(sys.argv) > 6 else 1
EP = te.EP
ign = set(range(8, 12)) if os.environ.get('IGNREC8') else set()


def setup(mod, prg):
    e2 = importlib.import_module(mod)
    m = te.make_mem(prg); t2.e2 = e2; t2.install(m, prg)
    return e2, m


A = setup(ma, pa); B = setup(mb, pb)
rng = random.Random(seed)
bad = 0
for b in range(N):
    acts = A[1].r(EP + 4021, 1)
    nst = rng.randrange(1, 4) if rng.random() < 0.12 else 0
    plan = []
    for v in rng.sample(range(8), nst):
        plan.append(dict(v=v, rate=rng.choice((0, 0, 1, 2)), seed=rng.random(), fmt=rng.choice((4, 5, 6, 7, 8)),
                         nchunks=rng.randrange(5, 120), loop=rng.random() < 0.4, pan=rng.randrange(3),
                         send=rng.randrange(2), stretch=rng.random() < 0.15,
                         semi=rng.choice((0, 0, -24, -12, -7, -1, 1, 5, 12)), fine=rng.choice((0, 0, 0, -50, -13, 7, 50))))
    stopv = None
    if rng.random() < 0.05 and acts:
        stopv = rng.choice([i for i in range(8) if acts >> i & 1])
    res = []
    for e2, m in (A, B):
        t2.e2 = e2
        for p in plan:
            v = p['v']; te.V = v; te.RING = 0x500000 + v * 0x10000
            keep = {x: m.r(EP + x, 1) for x in (4021, 4023, 4030, 4022, 4028)}
            os.environ['RATE'] = str(p['rate'])
            te.setup_voice(m, random.Random(p['seed']), fmt=p['fmt'], nbytes=12, nchunks=p['nchunks'],
                           loop=p['loop'], pan=p['pan'], send=p['send'])
            bit = 1 << v
            for x in (4021, 4023, 4030):
                m.w(EP + x, 1, (keep[x] & ~bit) | (m.r(EP + x, 1) & bit))
            for x in (4022, 4028):
                m.w(EP + x, 1, keep[x] & ~bit)
            if p['stretch']:
                rec = EP + 1020 + v * 208; m.w(rec + 148, 1, 2); m.w(rec + 187, 1, 2)
            m.w(t2.GP + 0x30000 + 13928 + v * 64 + 10, 2, 10 + v)
            m.w(t2.GP + 15312 + 48 * (10 + v) + 0x2D, 1, p['semi'] & 0xFF)
            m.w(t2.GP + 15312 + 48 * (10 + v) + 0x2E, 1, p['fine'] & 0xFF)
            m.w(e2.VTAB + (10 + v) * 4, 4, (0x5AC3 << 16) | ((p['fine'] & 0xFF) << 8) | (p['semi'] & 0xFF))
        if stopv is not None:
            m.w(EP + 4022, 1, m.r(EP + 4022, 1) | (1 << stopv))
        te.clear_out(m)
        m.w(EP + 876, 4, 0xABCD0); m.w(EP + 880, 4, 0)
        t2.run(m, e2.HOOK, {0x1B345C}, lp=0x6AF8)
        c2 = t2.CPU(m); c2.r[30] = EP; c2.r[3] = 0x42FF00; c2.pc = 0x96FC; c2.run({0x10FB4}, limit=2_000_000)
        if m.r(EP + 876, 4) != 0xABCD0:
            c3 = t2.run(m, m.r(EP + 876, 4), id_=1)
            assert c3.sr[0] == 0xABCD0 and c3.r[3] == 0x42FF00, 'POST return'
        out = te.read_out(m); mk = te.masks(m)
        recs = [tuple(m.r(EP + 1020 + v * 208 + i, 1) for i in range(208) if i not in ign) for v in range(8)]
        res.append((out, mk, recs, m.r(e2.ENG, 1)))
        te.epilogue(m)
    if res[0] != res[1]:
        bad += 1
        if bad <= 3:
            what = [n for n, x, y in zip(('out', 'masks', 'records', 'owned'), res[0], res[1]) if x != y]
            print('block %d differs: %s' % (b, what))
print('difffuzz %s vs %s: %d blocks, seed %d, %d differing' % (ma, mb, N, seed, bad))
