from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO, IOBase
from typing import Any, Callable

from mrcrowbar.common import BytesReadType
from mrcrowbar.transforms import TransformResult
from mrcrowbar import models as mrc, utils

verbs4: dict[int, str] = {
    1: "open",
    2: "close",
    3: "give",
    4: "turn_on",
    5: "turn_off",
    6: "push",
    7: "pull",
    8: "use",
    9: "look_at",
    10: "walk_to",
    11: "pick_up",
    13: "talk_to",
    80: "give",
    90: "unk",
    255: "default"
}

var_names4: list[str|None] = [
#	/* 0 */
	"VAR_RESULT",
	"VAR_EGO",
	"VAR_CAMERA_POS_X",
	"VAR_HAVE_MSG",
#	/* 4 */
	"VAR_ROOM",
	"VAR_OVERRIDE",
	"VAR_MACHINE_SPEED",
	"VAR_ME",
#	/* 8 */
	"VAR_NUM_ACTOR",
	"VAR_CURRENT_LIGHTS",
	"VAR_CURRENTDRIVE",
	"VAR_TMR_1",
#	/* 12 */
	"VAR_TMR_2",
	"VAR_TMR_3",
	"VAR_MUSIC_TIMER",
	"VAR_ACTOR_RANGE_MIN",
#	/* 16 */
	"VAR_ACTOR_RANGE_MAX",
	"VAR_CAMERA_MIN_X",
	"VAR_CAMERA_MAX_X",
	"VAR_TIMER_NEXT",
#	/* 20 */
	"VAR_VIRT_MOUSE_X",
	"VAR_VIRT_MOUSE_Y",
	"VAR_ROOM_RESOURCE",
	"VAR_LAST_SOUND",
#	/* 24 */
	"VAR_CUTSCENEEXIT_KEY",
	"VAR_TALK_ACTOR",
	"VAR_CAMERA_FAST_X",
	"VAR_SCROLL_SCRIPT",
#	/* 28 */
	"VAR_ENTRY_SCRIPT",
	"VAR_ENTRY_SCRIPT2",
	"VAR_EXIT_SCRIPT",
	"VAR_EXIT_SCRIPT2",
#	/* 32 */
	"VAR_VERB_SCRIPT",
	"VAR_SENTENCE_SCRIPT",
	"VAR_INVENTORY_SCRIPT",
	"VAR_CUTSCENE_START_SCRIPT",
#	/* 36 */
	"VAR_CUTSCENE_END_SCRIPT",
	"VAR_CHARINC",
	"VAR_WALKTO_OBJ",
	"VAR_DEBUGMODE",
#	/* 40 */
	"VAR_HEAPSPACE",
	None,
	"VAR_RESTART_KEY",
	"VAR_PAUSE_KEY",
#	/* 44 */
	"VAR_MOUSE_X",
	"VAR_MOUSE_Y",
	"VAR_TIMER",
	"VAR_TIMER_TOTAL",
#	/* 48 */
	"VAR_SOUNDCARD",
	"VAR_VIDEOMODE",
	"VAR_MAINMENU_KEY",
	"VAR_FIXEDDISK",
#	/* 52 */
	"VAR_CURSORSTATE",
	"VAR_USERPUT",
	"VAR_V5_TALK_STRING_Y",
#	/* Loom CD specific */
	None,
#	/* 56 */
	None,
	None,
	None,
	None,
#	/* 60 */
	"VAR_NOSUBTITLES",
	None,
	None,
	None,
#	/* 64 */
	"VAR_SOUNDPARAM",
	"VAR_SOUNDPARAM2",
	"VAR_SOUNDPARAM3",
	None
]

@dataclass
class V4Instr:
    opcode: int
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    target: str | None = None
    raw: bytes = b""
    repr: Callable[[V4Instr], str] | None = None
   
    def __str__(self):
        if self.repr is not None:
            return self.repr(self)
        result = ""
        if self.target is not None:
            result = f"{self.target} = "
        result += f"{self.name}("
        if self.args:
            components = [f"{k}={repr(v)}" for k, v in self.args.items()]
            result += ", ".join(components)
        result += ")"
        return result



def get_byte_or_none(stream: IOBase) -> int | None:
    data = stream.read(1)
    if len(data) == 0:
        return None
    return utils.from_uint8(data)

def get_byte(stream: IOBase) -> int:
    return utils.from_uint8(stream.read(1))

def get_signed_word(stream: IOBase) -> int:
    return utils.from_int16_le(stream.read(2))

def get_unsigned_word(stream: IOBase) -> int:
    return utils.from_uint16_le(stream.read(2))

def get_vararg(stream: IOBase) -> list[int | str]:
    result: list[str | int] = []
    while True:
        test = get_byte(stream)
        if test == 0xff:
            break
        result.append(get_var(stream) if (test & 0x80) else get_signed_word(stream))

    return result

def var_name(var_id: int, extra: int | None=None) -> str:
    if var_id in range(len(var_names4)):
        res = var_names4[var_id]
        if res:
            return res

    if var_id & 0x8000:
        return f"VAR[{(var_id & 0xff0) >> 4} bit {var_id & 0x00f}]"

    base = "LOCAL" if var_id & 0x4000 else "VAR"

    if var_id & 0x2000 and extra is not None:
        return f"{base}[{var_id & 0xfff} + {var_name(extra)}]"

    return f"{base}[{var_id & 0xfff}]"


def get_var(stream: IOBase) -> str:
    var_id = get_unsigned_word(stream)
    extra = None
    if (var_id & 0x2000):
        extra = get_unsigned_word(stream)

    return var_name(var_id, extra)

def get_result_pos(stream: IOBase) -> int:
    var_id = get_signed_word(stream)
    if var_id & 0x2000:
        a = get_signed_word(stream)
        var_id += a & 0xfff
    return var_id

def get_result_var(stream: IOBase) -> str|None:
    return var_name(get_result_pos(stream))

V4_ACTOROPS_REMAP  = [1, 0, 0, 2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,20]

