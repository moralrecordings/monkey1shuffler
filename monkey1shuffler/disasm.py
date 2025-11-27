from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from io import BytesIO, IOBase
from typing import Any, Literal

from mrcrowbar import utils

V4_VERBS: dict[int, str] = {
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
    255: "default",
}

V4_VARNAMES: list[str | None] = [
    # 	/* 0 */
    "VAR_RESULT",
    "VAR_EGO",
    "VAR_CAMERA_POS_X",
    "VAR_HAVE_MSG",
    # 	/* 4 */
    "VAR_ROOM",
    "VAR_OVERRIDE",
    "VAR_MACHINE_SPEED",
    "VAR_ME",
    # 	/* 8 */
    "VAR_NUM_ACTOR",
    "VAR_CURRENT_LIGHTS",
    "VAR_CURRENTDRIVE",
    "VAR_TMR_1",
    # 	/* 12 */
    "VAR_TMR_2",
    "VAR_TMR_3",
    "VAR_MUSIC_TIMER",
    "VAR_ACTOR_RANGE_MIN",
    # 	/* 16 */
    "VAR_ACTOR_RANGE_MAX",
    "VAR_CAMERA_MIN_X",
    "VAR_CAMERA_MAX_X",
    "VAR_TIMER_NEXT",
    # 	/* 20 */
    "VAR_VIRT_MOUSE_X",
    "VAR_VIRT_MOUSE_Y",
    "VAR_ROOM_RESOURCE",
    "VAR_LAST_SOUND",
    # 	/* 24 */
    "VAR_CUTSCENEEXIT_KEY",
    "VAR_TALK_ACTOR",
    "VAR_CAMERA_FAST_X",
    "VAR_SCROLL_SCRIPT",
    # 	/* 28 */
    "VAR_ENTRY_SCRIPT",
    "VAR_ENTRY_SCRIPT2",
    "VAR_EXIT_SCRIPT",
    "VAR_EXIT_SCRIPT2",
    # 	/* 32 */
    "VAR_VERB_SCRIPT",
    "VAR_SENTENCE_SCRIPT",
    "VAR_INVENTORY_SCRIPT",
    "VAR_CUTSCENE_START_SCRIPT",
    # 	/* 36 */
    "VAR_CUTSCENE_END_SCRIPT",
    "VAR_CHARINC",
    "VAR_WALKTO_OBJ",
    "VAR_DEBUGMODE",
    # 	/* 40 */
    "VAR_HEAPSPACE",
    None,
    "VAR_RESTART_KEY",
    "VAR_PAUSE_KEY",
    # 	/* 44 */
    "VAR_MOUSE_X",
    "VAR_MOUSE_Y",
    "VAR_TIMER",
    "VAR_TIMER_TOTAL",
    # 	/* 48 */
    "VAR_SOUNDCARD",
    "VAR_VIDEOMODE",
    "VAR_MAINMENU_KEY",
    "VAR_FIXEDDISK",
    # 	/* 52 */
    "VAR_CURSORSTATE",
    "VAR_USERPUT",
    "VAR_V5_TALK_STRING_Y",
    # 	/* Loom CD specific */
    None,
    # 	/* 56 */
    None,
    None,
    None,
    None,
    # 	/* 60 */
    "VAR_NOSUBTITLES",
    None,
    None,
    None,
    # 	/* 64 */
    "VAR_SOUNDPARAM",
    "VAR_SOUNDPARAM2",
    "VAR_SOUNDPARAM3",
    None,
]


@dataclass
class V4Instr:
    opcode: int
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    target: V4Var | None = None
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


def var_name(var_id: int, extra: int | None = None) -> str:
    if var_id in range(len(V4_VARNAMES)):
        res = V4_VARNAMES[var_id]
        if res:
            return res

    if var_id & 0x8000:
        return f"VAR[{(var_id & 0xff0) >> 4} bit {var_id & 0x00f}]"

    base = "LOCAL" if var_id & 0x4000 else "VAR"

    if var_id & 0x2000 and extra is not None:
        return f"{base}[{var_id & 0xfff} + {var_name(extra)}]"

    return f"{base}[{var_id & 0xfff}]"


def var_raw(var_id: int, extra: int | None = None) -> bytes:
    return utils.to_uint16_le(var_id) + (
        b"" if extra is None else utils.to_uint16_le(extra)
    )


@dataclass
class V4Var:
    id: int
    extra: int | None

    def __repr__(self) -> str:
        return var_name(self.id, self.extra)

    def __str__(self) -> str:
        return var_name(self.id, self.extra)

    def raw(self) -> bytes:
        return var_raw(self.id, self.extra)


@dataclass
class V4TextToken:
    name: str
    data: bytes | str | int | V4Var | None = None

    def __str__(self):
        return f"{self.name}({repr(self.data) if self.data is not None else ''})"


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


def get_vararg(stream: IOBase) -> list[int | V4Var]:
    result: list[int | V4Var] = []
    while True:
        test = get_byte(stream)
        if test == 0xFF:
            break
        result.append(get_var(stream) if (test & 0x80) else get_signed_word(stream))

    return result


def get_var(stream: IOBase) -> V4Var:
    var_id = get_unsigned_word(stream)
    extra = None
    if var_id & 0x2000:
        extra = get_unsigned_word(stream)

    return V4Var(var_id, extra)


def get_result_pos(stream: IOBase) -> int:
    var_id = get_signed_word(stream)
    if var_id & 0x2000:
        a = get_signed_word(stream)
        var_id += a & 0xFFF
    return var_id


def get_result_var(stream: IOBase) -> V4Var | None:
    return get_var(stream)


#    return var_name(get_result_pos(stream))

V4_ACTOROPS_REMAP = [
    1,
    0,
    0,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    20,
]


