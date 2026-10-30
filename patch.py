#!/usr/bin/env python3
"""SP-505 EXTRAfirmware patcher.

Turns the official BOSS SP-505 system update v1.02 (sp505.prg) into SP-505 EXTRAfirmware.
No BOSS/Roland code is included in this repository: you supply the official file, the patcher
adds the EXTRAfirmware code and fixes the checksums.

usage:  python3 patch.py <official sp505.prg> [-o <output sp505.prg>]
        (default output: ./out/sp505.prg)
Needs Python 3.8 or newer, nothing else.
"""
import sys, os, hashlib, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'src')); sys.path.insert(0, os.path.join(HERE, 'src', 'tools'))

RELEASE = '2.0.0'
VERSION_SCREEN = '2.00'
INPUT_MD5 = '20bb3983ec3144793deefd34075e7e58'      # official v1.02 sp505.prg
OUTPUT_MD5 = '38091b30cf86dc1780655bf73eb69e2c'     # result of this release
CHECKSUM = 'FA9AD007'                                # SYS checksum on the version screen


def md5(path):
    return hashlib.md5(open(path, 'rb').read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description='Build SP-505 EXTRAfirmware from the official v1.02 file.')
    ap.add_argument('official', help='official SP-505 v1.02 sp505.prg')
    ap.add_argument('-o', '--output', default=os.path.join('out', 'sp505.prg'))
    a = ap.parse_args()
    if not os.path.isfile(a.official):
        sys.exit('error: %s not found' % a.official)
    got = md5(a.official)
    if got != INPUT_MD5:
        sys.exit('error: %s is not the official SP-505 v1.02 update file\n'
                 '       (MD5 %s, expected %s). Nothing was written.' % (a.official, got, INPUT_MD5))
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    import extrafirmware
    tmp = a.output + '.tmp'
    extrafirmware.main(a.official, tmp)
    if md5(tmp) != OUTPUT_MD5:
        os.remove(tmp)
        sys.exit('error: the result does not match the released build (internal error). Nothing was written.')
    os.replace(tmp, a.output)
    print('SP-505 EXTRAfirmware %s written to %s' % (RELEASE, a.output))
    print('After updating, the version screen (hold EXIT + ENTER at power-on) shows')
    print('    version %s, SYS checksum %s' % (VERSION_SCREEN, CHECKSUM))
    print('Copy it to the SmartMedia card together with SMPINFO0.SP0 from the official update (see docs/INSTALL.md).')


if __name__ == '__main__':
    main()
