"""Emulator tests for the BPM rule (bpm.py): BPMWRAP, SETWRAP, REPGET.

The real UI-side code runs (getter, natural BPM 0x15BF84, our wrappers); the setter body
(message post) is stubbed: each call is logged and, in SYNC mode, applied to the record at once
(ASYNC mode: never applied, like a message still in the queue).

usage: test_bpm.py built.prg [build_module [official_v102.prg]]
       (official file: 3rd argument, or $SP505_V102; needed to rebuild and get the code labels)
"""
import sys, os, struct, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from v850emu import CPU
from test_engine import make_mem, EP

GP = 0x437000
SP0 = 0x4E0000
REC = GP + 15312
DESC = 0x110364
END = 0xDEAD00
S = 5


def desc(m, pid):
    off = m.r(DESC + pid * 20 + 12, 2); typ = m.r(DESC + pid * 20 + 14, 1)
    return off, typ


def rset(m, s, pid, v):
    off, typ = desc(m, pid)
    a = REC + 48 * s + off
    n = {1: 1, 2: 2, 4: 4}[typ]
    for i in range(n):
        m.w(a + i, 1, (v >> (8 * (n - 1 - i))) & 0xFF)


def rget(m, s, pid, signed=False):
    off, typ = desc(m, pid)
    a = REC + 48 * s + off
    n = {1: 1, 2: 2, 4: 4}[typ]
    v = 0
    for i in range(n):
        v = v << 8 | m.r(a + i, 1)
    if signed and v >> (8 * n - 1):
        v -= 1 << (8 * n)
    return v


class Run:
    def __init__(self, prg, mod):
        self.m = make_mem(prg)
        self.L = mod.main.labels if hasattr(mod.main, 'labels') else None
        self.mod = mod
        self.sync = True

    def call(self, pc, *args, limit=2_000_000):
        m = self.m
        c = CPU(m)
        c.r[30] = EP; c.r[4] = GP; c.r[3] = SP0; c.r[31] = END
        for i, v in enumerate(args):
            c.r[6 + i] = v & 0xFFFFFFFF
        c.pc = pc
        sets, redraws = [], 0
        body = self.mod.SETTER_BODY
        while True:
            c.run({END, body, self.mod.UI_REDRAW}, limit)
            if c.pc == END:
                break
            if c.pc == body:
                s, pid, v = c.r[6], c.r[7], c.r[8]
                v = v - (1 << 32) if v >> 31 else v
                sets.append((s, pid, v))
                if self.sync:
                    rset(m, s, pid, v)
                c.pc = 0x1C34F2                     # its 'dispose 16, {r20,r21,lp}, [lp]'
            else:
                redraws += 1
                c.pc = c.r[31]
        saved = [c.r[i] for i in range(20, 30)]
        return c.r[10], sets, redraws, c


def natural_py(n, semis, cents, tabs):
    st, ft = tabs
    if (semis, cents) == (0, 0) or not (-24 <= semis <= 12 and -50 <= cents <= 50):
        return n
    r = (st[semis + 24] * ft[cents + 50]) >> 16
    t = (n * r + 0x8000) >> 16
    return min(max(t, 400), 2000)


