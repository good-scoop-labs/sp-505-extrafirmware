#!/usr/bin/env python3
"""Check the web patcher's data against the Python patcher, without a browser.

Applies docs/extrafirmware-patch.js to the official v1.02 sp505.prg the same way docs/index.html
does (copy the file, write each [offset, base64 bytes] run) and checks that the result is
byte-identical to what patch.py builds, and that both hashes and the release / version /
checksum fields in the data match patch.py.

usage: check_web_patch.py official/sp505.prg
"""
import sys, os, json, base64, hashlib, tempfile, subprocess

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.abspath(os.path.join(here, '..', '..'))
sys.path.insert(0, root)


def main():
    official = sys.argv[1]
    src = open(os.path.join(root, 'docs', 'extrafirmware-patch.js')).read()
    data = json.loads(src[src.index('{'):src.rindex('}') + 1])
    inp = open(official, 'rb').read()
    ok = True

    def check(name, cond, info=''):
        nonlocal ok
        print('%-48s %s %s' % (name, 'ok' if cond else 'FAIL', info))
        ok &= bool(cond)

    check('input is the official file (SHA-256)', hashlib.sha256(inp).hexdigest() == data['inputSha256'])
    out = bytearray(inp)
    for off, b64 in data['runs']:
        b = base64.b64decode(b64)
        out[off:off + len(b)] = b
    check('size', len(out) == data['size'], len(out))
    check('result matches outputSha256', hashlib.sha256(out).hexdigest() == data['outputSha256'])
    with tempfile.TemporaryDirectory() as t:
        py = os.path.join(t, 'sp505.prg')
        r = subprocess.run([sys.executable, os.path.join(root, 'patch.py'), official, '-o', py],
                           capture_output=True, text=True)
        check('patch.py ran', r.returncode == 0, r.stderr.strip())
        if r.returncode == 0:
            check('web result == patch.py result', open(py, 'rb').read() == bytes(out))
    import patch
    check('release', data['release'] == patch.RELEASE, (data['release'], patch.RELEASE))
    check('version', data['versionScreen'] == patch.VERSION_SCREEN, (data['versionScreen'], patch.VERSION_SCREEN))
    check('checksum', data['checksum'] == patch.CHECKSUM, (data['checksum'], patch.CHECKSUM))
    print('all ok' if ok else 'FAILED')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