def parse_actorops(stream: IOBase) -> list[tuple[str, dict[str, Any]]]:
    opcode = get_byte(stream)
    ops: list[tuple[str, dict[str, Any]]] = []
    while opcode != 0xff:
        opcode = (opcode & 0xe0) | V4_ACTOROPS_REMAP[(opcode & 0x1f) - 1]
        a1 = True if opcode & 0x80 else False
        a2 = True if opcode & 0x40 else False
        a3 = True if opcode & 0x20 else False
        match opcode & 0x1f:
            case 0x00:
                ops.append(("SO_DUMMY", {"data": get_var(stream) if a1 else get_byte(stream)}))

            case 0x01:
                ops.append(("SO_COSTUME", {"costume": get_var(stream) if a1 else get_byte(stream)}))

            case 0x02:
                speed_x = get_var(stream) if a1 else get_byte(stream)
                speed_y = get_var(stream) if a2 else get_byte(stream)
                ops.append(("SO_STEP_DIST", {"speed_x": speed_x, "speed_y": speed_y }))

            case 0x03:
                sound = get_var(stream) if a1 else get_byte(stream)
                ops.append(("SO_SOUND", {"sound": sound}))

            case 0x04:
                frame = get_var(stream) if a1 else get_byte(stream)
                ops.append(("SO_WALK_ANIMATION", {"walk_frame": frame}))

            case 0x05:
                start_frame = get_var(stream) if a1 else get_byte(stream)
                stop_frame = get_var(stream) if a2 else get_byte(stream)
                ops.append(("SO_TALK_ANIMATION", {"talk_start_frame": start_frame, "talk_stop_frame": stop_frame}))

            case 0x06:
                frame = get_var(stream) if a1 else get_byte(stream)
                ops.append(("SO_STAND_ANIMATION", {"stand_frame": frame}))

            case 0x07:
                unk1 = get_var(stream) if a1 else get_byte(stream)
                unk2 = get_var(stream) if a2 else get_byte(stream)
                unk3 = get_var(stream) if a3 else get_byte(stream)
                ops.append(("SO_ANIMATION", {"unk1": unk1, "unk2": unk2, "unk3": unk3}))

            case 0x08:
                ops.append(("SO_DEFAULT", {}))

            case 0x09:
                ops.append(("SO_ELEVATION", {"elevation": get_var(stream) if a1 else get_signed_word(stream)}))

            case 0x0a:
                ops.append(("SO_ANIMATION_DEFAULT", {}))

            case 0x0b:
                idx = get_var(stream) if a1 else get_byte(stream)
                val = get_var(stream) if a2 else get_byte(stream)
                ops.append(("SO_PALETTE", {"idx": idx, "val": val}))

            case 0x0c:
                ops.append(("SO_TALK_COLOR", {"color": get_var(stream) if a1 else get_byte(stream)}))

            case 0x0d:
                ops.append(("SO_ACTOR_NAME", {"name": get_text_string(stream)}))

            case 0x0e:
                ops.append(("SO_INIT_ANIMATION", {"init_frame": get_var(stream) if a1 else get_byte(stream)}))

            case 0x10:
                ops.append(("SO_ACTOR_WIDTH", {"width": get_var(stream) if a1 else get_byte(stream)}))

            case 0x11:
                scale = get_var(stream) if a1 else get_byte(stream) 
                ops.append(("SO_ACTOR_SCALE", {"scale_x": scale, "scale_y": scale}))

            case 0x12:
                ops.append(("SO_NEVER_ZCLIP", {}))

            case 0x13:
                ops.append(("SO_ALWAYS_ZCLIP", {"force": get_var(stream) if a1 else get_byte(stream)}))

            case 0x14:
                ops.append(("SO_IGNORE_BOXES", {}))

            case 0x15:
                ops.append(("SO_FOLLOW_BOXES", {}))

            case 0x16:
                ops.append(("SO_ANIMATION_SPEED", {"anim_speed": get_var(stream) if a1 else get_byte(stream)}))

            case 0x17:
                ops.append(("SO_SHADOW", {"shadow_mode": get_var(stream) if a1 else get_byte(stream)}))

            case _:
                ops.append(("SO_UNK", {}))

        opcode = get_byte(stream)
    return ops

def parse_stringops(stream: IOBase):
    opcode = get_byte(stream) 
    a1 = True if opcode & 0x80 else False 
    a2 = True if opcode & 0x40 else False 
    a3 = True if opcode & 0x20 else False 
    func = "unk"
    args = {}
    result = None 
    match opcode & 0x1f:
        case 1:
            func = "loadstring"
            index = get_var(stream) if a1 else get_byte(stream)
            string = get_text_string(stream)
            args = {"index": index, "string": string}
        case 2:
            func = "copystring"
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a2 else get_byte(stream)
            args = {"a": a, "b": b}
        case 3:
            func = "setstringchar"
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a2 else get_byte(stream)
            c = get_var(stream) if a3 else get_byte(stream)
            args = {"a": a, "b": b, "c": c}
        case 4:
            func = "getstringchar"
            result = get_result_var(stream)
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a2 else get_byte(stream)
            args = {"a": a, "b": b}
        case 5:
            func = "createemptystring"
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a2 else get_byte(stream)
            args = {"a": a, "b": b}
        case _:
            pass
    return func, args, result


def parse_cursorcommand(stream: IOBase):
    opcode = get_byte(stream) 
    a1 = True if opcode & 0x80 else False
    a2 = True if opcode & 0x40 else False
    a3 = True if opcode & 0x20 else False
    op = "SO_UNK"
    args = {}
    match opcode & 0x1f:
        case 1:
            op = "SO_CURSOR_ON"
        case 2:
            op = "SO_CURSOR_OFF"
        case 3:
            op = "SO_USERPUT_ON"
        case 4:
            op = "SO_USERPUT_OFF"
        case 5:
            op = "SO_CURSOR_SOFT_ON"
        case 6:
            op = "SO_CURSOR_SOFT_OFF"
        case 7:
            op = "SO_USERPUT_SOFT_ON"
        case 8:
            op = "SO_USERPUT_SOFT_OFF"
        case 10:
            op = "SO_CURSOR_IMAGE"
            index = get_var(stream) if a1 else get_byte(stream)
            char = get_var(stream) if a2 else get_byte(stream)
            args = {"index": index, "char": char}
        case 11:
            op = "SO_CURSOR_HOTSPOT"
            index = get_var(stream) if a1 else get_byte(stream)
            x= get_var(stream) if a2 else get_byte(stream)
            y = get_var(stream) if a3 else get_byte(stream)
            args = {"index": index, "x": x, "y": y}
        case 12:
            op = "SO_CURSOR_SET"
            index = get_var(stream) if a1 else get_byte(stream)
            args = {"index": index}
        case 13:
            op = "SO_CHARSET_SET"
            charset = get_var(stream) if a1 else get_byte(stream)
            args = {"charset": charset}
        case 14:
            op = "SO_CHARSET_UNK"
            table = get_vararg(stream)
            args = {"table": table}
        case _:
            pass
    return op, args

def parse_matrixops(stream: IOBase):
    opcode = get_byte(stream)
    a1 = True if opcode & 0x80 else False
    a2 = True if opcode & 0x40 else False
    a3 = True if opcode & 0x20 else False
    op = ""
    args = {}
    match opcode & 0x1f:
        case 1:
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a2 else get_byte(stream)
            op = "setBoxFlags"
            args = {"box": a, "val": b}
        case 2:
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a2 else get_byte(stream)
            op = "setBoxScale"
            args = {"box": a, "val": b}
        case 3:
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a2 else get_byte(stream)
            op = "setBoxScaleAlt"
            args = {"box": a, "val": b}
        case 4:
            op = "createBoxMatrix"
        case _:
            pass
    return op, args


