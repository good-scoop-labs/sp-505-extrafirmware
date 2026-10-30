"""engine at exactly 1.0x (setting -1 with STEPTAB patched) vs the ROM playing the same notes as
Normal; outputs only. env: VOICES, STAGGER, RATE, BLOCKS, STOPAT, NORMALK. usage: mod prg [--loop]"""
import sys, os
os.environ['OUTONLY'] = '1'
import cmp_builds as cb
mod, prg = sys.argv[1:3]; loop = '--loop' in sys.argv
v = int(os.environ.get('VOICES', '1')); n = int(os.environ.get('BLOCKS', '300')); st = int(os.environ.get('STOPAT', '0'))
A = cb.run(mod, prg, 0, loop, v, n, st)
os.environ['UNITY'] = '1'
B = cb.run(mod, prg, -1, loop, v, n, st)
bad = [b for b in range(n) if A[b][0] != B[b][0]]
print('unity vs ROM: voices %d stagger %s rate %s loop %s: %d/%d blocks differ %s' % (v, os.environ.get('STAGGER', '0'), os.environ.get('RATE', '0'), loop, len(bad), n, bad[:6]))
