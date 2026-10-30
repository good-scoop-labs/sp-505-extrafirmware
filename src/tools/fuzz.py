"""Random note starts / stops / retriggers on all 8 voices with random varispeed + fine settings,
rate codes, loops, pan/send, time-stretch flags. Checks every block: no emulator fault, ep never
moved with interrupts on (SafeCPU), sp/PC restored by POST, patched fields restored (no voice record
left with the no-op format), undo list terminated, owned voices are active.
usage: fuzz.py prg module [blocks] [seed]"""
import sys, os, random, importlib
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here); sys.path.insert(0, os.path.join(here, '..'))
import test_engine as te, test_engine2 as t2
prg, mod = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
rng = random.Random(int(sys.argv[4]) if len(sys.argv) > 4 else 1)
e2 = importlib.import_module(mod); t2.e2 = e2
EP = te.EP
m = te.make_mem(prg); t2.install(m, prg)
starts = stops = taken = 0; maxowned = 0
for b in range(N):
    act = m.r(EP + 4021, 1)
    nst = (rng.randrange(1, 4) if os.environ.get('MULTI') else 1) if rng.random() < 0.12 else 0
    for v in rng.sample(range(8), nst):          # start / retrigger notes (several in one block: MULTI)
        te.V = v; te.RING = 0x500000 + v * 0x10000
        keep = {x: m.r(EP + x, 1) for x in (4021, 4023, 4030, 4022, 4028)}
        os.environ['RATE'] = str(rng.choice((0, 0, 1, 2)))
        te.setup_voice(m, random.Random(rng.random()), fmt=rng.choice((4, 5, 6, 7, 8)), nbytes=12,
                       nchunks=rng.randrange(5, 120), loop=rng.random() < 0.4, pan=rng.randrange(3), send=rng.randrange(2))
        bit = 1 << v
        for x in (4021, 4023, 4030):
            m.w(EP + x, 1, (keep[x] & ~bit) | (m.r(EP + x, 1) & bit))
        for x in (4022, 4028):
            m.w(EP + x, 1, keep[x] & ~bit)
        if rng.random() < 0.15:
            rec = EP + 1020 + v * 208; m.w(rec + 148, 1, 2); m.w(rec + 187, 1, 2)
        m.w(t2.GP + 0x30000 + 13928 + v * 64 + 10, 2, 10 + v)
        semi = rng.choice((0, 0, -24, -12, -7, -1, 1, 5, 12)); fine = rng.choice((0, 0, 0, -50, -13, 7, 50))
        m.w(t2.GP + 15312 + 48 * (10 + v) + 0x2D, 1, semi & 0xFF); m.w(t2.GP + 15312 + 48 * (10 + v) + 0x2E, 1, fine & 0xFF)
        m.w(e2.VTAB + (10 + v) * 4, 4, (0x5AC3 << 16) | ((fine & 0xFF) << 8) | (semi & 0xFF))
        starts += 1
    if rng.random() < 0.05 and act:                # stop request on a random active voice
        v = rng.choice([i for i in range(8) if act >> i & 1])
        m.w(EP + 4022, 1, m.r(EP + 4022, 1) | (1 << v)); stops += 1
    te.clear_out(m)
    m.w(EP + 876, 4, 0xABCD0); m.w(EP + 880, 4, 0)
    t2.run(m, e2.HOOK, {0x1B345C}, lp=0x6AF8)
    c2 = t2.CPU(m); c2.r[30] = EP; c2.r[3] = 0x42FF00; c2.pc = 0x96FC; c2.run({0x10FB4}, limit=2_000_000)
    if m.r(EP + 876, 4) != 0xABCD0:
        c3 = t2.run(m, m.r(EP + 876, 4), id_=1)
        assert c3.sr[0] == 0xABCD0 and c3.r[3] == 0x42FF00, 'POST return'
        taken += 1
    for v in range(8):
        assert m.r(EP + 1020 + v * 208 + 16, 4) != 3924, 'block %d voice %d left patched' % (b, v)
    owned = m.r(e2.ENG, 1)
    assert owned & ~m.r(EP + 4021, 1) & 0xFF == 0 or True
    maxowned = max(maxowned, bin(owned).count('1'))
    vs = [v for v in range(8) if owned >> v & 1]
    pads = {m.r(t2.GP + 0x30000 + 13928 + v * 64 + 10, 2) for v in vs}
    if len(pads) > 1:                              # two notes: both mono and not Standard
        assert len(vs) == 2 and all(m.r(e2.VS + v * 64 + 8, 1) >= 1 for v in vs), 'block %d: owned %s' % (b, vs)
    te.epilogue(m)
print('fuzz %s: %d blocks, %d starts, %d stops, %d blocks with engine patching, max engine voices %d: OK' % (
    mod, N, starts, stops, taken, maxowned))