def parse_roomops(stream: IOBase) -> tuple[str, dict[str, Any]]:
    op = "SO_UNK"
    args = {}
    opcode = get_byte(stream)
    a1 = True if opcode & 0x80 else False
    a2 = True if opcode & 0x80 else False
    a3 = True if opcode & 0x80 else False
    match opcode & 0x1f:
        case 1:
            op = "SO_ROOM_SCROLL"
            a = get_var(stream) if a1 else get_signed_word(stream)
            b = get_var(stream) if a2 else get_signed_word(stream)
            args = {"camera_min_x": a, "camera_max_x": b}
        case 2:
            op = "SO_ROOM_COLOR"
            val = get_var(stream) if a1 else get_signed_word(stream) 
            idx = get_var(stream) if a2 else get_signed_word(stream)
            args = {"val": val, "idx": idx}
        case 3:
            op = "SO_ROOM_SCREEN"
            b= get_var(stream) if a1 else get_signed_word(stream) 
            h = get_var(stream) if a2 else get_signed_word(stream)
            args = {"b": b, "h": h}
        
        case 4:
            op = "SO_ROOM_PALETTE"
            index_min= get_var(stream) if a1 else get_signed_word(stream) 
            index_max = get_var(stream) if a2 else get_signed_word(stream)
            # FIXME: check for v5
            args = {"index_min": index_min, "index_max": index_max}
        
        case 5:
            op = "SO_ROOM_SHAKE_ON"
        
        case 6:
            op = "SO_ROOM_SHAKE_OFF"

        case 7:
            op = "SO_ROOM_SCALE"
            a= get_var(stream) if a1 else get_byte(stream) 
            b = get_var(stream) if a2 else get_byte(stream)
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            c= get_var(stream) if a1 else get_byte(stream) 
            d= get_var(stream) if a2 else get_byte(stream) 
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            e = get_var(stream) if a2 else get_byte(stream) 
            args = {"a": a, "b": b, "c": c, "d": d, "e": e}

        case 8:
            op = "SO_ROOM_INTENSITY"
            a= get_var(stream) if a1 else get_byte(stream) 
            b = get_var(stream) if a2 else get_byte(stream)
            c = get_var(stream) if a3 else get_byte(stream)
            args = {"a": a, "b": b, "c": c}

        case 9:
            op = "SO_ROOM_SAVEGAME"
            flag = get_var(stream) if a1 else get_byte(stream)
            slot = get_var(stream) if a2 else get_byte(stream)
            args = {"flag": flag, "slot": slot}

        case 10:
            op = "SO_ROOM_FADE"
            a = get_var(stream) if a1 else get_signed_word(stream)
            args = {"a": a}

        case 11:
            op = "SO_RGB_ROOM_INTENSITY"
            a = get_var(stream) if a1 else get_byte(stream) 
            b = get_var(stream) if a2 else get_byte(stream)
            c = get_var(stream) if a3 else get_byte(stream)
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            d = get_var(stream) if a1 else get_byte(stream) 
            e = get_var(stream) if a2 else get_byte(stream)
            args = {"a": a, "b": b, "c": c, "d": d, "e": e}

        case 12:
            op = "SO_ROOM_SHADOW"
            a = get_var(stream) if a1 else get_byte(stream) 
            b = get_var(stream) if a2 else get_byte(stream)
            c = get_var(stream) if a3 else get_byte(stream)
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            d = get_var(stream) if a1 else get_byte(stream) 
            e = get_var(stream) if a2 else get_byte(stream)
            args = {"a": a, "b": b, "c": c, "d": d, "e": e}
        case 13:
            op = "SO_SAVE_STRING"

        case 14:
            op = "SO_LOAD_STRING"

        case 15:
            op = "SO_ROOM_TRANSFORM"
            a = get_var(stream) if a1 else get_byte(stream)
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            b = get_var(stream) if a1 else get_byte(stream)
            c = get_var(stream) if a2 else get_byte(stream)
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            d = get_var(stream) if a1 else get_byte(stream)
            args = {"a": a, "b": b, "c": c, "d": d}
        
        case 16:
            op = "SO_CYCLE_SPEED"
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a1 else get_byte(stream)
            args = {"a": a, "b": b}
        case _:
            pass

    return op, args

def parse_systemops(stream: IOBase) -> str | None:
    op = get_byte(stream)
    match op:
        case 1:
            return "SO_RESTART"
        case 2:
            return "SO_PAUSE"
        case 3:
            return "SO_QUIT"
    return None

def parse_saverestoreverbs(stream: IOBase) -> tuple[str | None, dict[str, Any]]:
    opcode = get_byte(stream)
    verb_id_start = get_var(stream) if opcode & 0x80 else get_byte(stream)
    verb_id_end = get_var(stream) if opcode & 0x40 else get_byte(stream)
    save_id = get_var(stream) if opcode & 0x20 else get_byte(stream)
    args = {"verb_id_start": verb_id_start, "verb_id_end": verb_id_end, "save_id": save_id}
    match opcode & 0x1f:
        case 0x01:
            return "SO_SAVE_VERBS", args 
        case 0x02:
            return "SO_RESTORE_VERBS", args
        case 0x03:
            return "SO_DELETE_VERBS", args

    return None, args



def get_text_string(stream: IOBase) -> bytes:
    orig = stream.tell()
    result = bytearray()
    test = get_byte(stream)
    while test != 0:
        if test == 0xff or test == 0xfe:
            test = get_byte(stream)
            match test:
                case 1:
                    result.extend(b"{{newline()}}")
                case 2:
                    result.extend(b"{{keepText()}}")
                case 3:
                    result.extend(b"{{wait()}}")
                case 4:
                    var = get_var(stream)
                    result.extend(b"{{getInt(" + str(var).encode('utf8') + b"}}")
                case 5:
                    var = get_var(stream)
                    result.extend(b"{{getVerb(" + str(var).encode('utf8') + b"}}")
                case 6:
                    var = get_var(stream)
                    result.extend(b"{{getName(" + str(var).encode('utf8') + b"}}")
                case 7:
                    var = get_var(stream)
                    result.extend(b"{{getString(" + str(var).encode('utf8') + b"}}")
                case 9:
                    anim = get_signed_word(stream)
                    result.extend(b"{{startAnim(" + str(anim).encode('utf8') + b"}}")
                case 10:
                    print("Nightmare instruction hit")
                case 12:
                    color = get_signed_word(stream)
                    result.extend(b"{{setColor(" + str(color).encode('utf8') + b"}}")
                case 14:
                    font = get_signed_word(stream)
                    result.extend(b"{{setFont(" + str(font).encode('utf8') + b"}}")

        else:
            result.append(test)
        test = get_byte(stream)

    return bytes(result)


