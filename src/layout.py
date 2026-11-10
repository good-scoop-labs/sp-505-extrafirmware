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

# UI key dispatch (0x1A065A): handler = CLASS_HANDLERS[KEY_CLASS[key]](screen r6, event r7);
# event +4 key code (byte), +8 state (0 released, 1 pressed, 2 repeat)
KEY_CLASS = 0x12046C            # u32 per key code
CLASS_HANDLERS = 0x120560       # u32 per key class
KEY_LR = 21                     # [L/R]; class 3 together with ZOOM IN (19) / ZOOM OUT (20)
LR_CLASS = 3
LR_STOCK = 0x19BDF8             # class 3 handler: calls the screen's slot +28 if there is one
SCREEN_ZOOM_SLOT = 28
LR_USERS = (0x186CF4,           # slot +28 handlers that use L/R: WAVE EDIT (vertical zoom
            0x1A4FE8)           # modifier) and the sample screens with a waveform (28, 29)
PADSAMPLE = 0x1A6B94            # sample(pad r6, bank r7) = bank * 16 + pad (pad 16 -> 512)
PROTECTED = 0x196710            # bank protected(bank r6) -> r10 != 0
POST_ERROR = 0x1A16C0           # show error message r6 (13 = "Protected!")
ERR_PROTECTED = 13
START_POS = 0x1A5758            # START (param 39) of sample r6 as a play position
END_POS = 0x1A5708              # END (param 40) as a play position
SET_START = 0x1A3BB0            # set START (sample r6, position r7): param 39, Measure, BPM, changed
SET_END = 0x1A3B14              # set END: param 40, ...
MIN_LEN = 193                   # shortest START..END the stock edits allow (positions)
WAVE_START_POS = 0x1A5790       # start of the recorded data (param 37) of sample r6 as a position
WAVE_END_POS = 0x1A5774         # end of the recorded data (param 42) as a position
TO_BYTES = 0x15C2E4             # (sample r6, position r7) -> START / END parameter value
PARAM_CURPAD, PARAM_CURBANK = 184, 185     # system params: last pressed pad / current bank
PARAM_REVERSE = 52
PARAM_START, PARAM_END = 39, 40
PRESET_BANKS = 4                # banks 0-3: PRESET 1-4 (protected; long bank names)
PAD_CLASS = 6                   # key class of PAD 1-16 / EXT SRC
KEY_PAD1 = 29                   # PAD 1 .. PAD 16 = 29 .. 44
PAD_STOCK = 0x19BAD0            # its handler
SENDNOTE = 0x1C34F8             # pad note as the panel task sends it (via the sequencer):
                                # (part r6, status r7 0x90 on / 0x80 off, sample r8, velocity r9, [sp] 0)
NOTE_ON = 0x90
AUDIO_POST = 0x1B3394           # put a message into the audio task's ring (gp+0x10000-12100,
                                # 128 x 16 bytes) and wake it; type 4 note {4, flags, part,
                                # status, h sample, h velocity, h extra} (the START / END
                                # editor's preview notes, 0x1A1718, go this way). (0x1C284C
                                # routes elsewhere: parameters via task 0, others to ROM 0x1393C.)
LAST_NOTE = 0x30000 + 22384     # gp + this: the audio task's last note-on: h extra, h sample,
                                # b part, b velocity, b flags (written by note-on 0x1BFA90)
PAD_VELOCITY = 0x10000 - 15356  # gp + this: velocity the panel uses for pad hits
CUR_SCREEN = 0x10000 - 17804    # gp + this: descriptor of the screen being dispatched
SCREEN_ENTER, SCREEN_DRAW = 64, 68         # descriptor slots: enter (draws the frame), draw
PLAY_SCREENS = ((0x11D36C, 0x189C0C, 0x189988),    # PATTERN PLAY (screen 3): desc, enter, draw
                (0x11E224, 0x191038, 0x190CD8))    # SONG PLAY (screen 6)
# LCD (128 x 64, framebuffer 0x41625E, 8 pages x 128 bytes)
LCD_FILL = 0x154DF8             # (x1, y1, x2, y2, [sp] 0 white / 1 black)
LCD_INVERT = 0x154DDC           # (x1, y1, x2, y2)
LCD_TEXT = 0x155B48             # (x, y, font r8: 0 6 px, 1 5 px, 2 7 px, string r9)
TAG_BOX = (104, 48, 125, 54)    # Mark tag, right end of the play screens' PAD BANK box
LCD_FB = 0x41625E
TAG_FB = LCD_FB + 6 * 128 + 104 # the tag's bytes: page 6 (rows 48-55; bit 7 = the box's bottom line)
TAG_BYTES = 22
GP_VALUE = 0x437000             # gp (for code outside the UI task: the idle loop)
TICK = 0x3FFE02C                # RTOS system tick counter (ROM tick handler)
BLINK_SHIFT = 8                 # the flashing tag changes every 2^8 ticks

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
MARK = 0x1D6000                 # Mark button ([L/R]) code (limit 0x1D6800)
MARK_END = 0x1D6800

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
MARK_RAM = 0x429E00             # Mark state: +0 MARK_MAGIC (else not initialised), +4 sample,
MARK_MAGIC = 0x4D41524B         # +8 next press (0 START, 1 END), +12 L/R held, +16 tag flashes,
                                # +20 flash phase shown, +24 the sample seen playing since
                                # (idle loop), +28 marked once the END wait ends (tag steady),
                                # +0x20 the tag's 22 bytes (rows 48-54)
