"""Emulator tests for the Mark button (mark.py).

Key events go through the stock UI dispatcher 0x1A042C (screen index, event), so the key-class
table, the class 3 / class 6 entries and the screen slot +28 rules are all exercised. The real
getter, bank protect check, position conversions and the stock START / END commits (0x1A3BB0 /
0x1A3B14, with Measure / BPM recalculation) run; the setter body is stubbed (logged and applied to
the record; SETWRAP in front of it runs for real), as are the error message, the redraw request,
the stock class 3 / class 6 handlers and the sequencer request the play screens make (0x17248C).
The LCD drawing runs for real into the framebuffer (0x41625E); the tag is checked against a
render of the same screen by the stock firmware.

usage: test_mark.py built.prg [build_module [official_v102.prg]]
"""
import sys, os, importlib, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from v850emu import CPU
from test_engine import make_mem, EP
from test_bpm import GP, SP0, REC, END, rset, rget
import layout as L
import mark

EVT = 0x4D0000                  # key / screen event
MODE = GP + 0x10000 - 17800     # UI mode (key-class dispatch for modes > 4)
SYS9 = GP + 14824               # class 9 system params (184 pad, 185 bank)
PROTECT = GP + 14788 + 2        # param 8: bank protect bits
FB = 0x41625E
SEQ_REQUEST = 0x17248C          # play screens ask the sequencer task for data (blocks)
PATTERN, SONG = 3, 6
SCREEN_MAIN, SCREEN_WAVE, SCREEN_WAVEPARAM = 1, 8, 29
BANK, PAD = 5, 5                # (param 8 below its min 15 reads as 15: banks 0-3 protected)
S = BANK * 16 + PAD


class Run:
    def __init__(self, prg, mod):
        self.m = make_mem(prg); self.mod = mod

    def call(self, pc, *args, limit=3_000_000):
        m = self.m
        c = CPU(m)
        c.r[30] = EP; c.r[4] = GP; c.r[3] = SP0; c.r[31] = END
        for i in range(20, 30):
            c.r[i] = 0x1000 + i
        for i, v in enumerate(args):
            c.r[6 + i] = v & 0xFFFFFFFF
        c.pc = pc
        log = {'set': [], 'redraw': 0, 'error': [], 'stock': 0, 'pad': 0, 'seq': [], 'note': []}
        stops = {END, self.mod.SETTER_BODY, L.UI_REDRAW, L.POST_ERROR, L.LR_STOCK, L.PAD_STOCK,
                 SEQ_REQUEST, L.AUDIO_POST}
        while True:
            c.run(stops, limit)
            if c.pc == END:
                break
            if c.pc == self.mod.SETTER_BODY:
                s, pid, v = c.r[6], c.r[7], c.r[8]
                log['set'].append((s, pid, v)); log['seq'].append(('set', pid))
                rset(m, s, pid, v)
                c.pc = 0x1C34F2                     # its 'dispose 16, {r20,r21,lp}, [lp]'
                continue
            if c.pc == L.UI_REDRAW:
                log['redraw'] += 1
            elif c.pc == L.POST_ERROR:
                log['error'].append(c.r[6])
            elif c.pc == L.AUDIO_POST:                  # message to the audio task
                p = c.r[6]
                if m.r(p, 1) == 4:                      # note: (part, status, sample, velocity, extra)
                    note = (m.r(p + 2, 1), m.r(p + 3, 1), m.r(p + 4, 2), m.r(p + 6, 2), m.r(p + 8, 2))
                    log['note'].append(note); log['seq'].append(('note',) + note)
                    log['note_flags'] = m.r(p + 1, 1)
                else:
                    log['seq'].append(('msg', m.r(p, 1)))
                if c.psw() & 0x20:
                    log['note_di'] = True               # (interrupts must be on)
            elif c.pc == L.PAD_STOCK:
                log['pad'] += 1; log['seq'].append(('pad',))
            elif c.pc == LR_STOCK_STOP:
                log['stock'] += 1
            c.r[10] = 0
            c.pc = c.r[31]
        log['regs'] = all(c.r[i] == 0x1000 + i for i in range(20, 30)) and c.r[3] == SP0
        return c.r[10], log