def parse_string(stream: IOBase) -> list[tuple[str, dict[str, Any]]]:
    opcode = get_byte(stream)
    ops: list[tuple[str, dict[str, Any]]] = []
    while opcode != 0xff:
        a1 = True if opcode & 0x80 else False
        a2 = True if opcode & 0x40 else False
        a3 = True if opcode & 0x20 else False
        a4 = True if opcode & 0x10 else False
        match opcode & 0x0f:
            case 0x00:
                xpos = get_var(stream) if a1 else get_signed_word(stream)
                ypos = get_var(stream) if a2 else get_signed_word(stream)
                ops.append(("SO_AT", {"xpos": xpos, "ypos": ypos }))

            case 0x01:
                color = get_var(stream) if a1 else get_byte(stream)
                ops.append(("SO_COLOR", {"color": color}))

            case 0x02:
                right = get_var(stream) if a1 else get_signed_word(stream)
                ops.append(("SO_CLIPPED", {"right": right}))
            
            case 0x03:
                width = get_var(stream) if a1 else get_signed_word(stream)
                height = get_var(stream) if a2 else get_signed_word(stream)
                ops.append(("SO_ERASE", {"width": width, "height": height}))

            case 0x04:
                ops.append(("SO_CENTER", {}))

            case 0x06:
                ops.append(("SO_LEFT", {}))
            
            case 0x07:
                ops.append(("SO_OVERHEAD", {}))

            case 0x08:
                offset =  get_var(stream) if a1 else get_signed_word(stream)
                delay =  get_var(stream) if a2 else get_signed_word(stream)
                ops.append(("SO_SAY_VOICE", {"offset": offset, "delay": delay}))

            case 0x0f:
                ops.append(("SO_TEXTSTRING", {"str": get_text_string(stream)})) 
                return ops
            case _:
                ops.append(("SO_UNK", {}))

        opcode = get_byte(stream)
    return ops

def parse_verbops(stream: IOBase):
    ops: list[tuple[str, dict[str, str|int|bytes]]] = []
    opcode = get_byte(stream)
    a1 = True if opcode & 0x80 else False
    a2 = True if opcode & 0x40 else False
    a3 = True if opcode & 0x20 else False
    while opcode != 0xff:
        match opcode & 0x1f:
            case 1:
                op = "SO_VERB_IMAGE"
                a = get_var(stream) if a1 else get_signed_word(stream)
                ops.append((op, {"obj": a}))
            case 2:
                op = "SO_VERB_NAME"
                text = get_text_string(stream)
                ops.append((op, {"text": text}))
            case 3:
                op = "SO_VERB_COLOR"
                color = get_var(stream) if a1 else get_byte(stream)
                ops.append((op, {"color": color}))
            case 4:
                op = "SO_VERB_HICOLOR"
                color = get_var(stream) if a1 else get_byte(stream)
                ops.append((op, {"color": color}))
            case 5:
                op = "SO_VERB_AT"
                x = get_var(stream) if a1 else get_signed_word(stream)
                y = get_var(stream) if a1 else get_signed_word(stream)
                ops.append((op, {"x": x, "y": y}))
            case 6:
                op = "SO_VERB_ON"
                ops.append((op, {}))
            case 7:
                op = "SO_VERB_OFF"
                ops.append((op, {}))
            case 8:
                op = "SO_VERB_DELETE"
                ops.append((op, {}))
            case 9:
                op = "SO_VERB_NEW"
                ops.append((op, {}))
            case 16:
                op = "SO_VERB_DIMCOLOR"
                color = get_var(stream) if a1 else get_byte(stream)
                ops.append((op, {"color": color}))
            case 17:
                op = "SO_VERB_DIM"
                ops.append((op, {}))
            case 18:
                op = "SO_VERB_KEY"
                key = get_var(stream) if a1 else get_byte(stream)
                ops.append((op, {"key": key}))
            case 19:
                op = "SO_VERB_CENTER"
                ops.append((op, {}))
            case 20:
                op = "SO_VERB_NAME_STR"
                idx = get_var(stream) if a1 else get_signed_word(stream)
                ops.append((op, {"idx": idx}))
            case 22:
                op = "SO_VERB_ASSIGN_OBJECT"
                obj = get_var(stream) if a1 else get_signed_word(stream)
                room = get_var(stream) if a2 else get_byte(stream)
                ops.append((op, {"obj": obj, "room": room}))

            case 23:
                op = "SO_VERB_BACKCOLOR"
                color = get_var(stream) if a1 else get_byte(stream)
            case _:
                op = "SO_UNK"

        opcode = get_byte(stream)
        a1 = True if opcode & 0x80 else False
        a2 = True if opcode & 0x40 else False
        a3 = True if opcode & 0x20 else False
    return ops



def parse_wait(stream: IOBase) -> dict[str, str]:
    opcode = get_byte(stream)
    a1 = True if opcode & 0x80 else False

    args = {}
    match opcode & 0x1f:
        case 1: 
            actor = get_var(stream) if a1 else get_byte(stream)
            args = {"op": "SO_WAIT_FOR_ACTOR", "actor": actor}
        case 2:
            args = {"op":"SO_WAIT_FOR_MESSAGE"}
        case 3:
            args = {"op": "SO_WAIT_FOR_CAMERA"}
        case 4:
            args = {"op": "SO_WAIT_FOR_SENTENCE"}
        case _:
            args = {"op": "SO_UNK"}
    return args


def parse_expression(stream: IOBase) -> str:
    opcode = get_byte(stream)
    a1 = True if opcode & 0x80 else False
    stack = []
    while opcode != 0xff:
        match opcode & 0x1f:
            case 1:
                stack.append(get_var(stream) if a1 else get_signed_word(stream))
            case 2:
                x = stack.pop()
                y = stack.pop()
                stack.append(f"({y} + {x})")
            case 3:
                x = stack.pop()
                y = stack.pop()
                stack.append(f"({y} - {x})")
            case 4:
                x = stack.pop()
                y = stack.pop()
                stack.append(f"({y} * {x})")
            case 5:
                x = stack.pop()
                y = stack.pop()
                stack.append(f"({y} / {x})")
            case 6:
                instr = get_v4_instr(stream)
                stack.append(f"({str(instr)})")
        opcode = get_byte(stream)
        a1 = True if opcode & 0x80 else False
    if len(stack) != 1:
        print(f"WARNING: stack contains {stack}")
        return "BAD"
    return stack.pop()