def parse_actorops(stream: IOBase) -> list[tuple[str, dict[str, Any]]]:
    opcode = get_byte(stream)
    ops: list[tuple[str, dict[str, Any]]] = []
    while opcode != 0xFF:
        opcode = (opcode & 0xE0) | V4_ACTOROPS_REMAP[(opcode & 0x1F) - 1]
        a1 = True if opcode & 0x80 else False
        a2 = True if opcode & 0x40 else False
        a3 = True if opcode & 0x20 else False
        match opcode & 0x1F:
            case 0x00:
                ops.append(
                    ("SO_DUMMY", {"data": get_var(stream) if a1 else get_byte(stream)})
                )

            case 0x01:
                ops.append(
                    (
                        "SO_COSTUME",
                        {"costume": get_var(stream) if a1 else get_byte(stream)},
                    )
                )

            case 0x02:
                speed_x = get_var(stream) if a1 else get_byte(stream)
                speed_y = get_var(stream) if a2 else get_byte(stream)
                ops.append(("SO_STEP_DIST", {"speed_x": speed_x, "speed_y": speed_y}))

            case 0x03:
                sound = get_var(stream) if a1 else get_byte(stream)
                ops.append(("SO_SOUND", {"sound": sound}))

            case 0x04:
                frame = get_var(stream) if a1 else get_byte(stream)
                ops.append(("SO_WALK_ANIMATION", {"walk_frame": frame}))

            case 0x05:
                start_frame = get_var(stream) if a1 else get_byte(stream)
                stop_frame = get_var(stream) if a2 else get_byte(stream)
                ops.append(
                    (
                        "SO_TALK_ANIMATION",
                        {
                            "talk_start_frame": start_frame,
                            "talk_stop_frame": stop_frame,
                        },
                    )
                )

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
                ops.append(
                    (
                        "SO_ELEVATION",
                        {
                            "elevation": (
                                get_var(stream) if a1 else get_signed_word(stream)
                            )
                        },
                    )
                )

            case 0x0A:
                ops.append(("SO_ANIMATION_DEFAULT", {}))

            case 0x0B:
                idx = get_var(stream) if a1 else get_byte(stream)
                val = get_var(stream) if a2 else get_byte(stream)
                ops.append(("SO_PALETTE", {"idx": idx, "val": val}))

            case 0x0C:
                ops.append(
                    (
                        "SO_TALK_COLOR",
                        {"color": get_var(stream) if a1 else get_byte(stream)},
                    )
                )

            case 0x0D:
                ops.append(("SO_ACTOR_NAME", {"name": get_text_tokens(stream)}))

            case 0x0E:
                ops.append(
                    (
                        "SO_INIT_ANIMATION",
                        {"init_frame": get_var(stream) if a1 else get_byte(stream)},
                    )
                )

            case 0x10:
                ops.append(
                    (
                        "SO_ACTOR_WIDTH",
                        {"width": get_var(stream) if a1 else get_byte(stream)},
                    )
                )

            case 0x11:
                scale = get_var(stream) if a1 else get_byte(stream)
                ops.append(("SO_ACTOR_SCALE", {"scale_x": scale, "scale_y": scale}))

            case 0x12:
                ops.append(("SO_NEVER_ZCLIP", {}))

            case 0x13:
                ops.append(
                    (
                        "SO_ALWAYS_ZCLIP",
                        {"force": get_var(stream) if a1 else get_byte(stream)},
                    )
                )

            case 0x14:
                ops.append(("SO_IGNORE_BOXES", {}))

            case 0x15:
                ops.append(("SO_FOLLOW_BOXES", {}))

            case 0x16:
                ops.append(
                    (
                        "SO_ANIMATION_SPEED",
                        {"anim_speed": get_var(stream) if a1 else get_byte(stream)},
                    )
                )

            case 0x17:
                ops.append(
                    (
                        "SO_SHADOW",
                        {"shadow_mode": get_var(stream) if a1 else get_byte(stream)},
                    )
                )

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
    match opcode & 0x1F:
        case 1:
            func = "loadstring"
            index = get_var(stream) if a1 else get_byte(stream)
            string = get_text_tokens(stream)
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
    match opcode & 0x1F:
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
            x = get_var(stream) if a2 else get_byte(stream)
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
    match opcode & 0x1F:
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
    match opcode & 0x1F:
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
            b = get_var(stream) if a1 else get_signed_word(stream)
            h = get_var(stream) if a2 else get_signed_word(stream)
            args = {"b": b, "h": h}

        case 4:
            op = "SO_ROOM_PALETTE"
            index_min = get_var(stream) if a1 else get_signed_word(stream)
            index_max = get_var(stream) if a2 else get_signed_word(stream)
            # FIXME: check for v5
            args = {"index_min": index_min, "index_max": index_max}

        case 5:
            op = "SO_ROOM_SHAKE_ON"

        case 6:
            op = "SO_ROOM_SHAKE_OFF"

        case 7:
            op = "SO_ROOM_SCALE"
            a = get_var(stream) if a1 else get_byte(stream)
            b = get_var(stream) if a2 else get_byte(stream)
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            c = get_var(stream) if a1 else get_byte(stream)
            d = get_var(stream) if a2 else get_byte(stream)
            opcode = get_byte(stream)
            a1 = True if opcode & 0x80 else False
            a2 = True if opcode & 0x40 else False
            e = get_var(stream) if a2 else get_byte(stream)
            args = {"a": a, "b": b, "c": c, "d": d, "e": e}

        case 8:
            op = "SO_ROOM_INTENSITY"
            a = get_var(stream) if a1 else get_byte(stream)
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
    args = {
        "verb_id_start": verb_id_start,
        "verb_id_end": verb_id_end,
        "save_id": save_id,
    }
    match opcode & 0x1F:
        case 0x01:
            return "SO_SAVE_VERBS", args
        case 0x02:
            return "SO_RESTORE_VERBS", args
        case 0x03:
            return "SO_DELETE_VERBS", args

    return None, args


