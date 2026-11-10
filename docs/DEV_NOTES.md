> Development log, kept as written during development. Build numbers here (v1 ... v32,
> `EXT Ver.V.01` ... `EXT Ver.V.26`) are internal steps; public release 2.0.0 (`EXT Ver.2.00`) is
> build v32 with its own version string. The project was called "SP-505 Varispeed" during
> development and was renamed SP-505 EXTRAfirmware for release.
> The builders named here (`build_engineNN.py`, one per internal build, each building on the
> previous one) were merged into the modules in `src/` for release; the result is the same
> firmware as build v32 apart from two unused leftovers of earlier builds (the v10-era pad set-up
> helper at 0x1D1000 and parameter hook at 0x1D1200), which are no longer written. "Result on hardware" lines are the tester's reports.

# SP-505 firmware notes (v1.02, "0042", Oct 24 2001)

## Hardware (from Roland service notes parts list)
- CPU: NEC uPD703102A-33 (V850E/MS1), IC33. Has 128 KB Roland mask ROM (-W04) at 0x000000-0x01FFFF ("CPU version" on the EXIT+ENTER screen). The ROM supplies low-level routines (flash erase/program, checksum, LCD text, delays). The SmartMedia updater logic itself lives in FLASH (see "Update process" below), not in the ROM.
- Program flash: Sharp LH28F800BJE (1 MB), IC36 -> mapped at **0x100000-0x1FFFFF**.
- Sound/effects engine: Roland/Toshiba **TC203C040AF "MR2"**, IC10, with its own DRAM (IC52).
- SmartMedia: card connector CN1; internal NAND MBM30LV0064 (IC29).

## sp505.prg format
| offset | contents |
|---|---|
| 0x000 | `BOSS SP505\0Ver.1.02\00042\0Oct 24 2001\0` |
| 0x040 | 16 x uint16 LE: byte sum (mod 65536) of each 64 KB block of the image |
| 0x080 | uint16 LE: `-(sum of the 16 words)` mod 65536 |
| 0x200 | 1 MB image, CPU address 0x100000 |

`sp505fw.py verify` checks this; `patch` / `effect-name` rewrite it. No other signature or
encryption. SMPINFO0.SP0 is a generic SmartMedia info file; copy it unchanged.

## Memory map seen from the code
- 0x000000-0x0FFFFF  CPU mask ROM (the app calls helper routines here, e.g. 0x5db0, 0x158cc)
- 0x100000-0x1FFFFF  flash (this image). Code ~0x13C000-0x1D0000; data/tables below.
- 0x200240-0x2003FE  16-bit peripheral registers (I/O gate logic)
- **0x3C00000-0x3C00005  MR2 host port (byte-wide)**: reg5 = bank select + addr bit 8,
  reg4 = addr low, reg0-2 = 24-bit data, reg3 bit 7 = busy. Driver: 0x158654-0x158d40.

## Effects
- Names: pointer table 0x120C7C (26 entries).
- Parameter records: 0x120EE0 (16-byte records: param id, name*, ...).
- **Algorithm table: 0x12B39C**, 27 x 20 bytes `{handler, dsp_start, dsp_end, program*, init_list*}`
  (entry 0 = OFF). Loader at 0x1A8114:
  1. (apparently) mute, then clear MR2 words 223..508 with the program at 0x12B5B8;
  2. upload `program*` (286 x 24-bit words, stored as uint32 LE) into MR2 words 223..508;
  3. apply `init_list*` ((addr, value) pairs, -1 terminated);
  4. the handler converts knob values to coefficients with lookup curves at 0x1330xx-0x136xxx
     and writes them with 0x1AC894 / 0x1AC8B0 (MR2 address, value).
- Pitch Shifter = entry 2 (prog 0x12C344, handler 0x1A8AB4).
  Chromatic P.S. = entry 24 (prog 0x132B20, handler 0x1ABAAC).
  Voice Transformer = entry 25. Center Canceler has no program (prog = 0).
- The OFF program and all 25 effect programs are exported in `dsp_programs/`.

## Update process (traced from the code) and brick risk
1. At power-on the *flash* app (startup code in block 12, ~0x1CE8xx) reads the buttons and,
   for SONG+PTN+BPM, disables interrupts and jumps to the card updater at 0x1EF63C (block 14).
2. Updater opens SP505.PRG and reads the 512-byte header. It refuses the file unless the
   header starts with "BOSS SP505".
3. Staging: blocks 0-14 are read from the card into DRAM one by one. Each block's byte sum is
   checked against the header table (one retry). **Any bad block aborts before flash is touched.**
4. It copies its own write loop (0x1EF000 block) into DRAM and jumps there. Erase, program and
   checksum calls go through RAM pointers to mask-ROM routines (0x4CE8, 0x15B60, 0x1684C,
   0x16880, 0x15D28, 0x158CC). Nothing in flash executes while flash is being written.
5. Blocks 0-14 (0x100000-0x1EFFFF) are written and verified. Block 15 (0x1F0000-, user/FAT
   area) is never written. The final header word at 0x80 isn't used by the updater.

Rules for safe custom builds:
- Keep the header's first 0x40 bytes intact, and always fix the checksums (`sp505fw.py` does).
- **Never modify block 12 (0x1C0000-0x1CFFFF: startup and button check) or block 14
  (0x1E0000-0x1EFFFF: the updater) unless there's no alternative.** If either breaks, the
  SmartMedia update path may be unreachable. Recovery would then need the MIDI update path
  (not yet analysed), a mask-ROM fallback (unknown), or a flash programmer on IC36.
- Power loss during step 5 remains the same risk as an official update.

## Test build v2 (test_build_card/)
Changes (data only, blocks 2 and 3; startup/updater blocks 12 and 14 untouched):
- effect 24 name "24 CHROMATIC P.S." -> "24 TEST FW OK"
- version-screen string "EXT Ver.1.02" (0x138AAB, used only by the EXIT+ENTER screen) -> "EXT Ver.T.01"
Version screen (EXIT+ENTER at power-on): the second line shows the flash checksum
(0 - byte sum of 0x100000-0x1EFFFF): original FA86B012, test v2 FA86B072.
Card update needs ALL THREE of SONG+PTN+BPM held at power-on. Holding only two of those keys
runs a different routine ("NOR --> CARD", "Copying ...") that copies the current firmware out
instead of loading a new one.

## Next steps
1. Flash the test build. If effect 24 shows the new name and works, the loader path and
   checksums are confirmed.
2. Decode the MR2 24-bit instruction set: diff the 26 programs, then make single-word
   patches to the OFF/bypass program and listen.
3. A new pitch effect = a new 286-word MR2 program + a handler (or reuse of an existing
   handler's parameter layout), dropped into one slot of the algorithm table.

## Tools
- `sp505fw.py`: verify / info / patch / effect-name / extract-dsp
- `tools/v850.py`: small V850E disassembler (`python3 tools/v850.py img.bin <offset> <count> 0x100000`)
- `tools/xrefs.py`: finds absolute-address references and call targets

## Sample playback findings (varispeed research)
- Parameter database: descriptors at 0x110364, 20 bytes per ID
  `{min i32, max i32, default i32, offset u16, size u8, class u8, ...}`. Getter: 0x16210C(id, pad).
- Per-sample record (class 4) holds IDs 0x25-0x3C. The ones that matter here:
  0x2C Play BPM (u16 @0x1C), 0x2D orig BPM (u16 @0x1E),
  **0x2E sample rate in 10 Hz units (u16 @0x20, 1102..4410)**, 0x2F format 4..8 (@0x22),
  0x30 Level, 0x32 Pad Play, 0x33 Loop, 0x34 Reverse, 0x37 Pan, 0x38 Play Type, 0x39 Beat,
  **0x3A-0x3C: 0..127, default 0, never read through the getter: likely spare** (@0x2D-0x2F).
- Sample parameter menu table: 0x11F55C, 12-byte entries {param id, label*, value-text*}
  (Level, Panpot, Pad Play, Loop Mode, Reverse, Play Type, Measure, Beat). Handler ~0x193960.
- At playback setup the rate is collapsed into a code at offset 136 of a 156-byte per-pad record
  (4410->0, 2205->1, 1102->2). The streaming code uses it for byte-size math (divide by 1/2/4).
  The final decode/mix/rate stage isn't in the flash code (likely CPU mask ROM, or an MR2
  program in addresses 0-127 loaded by the ROM).
- Samples are stored compressed (block sizes 504/510/512, param 0x2F).

## Test build v3 (test_build_v3_rate_experiment/): EXPERIMENT
v2 changes plus the playback rate-code mapping, at the 4 sites that read param 0x2E for pads
(0x1BA1A8, 0x1BC904, 0x1BCD58, 0x1BF0C8: `addi -2205` -> `addi -4410`):
44.1 kHz samples get code 1 ("half rate"), 22 kHz samples get code 0, LO-FI unchanged.
Version screen: "EXT Ver.T.02", checksum FA86AF09. Only block 11 code changed (plus data in
blocks 2 and 3). Recording/resampling paths are untouched.
Result on hardware: STANDARD samples played an octave lower AND slower, so the rate code
drives true varispeed in the playback engine.

## Test build v4 (test_build_v4_rom_dump/): dump CPU mask ROM to card
v2 changes (normal playback) plus 3 operand changes in the "NOR --> CARD" routine
(0x1EF1F4, reached only through the two-key power-on combo; card-updater code is
byte-identical):
- 0x1EF29E movhi 0x1 -> 0x2 (file size 128 KB)
- 0x1EF2C0 movhi 0x1F -> 0x0 (source = address 0x000000, mask ROM)
- 0x1EF2C4 movhi 0x1 -> 0x2 (length 128 KB)
- "Copying FAT..." text -> "Copying ROM..."
The first file (FILE_FAT.SP1 or similar) then holds the 128 KB CPU ROM. The other two files
are unchanged (4 KB updater stub, 896 KB program).
Version screen: "EXT Ver.T.03", checksum FA86B07A.
Two-key combo for the "NOR --> CARD" routine (confirmed by user): SONG + BPM/TAP at power-on.
(The card updater is SONG + PTN + BPM.)

