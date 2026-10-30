#!/usr/bin/env python3
"""SP-505 firmware (sp505.prg) tool.

File layout (v1.02, 1,049,088 bytes):
  0x000-0x1FF  update header
      0x00  "BOSS SP505\\0Ver.1.02\\0" + build no + date (ASCII)
      0x40  16 x uint16 LE: byte-sum (mod 65536) of each 64 KB block of the image
      0x80  uint16 LE: two's-complement of the sum of those 16 words
            (so all 16 block sums + this word == 0 mod 65536)
  0x200-       1 MB flash image, mapped at CPU address 0x100000
               (NEC V850E/MS1, uPD703102A; mask ROM below 0x100000 holds the updater)

Commands:
  verify  FILE
  info    FILE
  patch   IN OUT --set ADDR=HEX ... --str ADDR=TEXT ...   (ADDR = CPU address, e.g. 0x120c3f)
  effect-name IN OUT NUM "NEW NAME"   rename an effect in place (same length or shorter)
  extract-dsp IN OUTDIR               dump each effect's MR2 DSP program (286 x 24-bit words)
"""
import struct, sys, os, argparse

HDR = 0x200
BASE = 0x100000
BLOCK = 0x10000
NBLK = 16
EFFECT_NAME_TABLE = 0x120C7C   # 26 x char* (effects 1..26)
EFFECT_ALGO_TABLE = 0x12B39C   # 27 x {handler, start, end, prog*, init*} (0 = OFF)
EFFECT_NAMES = ['OFF', 'FILTER+DRIVE', 'PITCH SHIFTER', 'DELAY', 'VINYL SIMULATOR', 'ISOLATOR',
                'REVERB', 'TAPE ECHO', 'CHORUS', 'FLANGER', 'PHASER', 'TREMOLO-PAN', 'DISTORTION',
                'OVERDRIVE', 'FUZZ', 'WAH', 'OCTAVE', 'COMPRESSOR', 'EQUALIZER', 'LO-FI PROCESSOR',
                'NOISE GENERATOR', 'RADIO TUNING', 'SLICER+FLANGER', 'RING MODULATOR',
                'CHROMATIC PS', 'VOICE TRANSFORMER', 'CENTER CANCELER']


def load(path):
    d = bytearray(open(path, 'rb').read())
    if len(d) != HDR + NBLK * BLOCK:
        raise SystemExit('unexpected size %d (expected %d)' % (len(d), HDR + NBLK * BLOCK))
    if not d.startswith(b'BOSS SP505\0'):
        raise SystemExit('missing "BOSS SP505" header')
    return d


def put(d, addr, data, expect=None):
    """write data at CPU address addr; with expect, the bytes there must be exactly that first."""
    o = a2o(addr)
    if expect is not None:
        cur = bytes(d[o:o + len(expect)])
        if cur != expect:
            raise SystemExit('unexpected bytes at %#x: %s (expected %s)' % (addr, cur.hex(), expect.hex()))
    d[o:o + len(data)] = data


def compute_sums(d):
    sums = [sum(d[HDR + i * BLOCK:HDR + (i + 1) * BLOCK]) & 0xFFFF for i in range(NBLK)]
    final = (-sum(sums)) & 0xFFFF
    return sums, final


def stored_sums(d):
    return list(struct.unpack_from('<16H', d, 0x40)), struct.unpack_from('<H', d, 0x80)[0]


def fix(d):
    sums, final = compute_sums(d)
    struct.pack_into('<16H', d, 0x40, *sums)
    struct.pack_into('<H', d, 0x80, final)


def verify(d, quiet=False):
    (cs, cf), (ss, sf) = compute_sums(d), stored_sums(d)
    ok = cs == ss and cf == sf
    if not quiet:
        for i in range(NBLK):
            flag = '' if cs[i] == ss[i] else '   <-- MISMATCH'
            print('  block %2d @%06x  stored %04x  computed %04x%s' % (i, BASE + i * BLOCK, ss[i], cs[i], flag))
        print('  final word        stored %04x  computed %04x%s' % (sf, cf, '' if sf == cf else '   <-- MISMATCH'))
        print('VERIFY: %s' % ('OK' if ok else 'FAILED'))
    return ok


