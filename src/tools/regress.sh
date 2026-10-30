#!/bin/bash
# Full emulator regression for the current build. usage: regress.sh prg module
P=$1; M=${2:-extrafirmware}
export IGN4025=1
fail=0
chk() { if echo "$1" | grep -q "differing 0\|: 0/\|blocks differ \[\]"; then echo "ok   $2"; else echo "FAIL $2 :: $1"; fail=1; fi; }
# 1. Normal pads untouched (ROM identical)
chk "$(OUTONLY=1 ENGMOD=$M python3 test_engine2.py $P --vari 0 --voices 4 --mixed | head -1)" "normal 4 voices"
# 2. engine at exactly 1.0x == ROM (rate codes 0/1/2, loops, stops, pairs, formats, pan/send)
for r in 0 1 2; do for o in "" "--loop" "--stop-at 30" "--voices 2 --mixed" "--voices 4 --mixed --loop" "--fmt 4 --nbytes 8" "--fmt 8 --nbytes 16" "--pan 2 --send"; do
  chk "$(RATE=$r OUTONLY=1 SAMEPAD=1 ENGMOD=$M python3 test_engine2.py $P --vari -1 --unity $o | head -1)" "unity rate $r $o"; done; done
# 3. two lower-grade notes staggered == ROM (no hand-over)
for r in 1 2; do for l in "" "--loop"; do
  chk "$(RATE=$r VOICES=2 STAGGER=13 python3 unity_vs_rom.py $M $P $l)" "two notes rate $r $l"
  chk "$(RATE=$r VOICES=3 STAGGER=13 NORMALK=1 python3 unity_vs_rom.py $M $P $l)" "two notes + normal rate $r $l"; done; done
# 4. time-stretch flagged voices with varispeed == single
python3 - $P $M <<'PY'
import sys, os; sys.path.insert(0,'.')
os.environ['OUTONLY']='1'
import cmp_builds as cb
bad=0
for semi in (-12, 7):
  for rate in ('0','1'):
    os.environ['RATE']=rate; os.environ.pop('STRETCH',None)
    A=cb.run(sys.argv[2], sys.argv[1], semi, True, 2, 150, 0)
    os.environ['STRETCH']='1'
    B=cb.run(sys.argv[2], sys.argv[1], semi, True, 2, 150, 0)
    n=sum(A[b][0]!=B[b][0] for b in range(150)); bad+=n
print(('ok  ' if bad==0 else 'FAIL'), ' stretch override (%d differing blocks)' % bad)
PY
# 5. speed accuracy incl. fine tune
for vf in "-24 -50" "-7 23" "0 1" "0 -37" "5 -37" "12 50"; do set -- $vf
  out=$(ENGMOD=$M VARI=$1 FINE=$2 EXACT=1 python3 test_speed.py $P | tail -1)
  v=$(echo "$out" | sed 's/.*region: \([0-9.]*\).*/\1/'); if python3 -c "import sys; sys.exit(0 if float('$v')<=3 else 1)"; then echo "ok   speed $1 st $2 ct (err $v)"; else echo "FAIL speed $1 $2 :: $out"; fail=1; fi; done
exit $fail