# ported from scummvm/engines/scumm/script_v5.cpp
def get_v4_instr(stream: IOBase) -> V4Instr | None:
    start = stream.tell()
    opcode = get_byte_or_none(stream)
    if opcode is None:
        return None
    a1 = True if (opcode & 0x80) else False
    a2 = True if (opcode & 0x40) else False
    a3 = True if (opcode & 0x20) else False

    result = V4Instr(opcode)

    match opcode:
        case 0x00 | 0xa0:
            result.name = "stopObjectCode"

        case 0x01 | 0x21 | 0x41 | 0x61 | 0x81 | 0xa1 | 0xc1 | 0xe1:
            result.name = "putActor"
            act = get_var(stream) if a1 else get_byte(stream)
            x = get_var(stream) if a2 else get_signed_word(stream)
            y = get_var(stream) if a3 else get_signed_word(stream)
            result.args = {"act": act, "x": x, "y": y}
        
        case 0x02 | 0x82:
            result.name = "startMusic"
            cmd = get_var(stream) if a1 else get_byte(stream)
            result.args = {"cmd": cmd}
        
        case 0x03 | 0x83:
            result.name = "getActorRoom"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}
        
        case 0x04 | 0x84:
            result.name = "isGreaterEqual"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}
        
        case 0x05 | 0x25 | 0x45 | 0x65 | 0x85 | 0xa5 | 0xc5 | 0xe5:
            result.name = "drawObject"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            x = get_var(stream) if a2 else get_signed_word(stream)
            y = get_var(stream) if a3 else get_signed_word(stream)
            result.args = {"obj": obj, "x": x, "y": y}

        case 0x06 | 0x86:
            result.name = "getActorElevation"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x07 | 0x47 | 0x87 | 0xc7:
            result.name = "setState"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            state = get_var(stream) if a2 else get_byte(stream)
            result.args = {"obj": obj, "state": state}

        case 0x08 | 0x88:
            result.name = "isNotEqual"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}

        case 0x09 | 0x49 | 0x89 | 0xc9:
            result.name = "faceActor"
            act = get_var(stream) if a1 else get_byte(stream)
            obj = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"act": act, "obj": obj}

        case 0x0a | 0x2a | 0x4a | 0x6a | 0x8a | 0xaa | 0xca | 0xea:
            result.name = "startScript"
            script = get_var(stream) if a1 else get_byte(stream)
            var = get_vararg(stream)
            recursive = a2
            freeze_resistant = a3
            result.args = {"script": script, "var": var, "recursive": recursive, "freeze_resistant": freeze_resistant}

        case 0x0b | 0x4b | 0x8b | 0xcb:
            result.name = "getVerbEntrypoint"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            entry = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"obj": obj, "entry": entry}

        case 0x0c | 0x8c:
            result.name = "resourceRoutines"
            opr = get_byte(stream)
            a1 = True if opr & 0x80 else False 
            a2 = True if opr & 0x40 else False 
            op = opr & 0x3f
            resid = 0
            resid2 = 0
            resid3 = 0
            if op != 17:
                resid = get_var(stream) if a1 else get_byte(stream)
            if op == 20:
                resid2 = get_var(stream) if a2 else get_signed_word(stream)
            elif op == 36:
                resid2 = get_var(stream) if a2 else get_signed_word(stream)
                resid3 = get_byte(stream)
            elif op == 37:
                resid3 = get_var(stream) if a2 else get_byte(stream)

            result.args = {"op": op, "resid": resid, "resid2": resid2, "resid3": resid3}

        case 0x0d | 0x4d | 0x8d | 0xcd:
            result.name = "walkActorToActor"
            nr = get_var(stream) if a1 else get_byte(stream)
            nr2 = get_var(stream) if a2 else get_byte(stream)
            dist = get_byte(stream)
            result.args = {"nr": nr, "nr2": nr2, "dist": dist}

        case 0x0e | 0x4e | 0x8e | 0xce:
            result.name = "putActorAtObject"
            act = get_var(stream) if a1 else get_byte(stream)
            obj = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"act": act, "obj": obj}

        case 0x0f | 0x4f | 0x8f | 0xcf:
            result.name = "ifState"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            val = get_var(stream) if a2 else get_byte(stream)
            offset = get_signed_word(stream)
            result.args = {"obj": obj, "val": val, "offset": offset}
            
        #case 0x0f | 0x8f:
        #    result.name = "getObjectState"
        #    result.target = get_result_var(stream)
        #    obj = get_var(stream) if a1 else get_signed_word(stream)
        #    result.args = {"obj": obj}

        case 0x10 | 0x90:
            result.name = "getObjectOwner"
            result.target = get_result_var(stream)
            obj = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"obj": obj}

        case 0x11 | 0x51 | 0x91 | 0xd1:
            result.name = "animateActor"
            act = get_var(stream) if a1 else get_byte(stream)
            anim = get_var(stream) if a2 else get_byte(stream)
            result.args = {"act": act, "anim": anim}

        case 0x12 | 0x92:
            result.name = "panCameraTo"
            x = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"x": x}

        case 0x13 | 0x53 | 0x93 | 0xd3:
            result.name = "actorOps"
            act = get_var(stream) if a1 else get_byte(stream)
            ops = parse_actorops(stream)
            result.args = {"act": act, "ops": ops}

        case 0x14 | 0x94:
            result.name = "print"
            act = get_var(stream) if a1 else get_byte(stream)
            ops = parse_string(stream)
            result.args = {"act": act, "ops": ops}

        case 0x15 | 0x55 | 0x95 | 0xd5:
            result.name = "actorFromPos"
            result.target = get_result_var(stream)
            x = get_var(stream) if a1 else get_signed_word(stream)
            y = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"x": x, "y": y}

        case 0x16 | 0x96:
            result.name = "getRandomNr"
            result.target = get_result_var(stream)
            max = get_var(stream) if a1 else get_byte(stream)
            result.args = {"max": max}

        case 0x17 | 0x97:
            result.name = "and"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}

        case 0x18:
            result.name = "jumpRelative"
            offset = get_signed_word(stream)
            result.args = {"offset": offset}

        case 0x19 | 0x39 | 0x59 | 0x79 | 0x99 | 0xb9 | 0xd9 | 0xf9:
            result.name = "doSentence"
            verb = get_var(stream) if a1 else get_byte(stream)
            obj_a, obj_b = None, None
            if (verb != 0xfe):
                obj_a = get_var(stream) if a2 else get_signed_word(stream) 
                obj_b = get_var(stream) if a3 else get_signed_word(stream) 
            result.args = {"verb": verb, "obj_a": obj_a, "obj_b": obj_b}
            
        case 0x1a | 0x9a: # move
            result.name = "move"
            result.target= get_result_var(stream)
            value = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"value": value}
            result.repr = lambda x: f"{x.target} = {repr(x.args['value'])}"

        case 0x1b | 0x9b:
            result.name = "multiply"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} *= {repr(x.args['a'])}"

        case 0x1c | 0x9c:
            result.name = "startSound"
            sound = get_var(stream) if a1 else get_byte(stream)
            result.args = {"sound": sound}

        case 0x1d | 0x9d:
            result.name = "ifclassOfIs"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            classes = []
            test = get_byte(stream)
            while test != 0xff:
                a1 = True if test & 0x80 else False
                classes.append(get_var(stream) if a1 else get_signed_word(stream))
                test = get_byte(stream) 
            offset = get_signed_word(stream)
            result.args=  {"obj": obj, "classes": classes, "offset": offset}

        case 0x1e | 0x3e | 0x5e | 0x7e | 0x9e | 0xbe | 0xde | 0xfe:
            result.name = "walkActorTo"
            act = get_var(stream) if a1 else get_byte(stream)
            x = get_var(stream) if a2 else get_signed_word(stream)
            y = get_var(stream) if a3 else get_signed_word(stream)
            result.args = {"act": act, "x": x, "y": y}

        case 0x1f | 0x5f | 0x9f | 0xdf:
            result.name = "isActorInBox"
            act = get_var(stream) if a1 else get_byte(stream)
            box = get_var(stream) if a2 else get_byte(stream)
            offset = get_signed_word(stream)
            result.args = {"act": act, "box": box, "offset": offset}

        case 0x20:
            result.name = "stopMusic"

        case 0x22 | 0xa2:
            result.name = "saveLoadGame"
            result.target = get_result_var(stream)
            op = get_var(stream) if a1 else get_byte(stream)
            result.args = {"op": op}