def get_text_tokens(stream: IOBase) -> list[V4TextToken]:
    orig = stream.tell()
    result: list[V4TextToken] = []
    test = get_byte(stream)
    text_buffer = bytearray()
    while test != 0:
        if test == 0xFF or test == 0xFE:
            test = get_byte(stream)

            if text_buffer:
                result.append(V4TextToken("text", bytes(text_buffer)))
                text_buffer = bytearray()

            match test:
                case 1:
                    result.append(V4TextToken("newline"))
                case 2:
                    result.append(V4TextToken("keepText"))
                case 3:
                    result.append(V4TextToken("wait"))
                case 4:
                    var = get_var(stream)
                    result.append(V4TextToken("getInt", var))
                case 5:
                    var = get_var(stream)
                    result.append(V4TextToken("getVerb", var))
                case 6:
                    var = get_var(stream)
                    result.append(V4TextToken("getName", var))
                case 7:
                    var = get_var(stream)
                    result.append(V4TextToken("getString", var))
                case 9:
                    anim = get_signed_word(stream)
                    result.append(V4TextToken("startAnim", anim))
                case 12:
                    color = get_signed_word(stream)
                    result.append(V4TextToken("setColor", color))
                case 14:
                    font = get_signed_word(stream)
                    result.append(V4TextToken("setFont", font))

        else:
            text_buffer.append(test)
        test = get_byte(stream)

    if text_buffer:
        result.append(V4TextToken("text", bytes(text_buffer)))
        text_buffer = bytearray()

    return result


def stringops_to_bytes(op, args, target):
    result = b""
    match op:
        case "loadstring":
            index = args["index"]
            a1 = isinstance(index, V4Var)
            opcode = 0x01 | (0x80 if a1 else 0x00)
            result += bytes([opcode])
            result += index.raw() if a1 else utils.to_uint8(index)
            result += text_tokens_to_bytes(args["string"])

        case "copystring":
            a = args["a"]
            b = args["b"]
            a1 = isinstance(a, V4Var)
            a2 = isinstance(b, V4Var)
            opcode = 0x02 | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
            result += bytes([opcode])
            result += a.raw() if a1 else utils.to_uint8(a)
            result += b.raw() if a2 else utils.to_uint8(b)

        case "setstringchar":
            a = args["a"]
            b = args["b"]
            c = args["c"]
            a1 = isinstance(a, V4Var)
            a2 = isinstance(b, V4Var)
            a3 = isinstance(c, V4Var)
            opcode = (
                0x03
                | (0x80 if a1 else 0x00)
                | (0x40 if a2 else 0x00)
                | (0x20 if a3 else 0x00)
            )
            result += bytes([opcode])
            result += a.raw() if a1 else utils.to_uint8(a)
            result += b.raw() if a2 else utils.to_uint8(b)
            result += c.raw() if a3 else utils.to_uint8(c)

        case "getstringchar":
            a = args["a"]
            b = args["b"]
            a1 = isinstance(a, V4Var)
            a2 = isinstance(b, V4Var)
            opcode = 0x04 | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
            result += bytes([opcode])
            result += target.raw()
            result += a.raw() if a1 else utils.to_uint8(a)
            result += b.raw() if a2 else utils.to_uint8(b)

        case "createemptystring":
            a = args["a"]
            b = args["b"]
            a1 = isinstance(a, V4Var)
            a2 = isinstance(b, V4Var)
            opcode = 0x05 | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
            result += bytes([opcode])
            result += a.raw() if a1 else utils.to_uint8(a)
            result += b.raw() if a2 else utils.to_uint8(b)

    return result


def verbops_to_bytes(ops: list[tuple[str, Any]]) -> bytes:
    result = b""
    for op, args in ops:
        match op:
            case "SO_VERB_IMAGE":
                obj = args["obj"]
                a1 = isinstance(obj, V4Var)
                opcode = 0x01 | (0x80 if a1 else 0x00)
                result += bytes([opcode])
                result += obj.raw() if a1 else utils.to_int16_le(obj)
            case "SO_VERB_NAME":
                opcode = 0x02
                result += bytes([opcode])
                result += text_tokens_to_bytes(args["text"])
            case "SO_VERB_COLOR":
                color = args["color"]
                a1 = isinstance(color, V4Var)
                opcode = 0x03
                result += bytes([opcode])
                result += color.raw() if a1 else utils.to_uint8(color)
            case "SO_VERB_HICOLOR":
                color = args["color"]
                a1 = isinstance(color, V4Var)
                opcode = 0x04
                result += bytes([opcode])
                result += color.raw() if a1 else utils.to_uint8(color)
            case "SO_VERB_AT":
                x = args["x"]
                y = args["y"]
                a1 = isinstance(x, V4Var)
                a2 = isinstance(y, V4Var)
                opcode = 0x05 | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
                result += bytes([opcode])
                result += x.raw() if a1 else utils.to_int16_le(x)
                result += y.raw() if a2 else utils.to_int16_le(y)
            case "SO_VERB_ON":
                opcode = 0x06
                result += bytes([opcode])
            case "SO_VERB_OFF":
                opcode = 0x07
                result += bytes([opcode])
            case "SO_VERB_DELETE":
                opcode = 0x08
                result += bytes([opcode])
            case "SO_VERB_NEW":
                opcode = 0x09
                result += bytes([opcode])
            case "SO_VERB_DIMCOLOR":
                color = args["color"]
                a1 = isinstance(color, V4Var)
                opcode = 0x10 | (0x80 if a1 else 0x00)
                result += bytes([opcode])
                result += color.raw() if a1 else utils.to_int16_le(color)
            case "SO_VERB_DIM":
                opcode = 0x11
                result += bytes([opcode])
            case "SO_VERB_KEY":
                key = args["key"]
                a1 = isinstance(key, V4Var)
                opcode = 0x12 | (0x80 if a1 else 0x00)
                result += bytes([opcode])
                result += key.raw() if a1 else utils.to_int16_le(key)
            case "SO_VERB_CENTER":
                opcode = 0x13
                result += bytes([opcode])
            case "SO_VERB_NAME_STR":
                idx = args["idx"]
                a1 = isinstance(idx, V4Var)
                opcode = 0x14 | (0x80 if a1 else 0x00)
                result += bytes([opcode])
                result += idx.raw() if a1 else utils.to_int16_le(idx)
            case "SO_VERB_ASSIGN_OBJECT":
                obj = args["obj"]
                room = args["room"]
                a1 = isinstance(obj, V4Var)
                a2 = isinstance(room, V4Var)
                opcode = 0x16 | (0x80 if a1 else 0x00)
                result += bytes([opcode])
                result += obj.raw() if a1 else utils.to_int16_le(obj)
                result += room.raw() if a2 else utils.to_int16_le(room)

            case "SO_VERB_BACKCOLOR":
                color = args["color"]
                a1 = isinstance(color, V4Var)
                opcode = 0x17 | (0x80 if a1 else 0x00)
                result += bytes([opcode])
                result += color.raw() if a1 else utils.to_int16_le(color)

    result += b"\xff"
    return result