## CPU mask ROM (dumped with v4: rom_dump/cpu_mask_rom_v1.00.bin, 128 KB)
Header "BOSS SP505 Ver.1.00 May 16 2001". Version-screen ROM checksum FF27888D.
- Reset 0x1580C: sp=0x3FFEFF8, tp=0, gp=0x437000 (DRAM at 0x400000), ep=0x3FFE000 (internal RAM).
- Boot 0x17238: if flash 0x100010 == "BOSS SP505" -> jump to flash 0x100600, otherwise run the
  ROM's own updater (0x17528; "CARD UPDATER" / "MIDI UPDATER").
  So a damaged block 0 header falls back to a ROM recovery updater. Damage elsewhere does not.
- Most interrupt vectors forward to the flash table at 0x100140+. The ROM handles 0x240 (audio
  render, 0x6A6C), 0x2B0 (DMA ping-pong swap, 0x6A00) and a few others.

## Audio engine (ROM, audio interrupt 0x6A6C)
- First calls a flash hook through the pointer at ep+4004. Normally 0x1B345C, which does the
  mono-mode L/R average on the *previous* output block ep[2964].
- 0x6AF8: input monitoring into the current output block ep[2976] (16 frames x 16 bytes).
- 0x96FC: voice loop over 8 voice records at ep+1020 (208 bytes each). Each voice has a
  32-byte decoded buffer at ep+2700+32*v, refilled by the decoder at ROM 0x1A30.
  Mix kernels are unrolled and fixed-ratio (sample repetition, no interpolation):
  1:1 (0x9814/0x9958), 1:2 (0x9D84/0x9E80), 1:4 (0x9B3C/0x9C10). Kernel choice comes from
  voice bytes 139/140, set up from the pad rate code (pad record +136).
- Flash voice setup: 0x1BBFE0/0x1BC090 (fields 158/164 = 276/6, 138/3, 69/2 per rate code).
=> Continuous varispeed can't come from ROM kernels. It needs a custom resampling mixer in
   flash, e.g. run from the ep+4004 hook and mixing a varispeed voice into the just-rendered
   block ep[2964] (one block, 0.36 ms, of extra latency), with that voice muted in the ROM path.
   Octave-down steps (-1, -2 octaves) are possible now through the existing 1:2 and 1:4 kernels.

## Build v5 (build_v5_varispeed_octave/): per-sample Varispeed (octave steps)
Made by `build_octave.py` from the original 1.02 image (no test changes carried over).
- New row 9 in the sample parameter menu: **Varispeed: Normal / -1 Oct / -2 Oct**.
  Menu table copied to 0x1D1100 (pointer at 0x19398E), row count 8 -> 9 (0x1939B2, 0x193B8C).
  Labels at 0x1D1180 / 0x1D1190 (7-byte value slots).
- Stored in spare per-sample parameter 0x3A (sample record byte +0x2D). Descriptor max
  127 -> 2 (0x1107F0). Edited through the generic param path (0x183AC0 -> setter 0x1C34B4).
- Helper at 0x1D1000 (92 bytes) replaces get_param(46, pad) at the 3 pad-playback setup sites
  (0x1BA192, 0x1BC8EE, 0x1BCD42). It returns a rate value whose playback code is
  base code + octave setting (clamped to 2). The ROM then plays the sample through its
  1:2 or 1:4 kernel.
  The recording/resample site (0x1BF09C, system param 225) is untouched.
- Version screen "EXT Ver.P.01", checksum FA87600C. Blocks changed: 1, 3, 9, 11, 13.
  Blocks 0, 12 and 14 are untouched.
- Open questions for hardware testing: does the change apply immediately or only after the
  pad records are rebuilt (bank change / power cycle)? Does the value persist after power-off?
  Does the whole sample play when slowed?
Result on hardware (v5): menu works, value persists, and after a power cycle the sample plays
at the chosen octave. The change just didn't apply live.

## Build v6 (build_v6_varispeed_live/): v5 + live update
- Parameter-set messages (type 5) reach the audio task at 0x1B2810, which calls the handler
  0x1BA884(pad=r6, id=r7, value=r8). The firmware itself updates pad record +136 there when
  the sample rate (id 46) changes (0x1BAFB8..0x1BB008), with no reload.
- v6 replaces the handler's first instruction (prepare {0x7ff},8) with `jr 0x1D1200`.
  The intercept code at 0x1D1200 (136 bytes): if id == 58 and 0 <= pad <= 511, it computes
  code = base(rate) + value, clamped to 0..2, and stores it at gp+0x20000-720 + pad*156 + 136,
  then returns. Any other id runs the original prepare and jumps to 0x1BA888.
  The handler's only caller is 0x1B2820.
- Version screen "EXT Ver.P.02", checksum FA87B9DA. Blocks changed: 1, 3, 9, 11, 13.
Result on hardware (v6): works. A change applies on the next trigger of the pad. A note that's
already playing keeps its old speed, which is expected because the voice's speed is set when it starts.

## Build v7 (build_v7_measure/): v6 + CPU idle meter
- RTOS (in ROM): task table at 0x100700 (11 x {entry, stack, TCB, ?, 0, prio}). The
  lowest-priority task 0x1CE508 finishes start-up and then spins in `br 0x1CE556`: the idle loop.
  System tick counter at 0x3FFE02C, incremented by the ROM tick handler 0x6576/0x6588 (vector 0x290).
  Task delay = ROM 0x6676.
- Start-up order: power-on button check (incl. card updater) runs before the kernel starts
  (0x1CE908 -> ... -> jarl 0x5958), so idle-task code can't block the SmartMedia updater.
- v7 changes 0x1CE552 `jarl 0x5DB0` -> `jarl 0x1D1300` (block 12, 4 bytes, idle task only).
  0x1D1300 makes the original call, then counts loop iterations per 500-tick window.
  % = cur*100/best window. min = lowest % after the first 10 windows.
  Values go to sample record bytes +0x2E/+0x2F (params 0x3B/0x3C) for records 0..127.
- Sample menu: 11 rows (table 0x1D1400): ... Varispeed, "Idle %", "Idle min" (numeric).
- Version "EXT Ver.M.01", checksum FA88728A. Blocks changed: 1, 3, 9, 11, 12 (4 bytes), 13.
- Side effect: the meter values get saved into unused bytes of internal sample records.
  Harmless, and a later build can clear them.
Result on hardware (v7): idle% = 99 (none), 90 (1 voice), 65 (4), 25 (8), 35 (8 voices, two at -1 Oct).
Idle min 20. A voice costs about 9% at normal speed and about 4.5% at half speed, so cost scales with
source data rate (decode/stream dominates; mixing is small).

## Full-varispeed design (recommended: -24..+12 semitones + load guard)
Voice data flow (ROM audio ISR, per voice record ep+1020+v*208):
- Decoder ROM 0x1A30(desc=voice): +0 = output (16 samples -> ep+2700+v*32), +8 = input ptr into a
  ring buffer (+12 mask), +16 = format (4..8). 0x404 / 0xF1A are decoder variants.
- After each decode the ROM does +24 += +137 (frames), +36 += +143 (bytes). It then checks the
  ring-segment boundaries (+56..+112, state index +145 0..13). When it crosses one, it marks segment
  flags (+116..+129: 1 = free, 2 = in use) and ORs the voice bit into ep[4025]. At ISR end this wakes
  the streaming task (set_flg 0x5E90), which refills the freed segment. Streaming is demand-driven.
- Kernel selection: +133 state (0/3/other: fades), +134 (+8 = effect send), +140 (pan routing),
  +139 rate code (0 = 1:1, 1 = 1:2, 2 = 1:4), +151 phase for slow rates, +136 volume.
  Masks: ep[4021] active, 4022/4023/4028 state changes, 4026, 4027 stop.
- Output block ep[2976]: 16 frames x 16 bytes {L, R, sendL, sendR} as int32. ep[2964] = INPUT (ADC) block.
Injection point: the ROM has no post-render hook. The start-of-ISR hook (ep+4004) can redirect the
ISR's final `reti` (EIPC/EIPSW saved at ep+876/880) to our own routine. That routine runs after the
whole block is rendered and before it plays (v8 proves this).
Planned engine: varispeed voices are removed from the ROM's active mask and rendered by us in the
post-render routine. Per block: fractional read position, calling the ROM decoder for each 16-sample
chunk crossed, with the same position/segment bookkeeping and 4025 notification as the ROM, then
linear interpolation, volume and pan routing like the ROM kernels. Load guard: estimate cost
(about 9% x speed + mixer per voice) and steal the oldest voice when over budget.