#                act = get_var(stream) if a1 else get_byte(stream)
#                print(f"{ptr:04x}: getAnimCounter(act={act})")

        case 0x23 | 0xa3:
            result.name = "getActorY"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"act": act}

        case 0x24 | 0x64 | 0xa4 | 0xe4:
            result.name = "loadRoomWithEgo"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            room = get_var(stream) if a2 else get_byte(stream)
            x = get_signed_word(stream)
            y = get_signed_word(stream)
            result.args = {"obj": obj, "room": room, "x": x, "y": y}
        
        #case 0x25 | 0x65 | 0xa5 | 0xe5:
        #    obj = get_var(stream) if a1 else get_signed_word(stream)
        #    room = get_var(stream) if a2 else get_byte(stream)
        #    print(f"{ptr:04x}: pickupObject(obj={obj}, room={room})")
        
        case 0x25 | 0x45 | 0x65 | 0x85 | 0xa5 | 0xc5 | 0xe5:
            result.name = "drawObject"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            x = get_var(stream) if a2 else get_signed_word(stream)
            y = get_var(stream) if a3 else get_signed_word(stream)
            result.args = {"obj": obj, "x": x, "y": y}

        case 0x26 | 0xa6:
            result.name = "setVarRange"
            result.target = get_result_var(stream)
            count = get_byte(stream)
            values = []
            for i in range(count):
                values.append(get_signed_word(stream) if a1 else get_byte(stream))
            result.args = {"values": values}

        case 0x27:
            result.name = "stringOps"
            func, args, target  = parse_stringops(stream)
            result.target = target
            result.args = {"op": func, "args": args}

        case 0x28:
            result.name = "equalZero"
            a = get_var(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "offset": offset}
            
        case 0x29 | 0x69 | 0xa9 | 0xe9:
            result.name = "setOwner"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            owner = get_var(stream) if a2 else get_byte(stream)
            result.args = {"obj": obj, "owner": owner}

        case 0x2b:
            result.name = "delayVariable"
            var = get_var(stream)
            result.args = {"var": var}

        case 0x2c:
            result.name = "cursorCommand"
            op, args = parse_cursorcommand(stream)
            result.args = {"op": op, "args": args}
        
        case 0x2d | 0x6d | 0xad | 0xed:
            result.name = "putActorInRoom"
            act = get_var(stream) if a1 else get_byte(stream)
            room = get_var(stream) if a2 else get_byte(stream)
            result.args = {"act": act, "room": room}

        case 0x2e:
            result.name = "delay"
            delay = get_byte(stream)
            delay |= get_byte(stream) << 8
            delay |= get_byte(stream) << 16
            result.args = {"delay": delay}

        case 0x2f | 0x6f | 0xaf | 0xef:
            result.name = "ifNotState"
            a = get_var(stream) if a1 else get_signed_word(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}

        case 0x30 | 0xb0:
            result.name = "matrixOps"
            op, args = parse_matrixops(stream)
            result.args = {"op": op, "args": args}
    
        case 0x31 | 0xb1:
            result.name = "setInventoryCount"
            result.target = get_result_var(stream)
            owner = get_var(stream) if a1 else get_byte(stream)
            result.args = {"owner": owner}

        case 0x32 | 0xb2:
            result.name = "setCameraAt"
            x_pos = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"x_pos": x_pos}

        case 0x33 | 0x73 | 0xb3 | 0xf3:
            result.name = "roomOps"
            op, args = parse_roomops(stream)
            result.args = {"op": op, "args": args}

        case 0x34 | 0x74 | 0xb4 | 0xf4:
            result.name = "getDist"
            result.target = get_result_var(stream)
            obj_a = get_var(stream) if a1 else get_signed_word(stream)
            obj_b = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"obj_a": obj_a, "obj_b": obj_b}

        case 0x35 | 0x75 | 0xb5 | 0xf5:
            result.name = "findObject"
            result.target = get_result_var(stream)
            x = get_var(stream) if a1 else get_byte(stream)
            y = get_var(stream) if a2 else get_byte(stream)
            result.args = {"x": x, "y": y}

        case 0x36 | 0x76 | 0xb6 | 0xf6:
            result.name = "walkActorToObject"
            act = get_var(stream) if a1 else get_byte(stream)
            obj = get_var(stream) if a2 else get_signed_word(stream)
            result.args={"act": act, "obj": obj}

        case 0x37 | 0x77 | 0xb7 | 0xf7:
            result.name = "startObject"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            script = get_var(stream) if a2 else get_byte(stream)
            args = get_vararg(stream)
            result.args = {"obj": obj, "script": script, "args": args}

        case 0x38 | 0xb8:
            result.name = "isLessEqual"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}
        
        case 0x3a | 0xba: # subtract
            result.name = "subtract"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} -= {repr(x.args['a'])}"

        case 0x3b | 0xbb:
            result.name = "getActorScale"
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x3c | 0xbc:
            result.name = "stopSound"
            sound = get_var(stream) if a1 else get_byte(stream)
            result.args = {"sound": sound}

        case 0x3d | 0x7d | 0xbd | 0xfd:
            result.name = "findInventory"
            result.target = get_result_var(stream)
            x = get_var(stream) if a1 else get_byte(stream)
            y = get_var(stream) if a2 else get_byte(stream)
            result.args = {"x": x, "y": y}

        case 0x3f | 0x7f | 0xbf | 0xff:
            result.name = "drawBox"
            x = get_var(stream) if a1 else get_signed_word(stream)
            y = get_var(stream) if a2 else get_signed_word(stream)
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            a3 = True if opcode & 0x20 else False
            x2 = get_var(stream) if a1 else get_signed_word(stream)
            y2 = get_var(stream) if a2 else get_signed_word(stream)
            color = get_var(stream) if a3 else get_byte(stream)
            result.args = {"x": x, "y": y, "x2": x2, "y2": y2, "color": color}

        case 0x40:
            result.name = "cutscene"
            result.args = {"args": get_vararg(stream)}

        case 0x42 | 0xc2:
            result.name = "chainScript"
            script = get_var(stream) if a1 else get_byte(stream)
            args = get_vararg(stream)
            result.args = {"script": script, "args": args}

        case 0x43 | 0xc3:
            result.name = "getActorX"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"act": act}

        case 0x44 | 0xc4:
            result.name = "isLess"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}

        case 0x46: # increment
            result.name = "increment"
            result.target = get_result_var(stream)
            result.repr = lambda x: f"{x.target} += 1"
        
        case 0x48 | 0xc8:
            result.name = "isEqual"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)

            result.args = {"a": a, "b": b, "offset": offset}
           
        case 0x50 | 0xd0:
            result.name = "pickupObject"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"obj": obj}

        case 0x52 | 0xd2:
            result.name = "actorFollowCamera"
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x54 | 0xd4:
            result.name = "setObjectName"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            name = get_text_string(stream)
            result.args = {"obj": obj, "name": name}

        case 0x56 | 0xd6:
            result.name = "getActorMoving"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x57 | 0xd7:
            result.name = "or"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} |= {repr(x.args['a'])}"

        case 0x58:
            test = get_byte(stream)
            result.name = f"{'begin' if test else 'end'}Override"

        case 0x5a | 0xda: # add
            result.name = "add"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} += {repr(x.args['a'])}"
        
        case 0x5b | 0xdb: # divide
            result.name = "divide"
            result.target= get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} /= {repr(x.args['a'])}"

        case 0x5c | 0xdc:
            result.name = "oldRoomEffect"
            op = get_byte(stream)
            effect = None
            if op & 0x1f == 3:
                effect = get_var(stream) if (op & 0x80) else get_signed_word(stream)
            result.args = {"op": op, "effect": effect}

        case 0x5d | 0xdd:
            result.name = "setClass"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            cls = get_vararg(stream)
            result.args = {"obj": obj, "cls": cls}

        case 0x60 | 0xe0:
            result.name = "freezeScripts"
            scr = get_var(stream) if a1 else get_byte(stream)
            result.args = {"scr": scr}

        case 0x62 | 0xe2:
            result.name = "stopScript"
            idx = get_var(stream) if a1 else get_byte(stream)
            result.args = {"idx": idx}

        case 0x63 | 0xe3:
            result.name = "getActorFacing"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x68 | 0xe8:
            result.name = "isScriptRunning"
            result.target = get_result_var(stream)
            idx = get_var(stream) if a1 else get_byte(stream)
            result.args = {"idx": idx}

        case 0x6c | 0xec:
            result.name = "getActorWidth"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x70 | 0xf0:
            result.name = "lights"
            lights = get_var(stream) if a1 else get_byte(stream)
            x_strips = get_byte(stream)
            y_strips = get_byte(stream)
            result.args = {"lights": lights, "x_strips": x_strips, "y_strips": y_strips}

        case 0x71 | 0xf1:
            result.name = "getActorCostume"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x72 | 0xf2:
            result.name = "loadRoom"
            room = get_var(stream) if a1 else get_byte(stream)
            result.args = {"room": room}

        case 0x78 | 0xf8:
            result.name = "isGreater"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}

        case 0x7a | 0xfa:
            result.name = "verbOps"
            verb = get_var(stream) if a1 else get_byte(stream)
            ops = parse_verbops(stream)
            result.args = {"verb": verb, "ops": ops}

        case 0x7b | 0xfb:
            result.name = "getActorWalkBox"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x7c | 0xfc:
            result.name = "isSoundRunning"
            result.target = get_result_var(stream)
            snd = get_var(stream) if a1 else get_byte(stream)
            args = {"snd": snd}

        case 0x80:
            result.name = "breakHere"

        case 0x98:
            result.name = "systemOps"
            op = parse_systemops(stream)
            args = {"op": op}

        case 0xa8:
            result.name = "notEqualZero"
            a = get_var(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "offset": offset}

        case 0xab:
            result.name = "saveRestoreVerbs"
            op, args = parse_saverestoreverbs(stream)
            result.args = {"op": op, "args": args}

        case 0xac: # expression
            result.name = "expression"
            result .target = get_result_var(stream)
            expr = parse_expression(stream)
            result.args = {"expr": expr}
            result.repr = lambda x: f"[expr] {x.target} = {x.args['expr']}"

        case 0xae:
            result.name = "wait"
            result.args = parse_wait(stream)

        case 0xc0:
            result.name = "endCutscene"

        case 0xc6: # decrement
            result.name = "decrement"
            result.target = get_result_var(stream)
            result.repr = lambda x: f"{x.target} -= 1"
     


        case 0xcc:
            result.name = "pseudoRoom"
            val = get_byte(stream)
            src_in = get_byte(stream)
            sources = []
            while src_in != 0x00:
                sources.append(src_in)
                src_in = get_byte(stream)
            result.args = {"val": val, "sources": sources}

 
        case 0xd8:
            result.name = "printEgo"
            string = parse_string(stream)
            result.args = {"string": string}

        case _:
            result.name = "unk"
            result.repr = lambda x: f"unk(0x{x.opcode:02x})"

    end = stream.tell()
    stream.seek(start)
    result.raw = stream.read(end-start)
    return result