def sostring_to_bytes(ops: list[tuple[str, Any]]) -> bytes:
    result = bytearray()
    for op, data in ops:
        match op:
            case "SO_AT":
                a1 = isinstance(data["xpos"], V4Var)
                a2 = isinstance(data["ypos"], V4Var)
                opcode = 0x00 | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
                result.append(opcode)
                result.extend(
                    data["xpos"].raw() if a1 else utils.to_int16_le(data["xpos"])
                )
                result.extend(
                    data["ypos"].raw() if a2 else utils.to_int16_le(data["ypos"])
                )
            case "SO_COLOR":
                a1 = isinstance(data["color"], V4Var)
                opcode = 0x01 | (0x80 if a1 else 0x00)
                result.append(opcode)
                result.extend(
                    data["color"].raw() if a1 else utils.to_uint8(data["color"])
                )
            case "SO_CLIPPED":
                a1 = isinstance(data["right"], V4Var)
                opcode = 0x02 | (0x80 if a1 else 0x00)
                result.append(opcode)
                result.extend(
                    data["right"].raw() if a1 else utils.to_uint8(data["right"])
                )
            case "SO_ERASE":
                a1 = isinstance(data["width"], V4Var)
                a2 = isinstance(data["height"], V4Var)
                opcode = 0x03 | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
                result.append(opcode)
                result.extend(
                    data["width"].raw() if a1 else utils.to_int16_le(data["width"])
                )
                result.extend(
                    data["height"].raw() if a2 else utils.to_int16_le(data["height"])
                )
            case "SO_CENTER":
                opcode = 0x04
                result.append(opcode)
            case "SO_LEFT":
                opcode = 0x06
                result.append(opcode)
            case "SO_OVERHEAD":
                opcode = 0x07
                result.append(opcode)
            case "SO_SAY_VOICE":
                a1 = isinstance(data["offset"], V4Var)
                a2 = isinstance(data["delay"], V4Var)
                opcode = 0x08 | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
                result.append(opcode)
                result.extend(
                    data["offset"].raw() if a1 else utils.to_int16_le(data["offset"])
                )
                result.extend(
                    data["delay"].raw() if a2 else utils.to_int16_le(data["delay"])
                )
            case "SO_TEXTSTRING":
                result.append(0x0F)
                result.extend(text_tokens_to_bytes(data["str"]))
                return bytes(result)
    result.append(0xFF)

    return bytes(result)


def text_tokens_to_bytes(tokens: list[V4TextToken]) -> bytes:
    result = bytearray()

    for token in tokens:
        match token.name:
            case "text":
                result.extend(token.data)
            case "newline":
                result.extend(b"\xff\x01")
            case "keepText":
                result.extend(b"\xff\x02")
            case "wait":
                result.extend(b"\xff\x03")
            case "getInt":
                assert isinstance(token.data, V4Var)
                result.extend(b"\xff\x04" + token.data.raw())
            case "getVerb":
                assert isinstance(token.data, V4Var)
                result.extend(b"\xff\x05" + token.data.raw())
            case "getName":
                assert isinstance(token.data, V4Var)
                result.extend(b"\xff\x06" + token.data.raw())
            case "getString":
                assert isinstance(token.data, V4Var)
                result.extend(b"\xff\x07" + token.data.raw())
            case "startAnim":
                assert isinstance(token.data, V4Var)
                result.extend(b"\xff\x09" + token.data.raw())
            case "setColor":
                assert isinstance(token.data, int)
                result.extend(b"\xff\x0c" + utils.from_int16_le(token.data))
            case "setFont":
                assert isinstance(token.data, int)
                result.extend(b"\xff\x0e" + utils.from_int16_le(token.data))
    result.append(0x00)
    return bytes(result)


def get_text_string(stream: IOBase) -> bytes:
    orig = stream.tell()
    result = bytearray()
    test = get_byte(stream)
    while test != 0:
        if test == 0xFF or test == 0xFE:
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
                    result.extend(b"{{getInt(" + str(var).encode("utf8") + b"}}")
                case 5:
                    var = get_var(stream)
                    result.extend(b"{{getVerb(" + str(var).encode("utf8") + b"}}")
                case 6:
                    var = get_var(stream)
                    result.extend(b"{{getName(" + str(var).encode("utf8") + b"}}")
                case 7:
                    var = get_var(stream)
                    result.extend(b"{{getString(" + str(var).encode("utf8") + b"}}")
                case 9:
                    anim = get_signed_word(stream)
                    result.extend(b"{{startAnim(" + str(anim).encode("utf8") + b"}}")
                case 10:
                    print("Nightmare instruction hit")
                case 12:
                    color = get_signed_word(stream)
                    result.extend(b"{{setColor(" + str(color).encode("utf8") + b"}}")
                case 14:
                    font = get_signed_word(stream)
                    result.extend(b"{{setFont(" + str(font).encode("utf8") + b"}}")

        else:
            result.append(test)
        test = get_byte(stream)

    return bytes(result)


def parse_sostring(stream: IOBase) -> list[tuple[str, dict[str, Any]]]:
    opcode = get_byte(stream)
    ops: list[tuple[str, dict[str, Any]]] = []
    while opcode != 0xFF:
        a1 = True if opcode & 0x80 else False
        a2 = True if opcode & 0x40 else False
        a3 = True if opcode & 0x20 else False
        a4 = True if opcode & 0x10 else False
        match opcode & 0x0F:
            case 0x00:
                xpos = get_var(stream) if a1 else get_signed_word(stream)
                ypos = get_var(stream) if a2 else get_signed_word(stream)
                ops.append(("SO_AT", {"xpos": xpos, "ypos": ypos}))

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
                offset = get_var(stream) if a1 else get_signed_word(stream)
                delay = get_var(stream) if a2 else get_signed_word(stream)
                ops.append(("SO_SAY_VOICE", {"offset": offset, "delay": delay}))

            case 0x0F:
                ops.append(("SO_TEXTSTRING", {"str": get_text_tokens(stream)}))
                return ops
            case _:
                ops.append(("SO_UNK", {}))

        opcode = get_byte(stream)
    return ops