## Build v8 (build_v8_postrender_proof/): post-render injection proof
v7 + start-of-ISR hook at 0x1D1600 (installed by patching 0x1BB672: tp+0x1D1600 replaces the mono
hook; it chains to 0x1B345C) + post-render routine at 0x1D1680. Shared words at 0x426D00 (bottom of
the idle task's stack). PROOF EFFECT: right channel (dry and send) zeroed in every block.
Version "EXT Ver.R.01", checksum FA88F36E.
Result on hardware (v8): post-render injection WORKS (audio was modified after ROM rendering).
(Correction after v9: the user's stereo was wired swapped. The frame is {L, R, sendL, sendR}.)
"Too Busy!" appeared while hammering many pads. That's stock error code 2 (message 17): UI event 97
(post_error 0x1A16C0). It's raised by background tasks through the error-bit word gp-10556
(set in 0x1C4A60, dispatched at 0x1C4554 via table 0x138350). Most likely streaming overload.
Our added cost is about 0.1% per block (post-render) and nothing outside idle (meter).
To confirm: compare the same abuse on v6 or the original firmware.
Result on hardware: v6 under the same pad abuse showed NO "Too Busy!". v8 did, and afterwards pads
stopped triggering until a restart. So v7/v8 caused it.
Root cause (most likely): POST returned with a plain `reti` while PSW.EP=0. On V850E that's an
*interrupt* return, which clears the highest in-service (ISPR) bit. The ROM's reti had already
cleared the audio interrupt's bit, so whenever the audio ISR had nested inside another ISR, POST
cleared the OUTER handler's in-service bit, corrupting interrupt priority state under load.
(No dirty-compare of sample records exists, so the idle meter's record writes are unlikely to matter.)

## Build v9 (build_v9_postrender_fixed/) and v9b (build_v9b_postrender_fixed_nometer/)
- POST now sets PSW.EP before its final reti, making it an exception return (PC/PSW from
  EIPC/EIPSW, ISPR untouched).
- Test effect now mutes frame words +0/+8 (believed RIGHT). Expect LEFT-only audio.
- v9 = v7 (meter) + fixed hook. "EXT Ver.R.02", checksum FA88FB94.
- v9b = v6 (no meter, block 12 untouched) + fixed hook. "EXT Ver.R.2b", checksum FA8842B6.

Result on hardware (v9): no "Too Busy!" under the same abuse. With correct headphones, muting +0/+8
leaves only the right side, so the frame is {L, R, sendL, sendR}. Pan byte +140: 0 = both words,
1 = +0 (L), 2 = +4 (R).

## Build v10 (build_v10_engine_stage1/): varispeed engine, stage 1
build_engine.py. Base = original v1.02 (v6's rate-code octave trick removed) + idle meter.
- Varispeed row values: Normal (ROM plays it), "E 1.0x" (our engine at normal speed, should
  sound identical), "E 0.5x" (our engine at half speed, interpolated).
- VTAB (RAM 0x428400, 512 x u32 = 0x5AC3<<16 | value) per pad: written by helper 0x1D1000 at the
  3 pad set-up sites (rate returned unchanged) and by the param-handler intercept 0x1D1200 (id 58).
- RAM 0x427004-0x42FFFF is unreferenced (stacks end at 0x427000 with the "STK:" canary word;
  gp data starts at 0x430000). Engine uses 0x428000-0x42A000:
  +0 owned, +1 taken, +2 finished, +4 magic 'VARI', +8 saved sp, +0x20 per-voice {P, step},
  +0x100 per-voice x-buffer (x[0] = last sample of previous chunk, x[1..16] = chunk), +0x400 VTAB,
  0x429000-0x42A000 POST's private stack.
- HOOK 0x1D1600 (start of audio ISR, ints enabled; ROM saved r1,r6-r29,ep,lp to ep+888..):
  v9 redirect + take-over: on a pending note start (4023) of an eligible voice (active, not
  4026/4027, +148 == 0) whose pad (slot gp+0x30000+13928+v*64, +10) has VTAB value 1/2, the voice
  becomes owned; step = (0x20000 >> value) >> rate code(+139). Owned voices are removed from 4021
  for this block. Not eligible any more -> released to the ROM.
- POST 0x1D2000: quick exit if nothing taken. Else: save sp, switch to own stack, save regs,
  mask render IC (0xFFFFF138 bit 6) and dispatch IC (0xFFFFF13A bit 6, RTOS dispatch request,
  set by 0x6888/0x5F28), ei. Per owned voice: requests as ROM 0x971E, output pointer
  (send +8, pan), then one of 3 loops (steady single, steady both, fade/silent) with linear
  interpolation, ROM-identical volume/envelope math. Chunk advance (ADV) when P > 16.0:
  x[0] = x[16], BOOK (ROM 0xADBE..0xB0EA: +24 += +137, end-4 -> 4028, end -> finish or loop
  restart, +36 += +143 and segment switch / wrap, 4025 notify), DEC (ROM decoder 0x1A30 with
  output -> x[1..16]; saves all regs, the decoder clobbers r10 etc.). After all voices: di,
  4021 |= taken & ~finished, unmask, restore, exception-return as v9.
- ROM decode-format table (0x1A44 switch on +16 - 4): 4 = 8 bytes/chunk, 5 = 10, 6 = 12, 7/8 = 16.
- The playback start function is 0x1B6EBC (sets up voice records, ends with 4023|4021|4025 and
  set_flg). 0x1B6244 is a stop (clears 4021, sets 4022|4028).
- Emulator: tools/v850emu.py (V850E1 subset) + tools/test_engine.py runs one voice through the
  ROM's own voice loop (0x96FC..0x10FB4) and through POST and compares every output block and
  mask byte. Result: bit-exact at 1.0x for whole note lifetimes (fade-in, steady, end-4 fade-out,
  end), with loop, pan 0/1/2, send, stop requests, and 3 voices mixed ROM/engine. 0.5x: smooth,
  ends after twice as many blocks.
- Cost in emulated instructions per voice-block: ROM ~370, engine ~540 + ~140 fixed when any
  engine voice is active (20 when none). So an engine voice costs about 1.5x a ROM voice at 1.0x.
- Version "EXT Ver.V.01", checksum FA8D91CE. Blocks changed: 1, 3, 9, 11, 12 (4 bytes), 13.
- Known stage-1 limits: setting applies at the next trigger; reverse / time-stretch / recording
  voices stay with the ROM; at speeds above 1x the end fade would be cut short (stage 2).

Result on hardware (v10): random pops/crackles with E 1.0x and E 0.5x; two engine voices at once
-> freeze and "Too Busy". Diagnosis: the engine executed from external flash (16-bit bus, wait
states, no cache) while the ROM's kernels run from internal ROM; per-instruction cost is several
times higher, and v10's POST also saved/restored ~60 registers and ~50 more per decoded chunk.
One voice ~ a large fraction of the 363 us block; two voices overload, tasks starve (streaming ->
"Too Busy"). Bus config found: BSC (0xFFFFF066) = 0x4555 (16-bit areas), DWC never written (reset
default = max data waits), DRAM controller set at ROM 0x1573C (0xFFFFF200 = 0x9542, refresh
0xFFFFF210 = 0x803F). Internal RAM (4 KB) is fully used by the ROM/RTOS. Output blocks are in
internal RAM (ep+3492 / ep+3748), input blocks ep+2980 / ep+3236 (set at 0x1BA698).
Also: v10 raised 4025 (streaming wake-up) only after the ROM epilogue (one block late) and decoded
the next chunk one task-time-slice earlier than the ROM. Both fixed in v11.

## Build v11 (build_v11_engine_lean/): lean engine, load guard
build_engine2.py. RAM code image (4.5 KB) stored at flash 0x1D2000, copied to DRAM 0x42A000 by the
idle task at start-up (0x1D1300: original call, zero ENG, copy, READY word 'REDY' at ENG+4, then the
meter). Flash stubs: HOOK 0x1D1600 (v9 redirect, then jmp 0x42A000 if READY), POST 0x1D1700
(quick return unless READY and taken != 0, else jmp to RAM POST).
- All engine work in the RAM HOOK (start of the audio ISR; ROM has saved r1, r6-r29 -> no saving;
  lp kept at ENG+16): take-over over set bits only, then per taken voice: requests, route, decode
  due (ROM timing), 16 unrolled frames (ep temporarily = y buffer, sst.h), ADV/ADVL chunk advance
  (ADVL defers the next decode to the next block, as the ROM), envelope finalize.
  Output y[16] (s16, after volume/envelope) in the voice's own ROM decode buffer ep+2700+v*32.
- Decoder 0x1A30 clobbers exactly r7-r25 (emulator, all formats); keeps r1, r2, r6, r26-r29, ep, lp.
  DECW saves r8-r11, r17, r18, r20, r23-r25, lp to ENG+0x20.
- RAM POST: save r11-r16, ep; mask render/dispatch IC; ei; overrun check (ep[2976] still the block we
  rendered?). Overrun -> count at ENG+12, skip mixing, stop the oldest engine voice (serial numbers
  at VS+12) like a ROM end (4029, clear 4022/4028/4023, not given back). Else mix y of ready voices
  with ep = output block (sld.w/sst.w). Then 4021 |= taken & ~finished, unmask, return.
- Interpolation: frac15 = (P << 16) >> 17, d = (x1 - x0) >> 1, y = x0 + mulh(d, frac15) >> 14.
  Bit-exact at 1.0x (frac = 0); within 0.5 LSB of ideal linear interpolation at 0.5x.
- Menu: "Idle %" and "Overruns" (replaces Idle min).
- Emulator tests (tools/test_engine2.py, test_speed.py): bit-exact vs ROM for 1, 3, 8 voices,
  loop, pan 0/1/2, send, stop; overrun guard stops the oldest voice.
- Emulated cost (instructions per block, 1 voice 1.0x): v10 795 from flash; v11 ~770 from DRAM
  (of which ~300 per-frame interpolation, ~110 mixing), plus the ROM decoder (internal, fast).
  Per extra voice ~650. Whether DRAM fetch is faster than flash is unknown: measure with Idle %.
- Version "EXT Ver.V.02".

Result on hardware (v11): samples didn't trigger, the unit froze.
Cause: v11 moved ep (to the y buffer during the unrolled frames, to the output block during mixing)
while interrupts were enabled. The ROM's own ISRs (DMA ISR 0x6A00: st.w r1, 884[ep] ...) assume ep
is always 0x3FFE000, so any interrupt in those windows wrote into the wrong internal-RAM addresses.
RULE: never change ep while interrupts are enabled (hook and POST both run with ei).
tools/test_engine2.py now fails any run where ep != 0x3FFE000 while PSW.ID == 0.

## Build v11b (build_v11b_engine_fixed/): v11 without ep tricks
y stored with st.h k[r28], mixing with ld.w/st.w k[r14]. RAM code moved to 0x428C00-0x429EA4 (inside
the 0x428000-0x42A000 area v10 already used). All emulator tests pass (1.0x bit-exact incl. 8 voices,
Normal pads untouched, 0.5x within 0.5 LSB, overrun guard). "EXT Ver.V.03".

Result on hardware (v11b): Normal pads fine. One E 1.0x or E 0.5x pad: Overruns count up and the
voice stops right away (the guard). So even ONE engine voice did not finish within a block.
Also explains v10's pops (late blocks). Conclusion: external-memory code is far slower than
estimated (roughly 10 clocks per instruction or worse), and DRAM execution may be slower than flash
(code and data in DRAM -> page misses).

## Build v12 (build_v12_measure_engines/): measurement build
build_engine3.py. Same engine, two copies: executed in place from flash (0x1D2000) and from DRAM
(image at flash 0x1D4000, copied to 0x428C00). Varispeed values: Normal, F 1.0x, F 0.5x (flash
engine), R 1.0x, R 0.5x (RAM engine); the most recently started engine note picks the location
(ENG+0x1B), the hook/POST stubs jump accordingly.
Timing meter "Audio %": the output DMA's remaining-transfer count DBC0 (0xFFFFF1E0, from the DMA
set-up at 0x1BA6F0: DSA0 F1A0/F1A2, DDA0 F1A4/F1A6 = 0x200000, DBC0 F1E0, DADC0 F1F0, DCHC0 F0F0;
channel 1 = input) is read at the hook and at the end of POST (POSTEXIT 0x1D1780). Elapsed share of
the block = (count at hook - count now [+ block if the DMA already swapped]) / (max count + 1).
The maximum per idle-meter window is shown (capped at 127; >100 = overrun). Guard: stop the oldest
engine voice only after 8 overruns in a row (mixing continues during overruns).
"EXT Ver.V.04".

Result on hardware (v12): Normal pad and F/R 1.0x / 0.5x all "Audio 18%", Overruns 0, but the engine
voices crackle constantly ("like the vinyl sim effect"). 0.5x is a correct octave down. Later: Audio %
stays 0 with 8 Normal pads -> the DBC0 read-back meter is not valid (don't trust it).
Sample: mono, "Standard" mode, internal memory. v11b: Overruns jumped the moment an E pad was hit.
So: no measurable overload (the overrun check also works when the DMA ISR is held off, because POST
re-enables interrupts before checking). The crackle is NOT a CPU problem. Emulator: engine is
bit-exact vs the ROM for all decoder formats 4..8.

## Build v13 (build_v13_diagnostic/): which part makes the crackle?
build_engine4.py (flash engine only). Varispeed values:
- E 1.0x / E 0.5x: engine as v12 (control).
- D-ROM: the ROM decodes and does all bookkeeping itself; the hook only sets the voice to state 0
  (silent) for steady blocks without pending requests, and POST mixes the ROM's own decode buffer
  (rate code c: buf[base + (f >> c)], base = phase-before * (16 >> c)), then sets state 3 back.
  Emulator: identical to the ROM for rate codes 0, 1, 2.
- E-noEI: engine 1.0x, but POST runs with interrupts disabled and no IC masking.
Interpretation: D-ROM crackles -> mixing from POST itself is the problem; D-ROM clean but E crackles
-> my decode/bookkeeping path; E-noEI clean while E crackles -> the ei/masking in POST.
"EXT Ver.V.05".

Result on hardware (v13): Normal clean; E 1.0x crackles loud; D-ROM crackles soft; E-noEI clean.
=> The crackle came from POST re-enabling interrupts (ei with the render/dispatch ICs masked).
Exact mechanism not identified; D-ROM (ROM data, POST mixing with ei) also crackled, so it is the
ei window itself, not the engine's data path. POST is now short (mixing only) and runs with
interrupts disabled throughout.

## Build v14 (build_v14_semitones/): stage 2, semitone varispeed
build_engine5.py (flash engine, POST without ei). Varispeed values: Normal (ROM), -24 .. +12
semitones (0 = engine at normal speed). Param 58 range 0..37; value names at 0x1D1A00 (7-byte
slots), step table at 0x1D1C00 (round(65536 * 2^(st/12)), shifted by the rate code at take-over).
Above normal speed the fades use envelope step +-4 (half length) so the end fade fits in the
4 chunks the ROM's end-4 trigger leaves. If the sample end is still reached while audible, the
engine holds the last sample (P = 0, step = 0) and requests the fade-out instead of cutting.
Menu: Idle %, Overruns. Emulator: bit-exact vs ROM at 0 st (all tests), interpolation within
2 LSB of ideal at -24/-12/-7/+6/+12 (using the table step), clean endings at all speeds.
"EXT Ver.V.06".

Result on hardware (v14): one sample perfect (no crackle). Many samples at once: one voice got
stuck, repeating static, and the sampling-source LEDs flickered. Most likely cause: POST (now with
interrupts disabled) grew with the number of engine voices (16 frames x every voice), blocking other
interrupts (panel / NAND / serial handling) for too long.

## Build v15 (build_v15_short_post/): constant, short POST
build_engine6.py. Every engine voice is now added into one accumulator (ENG+0xD00, 16 frames x
{L, R, sendL, sendR} int32) inside the hook (interrupts enabled, inside the ROM's render ISR); a
used-words mask at ENG+0x1E. POST only adds the used words of the accumulator into the output block
and clears them: at most 4 x 16 x 5 instructions, independent of the voice count (2 words for
normal stereo use). The overrun-steal path also mixes/clears. Idle init clears the accumulator.
Emulator: bit-exact vs ROM incl. 8 voices with mixed pan/send, retrigger/steal of an engine
voice, loops, stops, overrun guard. "EXT Ver.V.07".

Result on hardware (v15): even one varispeed pad makes the UI slower and sometimes delays triggers;
many pads lock everything with clicks/static. => The CPU cost IS real: code in external flash is
several times slower per instruction than the ROM's internal code; one engine voice takes a large
share of the CPU. The overrun detector is blind since POST runs with interrupts off (the DMA ISR
that would swap ep[2976] can't run before POST finishes), and v12's Audio % meter was invalid.
Options given to the user: (1) one varispeed note at a time + bake pitched copies with the
SP-505's own resampling, (2) cheaper drop-sample engine, (3) background "bake" into sample memory.
User chose (1).

## Build v16 (build_v16_one_note/): one varispeed note at a time
build_engine7.py = v15 + note cap: voices taken over in this block are recorded at ENG+0x1F; if any,
all older engine voices are released to the ROM with 4022|4028 set (the ROM fades them out at normal
speed in ~1.5 ms and ends them) and only the new note stays engine-owned. A stereo sample's two voices
start in the same block, so they count as one note. Emulator: hand-over works (old voice ends
within 3 blocks), stereo pair both owned, all identity tests still bit-exact. "EXT Ver.V.08".

Result on hardware (v16): even one voice now triggers slowly / stutters (v14 single voice was
perfect). Cause: v15's accumulator design adds DRAM accumulate work per frame (+~3 instructions per
frame per word) plus a longer POST; v14 was already near the CPU limit with one voice.

## Build v17 (build_v17_one_note_v14base/): v14 + one-note cap
build_engine8.py = build_engine5 (v14: per-voice y buffer in internal RAM, POST mixes per voice,
interrupts off) + the v16 note cap (ENG+0x1F; older engine voices handed to the ROM with
4022|4028). With the cap there are at most 2 engine voices (a stereo pair), so POST stays short.
Emulator: same results as v14 plus hand-over. "EXT Ver.V.09".

Result on hardware (v17): "error busy" with one varispeed sample plus two normal ones.

## Build v18 (build_v18_rom_mix/, build_engine11.py; intermediate steps build_engine9/10): ROM-mix
Big restructure to move per-sample work back into the ROM:
- No-op decode: the ROM's decoder 0x1A30 dispatches with `switch (fmt-4)` from table 0x1A44. Format
  3924 reads entry at 0x38E4 -> target 0x269A = `jmp [lp]` (found by scanning the mask ROM). With
  +16 = 3924 the ROM's per-block decode does nothing and it mixes whatever is in ep+2700+v*32.
- The engine voice is no longer hidden from the ROM. In the hook the engine streams the sample itself
  (DECW/BOOK on the real fields), writes 16 >> c raw interpolated samples into ep+2700+v*32 (c =
  sample rate code: 22k/11k samples need only 8/4 per block, the ROM's 1:2 / 1:4 kernel repeats them
  exactly as for normal playback), then patches the fields: +16 = 3924 and +151 = 0 always; for
  c = 0 also +32 = 0x7FFFFFFF, +36 = 0x7FFF0000, +137 = +143 = 0, +145 = 5 (makes the ROM's
  bookkeeping a no-op; for c >= 1 the ROM skips bookkeeping itself because +151 becomes 1).
  The ROM does requests, fades, volume, pan, send, mixing and the fade-out end of the voice.
  POST (interrupts off) restores the fields. If nothing was patched, the hook undoes the
  post-render redirect so POST doesn't run at all.
- Bookkeeping after the last frame of a block is deferred to the next block start (P bit31), like
  the ROM; first decode flag P bit30. Per-voice cache (VS stride 64): +32 record, +36 x buffer,
  +40 ROM buffer. XB moved to ENG+0xC00.
- Take-over scan only runs when a note start is pending.
- One varispeed note at a time (newest wins, older handed to the ROM with a fade-out).
- Emulator: output bit-exact vs ROM at 0 st for rate codes 0, 1, 2 (incl. stops, loops, pan, send,
  formats 4..8, stereo pairs); only 4025/4028 snapshot timing differs by one block (same audio).
  Interpolation within 2 LSB of ideal. Endings clean at -24..+12; fields restored.
- Flash instructions per block (emulator), one voice at -7 st: v17 822 (Hi-Fi) / 798 (22k);
  v18 550 (Hi-Fi) / 354 (22k) / 270 (11k). Idle overhead 133 -> ~50.
"EXT Ver.V.12".

Result on hardware (v18): one varispeed pad + a couple of normal pads OK; many Normal pads alone
-> "Too Busy!". Asked for the menu to be centred on Normal.

## Build v19 (build_v19_centred_menu/, build_engine12.py): centred menu + lower idle cost
- Param 58 is now a signed byte: descriptor 0x110364+58*20 min -24, max +12, default 0, signed flag
  (+16) = 1. The ROM getter 0x16210C, edit path 0x183AC0 (clamp 0x5330 is signed) and writer
  (0x161050) all honour the signed flag; verified in the emulator (0xE8 -> -24, 13 -> default 0).
- Menu prints names[value] at table ptr + value*7 (0x1938E4), so the pointer goes to the middle
  entry: names -24..-1, "Normal", +1..+12 at VALUES2, ptr = VALUES2 + 24*7.
- Engine take-over sign-extends the VTAB byte and indexes STEPTAB[v+24]; 0 and out-of-range = ROM.
  Old v18 settings (stored 1..37) are NOT compatible: 1..12 now read as +1..+12, 13..37 as Normal.
- Hook stub exits straight to the ROM unless (owned | 4023) != 0; only then sets the post-render
  redirect and runs the engine. Idle cost per block: v18 61 flash instructions -> v19 10.
- Load meter removed (idle task back to `br .` after init), menu back to 9 rows.
- Tests: Normal 4 voices identical; identity at 1.0x (test hook --unity patches STEPTAB) bit-exact
  for loop/stop/pairs/formats 4..8/pan/send; speed accuracy unchanged from v18.
"EXT Ver.V.13", checksum FA903AAA.
Also packaged build_stock_v102_for_comparison/ (the untouched v1.02 file) for a Too-Busy A/B test.

Result on hardware (v19): no "Too Busy" with many Normal pads any more. 1 varispeed loop + 3 Normal
loops: slower setting -> menu a bit slow; faster setting -> menu a lot slower; no Too Busy at all.
Profile (tools/prof19.py, one Hi-Fi engine voice, flash halfwords fetched per block):
-12 st ~765, +12 st ~952 (frames 340, stubs+POSTEXIT 103, POST restore 94, patch 67, cap/take-over
~55, DECW 33..134, BOOK 17..69). Flash work only +25% from -12 to +12; the bigger difference for
fast settings is probably streaming: the voice reads sample data 2x as fast (like an extra pad) and
the ROM decodes 2 chunks per block. Possible trims: shorter stubs/POST path, DECW without the 11-reg
save (reload loop state from VS), cheaper per-frame index math; half-rate output for <= -12 st.

## Build v20 (build_v20_trimmed/, build_engine13.py): same sound as v19, less work per block
- Hook stub: idle check first, READY only when active, engine entered with r12 = ENG.
- Post-render redirect set at the end of the hook and only if a voice was patched; it points
  straight at the engine POST (flash POST stub and POSTEXIT gone). Interrupted PC/PSW kept at
  ENG+0x388/0x38C.
- Hand-over: undo list at ENG+0x280 (32 bytes per patched voice: rec + record words +16 +32 +36
  +136 +140 +144 +148; rec = 0 terminates; write pointer ENG+0x18). POST copies the words back.
  Mask-ROM scan: no stores into a voice record at the other bytes of those words during the ISR
  (st.w at 136..148 only in accumulator clears / struct copies).
- DECW: no register save; decoder keeps r1, r6, r26-r29; VS pointer now in r26; after the decode
  P, step, x buffer, voice index (VS+44) and lp (VS+48) are reloaded; direct jarl 0x1A30.
- Frames: per block, if P + n*step <= 16.0 an unrolled copy without the crossing test runs.
- Tests: unity bit-exact vs ROM for rate codes 0/1/2 (RATE env in test_engine.py), loops, stops,
  pairs, 4 voices; tools/cmp_builds.py: v20 identical to v19 block by block (outputs, masks, whole
  voice records) at -24..+12, rate codes 0..2, loops, stops, staggered starts with hand-over, a
  Normal voice mixed in. Per-block record state at unity identical to v19 (RECCMP=1).
- Flash halfwords per block, one Hi-Fi voice (tools/prof19.py): -24 734->622, -12 765->652,
  -1 819->704, +7 886->752, +12 952->799 (about 15% less). 22k: -12 509->459; 11k 411->370.
"EXT Ver.V.14".

Result on hardware (v20): 3 Normal loops + 1 varispeed loop fine; varispeed loop + spamming many
other pads -> "ERROR!!! Too Busy!" and playback stopped. User suggested counting a varispeed voice
as several voices of polyphony.

## Build v21 (build_v21_voice_weight/, build_engine14.py): varispeed note counts as 4 voices
Pad voice allocator 0x1BDCDC: slot lists at gp+0x30000+14440 + state*8 (head, count): 0 free,
1 playing/stealable (14448/14452), 4 marked for steal (14472/14476), 5 releasing (14480/14484),
6 (14488/14492) new. steal = needed(1 mono / 2 stereo) - free - releasing; 0x1BC3C4(steal, flag)
moves the oldest stealable voices to list 4 (fails -> note refused); they get 4022 (fade out) and go
to list 5; silent list-5 voices return to the free list; the new note takes the free head.
Patch: 0x1BDD28 (movhi 3,gp,r1; ld.w 14444[r1],r10) -> jarl VOICEHELP (0x1D1700) + 2 nops.
VOICEHELP returns free - (2 + engine voices, max 2) when READY and ENG+0 != 0: a mono varispeed
note counts as 4 voices (4 others max), a stereo one as 6 (2 others). Second allocator 0x1BE6DA
(needs 4 voices, other mode) untouched. Engine identical to v20. "EXT Ver.V.15".

Result on hardware (v21): still "Too Busy" with a Standard-grade varispeed loop + pad spamming;
Long-grade samples fine.

## Build v22 (build_v22_grade_weight/, build_engine15.py): weight by sample grade
VOICEHELP (now up to 0x1D1A00; POSTEXIT area unused since v20) sums per engine voice
WEIGHT[c] - 1 with c = VS+8 (rate code): Standard 6, Long (22k) 4, 11k 3; reserve capped at
6 - engine voices. Mono Standard -> 2 other voices, mono Long -> 4 (as v21), mono 11k -> 5;
stereo -> 2 others. Unit-tested in the emulator (all registers but r1/r10 kept). Engine = v20.
"EXT Ver.V.16".

## Build v23 (build_v23_two_lowgrade/, build_engine16.py): two lower-grade mono varispeed notes
build_engine13 now has emit_cap(a) (the one-note cap after the take-over scan) and INIT_ELIG
(VS+9 = 0 at take-over); v20 still builds byte-identical. v23's emit_cap: if exactly one new
engine voice and its rate code >= 1 (Long / 11k), VS+9 = 1; the newest older engine voice
(highest serial, VS+12) is kept if its VS+9 == 1; all other older voices are handed back
(4022|4028) as before. Standard or stereo -> one note at a time. Third lower-grade note replaces
the older of the two. VOICEHELP (v22) sums per voice: two lower-grade notes -> reserve 4 (2 others).
Tests: ownership trace (rate 1/2: 04 -> 24 -> a0 with voice 2 faded; rate 0 unchanged), two
staggered engine voices at exactly 1.0x equal the ROM playing them as Normal (rate 1/2, loops, stop,
Normal voice mixed in; tools/unity_vs_rom.py); identical to v22 for single notes and Standard.
"EXT Ver.V.17".

Result on hardware (v23): two Long varispeed loops + a third -> oldest fades out correctly.
Two lower-grade varispeed loops + pad spamming: works great. One Standard-grade varispeed loop +
pad spamming: works great (no Too Busy). v23 is the current good build.

## Build v24 (build_v24_fine_bpm/, build_engine17.py): Fine Tune + BPM follows varispeed
- Param 59 (spare record byte 0x2E, written by the old idle meter as "Idle %", which read 0) is
  "Fine Tune": signed -50..+50 cents (descriptor min/max/signed), menu row 10 (counts 9 -> 10),
  names at 0x1D5200 (pointer to the "0" entry), FINETAB 0x1D5000 (round(65536*2^(c/1200))).
- VTAB[pad] = TAG<<16 | cents<<8 | semis. New pad set-up helper HELPER2 0x1D5600 (reads 46, 58, 59)
  at the 3 sites, new audio-task handler LIVE2 0x1D5700 (58 / 59 update their byte).
- Engine take-over (b13.emit_vtab_step hook): ROM if both 0; step = STEPTAB*FINETAB >> 16 (mulu).
  With cents 0 the step is identical to v23 (cmp_builds: identical output). Speed accuracy with
  cents (EXACT=1 FINE=.. test_speed.py): <= 2 LSB vs ideal interpolation at the engine's step,
  step within 0.002 % of 2^((s+c/100)/12).
- BPM: 0x183B06 (jarl 0x1C34B4 in the generic value edit 0x183AC0) -> BPMWRAP 0x1D5800. For ids
  58/59: read old semis, cents, BPM (param 44 = BPM x 10), set the new value, then
  BPM = round(base * ratio_new), base = BPM_old / ratio_old (Q4), clamped 400..2000 (the UI's own
  BPM limits). Per-sample cache at ENG+0x1000 (512 x {u16 BPM written, u16 setting key, u32 base})
  is used only when BPM and setting still match, so knob round trips return exactly (also out of
  a clamped value); a manual BPM change resets the base. Emulator session test passes.
- Effect 24 name: already the original "24 CHROMATIC P.S." in every build since the test build.
"EXT Ver.V.18".

Result on hardware (v24): BPM is updated, but the display only after leaving/re-entering the edit
screen. With varispeed on, Phrase play type doesn't play correctly (Single works).

## Build v25 (build_v25_phrase_bpmdisplay/, build_engine18.py)
- Firmware BPM facts: 0x15BF84(sample) computes BPM (x10) from beat/measure/length/rate;
  0x1A296C(sample, bpm) sets p53 = 0, p44 = p45 = bpm and marks the project changed (0x19E4AC);
  0x15BEA8 = effective (target) BPM: p44, or p45 / master tempo (0x160274) for Phrase / p53.
  0x1BC090 (voice set-up) stores voice+152 = sample BPM, +154 = target, folds the target by octaves
  and sets the time-stretch mode +148 (0 none, 2 slower, 3 faster; copy at +187).
  Phrase voices go to allocator list 3 (14456/14460) instead of list 1.
  UI redraw event: 0x17FDE8(row), -1 = whole screen (Measure/Beat edits use it).
- BPMWRAP now posts 0x17FDE8(-1) after setting the BPM (b17.REDRAW).
- b13.STRETCH_OVERRIDE: the take-over no longer skips voices with +148 != 0; when the pad has a
  varispeed/fine setting it clears +148 and +187 before the ROM's first pass, so Phrase / synced
  samples play varispeed like Single ones. Normal pads keep the ROM's time stretch.
- Tests: identical to v24 for ordinary voices; stretch-flagged voices with varispeed give exactly the
  Single output; Normal + stretch not taken; BPMWRAP emits the redraw.
"EXT Ver.V.19".

## Build v26 (build_v26_auto_single/, build_engine19.py): Play Type follows varispeed
BPMWRAP (b17.AUTOSINGLE): after a Varispeed / Fine Tune change to a non-zero setting, if param 56
(Play Type, record 0x2B; 0 Single, 1 Phrase) is Phrase it is set to Single with the setter, and the
screen is redrawn (once, also covering the BPM change). Going back to Normal leaves Play Type as is.
Only BPMWRAP changed vs v25 (engine identical). Emulator unit test passes. "EXT Ver.V.20".

## Build v27 (build_v27_phrase_lock/, build_engine20.py): Phrase locked out while varispeed is on
Play Type edits go through the generic value edit too (0x193F66 -> 0x183AC0 -> setter at 0x183B06 =
BPMWRAP). b17.LOCKPHRASE: for param 56 with value != 0 (Phrase) BPMWRAP reads params 58/59 and skips
the setter if either is non-zero (Play Type stays Single; the caller still redraws). Single, other
params and Phrase on Normal samples pass straight to the setter. Emulator unit test passes.
"EXT Ver.V.21".

## Review of v27 (Oct 29) and build v28 (build_v28_reviewed/, build_engine21.py)
Checked:
- Byte diff vs v1.02: header first 0x40 bytes intact, checksums valid. Original code/data changed
  in 15 places, all known: descriptors 58/59 (block 1), version string (3), edit setter call
  0x183B06 (8), menu table pointer and row counts (9), 3 pad set-up calls, param handler entry,
  hook install, allocator free count (11), idle-task call 0x1CE552 (block 12, 4 bytes, since v7;
  runs after the updater check). All other changes are in former 0xFF space of block 13.
  Block 14 (updater) untouched.
- Every patched routine disassembled and read: hook stub, engine (take-over, cap, frames, patch,
  POST, ADV/DECW/BOOK), VOICEHELP, HELPER2, LIVE2, BPMWRAP, idle init. ABI (callee-saved r20-r29
  kept, lp saved), ep never moved, POST runs with interrupts off and restores PC/PSW, stack frames
  balanced. RAM used only in 0x428000-0x42A000 (unreferenced by the stock firmware; stacks end at
  0x427000, gp data at 0x430000). No stock code references it; 0x426D00 no longer used.
- ROM: with +148/+187 cleared a voice is an ordinary one (stretch fields +172..+204 are only read
  by the stretch paths 0x1297C..).
- Dead code: old HELPER 0x1D1000 and LIVE 0x1D1200 are unreferenced since v24 (harmless).
- Fine Tune (param 59, byte 0x2E) was written by the v7-v19 Idle % meter; records saved then may
  read a stray 1..50 as Fine Tune (51..127 read as 0 via the descriptor range).
Found and fixed (v28): notes starting in the same audio block (two varispeed pads on one pattern
step, or pressed together) were all kept -> two Standard notes, or 3+ engine voices, could run
together (fuzz.py MULTI=1 on v27: "owned [4, 6]" Standard pair). v28 emit_cap: note1 = pad of the
newest new engine voice (its new voices; stereo = 2); if note1 is mono and not Standard, the newest
other note is kept too when it is mono and not Standard; all other engine voices are handed back.
A voice handed back in its start block never sounds (4023+4022 together). Sequential behaviour is
the same as v23-v27.
Tests: tools/regress.sh (40 checks: Normal identity, unity = ROM for rate codes 0/1/2 with loops,
stops, multi-voice notes (SAMEPAD), formats 4..8, pan/send; two staggered lower-grade notes = ROM;
time-stretch override; speed accuracy incl. cents) all pass on v28; tools/fuzz.py (random starts,
stops, retriggers, several per block, stretch flags) passes with the note-limit invariant.
"EXT Ver.V.22".

Result on hardware (v28): copying a varispeed sample: the copy keeps the varispeed BPM but plays at
normal speed. Resampling (Auto) with two Long varispeed samples stops one of them at once.

## Build v29 (build_v29_record_resample/, build_engine22.py)
- Take-over reads params 58/59 straight from the sample record (gp + 15312 + 48*sample, bytes
  0x2D/0x2E; same record the getter 0x16210C uses for class-4 params, sample index = slot pad)
  instead of VTAB (VTAB was only refreshed by pad set-up / menu edits, so copied / loaded samples
  could play differently from what the record says). VTAB, HELPER2 and LIVE2 remain but the engine
  no longer uses them. A copy of a varispeed sample now plays varispeed (exact copy, BPM matches).
- VOICEHELP: reserve additionally capped at others + max(0, free + releasing - needed), others =
  list-1 (stealable playing) count - engine voices; needed = r19 at the call site. The reserve can
  then only force stealing of non-varispeed voices. Resample-like case (recorder holding voices,
  one Long varispeed playing, free 3): v28 stole 1 (the varispeed note), v29 steals 0. Unchanged
  when other voices play.
- Test harnesses write the record bytes as well as VTAB. regress.sh 40/40, fuzz OK, v29 = v28
  block by block when record and VTAB agree. "EXT Ver.V.23", checksum FA98D3F6.

Result on hardware (v29): copy still wrong: the copy plays at normal speed but keeps the varispeed
BPM. So the CLIPBOARD copy carries param 44 (BPM) but not record bytes 0x2D / 0x2E (58 / 59). The
paste routine itself wasn't found (no setter call for 44 / 58, no 48-byte record memcpy; it writes
the record directly).

## Build v30 (build_v30_bpm_rule/, build_engine23.py): BPM always follows the sample's own settings
Stock facts used:
- Every stock write of param 44 passes either the natural BPM 0x15BF84(sample) or the current
  param 44: post-sampling init 0x1A0F58, 0x1A296C (sets 53 = 0, 44 = 45 = value; called by the
  menu's Beat edit 0x193D4E and Measure edit 0x193E86 with natural, and by 0x193FF2 / 0x19402E with
  the current 44), Measure 0x1A2E10 / 0x1A3AEE / 0x1A3B8A / 0x1A3C26 (start / end edits). So stock
  keeps 44 == natural (descriptor range 400..2009); 15BF84 returns 0 for an empty / degenerate
  sample.
- The setter 0x1C34B4 posts a message (0x1C284C -> ROM 0x1393C queue, 256 x 16 bytes); stock code
  reads the record right after posting (Beat edit), so the receiver normally runs first.
- The getter returns param 44 clamped to 400..2009.
- Post-sampling init 0x1A0BE8 resets 37, 42, 52, 55, 58 individually (58 = 0 at 0x1A0D76) but not
  59: since v24 a new recording inherited the slot's old Fine Tune.
- Header line with the sample's BPM: 0x183B1C (called by the sample menu 0x193A20 and 0x18DE96,
  0x18E202) reads 44 at 0x183B60.

Rule: BPM = natural if Varispeed = Fine = 0, else clamp(round(natural * ratio), 400, 2000);
ratio = STEPTAB[semis] * FINETAB[cents] >> 16 (same as the engine). Only applied when natural is in
100..16000.
- BPMWRAP (0x1D5800, rewritten; the BCACHE per-sample cache is gone): 58 / 59 edits set the value,
  write record bytes 0x2D / 0x2E directly, BPM = rule (setter + record bytes 0x1C/0x1D directly),
  Play Type rules as v26 / v27. Its own setter calls use RAWSET (the original setter).
- SETWRAP at the setter entry (jr; RAWSET = original 'prepare {r20,r21,lp},16' + jr 0x1C34B8):
  id 44 with value == natural(sample) -> value = rule (Measure / Beat / start-end edits keep the
  varispeed BPM; before they reset it to natural); id 58 (stock callers only = init) -> also 59 = 0
  and record bytes written.
- REPGET at 0x183B60: if 44 != rule (rule <= 2009), set it (setter + record) and show the corrected
  value. Repairs CLIPBOARD copies (record says Normal, BPM is the varispeed one) when the sample's
  screen is shown.
Tests: tools/test_bpm.py (emulator, real getter / natural / wrappers, setter body stubbed, in sync
and async message modes): 46 checks incl. TARGET vs Python for 1295 settings; regress.sh 40/40;
fuzz OK. Engine bytes identical to v29. "EXT Ver.V.24".

User question (v30): effect switching feels a little slower while varispeed loops play. Expected:
the engine runs in the audio interrupt and the UI gets what is left. Asked for another trim pass.

## Build v31 (build_v31_trimmed/, build_engine24.py): less fixed work per block, same sound
Profile v30 (tools/prof30.py: flash halfwords per block incl. hook stub, engine, POST; region
breakdown by engine label): one Standard voice at -7 = 673, of which the 16 frames ~336 (19 hw per
frame, already minimal for exact output), the rest overhead: patch 68, voice loop head 43, POST
restore 39, redirect 28 + 27, hook entry 20, stub 18, DECW/BOOK ~55.
ROM facts used (mask ROM voice loop): bookkeeping 0xADBE is skipped for rate code >= 1 when the
phase +151 becomes non-zero (0xAD5C..0xAD86); for rate code 0 it always runs. Its segment step is
`switch +145` (0xAE02): cases 0..10 compare pointer + step (+36 + +143) with the segment table
+60 + 4k, cases 11..13 compare it with +104 (`bl`, ring wrap). Kernel choice reads +139/+140.
Only other read of +36 in the plain path: 0x9782 copies it into +8 before the decode.
Changes:
- Undo entries hold only the words the patch changes: rate >= 1: +16, +148 (12 bytes); Standard:
  +16, +148, +32, +36, +136 (24 bytes). Standard patch: end = 0x7FFFFFFF, +137 = 0, pointer +36 = 0
  (was 0x7FFF0000 with +143 = 0 and +145 = 5): 0 + step can't match a segment address or reach
  +104, so the bookkeeping is a no-op and +140 / +144 stay untouched. Side effect: +8 reads 0 after
  a block instead of 0x7FFF0000 (only the decoder uses it; DECW sets it). POST picks the entry size
  from the record's +139 (never written by patch or ROM pass). Terminator written once in v_done.
- Hook: note-start scan moved out of line (no pending start: one taken branch).
- Voice loop: 256-byte lowest-set-bit table instead of shifting through the mask.
- Rate dispatch: Standard reaches g16 with a short branch.
Flash halfwords per block v30 -> v31: Standard -12 654->617, -7 673->636, +7 754->717, +12 801->764
(about 5%); Long -7 464->412, +7 506->454 (11%); lowest -7 369->317 (14%); two Long -7 795->701
(12%); stereo Standard -7 1213->1149 (5%).
Tests: cmp_builds v30 vs v31 (IGNREC8=1 ignores record +8): 21 setting/rate combos with loops and
54 scenario runs (no loop, stops, 2 and 4 voices, staggered, Normal mixed in, stereo pairs, stretch,
fine) identical in output, masks and records; ring / segment modes (+145 = 9..13) identical;
tools/difffuzz.py (fuzz scenario on both builds in lockstep) 3 x 2500 blocks identical;
regress.sh 40/40; fuzz OK (3 runs); test_bpm all ok. "EXT Ver.V.25", checksum FA9B22F5.

## Build v32 (build_v32_zero_label/, build_engine25.py): Varispeed menu shows "0" instead of "Normal"
User request: show the middle Varispeed value as 0, like Fine Tune. Only the 7-byte name entry for
setting 0 in the value-name table (VALUES2 + 7 * 24 = 0x1D1AA8) changes; stored values, engine and
UI code identical to v31 (byte diff: name entry, version string, checksums). "EXT Ver.V.26",
checksum FA9B252D.

## Release 2.0.0: system version in the image header
Hardware report: the EXIT + ENTER screen still showed 1.02. That screen (0x1CE470: "*** CHECK SUM
***", CPU / SYS checksums) prints the system version from the image header, 0x10001F (the "1.02"
of "BOSS SP505\0Ver.1.02" at 0x100010); the card updater (0x1EF6A0) and the ROM's recovery
updater (0x17534) display the same bytes. "EXT Ver.1.02" at 0x138AAB belongs to a different test
screen (0x1CAC5C). The ROM's boot check (0x158B4) compares only the 10 bytes "BOSS SP505" at
0x100010, so the 4 version bytes can change: they now read "2.00". The .prg file header (outside
the image) is left as the official one.

## Mark button (branch add-mark-button, test build 2.1a, mark.py)
Goal: SP-303-style Mark on [L/R]: while the last pressed pad plays, 1st press = START, 2nd = END.
UI key path (found from the panel test mode's key table 0x138E60, {u32 LED/x/y, char *name} x 61,
index = key code: L/R 21, ZOOM IN 19, ZOOM OUT 20, ENTER 22, EXIT 23, PAD 1-16 29-44):
- Key event {+0 type 0, +4 key code (byte), +8 state 0 released / 1 pressed / 2 repeat}.
- UI dispatcher 0x1A042C(screen index, event): screen = table 0x120590[i] (62 descriptors {id,
  handler slots}); type switch; for keys (type 0), UI mode gp+0x10000-17800 <= 4 sends the event
  only to the screen's slot +40, otherwise 0x1A065A: handler = 0x120560[0x12046C[key]](screen,
  event). Key class 3 = ZOOM IN / ZOOM OUT / L/R -> 0x19BDF8, which calls slot +28 if non-null.
- Slot +28 handlers: 0x186CF4 (WAVE EDIT) and 0x1A4FE8 (screens 28 / 29, sample screens with a
  waveform) use L/R through 0x181CE4: L/R state -> gp-17580 (held), ZOOM then changes the vertical
  zoom (0x1A5C70) instead of horizontal (0x1A5CE0). 0x1A4E38 (default, main screens), 0x18AB98,
  0x1919C0, 0x190998 only act on 19 / 20. So L/R was inert everywhere else.
- Mode table 0x120838: mode 6 and 14-21 go to screen 1 (0x180750(n) = show screen n).
Sample / position facts:
- Last pressed pad: system params 184 (pad, class 9 byte gp+14824) and 185 (bank, gp+14825), set
  by the pad handler 0x19BAD0; sample = 0x1A6B94(pad, bank) = bank*16 + pad (pad 16 -> 512).
- START = param 39 (record +0x08), END = 40 (+0x0C), 37 / 38 the wave's own range, 42 a third
  point. Positions <-> bytes: 0x15C364(sample, bytes) / 0x15C2E4(sample, position).
- Pad set-up (0x1B9FF8 loop) stores pad record (gp+0x20000-720 + 156*sample) +80 / +84 / +88 =
  positions of 39 / 40 / 42, +100 / +104 the raw values; the audio task's parameter handler
  0x1BA884 updates them for ids 39 / 40 (0x1BB06C / 0x1BB212), no reload.
- Note start 0x1B6EBC: voice +28 = pad record +80, +32 = +84, +24 = +28 + start offset
  (gp+0x10000-9816 + 4v, normally 0); +137 = 1 / 2 / 4 per rate code. The ROM adds +137 to +24 per
  chunk and loops back to +28. So voice +24 is the play position in START / END position units.
- Stock commits: 0x1A3BB0(sample, position) START, 0x1A3B14 END (param, Measure halved / doubled
  until BPM fits, 44 / 45, project changed 0x19E4AC). Their WAVE EDIT wrappers 0x1A5724 / 0x1A56D4
  check the 193-step minimum against the edit context gp-14692 (0x1A6330), so Mark does its own
  check with 0x1A5758 / 0x1A5708 (START / END of a sample as positions).
- Protect: 0x196710(bank) (param 8 bits; param 8 values below its min 15 read as the default 15,
  i.e. banks 0-3 protected) -> stock answer is error 13 via 0x1A16C0 ("ERROR!!! Protected!";
  message table 0x11FA34, 12 bytes per entry).
Build: data word 0x12056C (class 3 entry) 0x19BDF8 -> MARKKEY 0x1D6000 (block 13 free space;
0x196 bytes). L/R on a screen whose slot +28 is 0x186CF4 / 0x1A4FE8, ZOOM keys and everything
else -> 0x19BDF8 unchanged. L/R press elsewhere -> MARK: sample of the last pad; protected ->
"Protected!"; reverse (param 52) -> nothing; voice = active and not 4022 / 4023 / 4026 / 4027,
slot +10 == sample, +28 <= +24 < +32, smallest +24; state at RAM 0x429E00 {magic 'MARK',
sample, next tap}; END tap needs position >= START + 193 (else it moves START), START tap needs
position + 193 <= END; then redraw (0x17FDE8(-1)). Runs in the UI task like WAVE EDIT's own commits.
Emulator: v850emu got divh / divhu (format XI 0x280, used by 0x15C364). tools/test_mark.py: 30
checks through the real dispatcher, all ok; regress.sh 40/40, fuzz OK, test_bpm all ok; difffuzz vs
2.0.0 identical (audio path untouched). "2.1a", checksum FA9BD53D. Blocks changed: 0 (version),
2 (one table word), 3 (version text), 13. Blocks 12 and 14 untouched.

## Test build 2.1b: SP-303-style clear, marked flag, LCD tag, hold-to-start
User request: like the SP-303, a marked sample "lights" the button and pressing Mark again clears
the marks; holding Mark before triggering the pad sets START to the beginning.
- No LED behind L/R: the panel test table 0x138E60 ({u8 LED or 0xFF, u8 x, u8 y, -, char *name}
  x 61; first reading in the 2.1a notes was one entry out of step) lists no LED for L/R or the ZOOM
  keys. LED driver 0x1C81D8(led, state): state table gp-2268, hardware writer callback gp-2012
  (0x1C500C). 0x180750(n) is a per-mode LED pattern (table 0x11B72C, 124 bytes each), not a screen.
- Marked flag: only spare record byte is +0x2F (param 60; every other byte of the 48 belongs to a
  parameter). Value 0x80 | hash7(START value, END value) (mark.flag_of); old internal builds
  (v7-v19) wrote 0..127 there, never >= 0x80. Post-sampling init sets END through a direct
  message (0x1C31EC), not the setter, so the hash (not only SETWRAP's clear) ends the mark when
  the points change. SETWRAP clears the byte for setter calls with id 39 / 40.
- Clear = WAVE EDIT's limits: 0x1A5790(s) = position of param 37 (data start), 0x1A5774(s) =
  position of param 42 (data end; post-sampling init: 37 == 42 means empty, 0x1A6954).
- LCD: 128 x 64, framebuffer 0x41625E (8 pages x 128 bytes, bit = row). Primitives: 0x154D64 clear,
  0x154DF8(x1, y1, x2, y2, [sp] 0 white / 1 black) fill, 0x154DDC(x1, y1, x2, y2) invert,
  0x155B48(x, y, font, string) text (font 0 = 6 px, 1 = 5 px, 2 = 7 px), 0x155E6C / 0x155EC4 text in
  6 x 8 cells, 0x155960 number. The LCD routines take a lock at 8[ep] and write only the
  framebuffer; the display is refreshed from it without a dirty flag.
- Screens identified by rendering every descriptor's enter (+64) and draw (+68) slots in the
  emulator (needs the v850emu prepare fix below; the play screens' sequencer request 0x17248C
  blocks on another task and is stubbed): screen 3 = PATTERN PLAY (desc 0x11D36C), 6 = SONG PLAY
  (0x11E224), 31 = DELETE SAMPLE, 1 = PAD BANK list, 2 Pad Accent, 9 Resolution, 12 Play BPM,
  13 Sync BPM, 27 sample parameters, 34 pad assign, 37 LCD contrast, 51 a diagnostic. Current
  screen: gp+0x10000-21728 (index), state table 0x11B308 (62 x 16), switch request 0x180204(n),
  UI init 0x1A091C(n) sets mode 5. The play screens draw the PAD BANK box in their enter routine
  (0x189C14 / 0x191038): "PAD BANK:" at (2, 49) font 1, number at 50, name[bank] (table 0x12A354)
  at 65, frame (0, 47)-(127, 55). Longest non-preset name 7 characters -> ends at x 101; the tag
  box is (104, 48)-(125, 54). Preset banks (0-3, protected, "PRESET n" reaches x 106) are skipped.
- Tag redrawn after the play screens' enter / draw slots (descriptor words +64 / +68 -> wrappers),
  after every pad key (class 6 table entry 0x120578 -> PADW) and after each mark press.
- Hold: L/R press / release events (state 1 / 0, repeat 2 keeps it) -> MARK_RAM +12. PADW: pad
  press (keys 29..44) while held, on a screen that doesn't use L/R: sample = bank * 16 + pad,
  protect / reverse checks, START = data start committed before the stock pad handler 0x19BAD0
  runs (the parameter message is queued ahead of the note start), next press = END.
- v850emu: prepare with a frame >= 64 bytes (imm5 bit 4 in the opcode field, op 0x3D) wasn't
  recognised and ran as ld.bu, leaving the frame unbuilt; fixed (r2 == 0 identifies prepare).
- tools/test_mark.py: 75 checks; tag renders compared with the stock firmware's render of the same
  RAM state (sync_ram), identical outside the tag box. "2.1b", checksum FA9E8E9A.

## Test build 2.1c: END press restarts playback (SP-303 style)
Hardware report (2.1b): after the END press the note kept playing to the end of its original range
before looping the marked range (a voice takes START / END from the pad record at note start).
- Pad notes: the panel task (0x1C54E8) sends pad hits as SENDNOTE 0x1C34F8(part 0, 0x90 / 0x80,
  sample, velocity = gp+0x10000-15356, [sp] 0) -> 0x1C2680 -> the sequencer (0x172650), which passes
  them on to the audio task (type 4 messages, status 0x90 -> note on 0x1BFA90, 0x80 / velocity 0 ->
  note off 0x1BF9AC, 0xB0 120 -> all off 0x1BFE88; type 5 = parameter, 0x1BA884). The UI's preview
  path is 0x1C330C -> 0x1C26FC -> 0x172614. Parameter messages (setter -> 0x1C284C) go straight to
  the audio task, so a note sent after a commit always starts with the new range.
- RETRIG (after the END commit): the sample's active voices get 4022 | 4028 (stock fade-out request,
  as a voice steal / the engine's hand-over), set with interrupts disabled (the audio ISR writes
  these bytes), then SENDNOTE as a pad hit. START presses and clears don't touch playback.
- Open: the hold-L/R-then-pad START commit (PADW) runs in the UI task while the pad's own note goes
  panel -> sequencer -> audio; if the sequencer task delivers before the UI task runs, that note
  starts from the old START (only matters when START wasn't already the beginning).
- tools/test_mark.py: 80 checks (note sent after the END commit with interrupts back on, fades only
  the sample's voices, none for START / clear). "2.1c", checksum FA9EE4CD.

## Test build 2.1d: no direct fade on retrigger, flashing MARK
Hardware report (2.1c): random distortion and the level getting quieter / louder during playback;
the ">END" / "MARK" tags hard to read.
- Note-on 0x1BFA90 already cuts the sample's playing voices itself: per part a count table at
  gp+0x30000+15188 + part*1028 + sample*2; non-zero -> 0x1BD184(part, sample, -1) (stop with the
  allocator's lists) before the allocator 0x1BDCDC. 2.1c's RETRIG also set 4022 | 4028 on those
  voices from the UI task, outside the allocator -> voices ending behind its back, then the stock
  cut on voices already finishing; most likely the cause. 2.1d's RETRIG only sends the note.
- Also seen: the parameter handler re-runs voice set-up (0x1BBFE0) on the sample's playing voices
  after a START / END change (0x1BB14E..0x1BB1D2; time-stretch / BPM fields), as for a WAVE EDIT
  edit while previewing. Stock behaviour, left as is; a suspect only if the distortion remains
  (especially Phrase play type or varispeed samples, whose BPM changes with the marks).
- Pad velocity gp+0x10000-15356 is the PAD ACCENT level (127 at start-up; written by the Pad Accent
  screen), used by every panel note-on; so the retrigger level equals a pad hit.
- Flashing tag: TAG draws MARK inverted in both states; for "START set, END due" it keeps the
  tag's 22 framebuffer bytes (page 6, x 104..125, rows 48-54; bit 7 = the box line) in MARK_RAM
  +0x20 and sets +16. The idle task's endless loop (engine.build_idle 'br .' at 0x1D1330) now jumps
  to MIDLE: every 2^8 ticks (0x3FFE02C) it rewrites those bytes on / off, with interrupts off from
  the checks (MARK_RAM magic, +16, current screen = a play screen) to the last byte. It calls no UI
  or LCD code (the LCD lock 8[ep] is a spin lock: a low-priority holder would hang the UI). No
  safe periodic UI event was found: the UI waits on its flag without a timeout, 0x17FD1C
  dispatches synchronously and 0x17FDE8 writes the UI's ring without a lock.
- SP-303 START semantics confirmed: a START press commits START at once; stopping playback then
  leaves START = mark point, END = old END.
- tools/test_mark.py: 95 checks (incl. the idle loop run in the emulator: off / on phases, other
  screen, RAM not initialised). "2.1d", checksum FA9F3134.

## Test build 2.1e: flashing stops when playback stops, restart straight to the audio task
Hardware report (2.1d): sound fine. (1) After a START press, stopping the sample left MARK flashing
(SP-303: it stops). (2) A little audio past the END played before the restart.
- (2) 2.1d's restart went panel-style through the sequencer: SENDNOTE 0x1C34F8 -> 0x1C2680 builds an
  8-byte event for the sequencer's mailbox (gp-18764, ROM 0x5288 via 0x172650, which doesn't
  set_flg the sequencer; 0x172614, the UI variant, does), so the old note ran on until the
  sequencer passed the note to the audio task. Audio task input: 0x1C284C routes messages; type 5
  parameters (id < 307) go to a shadow table at gp+0x30000+22660 + set_flg(ep+64) (the audio
  task, highest priority, runs at once), everything else to the ROM queue 0x1393C (the only caller
  of 0x1393C; the audio task re-posts messages it can't take yet through 0x1C284C). 2.1e's RETRIG
  posts {4, flags, part, 0x90, h sample, h velocity, h extra} through 0x1C284C right after the END
  commit (before the flag / redraw work). Part / velocity / flags / extra are copied from the audio
  task's last note-on record (gp+0x30000+22384: h extra, h sample, b part, b velocity, b flags,
  written by 0x1BFA90) when it is this sample, else 0 / PAD ACCENT level / 1 / 0. Not seen by the
  sequencer: no MIDI OUT, not recorded.
- (1) The idle loop (MIDLE) also watches the "END due" state (MARK_RAM +8): +24 = the sample has
  been seen playing (set by the START press; 0 for hold + pad, whose note may start later; set by
  the loop when it sees a voice). Seen and no voice of the sample active (ep[4021], slot +10) ->
  with interrupts off, after scanning again: +8 = 0 (next press START), +16 = 0, +24 = 0, and the
  tag blanked if it was flashing on a play screen. START / END stay as committed.
- tools/test_mark.py: 105 checks. "2.1e", checksum FAA00130.

## Test build 2.1f: restart note into the audio task's ring
Hardware report (2.1e): marks set correctly, but the END press no longer restarted playback (the
note ran to the sample's end, then looped the marks).
- 0x1C284C doesn't feed the audio task: type 5 (parameter) messages go to a shadow table and
  wake task 0 (TCB ep+64, highest priority), which forwards them; other types go to ROM 0x1393C
  (not the audio task). 2.1e's restart therefore never arrived.
- The audio task reads a ring at gp+0x10000-12100 (128 x 16 bytes; read index -10052, write
  -10048), written by 0x1B3394(message) (blocks while full, then set_flg ep+128 0x20000000 =
  audio task, TCB 0x3FFE080). Task 0 (0x1C19xx-0x1C2xxx) and the UI's preview notes (0x1A16E0 /
  0x1A1718: {4, 1, 4, 0x80 / 0x90, h 513, h 0 / 127, h 0}, used by the START / END editor) use it.
  Dispatch: 0x1B19A8 copies an entry to sp+4; type 1 = commands (switch on byte 8), type 4 =
  notes, type 5 = parameters (0x1B276C...).
- RETRIG posts through 0x1B3394. The END commit's parameter message is already in the ring (task 0
  runs at once on its flag), so the note follows it.
- test_mark.py now also runs the real 0x1B3394 (ROM kernel calls stubbed) and checks the note in the
  ring, which would have caught 2.1e. 106 checks. "2.1f", checksum FAA000DC.

## Test build 2.1g: "marked" = START / END not the whole recording
Hardware report (2.1f): restart works. Request: show MARK whenever START / END differ from the raw
sample's start / end, also when set in WAVE EDIT (otherwise the display is misleading).
- ISMARKED(s) = START position (0x1A5758) != data start (0x1A5790, param 37) or END position
  (0x1A5708) != data end (0x1A5774, param 42). The record flag byte (+0x2F hash), FLAGV and
  SETWRAP's clear for ids 39 / 40 are gone (bpm.py back to the 2.0.0 code).
- Press order: END due (MARK_RAM +8) -> END press; else marked -> clear (so a WAVE EDIT trim is
  cleared by L/R, consistent with a steady MARK); else START. TAG: END due -> flashing, else
  marked -> steady.
- When the END wait ends because playback stopped, the idle loop shows the tag steady or blank
  from MARK_RAM +28 = ISMARKED after the START commit (stored by the START press and PADW), since
  the idle task can't call the getters.
- Open: a freshly recorded sample whose END isn't exactly param 42 (post-sampling init sets END
  through 0x1C31EC from its own computation) would show MARK; check on hardware.

## Release 2.10
Test build 2.1g confirmed on hardware; released as 2.10 (version string only differs from 2.1g):
version screen 2.10, SYS checksum FA9FB0F6, output MD5 aa81955a4f373d1128c5c466f922ae7a. From
this release on, releases are named like the version screen ("2.10", "2.20", ...).