def scumm_v4_tokenizer(data: bytes, offset: int=0, print_offset: int=0, dump_all: bool=True, print_data: bool=False, print_prefix: str=""):
    ptr = 0

    stream = BytesIO(data)
    stream.seek(offset)
    result = []
    while True:
        ptr = stream.tell()
        instr = get_v4_instr(stream)
        if instr is None:
            break
        result.append((ptr, instr))
        if print_data:
            print(f"{print_prefix}[{ptr+print_offset:04x}] {str(instr)}")
        if not dump_all and instr.name == "stopObjectCode":
            break
    return result


class SC(mrc.Block):
    data = mrc.Bytes()
    
    def get_instr(self):
        return scumm_v4_tokenizer(self.data)

class LS(mrc.Block):
    id = mrc.UInt8()
    data = mrc.Bytes()

    def get_instr(self):
        return scumm_v4_tokenizer(self.data)

class ObjectEvent(mrc.Block):
    verb_id = mrc.UInt8()
    code_offset = mrc.UInt16_LE()

class OC(mrc.Block):
    id = mrc.Int16_LE(0x00)
    unk = mrc.UInt8(0x02)
    x_pos = mrc.UInt8(0x03)
    y_pos = mrc.Bits(0x04, 0b01111111)
    parent_state = mrc.Bits(0x04, 0b10000000)
    width = mrc.UInt8(0x05)
    parent = mrc.UInt8(0x06)
    walk_x = mrc.Int16_LE(0x07)
    walk_y = mrc.Int16_LE(0x09)
    height = mrc.Bits(0x0b, 0b01111111)
    actor_dir = mrc.Bits(0x0b, 0b10000000)

    @property
    def name_offset(self):
        return self.get_field_end_offset("events") - 0x06
    

    name_raw_offset = mrc.Pointer( mrc.UInt8( 0x0c ), mrc.Ref("name_offset") )
    events = mrc.BlockField(ObjectEvent, 0x0d, stream=True, stream_end=b'\x00')
    name = mrc.CString(encoding='cp437')
    data = mrc.Bytes()
    
    def get_instr(self):
        return scumm_v4_tokenizer(self.data)

