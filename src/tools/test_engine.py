"""Shared emulator helpers for the tests: memory set-up (mask ROM + flash image + RAM), a test
voice, the ROM's per-block voice loop, output and voice-mask access."""
import sys, os, random, struct, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from v850emu import Mem, CPU, Halt

EP = 0x3FFE000
ROMF = os.environ.get('SP505_MASK_ROM') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rom_dump', 'cpu_mask_rom_v1.00.bin')
OUT = 0x4F0000          # output block (16 frames x 16 bytes)
RING = 0x500000
V = 2                   # voice under test


def make_mem(prg):
    m = Mem()
    m.add(0, open(ROMF, 'rb').read())
    img = open(prg, 'rb').read()[0x200:]
    m.add(0x100000, bytearray(img))
    m.add(EP, bytearray(0x1000))
    m.add(0x400000, bytearray(0x200000))
    m.add(0xFFFFF000, bytearray(0x1000))
    return m


def setup_voice(m, rng, fmt=6, nbytes=12, nchunks=60, loop=False, pan=0, send=0, vol=100):
    rec = EP + 1020 + V * 208
    w = lambda off, n, v: m.w(rec + off, n, v)
    data = bytes(rng.getrandbits(8) for _ in range(nbytes * 400))
    for i, b in enumerate(data):
        m.w(RING + i, 1, b)
    seg = nbytes * 10
    for k in range(15):                     # +56 .. +112
        w(56 + 4 * k, 4, RING + k * seg)
    w(16, 4, fmt); w(12, 4, 0xFFFFF); w(20, 4, 0)
    w(36, 4, RING); w(40, 4, RING)
    w(143, 1, nbytes); w(137, 1, 1); w(139, 1, int(os.environ.get('RATE', '0'))); w(148, 1, 0); w(151, 1, 0)
    w(24, 4, 0); w(28, 4, 0); w(32, 4, nchunks)
    w(145, 1, 0)
    for k in range(14): w(116 + k, 1, 0)
    w(116, 1, 2); w(117, 1, 1)
    w(130, 2, 128); w(133, 1, 0); w(195, 1, 0)
    w(134, 1, send); w(136, 1, vol); w(140, 1, pan); w(142, 1, 1 << V)
    mask = 1 << V
    m.w(EP + 4021, 1, mask); m.w(EP + 4023, 1, mask)
    m.w(EP + 4030, 1, mask if loop else 0)
    m.w(EP + 4020, 1, 0xFF)
    for a in (4022, 4025, 4026, 4027, 4028, 4029, 4019):
        m.w(EP + a, 1, 0)
    m.w(EP + 2976, 4, OUT)
    return rec


def clear_out(m):
    for i in range(0, 256, 4):
        m.w(OUT + i, 4, 0)


def read_out(m):
    return [m.r(OUT + i, 4, signed=True) for i in range(0, 256, 4)]


def masks(m):
    return {a: m.r(EP + a, 1) for a in (4019, 4021, 4022, 4023, 4025, 4028, 4029)}


def rom_block(m):
    c = CPU(m)
    c.r[30] = EP; c.r[3] = 0x430000 - 0x100
    c.pc = 0x96FC
    c.run({0x10FB4})
    return c.steps


def epilogue(m):
    # what the ROM does with 4025/4029/4019 after the voice loop (they get consumed)
    for a in (4025, 4029, 4019):
        m.w(EP + a, 1, 0)