LR_STOCK_STOP = L.LR_STOCK


def sync_ram(src, dst):
    """dst gets src's RAM (internal RAM, DRAM, peripherals): same machine state, other firmware"""
    for (base, buf), (base2, buf2) in zip(src.regions, dst.regions):
        assert base == base2
        if base >= EP:
            buf2[:] = buf
        elif base == 0x400000:
            buf2[:] = buf


def fb(m):
    return bytes(m.r(FB + i, 1) for i in range(1024))


def pixel(buf, x, y):
    return buf[(y >> 3) * 128 + x] >> (y & 7) & 1


def show(buf, y0=44, y1=57):
    return '\n'.join(''.join('#' if pixel(buf, x, y) else '.' for x in range(128)) for y in range(y0, y1))


def main():
    prg = sys.argv[1]
    mod = importlib.import_module(sys.argv[2] if len(sys.argv) > 2 else 'extrafirmware')
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
    labels = mod.main.labels
    R = Run(prg, mod); m = R.m
    STOCK = Run(base, mod)                          # the official firmware, for screen renders
    fails = []

    def check(name, cond, info=''):
        print('%-66s %s %s' % (name, 'ok' if cond else 'FAIL', info))
        if not cond:
            fails.append(name)

    def pos_of(s, value):                       # stock bytes -> position conversion
        return R.call(0x15C364, s, value)[0]

    def bytes_of(s, pos):                       # stock position -> bytes conversion
        return R.call(L.TO_BYTES, s, pos)[0]

    def sample(s, rate=4410, fmt=6, reverse=0, mm=None):
        mm = mm or m
        for i in range(48):
            mm.w(REC + 48 * s + i, 1, 0)
        rset(mm, s, 37, 0); rset(mm, s, 38, 4410 * 12 * 8); rset(mm, s, 42, 4410 * 12 * 8)
        rset(mm, s, 39, 0); rset(mm, s, 40, 4410 * 12 * 8); rset(mm, s, 43, 256); rset(mm, s, 57, 3)
        rset(mm, s, 46, rate); rset(mm, s, 47, fmt); rset(mm, s, L.PARAM_REVERSE, reverse)
        nat = R.call(mod.NATURAL, s)[0]
        rset(mm, s, 44, nat); rset(mm, s, 45, nat)
        return pos_of(s, rget(m, s, 39)), pos_of(s, rget(m, s, 40))

    def voices_off():
        for x in (4021, 4022, 4023, 4026, 4027, 4028, 4030):
            m.w(EP + x, 1, 0)

    def voice(v, s, pos, start, end, fading=False):
        m.w(GP + 0x30000 + L.SLOTS + 64 * v + 10, 2, s)
        rec = EP + L.VOICE_REC + 208 * v
        m.w(rec + 24, 4, pos); m.w(rec + 28, 4, start); m.w(rec + 32, 4, end)
        m.w(EP + 4021, 1, m.r(EP + 4021, 1) | 1 << v)
        if fading:
            m.w(EP + 4022, 1, m.r(EP + 4022, 1) | 1 << v)

    def key(code, state=1, screen=SCREEN_MAIN, run=R, hold=False):
        """a key event; an L/R press is followed by its release unless hold=True"""
        run.m.w(EVT, 4, 0); run.m.w(EVT + 4, 4, code); run.m.w(EVT + 8, 4, state)
        lg = run.call(0x1A042C, screen, EVT)[1]
        if code == L.KEY_LR and state == 1 and not hold:
            run.m.w(EVT, 4, 0); run.m.w(EVT + 4, 4, code); run.m.w(EVT + 8, 4, 0)
            run.call(0x1A042C, screen, EVT)
        return lg

    def show_screen(i, run=R, bank=BANK):
        """the screen's enter and draw slots, as the dispatcher would call them"""
        mm = run.m
        mm.w(SYS9 + 1, 1, bank)
        d = mm.r(0x120590 + 4 * i, 4)
        mm.w(GP + 0x10000 - 17804, 4, d)
        mm.w(EVT, 4, 4); mm.w(EVT + 8, 4, 3); mm.w(EVT + 12, 2, 0xFFFF)
        run.call(mm.r(d + L.SCREEN_ENTER, 4), EVT)
        mm.w(EVT + 8, 4, 4)
        lg = run.call(mm.r(d + L.SCREEN_DRAW, 4), EVT)[1]
        return fb(mm), lg

    def idle(mm, phase, steps=4000):
        # run the idle loop (MIDLE) for a while with the tick in the given flash phase
        mm.w(L.TICK, 4, phase << L.BLINK_SHIFT)
        c = CPU(mm); c.r[30] = EP; c.r[4] = GP; c.r[3] = SP0; c.pc = labels['MIDLE']
        for _ in range(steps):
            c.step()

    def phase():
        return m.r(L.MARK_RAM + 8, 4)

    def marked_ok(s=S):                         # START / END not the whole recorded sample
        return (pos_of(s, rget(m, s, 39)) != pos_of(s, rget(m, s, 37)) or
                pos_of(s, rget(m, s, 40)) != pos_of(s, rget(m, s, 42)))

    m.w(MODE, 4, 6)
    m.w(SYS9 + 0, 1, PAD); m.w(SYS9 + 1, 1, BANK)
    for i in range(4):
        m.w(PROTECT + i, 1, 0)
    m.w(L.MARK_RAM, 4, 0x12345678)                  # RAM not initialised (power-on garbage)

    # ======================================================================= marking
    st0, en0 = sample(S)
    whole = (rget(m, S, 37), rget(m, S, 42))
    check('test sample START / END positions', st0 == 0 and en0 > 4000, (st0, en0))
    voices_off(); voice(2, S, 1000, st0, en0)
    lg = key(21)
    check('press 1: START = play position (stock conversion)',
          (S, 39, bytes_of(S, 1000)) in lg['set'] and pos_of(S, rget(m, S, 39)) == 1000, lg['set'])
    check('press 1: Measure / BPM recalculated by the stock commit',
          [p for _, p, _ in lg['set']][:3] == [39, 43, 44], lg['set'])
    check('press 1: redraw, stock handler not called, regs kept, END due',
          lg['redraw'] == 1 and lg['stock'] == 0 and lg['regs'] and phase() == 1, lg)
    check('press 1: START press leaves the note playing (no note sent, no fade)',
          lg['note'] == [] and m.r(EP + 4022, 1) == 0, lg['note'])
    check('press 1 then playback stops: START = the mark point, END = the old END (SP-303)',
          pos_of(S, rget(m, S, 39)) == 1000 and pos_of(S, rget(m, S, 40)) == en0, (rget(m, S, 39), rget(m, S, 40)))
    voice(2, S, 3000, st0, en0)
    lg = key(21)
    check('press 2: END = play position', (S, 40, bytes_of(S, 3000)) in lg['set'] and
          pos_of(S, rget(m, S, 40)) == 3000 and pos_of(S, rget(m, S, 39)) == 1000, lg['set'])
    vel = m.r(GP + L.PAD_VELOCITY, 4)
    check('press 2: playback restarts at once: note-on straight to the audio task, after the END commit',
          lg['note'] == [(0, L.NOTE_ON, S, vel, 0)] and lg.get('note_flags') == 1 and
          lg['seq'][-1][0] == 'note' and ('set', 40) in lg['seq'][:-1] and 'note_di' not in lg, lg['seq'])
    check('press 2: no direct fade request (the stock note-on replaces the note)',
          m.r(EP + 4022, 1) == 0 and m.r(EP + 4028, 1) == 0, (m.r(EP + 4022, 1), m.r(EP + 4028, 1)))
    check('press 2: sample marked', marked_ok() and phase() == 0 and lg['regs'])
    # press 3 on a marked sample: clear to the whole sample (also when it isn't playing)
    voices_off()
    lg = key(21)
    check('press 3 (marked, not playing): START / END = whole sample',
          (rget(m, S, 39), rget(m, S, 40)) == whole and not marked_ok() and phase() == 0, (lg['set'], whole))
    check('press 3: clear sends no note', lg['note'] == [], lg['note'])
    check('press 3: clear through the stock commits (Measure / BPM)',
          [p for _, p, _ in lg['set']].count(43) == 2 and lg['redraw'] == 1 and lg['regs'], lg['set'])
    voice(2, S, 1500, st0, en0)
    lg = key(21)
    check('press 4: START again', pos_of(S, rget(m, S, 39)) == 1500 and phase() == 1, lg['set'])
    # END too close to START moves START; then exactly START + 193 is accepted
    voice(2, S, 1500 + L.MIN_LEN - 1, st0, en0)
    lg = key(21)
    check('END press < START + 193: sets START, still waiting for END',
          pos_of(S, rget(m, S, 39)) == 1500 + L.MIN_LEN - 1 and phase() == 1 and
          all(p != 40 for _, p, _ in lg['set']), lg['set'])
    voice(2, S, 1500 + 2 * L.MIN_LEN - 1, st0, en0)
    key(21)
    check('END press exactly START + 193: accepted and marked',
          pos_of(S, rget(m, S, 40)) == 1500 + 2 * L.MIN_LEN - 1 and phase() == 0 and marked_ok())
    key(21)                                                             # clear
    # START press too close to the (untrimmed) END: ignored
    voice(2, S, en0 - L.MIN_LEN + 1, st0, en0)
    lg = key(21)
    check('START press within 193 of END: nothing changes', lg['set'] == [] and lg['redraw'] == 0, lg)
    sample(S)

    # ======================================================================= what counts as marked
    def mark_it(s=S, a=1000, b=3000):
        m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF)
        voices_off(); voice(2, s, a, 0, en0); key(21); voice(2, s, b, 0, en0); key(21)
        return marked_ok(s)
    check('mark again', mark_it())
    sample(S)
    check('whole sample: not marked', not marked_ok() and R.call(labels['ISMARKED'], S)[0] == 0)
    R.call(mod.SETTER, S, 39, bytes_of(S, 1200))                        # WAVE EDIT moves START
    check('START moved in WAVE EDIT: marked', R.call(labels['ISMARKED'], S)[0] == 1)
    sample(S); R.call(mod.SETTER, S, 40, bytes_of(S, 3100))             # only END moved
    check('END moved in WAVE EDIT: marked', R.call(labels['ISMARKED'], S)[0] == 1)
    voices_off()
    lg = key(21)
    check('L/R on a WAVE EDIT trim (no END due): clears it to the whole sample',
          (rget(m, S, 39), rget(m, S, 40)) == whole and phase() == 0, lg['set'])
    for i in range(48):
        m.w(REC + 48 * 7 + i, 1, 0)
    check('empty sample: not marked', R.call(labels['ISMARKED'], 7)[0] == 0)
    sample(S); mark_it()
    S3 = BANK * 16 + 11
    for i in range(48):                                                 # CLIPBOARD copy: record bytes
        m.w(REC + 48 * S3 + i, 1, m.r(REC + 48 * S + i, 1))
    check('copied sample (record copy): marked', R.call(labels['ISMARKED'], S3)[0] == 1)
    sample(S)

    # ======================================================================= key routing
    sample(S); voices_off(); voice(2, S, 1000, st0, en0)
    for scr, name in ((SCREEN_WAVE, 'WAVE EDIT'), (SCREEN_WAVEPARAM, 'sample screen with waveform')):
        for state in (1, 0):
            lg = key(21, state, scr)
            check('%s: L/R %s goes to the stock handler' % (name, 'press' if state else 'release'),
                  lg['stock'] == 1 and lg['set'] == [] and lg['redraw'] == 0, lg)
    for code in (19, 20):
        lg = key(code)
        check('main screen: ZOOM key %d goes to the stock handler' % code, lg['stock'] == 1 and lg['set'] == [], lg)
    for state in (0, 2):
        lg = key(21, state)
        check('L/R state %d does nothing' % state, lg['stock'] == 0 and lg['set'] == [] and lg['redraw'] == 0, lg)
    m.w(MODE, 4, 3)
    lg = key(21)
    check('UI mode 0..4 (no key-class dispatch): untouched', lg['set'] == [] and lg['stock'] == 0, lg)
    m.w(MODE, 4, 6)
    lg = key(29 + 3, 1, PATTERN)
    check('pad key: the stock pad handler still runs', lg['pad'] == 1 and lg['regs'], lg)

    # ======================================================================= which voice / nothing
    m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF)
    voices_off()
    lg = key(21)
    check('no voice playing (unmarked): nothing', lg['set'] == [] and lg['redraw'] == 0 and lg['regs'], lg)
    voice(2, S, 1000, st0, en0, fading=True)
    check('only a fading voice: nothing', key(21)['set'] == [])
    voices_off(); voice(4, S + 1, 1000, st0, en0)
    check('another sample playing: nothing', key(21)['set'] == [])
    voice(1, S, 2500, st0, en0); voice(6, S, 1200, st0, en0)
    key(21)
    check('two voices of the sample: the earliest position', pos_of(S, rget(m, S, 39)) == 1200)
    voice(1, S, 3000, st0, en0); voice(6, S, 3000, st0, en0)
    lg = key(21)
    check('END with two voices of the sample: one note sent, voice masks untouched',
          m.r(EP + 4022, 1) == 0 and lg['note'] == [(0, L.NOTE_ON, S, m.r(GP + L.PAD_VELOCITY, 4), 0)],
          (m.r(EP + 4022, 1), lg['note']))
    sample(S); voices_off(); voice(2, S, en0 + 5, st0, en0)
    check('position outside the voice range: nothing', key(21)['set'] == [])
    S2 = BANK * 16 + 9
    st2, en2 = sample(S2); sample(S)
    voices_off(); voice(2, S, 1000, st0, en0)
    key(21)
    m.w(SYS9, 1, 9); voice(3, S2, 2000, st2, en2)
    lg = key(21)
    check('other pad pressed: its first press is a START',
          (S2, 39, bytes_of(S2, 2000)) in lg['set'] and phase() == 1, lg['set'])
    m.w(SYS9, 1, PAD)
    sample(S); voices_off(); voice(2, S, 1000, st0, en0)
    m.w(PROTECT + 3, 1, 1 << BANK)
    lg = key(21)
    check('protected bank: "Protected!" and nothing changed', lg['error'] == [L.ERR_PROTECTED] and lg['set'] == [], lg)
    m.w(PROTECT + 3, 1, 0)
    sample(S, reverse=1)
    check('reverse sample: nothing', key(21)['set'] == [])
    sample(S); mark_it(); rset(m, S, L.PARAM_REVERSE, 1)
    check('reverse sample that is marked: the press still clears', key(21)['set'] and not marked_ok())
    m.w(SYS9, 1, 16)
    lg = key(21)
    check('pad 16 (no sample): nothing', lg['set'] == [] and lg['regs'], lg)
    m.w(SYS9, 1, PAD)
    for rate, step in ((2205, 2), (1102, 4)):
        st, en = sample(S, rate=rate); voices_off(); voice(2, S, st + 300 * step, st, en)
        m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF)
        key(21); voice(2, S, st + 900 * step, st, en); key(21)
        check('rate %d: START / END round-trip exactly, marked' % rate,
              pos_of(S, rget(m, S, 39)) == st + 300 * step and pos_of(S, rget(m, S, 40)) == st + 900 * step
              and marked_ok(), (pos_of(S, rget(m, S, 39)), pos_of(S, rget(m, S, 40))))

    # ======================================================================= hold L/R + pad
    sample(S); voices_off()
    rset(m, S, 39, bytes_of(S, 1500))                                   # START somewhere later
    m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF)
    lg = key(29 + PAD, 1, PATTERN)
    check('pad without L/R held: START unchanged', lg['set'] == [] and lg['pad'] == 1)
    lg = key(21, 1, PATTERN, hold=True)                                 # hold: START was moved, so
    check('L/R on the trimmed sample (nothing playing): clears it first', not marked_ok())  # clear
    rset(m, S, 39, bytes_of(S, 1500))
    lg = key(29 + PAD, 1, PATTERN)
    check('pad while L/R held: START = beginning of the sample',
          rget(m, S, 39) == rget(m, S, 37) and phase() == 1 and lg['pad'] == 1 and lg['regs'], lg['set'])
    check('... committed before the stock pad handler starts the note',
          lg['seq'] and lg['seq'][0] == ('set', 39) and lg['seq'][-1] == ('pad',), lg['seq'])
    lg = key(29 + PAD, 0, PATTERN)
    check('pad release while held: nothing more', lg['set'] == [])
    key(21, 0, PATTERN)                                                 # let go
    voices_off(); voice(2, S, 3000, 0, en0)
    lg = key(21, 1, PATTERN)
    check('next L/R press: END, sample marked', pos_of(S, rget(m, S, 40)) == 3000 and marked_ok() and
          rget(m, S, 39) == rget(m, S, 37), lg['set'])
    key(21, 0, PATTERN)
    lg = key(29 + PAD, 1, PATTERN)
    check('after L/R released, a pad press changes nothing', lg['set'] == [] and marked_ok())
    key(21, 1, PATTERN)                                                 # clear
    rset(m, S, 39, bytes_of(S, 1500))
    key(21, 1, PATTERN, hold=True); key(21, 2, PATTERN)                 # held, auto-repeat event
    lg = key(29 + PAD, 1, PATTERN)
    check('held with key repeat events: still held', rget(m, S, 39) == rget(m, S, 37), lg['set'])
    key(21, 0, PATTERN)
    rset(m, S, 39, bytes_of(S, 1500))
    key(21, 1, SCREEN_WAVE, hold=True)
    lg = key(29 + PAD, 1, SCREEN_WAVE)
    check('held on WAVE EDIT (vertical zoom): pad press changes nothing', lg['set'] == [], lg['set'])
    key(21, 0, SCREEN_WAVE)
    m.w(PROTECT + 3, 1, 1 << BANK)
    key(21, 1, PATTERN, hold=True)
    lg = key(29 + PAD, 1, PATTERN)
    check('held + pad on a protected bank: "Protected!", note still played',
          lg['error'] == [L.ERR_PROTECTED] and lg['set'] == [] and lg['pad'] == 1, lg)
    key(21, 0, PATTERN)
    m.w(PROTECT + 3, 1, 0)
    sample(S)

    # ======================================================================= the tag
    x0, y0, x1, y1 = L.TAG_BOX
    inbox = lambda x, y: x0 <= x <= x1 and y0 <= y <= y1

    def tag_px(buf):
        return sum(pixel(buf, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))

    def outside_same(a, b):
        return all(pixel(a, x, y) == pixel(b, x, y) for x in range(128) for y in range(64) if not inbox(x, y))

    area = (x1 - x0 + 1) * (y1 - y0 + 1)
    for scr, name in ((PATTERN, 'PATTERN PLAY'), (SONG, 'SONG PLAY')):
        for bank in (BANK, 14):                                         # USER 6, PITCH 1 (longest name)
            m.w(SYS9 + 1, 1, bank)
            s = bank * 16 + PAD
            sample(s)
            mark_it(s)
            sync_ram(m, STOCK.m); ref, _ = show_screen(scr, STOCK, bank)
            got, lg = show_screen(scr, R, bank)
            check('%s bank %d marked: inverted MARK tag, rest of the screen as stock' % (name, bank),
                  tag_px(got) > area * 0.55 and outside_same(got, ref) and lg['regs'],
                  (tag_px(got), area))
            if scr == PATTERN and bank == 25:
                print(show(got))
            key(21, 1, scr)                                             # clear
            sync_ram(m, STOCK.m); ref, _ = show_screen(scr, STOCK, bank)
            got, _ = show_screen(scr, R, bank)
            if not outside_same(got, ref):
                print('differs at', [(x, y) for x in range(128) for y in range(64) if not inbox(x, y) and pixel(got, x, y) != pixel(ref, x, y)][:12])
            check('%s bank %d after the clear: no tag, screen as stock' % (name, bank),
                  tag_px(got) == tag_px(ref) and outside_same(got, ref) and tag_px(got) == 0, tag_px(got))
            voices_off(); voice(2, s, 1000, 0, en0)
            m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF)
            show_screen(scr, R, bank)
            lg = key(21, 1, scr)                                        # START: END due
            got = fb(m)
            sync_ram(m, STOCK.m); ref, _ = show_screen(scr, STOCK, bank)
            check('%s bank %d START set: MARK drawn, set to flash' % (name, bank),
                  tag_px(got) > area * 0.55 and outside_same(got, ref) and lg['regs'] and
                  m.r(L.MARK_RAM + 16, 4) == 1, (tag_px(got), m.r(L.MARK_RAM + 16, 4)))
            on = got
            idle(m, 0)
            off = fb(m)
            check('%s bank %d flashing: off phase blanks the tag, box line and screen kept' % (name, bank),
                  tag_px(off) == 0 and outside_same(off, on), tag_px(off))
            idle(m, 1)
            check('%s bank %d flashing: on phase shows it again' % (name, bank), fb(m) == on)
            voice(2, s, 3000, 0, en0)
            key(21, 1, scr)                                             # END: marked
            check('%s bank %d END set: MARK solid (no flashing)' % (name, bank),
                  tag_px(fb(m)) > area * 0.55 and m.r(L.MARK_RAM + 16, 4) == 0)
            before = fb(m); idle(m, 0)
            check('%s bank %d marked: the idle loop leaves the tag alone' % (name, bank), fb(m) == before)
            sample(s)
    m.w(SYS9 + 1, 1, BANK)
    # the tag follows the last pressed pad
    sample(S); mark_it(); S4 = BANK * 16 + 2; sample(S4)
    show_screen(PATTERN, R)
    m.w(SYS9, 1, 2)                                                     # (the stock handler sets 184)
    key(29 + 2, 1, PATTERN)
    check('pad of an unmarked sample pressed on PATTERN PLAY: tag removed', tag_px(fb(m)) == 0)
    m.w(SYS9, 1, PAD)
    key(29 + PAD, 1, PATTERN)
    check('marked pad pressed again: tag back', tag_px(fb(m)) > area * 0.55)
    # flashing never touches another screen
    voices_off(); voice(2, S, 1000, 0, en0); key(21, 1, PATTERN)        # clear
    key(21, 1, PATTERN)                                                 # START: flashing
    m.w(GP + 0x10000 - 17804, 4, m.r(0x120590 + 4 * SCREEN_MAIN, 4))    # another screen is current
    before = fb(m); idle(m, 0)
    check('flash pending but another screen current: framebuffer untouched', fb(m) == before)
    sample(S)
    m.w(GP + 0x10000 - 17804, 4, m.r(0x120590 + 4 * PATTERN, 4))
    m.w(L.MARK_RAM, 4, 0); m.w(L.MARK_RAM + 16, 4, 1)                  # garbage, RAM not initialised
    before = fb(m); idle(m, 0)
    check('RAM not initialised: the idle loop writes nothing', fb(m) == before)
    m.w(L.MARK_RAM + 16, 4, 0)
    # playback stops while the END is due: flashing stops, START stays, END is the old one
    sample(S); show_screen(PATTERN, R)
    voices_off(); voice(2, S, 1000, 0, en0)
    m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF)
    key(21, 1, PATTERN)                                                 # START
    end_before = rget(m, S, 40)
    idle(m, 1)
    check('END due, sample still playing: still flashing', m.r(L.MARK_RAM + 16, 4) == 1 and phase() == 1)
    voices_off()                                                        # playback stops
    idle(m, 1)
    check('playback stopped: flashing stops, MARK steady (START moved), END wait over',
          m.r(L.MARK_RAM + 16, 4) == 0 and phase() == 0 and tag_px(fb(m)) > area * 0.55,
          (m.r(L.MARK_RAM + 16, 4), phase(), tag_px(fb(m))))
    check('... START = the mark point, END = the old END',
          pos_of(S, rget(m, S, 39)) == 1000 and rget(m, S, 40) == end_before and marked_ok())
    got, _ = show_screen(PATTERN, R)
    check('... and the screen redrawn later shows MARK steady', tag_px(got) > area * 0.55 and
          m.r(L.MARK_RAM + 16, 4) == 0)
    voice(2, S, 2000, 0, en0)
    lg = key(21, 1, PATTERN)
    check('... next press clears (steady MARK)', not marked_ok() and phase() == 0 and
          tag_px(fb(m)) == 0, lg['set'])
    # hold L/R + pad: the note starts after the mark; not cancelled before it has played
    sample(S); voices_off(); key(21, 0, PATTERN)
    m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF); rset(m, S, 39, bytes_of(S, 1500))
    key(21, 1, PATTERN, hold=True); key(29 + PAD, 1, PATTERN); key(21, 0, PATTERN)
    idle(m, 1)
    check('hold + pad, note not started yet: still flashing', m.r(L.MARK_RAM + 16, 4) == 1 and phase() == 1)
    voice(2, S, 10, 0, en0); idle(m, 1)
    voices_off(); idle(m, 1)
    check('... note played and stopped: flashing stops; START at the beginning, END whole: no tag',
          m.r(L.MARK_RAM + 16, 4) == 0 and phase() == 0 and tag_px(fb(m)) == 0 and not marked_ok())
    # END due set on another screen (tag not drawn): the wait still ends when playback stops
    sample(S); voices_off(); voice(2, S, 1000, 0, en0)
    m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF)
    key(21, 1, SCREEN_MAIN)
    m.w(GP + 0x10000 - 17804, 4, m.r(0x120590 + 4 * SCREEN_MAIN, 4))
    voices_off(); before = fb(m); idle(m, 1)
    check('START set on another screen, playback stopped: wait ends, framebuffer untouched',
          phase() == 0 and fb(m) == before)
    # the restart copies the hit's note when the audio task's last note-on was this sample
    sample(S); voices_off(); voice(2, S, 1000, 0, en0)
    m.w(L.MARK_RAM + 4, 4, 0xFFFFFFFF)
    key(21, 1, PATTERN)
    ln = GP + L.LAST_NOTE
    m.w(ln, 2, 7); m.w(ln + 2, 2, S); m.w(ln + 4, 1, 2); m.w(ln + 5, 1, 99); m.w(ln + 6, 1, 3)
    voice(2, S, 3000, 0, en0)
    lg = key(21, 1, PATTERN)
    check('restart copies part / velocity / flags / extra of the last note-on of this sample',
          lg['note'] == [(2, L.NOTE_ON, S, 99, 7)] and lg.get('note_flags') == 3, (lg['note'], lg.get('note_flags')))
    m.w(ln + 2, 2, S + 1)
    sample(S); key(21, 1, PATTERN)
    voice(2, S, 1000, 0, en0); key(21, 1, PATTERN); voice(2, S, 3000, 0, en0)
    lg = key(21, 1, PATTERN)
    check('... last note-on was another sample: pad defaults',
          lg['note'] == [(0, L.NOTE_ON, S, m.r(GP + L.PAD_VELOCITY, 4), 0)] and lg.get('note_flags') == 1, lg['note'])
    # the restart really reaches the audio task: run the real post (no stub) into its ring
    ring, rd, wr = GP + 0x10000 - 12100, GP + 0x10000 - 10052, GP + 0x10000 - 10048
    m.w(rd, 4, 5); m.w(wr, 4, 5); m.w(ln + 2, 2, S + 1)
    c = CPU(m); c.r[30] = EP; c.r[4] = GP; c.r[3] = SP0; c.r[31] = END; c.r[6] = S
    c.pc = labels['RETRIG']
    rtos = {0x5FC4, 0x6082, 0x5DB0, 0x5CEA}     # ROM kernel calls (lock / unlock / set / wait flag)
    while True:
        c.run({END} | rtos, 200000)
        if c.pc == END:
            break
        c.r[10] = 0; c.pc = c.r[31]
    e = ring + 16 * 6
    check('restart note lands in the audio task ring (what its dispatcher reads)',
          m.r(wr, 4) == 6 and m.r(e, 1) == 4 and m.r(e + 3, 1) == L.NOTE_ON and m.r(e + 4, 2) == S,
          (m.r(wr, 4), [m.r(e + i, 1) for i in range(10)]))
    sample(S); voices_off()
    # other screens and preset banks are never drawn on
    before = fb(m)
    key(29 + 2, 1, SCREEN_MAIN)
    check('pad pressed on another screen: framebuffer untouched', fb(m) == before)
    m.w(SYS9 + 1, 1, 0); sync_ram(m, STOCK.m)
    ref, _ = show_screen(PATTERN, STOCK, 0)
    got, _ = show_screen(PATTERN, R, 0)
    check('PRESET bank: screen exactly as stock (bank name not overwritten)', got == ref)
    m.w(SYS9 + 1, 1, BANK)

    print('FAILED: %s' % fails if fails else 'all ok')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