class RO(mrc.Block):
    chunks = mrc.ChunkField({b'LS': LS, b'OC': OC}, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)

class LF(mrc.Block):
    id = mrc.UInt16_LE()
    chunks = mrc.ChunkField({b'RO': RO, b'SC': SC}, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)

class LE(mrc.Block):
    chunks = mrc.ChunkField({b'LF': LF}, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)


class LEC(mrc.Block):
    chunks = mrc.ChunkField({b'LE': LE}, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)


class XORBytes(mrc.Transform):
    def __init__(self, secret, *args, **kwargs):
        self.secret = secret
        super().__init__(*args, **kwargs)

    def import_data(self, buffer: BytesReadType, parent: mrc.Block | None = None
    ) -> TransformResult:
        return TransformResult(payload=bytes([x ^ self.secret for x in buffer]), end_offset=len(buffer))
    
    def export_data(self, buffer: BytesReadType, parent: mrc.Block | None = None
    ) -> TransformResult:
        return TransformResult(payload=bytes([x ^ self.secret for x in buffer]), end_offset=len(buffer))

class RNEntry(mrc.Block):
    id = mrc.UInt8()
    name = mrc.Bytes(length=9, transform=XORBytes(0xff))

class RN(mrc.Block):
    entries = mrc.BlockField(RNEntry, stream=True)


class GlobalIndexItem(mrc.Block):
    room_id = mrc.UInt8()
    offset = mrc.UInt32_LE()

class GlobalIndex(mrc.Block):
    num_items = mrc.UInt16_LE()
    items = mrc.BlockField(GlobalIndexItem, count=mrc.Ref('num_items'))


class LFL(mrc.Block):
    chunks = mrc.ChunkField({b'RN': RN, b'0S': GlobalIndex, b'0N': GlobalIndex, b'0C': GlobalIndex}, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)



DISKS = {}
for arch in ["DISK01.LEC", "DISK02.LEC", "DISK03.LEC", "DISK04.LEC"]:
    f = bytes(x^0x69 for x in open(arch, "rb").read())
    DISKS[arch] = LEC(f)

lfl = LFL(open("000.LFL", "rb").read())
ROOM_NAMES: dict[int, str] = {
    entry.id: entry.name.strip(b'\x00').decode('utf8')
    for entry in lfl.chunks[0].obj.entries
}

GLOBAL_SCRIPT_MAP: dict[tuple[int, int], int] = {
    (gi.room_id, gi.offset + 2): i for i, gi in enumerate(lfl.chunks[2].obj.items)
}


def dump_all(print_data: bool=False):
    results = {}
    for key, disk in DISKS.items():
        if print_data:
            print(f"- {key}")
        for le in disk.chunks:
            if le.id != b'LE':
                continue
            for lf in le.obj.chunks:
                if lf.id != b'LF':
                    continue
                results[lf.obj.id] = {"name": ROOM_NAMES.get(lf.obj.id), "globals": {}, "objects": {}, "locals": {}}
                if print_data:
                    print(f"  - room {lf.obj.id} ({ROOM_NAMES.get(lf.obj.id)})")
                for i, ro in enumerate(lf.obj.chunks):
                    if ro.id == b'SC':
                        global_id = GLOBAL_SCRIPT_MAP.get((lf.obj.id, lf.obj.get_field_start_offset('chunks', i)))
                        if print_data:
                            print(f"    - global script {global_id} ({len(ro.obj.data)} bytes)")
                        results[lf.obj.id]["globals"][global_id] = scumm_v4_tokenizer(ro.obj.data, 0, dump_all=True, print_data=print_data, print_prefix="    ")
                        continue
                    elif ro.id != b'RO':
                        continue
                    for o in ro.obj.chunks:
                        if o.id == b'OC':
                            if print_data:
                                print(f"    - object script {o.obj.id} ({o.obj.name}) ({len(o.obj.events)} events, {len(o.obj.data)} bytes)")
                            results[lf.obj.id]["objects"][o.obj.id] = {"name": o.obj.name, "verbs": {}}
                            for ev in o.obj.events:
                                verb_name = verbs4.get(ev.verb_id)
                                if print_data:
                                    print(f"        - verb {ev.verb_id} ({verb_name})")
                                start_offset =o .obj.get_field_start_offset("data")+6 
                                results[lf.obj.id]["objects"][o.obj.id]["verbs"][ev.verb_id] = scumm_v4_tokenizer(o.obj.data, ev.code_offset - start_offset, dump_all=False, print_offset=start_offset, print_data=print_data, print_prefix="        ")
                        elif o.id == b'LS':
                            if print_data:
                                print(f"    - local script {o.obj.id} ({len(o.obj.data)} bytes)")
                            
                            results[lf.obj.id]["locals"][o.obj.id] = scumm_v4_tokenizer(o.obj.data, 0, dump_all=True, print_data=print_data, print_prefix="    ")
    return results



#payload = DISKS["DISK03.LEC"].chunks[0].obj.chunks[12].obj.chunks[0].obj.chunks[-4].obj.data
#for off, instr in scumm_v4_tokenizer(payload):
#    print(f"[{off:04x}] {str(instr)}")
