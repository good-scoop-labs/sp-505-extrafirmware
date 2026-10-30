#!/usr/bin/env python3
"""SP-505 EXTRAfirmware: build the firmware from the official v1.02 sp505.prg.

    menu.py     Varispeed / Fine Tune menu rows, parameter descriptors, speed tables
    engine.py   the varispeed engine (audio-block hook), pad set-up, parameter handler
    voices.py   polyphony weighting (pad voice allocator)
    bpm.py      BPM rule, Play Type rules (value edit, parameter setter, header line)
    layout.py   every address used: stock firmware locations, EXTRAfirmware flash and RAM

usage: extrafirmware.py official_v102.prg out.prg
"""
import sys, os
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import sp505fw as fw
import layout as L
import menu, engine, voices, bpm

SYSTEM_VERSION = b'2.00'            # shown on the EXIT+ENTER screen, exactly 4 characters
VERSION = b'EXT Ver.' + SYSTEM_VERSION     # internal test screen text, 12 characters
assert len(SYSTEM_VERSION) == 4


def build(inp, out):
    d = fw.load(inp)
    if not fw.verify(d, quiet=True):
        raise SystemExit('input checksums bad')
    menu.install(d)
    labels = engine.install(d)
    voices.install(d)
    labels.update(bpm.install(d))
    fw.put(d, L.SYSTEM_VERSION, SYSTEM_VERSION, L.STOCK_SYSTEM_VERSION)
    fw.put(d, L.VERSION_TEXT, VERSION, L.STOCK_VERSION)
    fw.fix(d)
    assert fw.verify(d, quiet=True)
    open(out, 'wb').write(d)
    build.labels = labels
    return d


def checksum(d):
    """the checksum the SP-505's version screen shows"""
    return (-sum(bytes(d[0x200:0x200 + 0xF0000]))) & 0xFFFFFFFF


main = build                        # (name used by the test tools)
main.labels = {}
# constants for the test tools (ENGMOD=extrafirmware)
globals().update({k: getattr(L, k) for k in dir(L) if k.isupper() and k not in globals()})
build_ram = engine.build_engine

if __name__ == '__main__':
    d = build(sys.argv[1], sys.argv[2])
    print('version-screen checksum: %08X' % checksum(d))