def parse_verbops(stream: IOBase):
    ops: list[tuple[str, dict[str, V4Var | int | bytes]]] = []
    opcode = get_byte(stream)
    a1 = True if opcode & 0x80 else False
    a2 = True if opcode & 0x40 else False
    a3 = True if opcode & 0x20 else False
    while opcode != 0xFF:
        match opcode & 0x1F:
            case 1:
                op = "SO_VERB_IMAGE"
                a = get_var(stream) if a1 else get_signed_word(stream)
                ops.append((op, {"obj": a}))
            case 2:
                op = "SO_VERB_NAME"
                text = get_text_tokens(stream)
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
                y = get_var(stream) if a2 else get_signed_word(stream)
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
    match opcode & 0x1F:
        case 1:
            actor = get_var(stream) if a1 else get_byte(stream)
            args = {"op": "SO_WAIT_FOR_ACTOR", "actor": actor}
        case 2:
            args = {"op": "SO_WAIT_FOR_MESSAGE"}
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
    while opcode != 0xFF:
        match opcode & 0x1F:
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


def v4_instr_to_bytes(instr: V4Instr) -> bytes:
    match instr.name:
        case (
            "isGreaterEqual"
            | "isNotEqual"
            | "isLessEqual"
            | "isLess"
            | "isEqual"
            | "isGreater"
        ):
            a = instr.args["a"]
            b = instr.args["b"]
            offset = instr.args["offset"]
            a1 = isinstance(b, V4Var)
            match instr.name:
                case "isGreaterEqual":
                    opcode = 0x04
                case "isNotEqual":
                    opcode = 0x08
                case "isLessEqual":
                    opcode = 0x38
                case "isLess":
                    opcode = 0x44
                case "isEqual":
                    opcode = 0x48
                case "isGreater":
                    opcode = 0x78

            opcode = opcode | (0x80 if a1 else 0x00)
            raw = bytes([opcode])
            raw += a.raw()
            raw += b.raw() if a1 else utils.to_int16_le(b)
            raw += utils.to_int16_le(offset)
            return raw

        case "ifState" | "ifNotState":
            obj = instr.args["obj"]
            val = instr.args["val"]
            offset = instr.args["offset"]
            a1 = isinstance(obj, V4Var)
            a2 = isinstance(val, V4Var)
            opcode = 0x0F if instr.name == "ifState" else 0x2F
            opcode = opcode | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
            raw = bytes([opcode])
            raw += obj.raw() if a1 else utils.to_int16_le(obj)
            raw += val.raw() if a2 else utils.to_uint8(val)
            raw += utils.to_int16_le(offset)
            return raw

        case "print":
            act = instr.args["act"]
            a1 = isinstance(act, V4Var)
            opcode = 0x14 | (0x80 if a1 else 0x00)
            raw = bytes([opcode])
            raw += act.raw() if a1 else utils.to_uint8(act)
            raw += sostring_to_bytes(instr.args["ops"])
            return raw

        case "jumpRelative":
            offset = instr.args["offset"]
            opcode = 0x18
            raw = bytes([opcode])
            raw += utils.to_int16_le(offset)
            return raw

        case "move":
            target = instr.target
            assert target is not None
            value = instr.args["value"]
            a1 = isinstance(value, V4Var)
            opcode = 0x1A | (0x80 if a1 else 0x00)
            raw = bytes([opcode])
            raw += target.raw()
            raw += value.raw() if a1 else utils.to_int16_le(value)
            return raw

        case "ifClassOfIs":
            obj = instr.args["obj"]
            classes = instr.args["classes"]
            offset = instr.args["offset"]
            a1 = isinstance(obj, V4Var)
            opcode = 0x1D | (0x80 if a1 else 0x00)
            raw = bytes([opcode])
            raw += obj.raw() if a1 else utils.to_int16_le(obj)
            for klass in classes:
                a1 = isinstance(klass, V4Var)
                raw += b"\x80" if a1 else b"\x00"
                raw += klass.raw() if a1 else utils.to_int16_le(klass)
            raw += b"\xff"
            raw += utils.to_int16_le(offset)
            return raw

        case "isActorInBox":
            act = instr.args["act"]
            box = instr.args["box"]
            offset = instr.args["offset"]
            a1 = isinstance(act, V4Var)
            a2 = isinstance(box, V4Var)
            opcode = 0x1F | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
            raw = bytes([opcode])
            raw += act.raw() if a1 else utils.to_uint8(act)
            raw += box.raw() if a2 else utils.to_uint8(box)
            raw += utils.to_int16_le(offset)
            return raw

        case "stringOps":
            opcode = 0x27
            raw = bytes([opcode])
            raw += stringops_to_bytes(
                instr.args["op"], instr.args["args"], instr.target
            )
            return raw

        case "equalZero" | "notEqualZero":
            a = instr.args["a"]
            offset = instr.args["offset"]

            opcode = 0x28 if instr.name == "equalZero" else 0xA8
            raw = bytes([opcode])
            raw += a.raw()
            raw += utils.to_int16_le(offset)
            return raw

        case "loadRoomWithEgo":
            obj = instr.args["obj"]
            room = instr.args["room"]
            x = instr.args["x"]
            y = instr.args["y"]
            a1 = isinstance(obj, V4Var)
            a2 = isinstance(room, V4Var)
            opcode = 0x24 | (0x80 if a1 else 0x00) | (0x40 if a2 else 0x00)
            raw = bytes([opcode])
            raw += obj.raw() if a1 else utils.to_int16_le(obj)
            raw += room.raw() if a2 else utils.to_uint8(room)
            raw += utils.to_int16_le(x)
            raw += utils.to_int16_le(y)
            return raw

        case "actorFollowCamera":
            act = instr.args["act"]
            a1 = isinstance(act, V4Var)
            opcode = 0x52 | (0x80 if a1 else 0x00)
            raw = bytes([opcode])
            raw += act.raw() if a1 else utils.to_int16_le(act)
            return raw

        case "verbOps":
            verb = instr.args["verb"]
            a1 = isinstance(verb, V4Var)
            opcode = 0x7A | (0x80 if a1 else 0x00)
            raw = bytes([opcode])
            raw += verb.raw() if a1 else utils.to_uint8(verb)
            raw += verbops_to_bytes(instr.args["ops"])
            return raw

        case "printEgo":
            opcode = 0xD8
            raw = bytes([opcode])
            raw += sostring_to_bytes(instr.args["string"])
            return raw
        case _:
            return instr.raw