def a2o(addr):
    if not BASE <= addr < BASE + NBLK * BLOCK:
        raise SystemExit('address %#x outside flash image' % addr)
    return HDR + addr - BASE


def u32(d, addr):
    return struct.unpack_from('<I', d, a2o(addr))[0]


def cstr(d, addr):
    o = a2o(addr); e = d.index(0, o)
    return d[o:e].decode('latin1')


def info(d):
    print('header :', d[:0x25].replace(b'\0', b' | ').decode('latin1'))
    print('checksums', 'OK' if verify(d, quiet=True) else 'BAD')
    print('\neffects (name / DSP program):')
    for n in range(27):
        h, s, e, p, i = struct.unpack_from('<5I', d, a2o(EFFECT_ALGO_TABLE + 20 * n))
        name = cstr(d, u32(d, EFFECT_NAME_TABLE + 4 * (n - 1))) if n else 'OFF'
        print('  %2d %-20s handler %06x  dsp %d..%d  prog %06x  init %06x' % (n, name, h, s, e, p, i))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('verify').add_argument('file')
    sub.add_parser('info').add_argument('file')
    p = sub.add_parser('patch'); p.add_argument('inp'); p.add_argument('out')
    p.add_argument('--set', action='append', default=[], help='ADDR=hexbytes')
    p.add_argument('--str', action='append', default=[], help='ADDR=text (null-terminated, must fit)')
    e = sub.add_parser('effect-name'); e.add_argument('inp'); e.add_argument('out')
    e.add_argument('num', type=int); e.add_argument('name')
    x = sub.add_parser('extract-dsp'); x.add_argument('inp'); x.add_argument('outdir')
    a = ap.parse_args()

    if a.cmd == 'verify':
        sys.exit(0 if verify(load(a.file)) else 1)
    if a.cmd == 'info':
        info(load(a.file)); return
    if a.cmd == 'extract-dsp':
        d = load(a.inp); os.makedirs(a.outdir, exist_ok=True)
        for n in range(27):
            h, s, en, p, i = struct.unpack_from('<5I', d, a2o(EFFECT_ALGO_TABLE + 20 * n))
            if not p:
                continue
            cnt = abs(s - en) + 1
            words = struct.unpack_from('<%dI' % cnt, d, a2o(p))
            fn = os.path.join(a.outdir, '%02d_%s.txt' % (n, EFFECT_NAMES[n].replace(' ', '_')))
            with open(fn, 'w') as f:
                f.write('# effect %d %s  prog@%06x  loads MR2 addr %d..%d\n' % (n, EFFECT_NAMES[n], p, min(s, en), max(s, en)))
                for k, w in enumerate(words):
                    f.write('%3d %06x\n' % (min(s, en) + k, w))
        print('wrote DSP programs to', a.outdir); return

    d = load(a.inp)
    if not verify(d, quiet=True):
        raise SystemExit('input checksums are already bad; refusing to patch')
    if a.cmd == 'effect-name':
        if not 1 <= a.num <= 26:
            raise SystemExit('effect number must be 1..26')
        addr = u32(d, EFFECT_NAME_TABLE + 4 * (a.num - 1))
        old = cstr(d, addr)
        new = a.name.encode('ascii')
        if len(new) > len(old):
            raise SystemExit('new name %r is longer than %r (%d chars max)' % (a.name, old, len(old)))
        new = new.ljust(len(old), b' ')   # pad with spaces, keep layout identical
        o = a2o(addr); d[o:o + len(new)] = new
        print('effect %d: %r -> %r' % (a.num, old, new.decode()))
    else:
        for s in a.set:
            k, v = s.split('=', 1); o = a2o(int(k, 0)); b = bytes.fromhex(v)
            d[o:o + len(b)] = b
        for s in a.str:
            k, v = s.split('=', 1); addr = int(k, 0); old = cstr(d, addr)
            if len(v) > len(old):
                raise SystemExit('string at %#x: %r longer than original %r' % (addr, v, old))
            o = a2o(addr); d[o:o + len(old)] = v.encode('ascii').ljust(len(old), b' ')
    fix(d)
    assert verify(d, quiet=True)
    open(a.out, 'wb').write(d)
    print('wrote', a.out, '(checksums fixed)')


if __name__ == '__main__':
    main()
