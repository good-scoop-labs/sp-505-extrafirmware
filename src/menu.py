"""Sample parameter menu: two new rows, Varispeed (parameter 58) and Fine Tune (parameter 59),
under the stock eight (Level ... Measure, Beat), plus the speed tables they select.

Both parameters use spare bytes of the sample's parameter record (+0x2D, +0x2E) that the stock
firmware already defines (range 0..127, unused). Their descriptors become signed with the ranges
-24..+12 and -50..+50; the menu prints names[value] from a pointer to the 0 entry, so negative
values index backwards.
"""
import struct
import layout as L
from sp505fw import put, a2o
from v850asm import mov_i


def names(values):
    return b''.join((('%+d' % v) if v else '0').encode().ljust(7, b'\0') for v in values)


def step_table(values, per_octave):
    return b''.join(struct.pack('<I', round(65536 * 2 ** (v / per_octave))) for v in values)


def install(d):
    ff = lambda b: b'\xff' * len(b)
    # value names, labels and speed tables (16.16; the engine multiplies STEPTAB x FINETAB)
    for addr, data in ((L.VARI_LABEL, b'Varispeed\0'), (L.VARI_NAMES, names(L.SEMIS)),
                       (L.STEPTAB, step_table(L.SEMIS, 12)), (L.FINETAB, step_table(L.FINE, 1200)),
                       (L.FINE_NAMES, names(L.FINE)), (L.FINE_LABEL, b'Fine Tune\0')):
        put(d, addr, data, ff(data))
    # menu table: the stock 8 rows + Varispeed + Fine Tune
    o = a2o(L.STOCK_MENU_TABLE)
    table = (bytes(d[o:o + 96]) +
             struct.pack('<III', L.PARAM_VARI, L.VARI_LABEL, L.VARI_NAMES + 7 * -L.SEMIS[0]) +
             struct.pack('<III', L.PARAM_FINE, L.FINE_LABEL, L.FINE_NAMES + 7 * -L.FINE[0]))
    assert L.MENU_TABLE + len(table) <= L.VARI_LABEL
    put(d, L.MENU_TABLE, table, ff(table))
    put(d, L.MENU_TABLE_PTR, struct.pack('<I', L.MENU_TABLE), struct.pack('<I', L.STOCK_MENU_TABLE))
    put(d, L.MENU_ROWS_SITES[0], mov_i(10, 'r7'), mov_i(8, 'r7'))
    put(d, L.MENU_ROWS_SITES[1], mov_i(10, 'r8'), mov_i(8, 'r8'))
    # descriptors: signed ranges, default 0
    for pid, values in ((L.PARAM_VARI, L.SEMIS), (L.PARAM_FINE, L.FINE)):
        desc = L.DESC + 20 * pid
        put(d, desc, struct.pack('<ii', values[0], values[-1]), struct.pack('<ii', 0, 127))
        put(d, desc + 16, b'\x01', b'\x00')