def instr_list_to_bytes(instrs: list[tuple[int, V4Instr]]) -> bytes:
    result = bytearray()

    # - create new offsets list based on code size
    pos = instrs[0][0]
    old_bases = [x for x, _ in instrs]
    # print(f"Old bases: {old_bases}")
    new_bases = []
    for off, instr in instrs:
        new_bases.append(pos)
        pos += len(v4_instr_to_bytes(instr))
    # print(f"New bases: {new_bases}")
    for i, (off, instr) in enumerate(instrs):
        # print((off, instr))
        if "offset" in instr.args:
            # filter nops
            if instr.name == "jumpRelative" and instr.args["offset"] == 0:
                result.extend(v4_instr_to_bytes(instr))
                continue
            target = off + len(v4_instr_to_bytes(instr)) + instr.args["offset"]
            target_idx = old_bases.index(target)

            offset_old = instr.args["offset"]
            instr.args["offset"] = new_bases[target_idx] - len(instr.raw) - new_bases[i]
            result.extend(v4_instr_to_bytes(instr))
            instr.args["offset"] = offset_old
        else:
            result.extend(v4_instr_to_bytes(instr))

    return bytes(result)


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
        case 0x00 | 0xA0:
            result.name = "stopObjectCode"

        case 0x01 | 0x21 | 0x41 | 0x61 | 0x81 | 0xA1 | 0xC1 | 0xE1:
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

        case 0x05 | 0x25 | 0x45 | 0x65 | 0x85 | 0xA5 | 0xC5 | 0xE5:
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

        case 0x07 | 0x47 | 0x87 | 0xC7:
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

        case 0x09 | 0x49 | 0x89 | 0xC9:
            result.name = "faceActor"
            act = get_var(stream) if a1 else get_byte(stream)
            obj = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"act": act, "obj": obj}

        case 0x0A | 0x2A | 0x4A | 0x6A | 0x8A | 0xAA | 0xCA | 0xEA:
            result.name = "startScript"
            script = get_var(stream) if a1 else get_byte(stream)
            var = get_vararg(stream)
            recursive = a2
            freeze_resistant = a3
            result.args = {
                "script": script,
                "var": var,
                "recursive": recursive,
                "freeze_resistant": freeze_resistant,
            }

        case 0x0B | 0x4B | 0x8B | 0xCB:
            result.name = "getVerbEntrypoint"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            entry = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"obj": obj, "entry": entry}

        case 0x0C | 0x8C:
            result.name = "resourceRoutines"
            opr = get_byte(stream)
            a1 = True if opr & 0x80 else False
            a2 = True if opr & 0x40 else False
            op = opr & 0x3F
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

        case 0x0D | 0x4D | 0x8D | 0xCD:
            result.name = "walkActorToActor"
            nr = get_var(stream) if a1 else get_byte(stream)
            nr2 = get_var(stream) if a2 else get_byte(stream)
            dist = get_byte(stream)
            result.args = {"nr": nr, "nr2": nr2, "dist": dist}

        case 0x0E | 0x4E | 0x8E | 0xCE:
            result.name = "putActorAtObject"
            act = get_var(stream) if a1 else get_byte(stream)
            obj = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"act": act, "obj": obj}

        case 0x0F | 0x4F | 0x8F | 0xCF:
            result.name = "ifState"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            val = get_var(stream) if a2 else get_byte(stream)
            offset = get_signed_word(stream)
            result.args = {"obj": obj, "val": val, "offset": offset}

        # case 0x0f | 0x8f:
        #    result.name = "getObjectState"
        #    result.target = get_result_var(stream)
        #    obj = get_var(stream) if a1 else get_signed_word(stream)
        #    result.args = {"obj": obj}

        case 0x10 | 0x90:
            result.name = "getObjectOwner"
            result.target = get_result_var(stream)
            obj = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"obj": obj}

        case 0x11 | 0x51 | 0x91 | 0xD1:
            result.name = "animateActor"
            act = get_var(stream) if a1 else get_byte(stream)
            anim = get_var(stream) if a2 else get_byte(stream)
            result.args = {"act": act, "anim": anim}

        case 0x12 | 0x92:
            result.name = "panCameraTo"
            x = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"x": x}

        case 0x13 | 0x53 | 0x93 | 0xD3:
            result.name = "actorOps"
            act = get_var(stream) if a1 else get_byte(stream)
            ops = parse_actorops(stream)
            result.args = {"act": act, "ops": ops}

        case 0x14 | 0x94:
            result.name = "print"
            act = get_var(stream) if a1 else get_byte(stream)
            ops = parse_sostring(stream)
            result.args = {"act": act, "ops": ops}

        case 0x15 | 0x55 | 0x95 | 0xD5:
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

        case 0x19 | 0x39 | 0x59 | 0x79 | 0x99 | 0xB9 | 0xD9 | 0xF9:
            result.name = "doSentence"
            verb = get_var(stream) if a1 else get_byte(stream)
            obj_a, obj_b = None, None
            if verb != 0xFE:
                obj_a = get_var(stream) if a2 else get_signed_word(stream)
                obj_b = get_var(stream) if a3 else get_signed_word(stream)
            result.args = {"verb": verb, "obj_a": obj_a, "obj_b": obj_b}

        case 0x1A | 0x9A:  # move
            result.name = "move"
            result.target = get_result_var(stream)
            value = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"value": value}
            result.repr = lambda x: f"{x.target} = {repr(x.args['value'])}"

        case 0x1B | 0x9B:
            result.name = "multiply"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} *= {repr(x.args['a'])}"

        case 0x1C | 0x9C:
            result.name = "startSound"
            sound = get_var(stream) if a1 else get_byte(stream)
            result.args = {"sound": sound}

        case 0x1D | 0x9D:
            result.name = "ifClassOfIs"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            classes = []
            test = get_byte(stream)
            while test != 0xFF:
                a1 = True if test & 0x80 else False
                classes.append(get_var(stream) if a1 else get_signed_word(stream))
                test = get_byte(stream)
            offset = get_signed_word(stream)
            result.args = {"obj": obj, "classes": classes, "offset": offset}

        case 0x1E | 0x3E | 0x5E | 0x7E | 0x9E | 0xBE | 0xDE | 0xFE:
            result.name = "walkActorTo"
            act = get_var(stream) if a1 else get_byte(stream)
            x = get_var(stream) if a2 else get_signed_word(stream)
            y = get_var(stream) if a3 else get_signed_word(stream)
            result.args = {"act": act, "x": x, "y": y}

        case 0x1F | 0x5F | 0x9F | 0xDF:
            result.name = "isActorInBox"
            act = get_var(stream) if a1 else get_byte(stream)
            box = get_var(stream) if a2 else get_byte(stream)
            offset = get_signed_word(stream)
            result.args = {"act": act, "box": box, "offset": offset}

        case 0x20:
            result.name = "stopMusic"

        case 0x22 | 0xA2:
            result.name = "saveLoadGame"
            result.target = get_result_var(stream)
            op = get_var(stream) if a1 else get_byte(stream)
            result.args = {"op": op}
        #                act = get_var(stream) if a1 else get_byte(stream)
        #                print(f"{ptr:04x}: getAnimCounter(act={act})")

        case 0x23 | 0xA3:
            result.name = "getActorY"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"act": act}

        case 0x24 | 0x64 | 0xA4 | 0xE4:
            result.name = "loadRoomWithEgo"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            room = get_var(stream) if a2 else get_byte(stream)
            x = get_signed_word(stream)
            y = get_signed_word(stream)
            result.args = {"obj": obj, "room": room, "x": x, "y": y}

        # case 0x25 | 0x65 | 0xa5 | 0xe5:
        #    obj = get_var(stream) if a1 else get_signed_word(stream)
        #    room = get_var(stream) if a2 else get_byte(stream)
        #    print(f"{ptr:04x}: pickupObject(obj={obj}, room={room})")

        case 0x25 | 0x45 | 0x65 | 0x85 | 0xA5 | 0xC5 | 0xE5:
            result.name = "drawObject"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            x = get_var(stream) if a2 else get_signed_word(stream)
            y = get_var(stream) if a3 else get_signed_word(stream)
            result.args = {"obj": obj, "x": x, "y": y}

        case 0x26 | 0xA6:
            result.name = "setVarRange"
            result.target = get_result_var(stream)
            count = get_byte(stream)
            values = []
            for i in range(count):
                values.append(get_signed_word(stream) if a1 else get_byte(stream))
            result.args = {"values": values}

        case 0x27:
            result.name = "stringOps"
            func, args, target = parse_stringops(stream)
            result.target = target
            result.args = {"op": func, "args": args}

        case 0x28:
            result.name = "equalZero"
            a = get_var(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "offset": offset}

        case 0x29 | 0x69 | 0xA9 | 0xE9:
            result.name = "setOwner"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            owner = get_var(stream) if a2 else get_byte(stream)
            result.args = {"obj": obj, "owner": owner}

        case 0x2B:
            result.name = "delayVariable"
            var = get_var(stream)
            result.args = {"var": var}

        case 0x2C:
            result.name = "cursorCommand"
            op, args = parse_cursorcommand(stream)
            result.args = {"op": op, "args": args}

        case 0x2D | 0x6D | 0xAD | 0xED:
            result.name = "putActorInRoom"
            act = get_var(stream) if a1 else get_byte(stream)
            room = get_var(stream) if a2 else get_byte(stream)
            result.args = {"act": act, "room": room}

        case 0x2E:
            result.name = "delay"
            delay = get_byte(stream)
            delay |= get_byte(stream) << 8
            delay |= get_byte(stream) << 16
            result.args = {"delay": delay}

        case 0x2F | 0x6F | 0xAF | 0xEF:
            result.name = "ifNotState"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            val = get_var(stream) if a2 else get_byte(stream)
            offset = get_signed_word(stream)
            result.args = {"obj": obj, "val": val, "offset": offset}

        case 0x30 | 0xB0:
            result.name = "matrixOps"
            op, args = parse_matrixops(stream)
            result.args = {"op": op, "args": args}

        case 0x31 | 0xB1:
            result.name = "setInventoryCount"
            result.target = get_result_var(stream)
            owner = get_var(stream) if a1 else get_byte(stream)
            result.args = {"owner": owner}

        case 0x32 | 0xB2:
            result.name = "setCameraAt"
            x_pos = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"x_pos": x_pos}

        case 0x33 | 0x73 | 0xB3 | 0xF3:
            result.name = "roomOps"
            op, args = parse_roomops(stream)
            result.args = {"op": op, "args": args}

        case 0x34 | 0x74 | 0xB4 | 0xF4:
            result.name = "getDist"
            result.target = get_result_var(stream)
            obj_a = get_var(stream) if a1 else get_signed_word(stream)
            obj_b = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"obj_a": obj_a, "obj_b": obj_b}

        case 0x35 | 0x75 | 0xB5 | 0xF5:
            result.name = "findObject"
            result.target = get_result_var(stream)
            x = get_var(stream) if a1 else get_byte(stream)
            y = get_var(stream) if a2 else get_byte(stream)
            result.args = {"x": x, "y": y}

        case 0x36 | 0x76 | 0xB6 | 0xF6:
            result.name = "walkActorToObject"
            act = get_var(stream) if a1 else get_byte(stream)
            obj = get_var(stream) if a2 else get_signed_word(stream)
            result.args = {"act": act, "obj": obj}

        case 0x37 | 0x77 | 0xB7 | 0xF7:
            result.name = "startObject"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            script = get_var(stream) if a2 else get_byte(stream)
            args = get_vararg(stream)
            result.args = {"obj": obj, "script": script, "args": args}

        case 0x38 | 0xB8:
            result.name = "isLessEqual"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}

        case 0x3A | 0xBA:  # subtract
            result.name = "subtract"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} -= {repr(x.args['a'])}"

        case 0x3B | 0xBB:
            result.name = "getActorScale"
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x3C | 0xBC:
            result.name = "stopSound"
            sound = get_var(stream) if a1 else get_byte(stream)
            result.args = {"sound": sound}

        case 0x3D | 0x7D | 0xBD | 0xFD:
            result.name = "findInventory"
            result.target = get_result_var(stream)
            x = get_var(stream) if a1 else get_byte(stream)
            y = get_var(stream) if a2 else get_byte(stream)
            result.args = {"x": x, "y": y}

        case 0x3F | 0x7F | 0xBF | 0xFF:
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

        case 0x42 | 0xC2:
            result.name = "chainScript"
            script = get_var(stream) if a1 else get_byte(stream)
            args = get_vararg(stream)
            result.args = {"script": script, "args": args}

        case 0x43 | 0xC3:
            result.name = "getActorX"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"act": act}

        case 0x44 | 0xC4:
            result.name = "isLess"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}

        case 0x46:  # increment
            result.name = "increment"
            result.target = get_result_var(stream)
            result.repr = lambda x: f"{x.target} += 1"

        case 0x48 | 0xC8:
            result.name = "isEqual"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)

            result.args = {"a": a, "b": b, "offset": offset}

        case 0x50 | 0xD0:
            result.name = "pickupObject"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"obj": obj}

        case 0x52 | 0xD2:
            result.name = "actorFollowCamera"
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x54 | 0xD4:
            result.name = "setObjectName"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            name = get_text_tokens(stream)
            result.args = {"obj": obj, "name": name}

        case 0x56 | 0xD6:
            result.name = "getActorMoving"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x57 | 0xD7:
            result.name = "or"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} |= {repr(x.args['a'])}"

        case 0x58:
            test = get_byte(stream)
            result.name = f"{'begin' if test else 'end'}Override"

        case 0x5A | 0xDA:  # add
            result.name = "add"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} += {repr(x.args['a'])}"

        case 0x5B | 0xDB:  # divide
            result.name = "divide"
            result.target = get_result_var(stream)
            a = get_var(stream) if a1 else get_signed_word(stream)
            result.args = {"a": a}
            result.repr = lambda x: f"{x.target} /= {repr(x.args['a'])}"

        case 0x5C | 0xDC:
            result.name = "oldRoomEffect"
            op = get_byte(stream)
            effect = None
            if op & 0x1F == 3:
                effect = get_var(stream) if (op & 0x80) else get_signed_word(stream)
            result.args = {"op": op, "effect": effect}

        case 0x5D | 0xDD:
            result.name = "setClass"
            obj = get_var(stream) if a1 else get_signed_word(stream)
            cls = get_vararg(stream)
            result.args = {"obj": obj, "cls": cls}

        case 0x60 | 0xE0:
            result.name = "freezeScripts"
            scr = get_var(stream) if a1 else get_byte(stream)
            result.args = {"scr": scr}

        case 0x62 | 0xE2:
            result.name = "stopScript"
            idx = get_var(stream) if a1 else get_byte(stream)
            result.args = {"idx": idx}

        case 0x63 | 0xE3:
            result.name = "getActorFacing"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x68 | 0xE8:
            result.name = "isScriptRunning"
            result.target = get_result_var(stream)
            idx = get_var(stream) if a1 else get_byte(stream)
            result.args = {"idx": idx}

        case 0x6C | 0xEC:
            result.name = "getActorWidth"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x70 | 0xF0:
            result.name = "lights"
            lights = get_var(stream) if a1 else get_byte(stream)
            x_strips = get_byte(stream)
            y_strips = get_byte(stream)
            result.args = {"lights": lights, "x_strips": x_strips, "y_strips": y_strips}

        case 0x71 | 0xF1:
            result.name = "getActorCostume"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x72 | 0xF2:
            result.name = "loadRoom"
            room = get_var(stream) if a1 else get_byte(stream)
            result.args = {"room": room}

        case 0x78 | 0xF8:
            result.name = "isGreater"
            a = get_var(stream)
            b = get_var(stream) if a1 else get_signed_word(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "b": b, "offset": offset}

        case 0x7A | 0xFA:
            result.name = "verbOps"
            verb = get_var(stream) if a1 else get_byte(stream)
            ops = parse_verbops(stream)
            result.args = {"verb": verb, "ops": ops}

        case 0x7B | 0xFB:
            result.name = "getActorWalkBox"
            result.target = get_result_var(stream)
            act = get_var(stream) if a1 else get_byte(stream)
            result.args = {"act": act}

        case 0x7C | 0xFC:
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

        case 0xA8:
            result.name = "notEqualZero"
            a = get_var(stream)
            offset = get_signed_word(stream)
            result.args = {"a": a, "offset": offset}

        case 0xAB:
            result.name = "saveRestoreVerbs"
            op, args = parse_saverestoreverbs(stream)
            result.args = {"op": op, "args": args}

        case 0xAC:  # expression
            result.name = "expression"
            result.target = get_result_var(stream)
            expr = parse_expression(stream)
            result.args = {"expr": expr}
            result.repr = lambda x: f"[expr] {x.target} = {x.args['expr']}"

        case 0xAE:
            result.name = "wait"
            result.args = parse_wait(stream)

        case 0xC0:
            result.name = "endCutscene"

        case 0xC6:  # decrement
            result.name = "decrement"
            result.target = get_result_var(stream)
            result.repr = lambda x: f"{x.target} -= 1"

        case 0xCC:
            result.name = "pseudoRoom"
            val = get_byte(stream)
            src_in = get_byte(stream)
            sources = []
            while src_in != 0x00:
                sources.append(src_in)
                src_in = get_byte(stream)
            result.args = {"val": val, "sources": sources}

        case 0xD8:
            result.name = "printEgo"
            string = parse_sostring(stream)
            result.args = {"string": string}

        case _:
            result.name = "unk"
            result.repr = lambda x: f"unk(0x{x.opcode:02x})"

    end = stream.tell()
    stream.seek(start)
    result.raw = stream.read(end - start)
    return result


def nop():
    return V4Instr(0x18, "jumpRelative", {"offset": 0})


def scumm_v4_tokenizer(
    data: bytes,
    offset: int = 0,
    print_offset: int = 0,
    dump_all: bool = True,
    print_data: bool = False,
    print_prefix: str = "",
):
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
