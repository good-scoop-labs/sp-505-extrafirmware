"""Addresses and constants: the stock v1.02 firmware locations EXTRAfirmware uses, and where its
own code, tables and RAM live. All CPU addresses (flash image at 0x100000)."""

# ---------------------------------------------------------------- CPU / mask ROM
EP = 0x3FFE000                  # ep (internal RAM); never moved while interrupts are enabled
DECODE = 0x1A30                 # ROM: decode the voice's next chunk (r6 = voice record)
NOOP_FMT = 3924                 # voice format whose decoder switch entry is a bare `jmp [lp]`
VOICE_REC = 1020                # ep + 1020 + 208 * v: voice records (8 voices)
ROM_BUF = 2700                  # ep + 2700 + 32 * v: the voice's decode buffer (16 samples)

# ---------------------------------------------------------------- stock flash firmware
SYSTEM_VERSION = 0x10001F       # system version in the image header ("BOSS SP505\0Ver.1.02"),
STOCK_SYSTEM_VERSION = b'1.02'  # shown by the EXIT+ENTER checksum screen and the card updater
VERSION_TEXT = 0x138AAB         # "EXT Ver.1.02": text of a second, internal test screen
STOCK_VERSION = b'EXT Ver.1.02'
GETTER = 0x16210C               # get_param(id r6, sample r7) -> r10
SETTER = 0x1C34B4               # set_param(sample r6, id r7, value r8): posts a message
SETTER_FIRST = bytes.fromhex('8807210c')   # its first instruction: prepare {r20,r21,lp}, 16
SETTER_BODY = SETTER + 4
NATURAL = 0x15BF84              # natural BPM x 10 of a sample (from length, rate, Measure, Beat)
UI_REDRAW = 0x17FDE8            # post a redraw event (row, -1 = whole screen)
EDIT_SET_SITE = 0x183B06        # `jarl SETTER` in the generic value edit 0x183AC0
HDR_GET_SITE = 0x183B60         # `jarl GETTER` (44 = BPM) in the sample header line 0x183B1C
MENU_TABLE_PTR = 0x19398E       # imm32 of `mov TABLE, r12` in the sample parameter menu
MENU_ROWS_SITES = (0x1939B2, 0x193B8C)     # `mov 8, r7` / `mov 8, r8`: number of rows
STOCK_MENU_TABLE = 0x11F55C     # 8 rows x 12 bytes {param id, label*, names*}
DESC = 0x110364                 # parameter descriptors, 20 bytes per id: min, max, default,
                                # +12 record offset, +14 type, +16 signed flag
PAD_SETUP_SITES = (0x1BA192, 0x1BC8EE, 0x1BCD42)   # `jarl GETTER` (46 = rate) in pad set-up
PARAM_HANDLER = 0x1BA884        # audio task on_param_change(pad r6, id r7, value r8)
HANDLER_FIRST = bytes.fromhex('8407e1ff')  # its first instruction: prepare {r20-r29,lp}, 8
HOOK_INSTALL = 0x1BB672         # movhi/movea that put the audio-block hook into ep+4004
MONO_HOOK = 0x1B345C            # the stock hook function
ALLOC_SITE = 0x1BDD28           # pad voice allocator: movhi 3, gp, r1 ; ld.w 14444[r1], r10
ALLOC_ORIG = bytes.fromhex('440e030021576d38')
IDLE_CALL_SITE = 0x1CE552       # idle task: `jarl 0x5DB0` before its endless loop
SET_FLG = 0x5DB0

# gp-relative data (gp = 0x437000)
REC_GPOFF = 15312               # sample parameter records: gp + 15312 + 48 * sample
SLOTS = 13928                   # gp + 0x30000 + 13928 + 64 * v: voice slot (+10 = pad / sample)
FREE_COUNT, LIST1_COUNT, REL_COUNT = 14444, 14452, 14484   # gp + 0x30000: voice list counts

# sample parameters (ids) and their record bytes
PARAM_BPM = 44                  # BPM x 10, big-endian halfword at record +0x1C
PARAM_RATE = 46
PARAM_PLAYTYPE = 56             # 0 Single, 1 Phrase
PARAM_VARI = 58                 # Varispeed, record +0x2D (signed byte)
PARAM_FINE = 59                 # Fine Tune, record +0x2E (signed byte)
OFF_BPM, OFF_SEMI, OFF_FINE = 0x1C, 0x2D, 0x2E
SEMIS = list(range(-24, 13))    # Varispeed values
FINE = list(range(-50, 51))     # Fine Tune values
NSAMPLES = 512

# ---------------------------------------------------------------- EXTRAfirmware flash (block 13)
MENU_TABLE = 0x1D1100           # 10-row sample menu table
VARI_LABEL = 0x1D1180
IDLE = 0x1D1300                 # idle-task start-up: engine RAM init
HOOK = 0x1D1600                 # audio-block hook stub
VOICEHELP = 0x1D1700            # allocator helper (polyphony weight)
VARI_NAMES = 0x1D1A00           # 37 x 7-byte value names
STEPTAB = 0x1D1C00              # 37 x u32 16.16 speed per semitone
ENGINE = 0x1D2000               # the engine, executed in place (limit 0x1D4000)
ENGINE_END = 0x1D4000
FINETAB = 0x1D5000              # 101 x u32 16.16 speed per cent
FINE_NAMES = 0x1D5200           # 101 x 7-byte value names
FINE_LABEL = 0x1D5500
PADSETUP = 0x1D5600             # pad set-up helper (replaces get_param(46) at PAD_SETUP_SITES)
PARAMHOOK = 0x1D5700            # audio task parameter handler entry
BPM_CODE = 0x1D5800             # BPM rule: edit wrapper, setter wrapper, header repair (limit 0x1D6000)
BPM_END = 0x1D6000

# ---------------------------------------------------------------- EXTRAfirmware RAM (unused DRAM)
ENG = 0x428000                  # +0 owned voices, +4 READY, +8 start serial, +16 hook return,
                                # +0x18 undo cursor, +0x388 interrupted PC / PSW
READY = 0x52454459              # 'REDY': set by the idle-task init
VS = ENG + 0x80                 # per voice 64 bytes: +0 P (bit30 first decode due, bit31 advance
                                # due), +4 step, +8 rate shift c, +9 2nd-note flag, +12 serial,
                                # +32 voice record, +36 x buffer, +40 ROM buffer, +44 voice index,
                                # +48 DECW return address
UNDO = ENG + 0x280              # undo list (rec + saved record words), 0-terminated
CURSOR = 0x18
SAVEPC = 0x388
VTAB = 0x428400                 # per pad u32: TAG << 16 | cents << 8 | semitones (pad set-up)
TAG = 0x5AC3
XB = ENG + 0xC00                # per voice 64 bytes: x[0] = previous sample, x[1..16] = chunk