def main():
    prg = sys.argv[1]
    mod = importlib.import_module(sys.argv[2] if len(sys.argv) > 2 else 'extrafirmware')
    # labels: rebuild in memory (main() records them)
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    official = os.path.join(here, '..', '..', 'official', 'sp505.prg')
    base = (sys.argv[3] if len(sys.argv) > 3 else os.environ.get('SP505_V102') or
            (official if os.path.isfile(official) else None))
    if not base:
        sys.exit('need the official v1.02 sp505.prg (3rd argument or $SP505_V102)')
    tmp = tempfile.mktemp(suffix='.prg')
    mod.main(base, tmp)
    assert open(tmp, 'rb').read() == open(prg, 'rb').read(), 'prg differs from a fresh build'
    os.unlink(tmp)
    L = mod.main.labels
    R = Run(prg, mod)
    m = R.m
    st = [m.r(mod.STEPTAB + 4 * i, 4) for i in range(37)]
    ft = [m.r(mod.FINETAB + 4 * i, 4) for i in range(101)]
    tabs = (st, ft)
    fails = []

    def check(name, cond, info=''):
        print('%-58s %s %s' % (name, 'ok' if cond else 'FAIL', info))
        if not cond:
            fails.append(name)

    def setup(s=S, start=0, end=4410 * 2 * 4 * 2, measure=256, beat=3, rate=4410, fmt=6):
        for i in range(48):
            m.w(REC + 48 * s + i, 1, 0)
        rset(m, s, 39, start); rset(m, s, 40, end); rset(m, s, 43, measure)
        rset(m, s, 57, beat); rset(m, s, 46, rate); rset(m, s, 47, fmt)
        nat, _, _, _ = R.call(mod.NATURAL, s)
        rset(m, s, 44, nat); rset(m, s, 45, nat)
        return nat

    for sync in (True, False):
        R.sync = sync
        tag = 'sync ' if sync else 'async'
        N = setup()
        check('%s natural BPM of the test sample plausible' % tag, 400 <= N <= 2009, N)
        # A. Varispeed edit 0 -> -12
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 58, -12)
        exp = natural_py(N, -12, 0, tabs)
        check('%s BPMWRAP 58=-12: setter calls' % tag, sets == [(S, 58, -12), (S, 44, exp)], sets)
        check('%s BPMWRAP 58=-12: record 58 / 44' % tag,
              rget(m, S, 58, True) == -12 and rget(m, S, 44) == exp, (rget(m, S, 58, True), rget(m, S, 44)))
        check('%s BPMWRAP 58=-12: one redraw' % tag, rd == 1, rd)
        # fine +23
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 59, 23)
        exp2 = natural_py(N, -12, 23, tabs)
        check('%s BPMWRAP 59=+23: BPM' % tag, sets == [(S, 59, 23), (S, 44, exp2)] and rget(m, S, 44) == exp2,
              (sets, exp2))
        # -24 at a BPM that clamps
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 58, -24)
        exp3 = natural_py(N, -24, 23, tabs)
        check('%s BPMWRAP 58=-24: clamp' % tag, rget(m, S, 44) == exp3, (exp3, sets))
        # back to Normal: exact original
        R.call(L['BPMWRAP'], S, 59, 0)
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 58, 0)
        check('%s BPMWRAP back to Normal: exact original BPM' % tag, rget(m, S, 44) == N and sets[-1] == (S, 44, N),
              (rget(m, S, 44), N, sets))
        # same value: nothing
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 58, 0)
        check('%s BPMWRAP unchanged value: only the edit' % tag, sets == [(S, 58, 0)] and rd == 0, (sets, rd))
        # Play Type: Phrase -> Single on a non-zero setting
        rset(m, S, 56, 1)
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 58, 3)
        check('%s BPMWRAP 58=+3 with Phrase -> Single' % tag, (S, 56, 0) in sets and rd == 1, sets)
        rset(m, S, 56, 0)
        # LOCKPHRASE
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 56, 1)
        check('%s Play Type Phrase refused while varispeed' % tag, sets == [], sets)
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 52, 1)
        check('%s other params pass straight through' % tag, sets == [(S, 52, 1)], sets)
        R.call(L['BPMWRAP'], S, 58, 0)
        _, sets, rd, c = R.call(L['BPMWRAP'], S, 56, 1)
        check('%s Play Type Phrase allowed on Normal' % tag, sets == [(S, 56, 1)], sets)
        rset(m, S, 56, 0)

        # B. SETWRAP: 44 := natural on a varispeed sample -> scaled
        N = setup()
        R.call(L['BPMWRAP'], S, 58, -7)
        expv = natural_py(N, -7, 0, tabs)
        _, sets, rd, c = R.call(mod.SETTER, S, 44, N)
        check('%s SETWRAP 44:=natural on -7 -> varispeed BPM' % tag, sets == [(S, 44, expv)], (sets, expv))
        _, sets, rd, c = R.call(mod.SETTER, S, 44, 1234)
        check('%s SETWRAP 44:=other value passes' % tag, sets == [(S, 44, 1234)], sets)
        rset(m, S, 44, expv)
        # Measure x2 like the menu's Measure edit: 43 then 1A296C(s, natural) -> 44
        if sync:
            rset(m, S, 43, 512)
            N2, _, _, _ = R.call(mod.NATURAL, S)
            _, sets, rd, c = R.call(0x1A296C, S, N2)
            e2 = natural_py(N2, -7, 0, tabs)
            check('%s Measure x2 (0x1A296C) keeps varispeed BPM' % tag, (S, 44, e2) in sets and rget(m, S, 44) == e2,
                  (sets, e2))
            rset(m, S, 43, 256); rset(m, S, 44, expv)
        # C. SETWRAP 58 by stock code: Fine Tune reset too
        rset(m, S, 59, 20 & 0xFF)
        _, sets, rd, c = R.call(mod.SETTER, S, 58, 0)
        check('%s SETWRAP 58:=0 (init) resets 59' % tag, sets == [(S, 58, 0), (S, 59, 0)] and
              rget(m, S, 58) == 0 and rget(m, S, 59) == 0, sets)
        # other params through SETWRAP
        _, sets, rd, c = R.call(mod.SETTER, S, 43, 256)
        check('%s SETWRAP other ids unchanged' % tag, sets == [(S, 43, 256)], sets)

        # D. REPGET: copy case (Normal record, varispeed BPM carried over)
        N = setup()
        rset(m, S, 44, natural_py(N, -12, 0, tabs))
        r10, sets, rd, c = R.call(L['REPGET'], 44, S)
        check('%s REPGET copy case -> original BPM' % tag, r10 == N and sets == [(S, 44, N)] and rget(m, S, 44) == N,
              (r10, N, sets))
        r10, sets, rd, c = R.call(L['REPGET'], 44, S)
        check('%s REPGET consistent -> no change' % tag, r10 == N and sets == [], (r10, sets))
        # varispeed record whose BPM got reset to natural (e.g. Beat edit when async)
        m.w(REC + 48 * S + 0x2D, 1, (-5) & 0xFF)
        e5 = natural_py(N, -5, 0, tabs)
        r10, sets, rd, c = R.call(L['REPGET'], 44, S)
        check('%s REPGET varispeed record with natural BPM -> scaled' % tag, r10 == e5 and rget(m, S, 44) == e5,
              (r10, e5, sets))
        # empty pad: natural 0 -> untouched
        for i in range(48):
            m.w(REC + 48 * 7 + i, 1, 0)
        rset(m, 7, 44, 1200)
        r10, sets, rd, c = R.call(L['REPGET'], 44, 7)
        check('%s REPGET empty pad untouched' % tag, r10 == 1200 and sets == [], (r10, sets))
        # callee-saved registers
        _, _, _, c = R.call(L['REPGET'], 44, S)
        check('%s REPGET returns with sp restored' % tag, c.r[3] == SP0, hex(c.r[3]))
        # Normal sample whose natural BPM is above the descriptor range: left alone
        N = setup(end=4410 * 2 * 4)
        r10, sets, rd, c = R.call(L['REPGET'], 44, S)
        r10b, sets2, rd, c = R.call(L['REPGET'], 44, S)
        check('%s REPGET natural > 200.9 (Normal): no repair loop' % tag, sets2 == [], (N, sets, sets2))

    # E. sweep TARGET against Python for all settings at a few naturals
    bad = 0
    for n in (400, 777, 1200, 2009, 3000):
        for semis in range(-24, 13):
            for cents in (-50, -23, -1, 0, 1, 37, 50):
                r10, _, _, _ = R.call(L['TARGET'], n, semis, cents)
                if r10 != natural_py(n, semis, cents, tabs):
                    bad += 1
    check('TARGET = Python model (5 x 37 x 7 settings)', bad == 0, bad)
    print('FAILED: %s' % fails if fails else 'all ok')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
