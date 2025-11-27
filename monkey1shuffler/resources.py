from __future__ import annotations

import hashlib
import pathlib
from typing import Any, TypedDict

from mrcrowbar import models as mrc
from mrcrowbar import utils
from mrcrowbar.common import BytesReadType
from mrcrowbar.transforms import TransformResult

from .disasm import (
    V4_VERBS,
    V4Instr,
    instr_list_to_bytes,
    scumm_v4_tokenizer,
)


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


class CO(mrc.Block):
    id = mrc.UInt8()
    unk = mrc.Bytes()


class SO(mrc.Block):
    id = mrc.UInt8()
    unk = mrc.Bytes()


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
    height = mrc.Bits(0x0B, 0b01111111)
    actor_dir = mrc.Bits(0x0B, 0b10000000)

    @property
    def name_offset(self):
        return self.get_field_end_offset("events") + 0x06

    name_raw_offset = mrc.Pointer(mrc.UInt8(0x0C), mrc.Ref("name_offset"))
    events = mrc.BlockField(ObjectEvent, 0x0D, stream=True, stream_end=b"\x00")
    name = mrc.CString(encoding="cp437")
    data = mrc.Bytes()

    def get_instr(self):
        return scumm_v4_tokenizer(self.data)


class RO(mrc.Block):
    chunks = mrc.ChunkField(
        {b"LS": LS, b"OC": OC, b"EX": SC, b"EN": SC},
        id_size=2,
        length_field=mrc.UInt32_LE,
        default_klass=mrc.Unknown,
        length_before_id=True,
        length_inclusive=True,
    )


class FOEntry(mrc.Block):
    room_id = mrc.UInt8()
    offset = mrc.UInt32_LE()


class FO(mrc.Block):
    count = mrc.UInt8()
    entries = mrc.BlockField(FOEntry, count=mrc.Ref("count"))


class LF(mrc.Block):
    id = mrc.UInt16_LE()
    chunks = mrc.ChunkField(
        {b"RO": RO, b"SC": SC, b"SO": SO, b"CO": CO},
        id_size=2,
        length_field=mrc.UInt32_LE,
        default_klass=mrc.Unknown,
        length_before_id=True,
        length_inclusive=True,
    )


class LE(mrc.Block):
    chunks = mrc.ChunkField(
        {b"FO": FO, b"LF": LF},
        id_size=2,
        length_field=mrc.UInt32_LE,
        default_klass=mrc.Unknown,
        length_before_id=True,
        length_inclusive=True,
    )


class LEC(mrc.Block):
    chunks = mrc.ChunkField(
        {b"LE": LE},
        id_size=2,
        length_field=mrc.UInt32_LE,
        default_klass=mrc.Unknown,
        length_before_id=True,
        length_inclusive=True,
    )


class XORBytes(mrc.Transform):
    def __init__(self, secret, *args, **kwargs):
        self.secret = secret
        super().__init__(*args, **kwargs)

    def import_data(
        self, buffer: BytesReadType, parent: mrc.Block | None = None
    ) -> TransformResult:
        return TransformResult(
            payload=bytes([x ^ self.secret for x in buffer]), end_offset=len(buffer)
        )

    def export_data(
        self, buffer: BytesReadType, parent: mrc.Block | None = None
    ) -> TransformResult:
        return TransformResult(
            payload=bytes([x ^ self.secret for x in buffer]), end_offset=len(buffer)
        )


class RNEntry(mrc.Block):
    id = mrc.UInt8()
    name = mrc.Bytes(length=9, transform=XORBytes(0xFF))


class RN(mrc.Block):
    entries = mrc.BlockField(RNEntry, stream=True, stream_end=b"\x00")


class GlobalIndexItem(mrc.Block):
    room_id = mrc.UInt8()
    offset = mrc.UInt32_LE()


class GlobalIndex(mrc.Block):
    num_items = mrc.UInt16_LE()
    items = mrc.BlockField(GlobalIndexItem, count=mrc.Ref("num_items"))


class LFL(mrc.Block):
    chunks = mrc.ChunkField(
        {
            b"RN": RN,
            b"0S": GlobalIndex,  # lookup for SC chunks
            b"0N": GlobalIndex,  # lookup for SO chunks
            b"0C": GlobalIndex,  # lookup for CO chunks
        },
        id_size=2,
        length_field=mrc.UInt32_LE,
        default_klass=mrc.Unknown,
        length_before_id=True,
        length_inclusive=True,
    )


def get_archives(path: pathlib.Path) -> dict[str, Any]:
    result = {}
    for arch in ["DISK01.LEC", "DISK02.LEC", "DISK03.LEC", "DISK04.LEC"]:
        with open(path / arch, "rb") as file:
            f = bytearray(x ^ 0x69 for x in file.read())

        # for some reason, DISK01.LEC has an invalid chunk size for the sound block in room 10.
        # fix it manually before loading.
        if arch == "DISK01.LEC":
            bodge = utils.find(b"\x15\x82\x00\x00SO--", f)
            if bodge:
                f[bodge[0][0] : bodge[0][0] + 4] = utils.to_uint32_le(0x8115)
        f = bytes(f)
        print(f"Parsing {arch} ({len(f)} bytes, md5 {hashlib.md5(f).hexdigest()})...")
        result[arch] = LEC(f, strict=True)
    with open(path / "000.LFL", "rb") as file:
        f = file.read()
        print(f"Parsing 000.LFL ({len(f)} bytes, md5 {hashlib.md5(f).hexdigest()})...")
        result["000.LFL"] = LFL(f, strict=True)
    return result


def get_room_names(archives: dict[str, Any]) -> dict[int, str]:
    return {
        entry.id: entry.name.strip(b"\x00").decode("cp437")
        for entry in archives["000.LFL"].chunks[0].obj.entries
    }


def get_object_names(archives: dict[str, Any]) -> dict[int, str]:
    return {
        oc.obj.id: oc.obj.name
        for disk in archives.values()
        for le in disk.chunks
        if le.id == b"LE"
        for lf in le.obj.chunks
        if lf.id == b"LF"
        for ro in lf.obj.chunks
        if ro.id == b"RO"
        for oc in ro.obj.chunks
        if oc.id == b"OC"
    }


IDisassembly = tuple[int, V4Instr]


class IGlobalData(TypedDict):
    index: int
    script: list[IDisassembly]


class IObjectData(TypedDict):
    name: str
    index: tuple[int, int]
    verbs: dict[int, list[IDisassembly]]


class ILocalData(TypedDict):
    index: tuple[int, int]
    script: list[IDisassembly]


class IEntryData(TypedDict):
    index: tuple[int, int]
    script: list[IDisassembly]


class IExitData(TypedDict):
    index: tuple[int, int]
    script: list[IDisassembly]


class ICostumeData(TypedDict):
    index: int


class ISoundData(TypedDict):
    index: int


class IRoomData(TypedDict):
    name: str | None
    archive: str
    index: tuple[int, int]
    globals: dict[int, IGlobalData]
    objects: dict[int, IObjectData]
    locals: dict[int, ILocalData]
    costumes: dict[int, ICostumeData]
    sounds: dict[int, ISoundData]
    entry: IEntryData
    exit: IExitData


IGameData = dict[int, IRoomData]


def dump_all(archives: dict[str, Any], print_data: bool = False) -> IGameData:
    results: dict[int, IRoomData] = {}
    ROOM_NAMES = get_room_names(archives)
    GLOBAL_SCRIPT_MAP: dict[tuple[int, int], int] = {
        (gi.room_id, gi.offset + 2): i
        for i, gi in enumerate(archives["000.LFL"].chunks[2].obj.items)
    }

    GLOBAL_SOUND_MAP: dict[tuple[int, int], int] = {
        (gi.room_id, gi.offset + 2): i
        for i, gi in enumerate(archives["000.LFL"].chunks[3].obj.items)
    }

    GLOBAL_COSTUME_MAP: dict[tuple[int, int], int] = {
        (gi.room_id, gi.offset + 2): i
        for i, gi in enumerate(archives["000.LFL"].chunks[4].obj.items)
    }

    for key in ["DISK01.LEC", "DISK02.LEC", "DISK03.LEC", "DISK04.LEC"]:
        disk = archives[key]
        if print_data:
            print(f"- {key}")
        for i, le in enumerate(disk.chunks):
            if le.id != b"LE":
                continue
            for j, lf in enumerate(le.obj.chunks):
                if lf.id != b"LF":
                    continue
                results[lf.obj.id] = {
                    "name": ROOM_NAMES.get(lf.obj.id),
                    "archive": key,
                    "index": (i, j),
                    "globals": {},
                    "objects": {},
                    "locals": {},
                    "costumes": {},
                    "sounds": {},
                }
                if print_data:
                    print(f"  - room {lf.obj.id} ({ROOM_NAMES.get(lf.obj.id)})")
                for k, ro in enumerate(lf.obj.chunks):
                    if ro.id == b"SC":
                        global_idx = (
                            lf.obj.id,
                            lf.obj.get_field_start_offset("chunks", k),
                        )
                        global_id = GLOBAL_SCRIPT_MAP.get(global_idx)
                        if global_id is None:
                            print(
                                f"WARNING: could not find global matching {global_idx}"
                            )
                            continue
                        if print_data:
                            print(
                                f"    - global script {global_id} ({len(ro.obj.data)} bytes)"
                            )
                        results[lf.obj.id]["globals"][global_id] = {
                            "index": k,
                            "script": scumm_v4_tokenizer(
                                ro.obj.data,
                                0,
                                dump_all=True,
                                print_data=print_data,
                                print_prefix="    ",
                            ),
                        }
                        continue
                    elif ro.id == b"CO":
                        costume_idx = (
                            lf.obj.id,
                            lf.obj.get_field_start_offset("chunks", k),
                        )
                        costume_id = GLOBAL_COSTUME_MAP[costume_idx]
                        results[lf.obj.id]["costumes"][costume_id] = {"index": k}
                        continue
                    elif ro.id == b"SO":
                        sound_idx = (
                            lf.obj.id,
                            lf.obj.get_field_start_offset("chunks", k),
                        )
                        sound_id = GLOBAL_SOUND_MAP[sound_idx]
                        results[lf.obj.id]["sounds"][sound_id] = {"index": k}
                        continue
                    elif ro.id != b"RO":
                        continue
                    for l, o in enumerate(ro.obj.chunks):
                        if o.id == b"OC":
                            if print_data:
                                print(
                                    f"    - object script {o.obj.id} ({o.obj.name}) ({len(o.obj.events)} events, {len(o.obj.data)} bytes)"
                                )
                            results[lf.obj.id]["objects"][o.obj.id] = {
                                "name": o.obj.name,
                                "index": (k, l),
                                "verbs": {},
                            }
                            for ev in o.obj.events:
                                verb_name = V4_VERBS.get(ev.verb_id)
                                if print_data:
                                    print(f"        - verb {ev.verb_id} ({verb_name})")
                                start_offset = o.obj.get_field_start_offset("data") + 6
                                results[lf.obj.id]["objects"][o.obj.id]["verbs"][
                                    ev.verb_id
                                ] = scumm_v4_tokenizer(
                                    o.obj.data,
                                    ev.code_offset - start_offset,
                                    dump_all=False,
                                    print_offset=start_offset,
                                    print_data=print_data,
                                    print_prefix="        ",
                                )
                        elif o.id == b"LS":
                            if print_data:
                                print(
                                    f"    - local script {o.obj.id} ({len(o.obj.data)} bytes)"
                                )

                            results[lf.obj.id]["locals"][o.obj.id] = {
                                "index": (k, l),
                                "script": scumm_v4_tokenizer(
                                    o.obj.data,
                                    0,
                                    dump_all=True,
                                    print_data=print_data,
                                    print_prefix="    ",
                                ),
                            }
                        elif o.id == b"EN":
                            if print_data:
                                print(f"    - entry script ({len(o.obj.data)} bytes)")
                            results[lf.obj.id]["entry"] = {
                                "index": (k, l),
                                "script": scumm_v4_tokenizer(
                                    o.obj.data,
                                    0,
                                    dump_all=True,
                                    print_data=print_data,
                                    print_prefix="    ",
                                ),
                            }
                        elif o.id == b"EX":
                            if print_data:
                                print(f"    - exit script ({len(o.obj.data)} bytes)")
                            results[lf.obj.id]["exit"] = {
                                "index": (k, l),
                                "script": scumm_v4_tokenizer(
                                    o.obj.data,
                                    0,
                                    dump_all=True,
                                    print_data=print_data,
                                    print_prefix="    ",
                                ),
                            }
    return results


def get_room_model(archives: dict[str, Any], scripts: IGameData, room_id: int):
    room = scripts[room_id]
    room_model = (
        archives[room["archive"]]
        .chunks[room["index"][0]]
        .obj.chunks[room["index"][1]]
        .obj
    )
    return room_model


def get_local_model(
    archives: dict[str, Any], scripts: IGameData, room_id: int, script_id: int
):
    src = scripts[room_id]["locals"][script_id]
    room_model = get_room_model(archives, scripts, room_id)
    return room_model.chunks[src["index"][0]].obj.chunks[src["index"][1]].obj


def update_local_model(
    archives: dict[str, Any], scripts: IGameData, room_id: int, script_id: int
):
    src = scripts[room_id]["locals"][script_id]
    local_model = get_local_model(archives, scripts, room_id, script_id)
    local_model.data = instr_list_to_bytes(src["script"])


def get_global_model(
    archives: dict[str, Any], scripts: IGameData, room_id: int, script_id: int
):
    src = scripts[room_id]["globals"][script_id]
    room_model = get_room_model(archives, scripts, room_id)
    return room_model.chunks[src["index"]].obj


def update_global_model(
    archives: dict[str, Any], scripts: IGameData, room_id: int, script_id: int
):
    src = scripts[room_id]["globals"][script_id]
    global_model = get_global_model(archives, scripts, room_id, script_id)
    global_model.data = instr_list_to_bytes(src["script"])


def get_object_model(
    archives: dict[str, Any], scripts: IGameData, room_id: int, object_id: int
):
    src = scripts[room_id]["objects"][object_id]
    room_model = get_room_model(archives, scripts, room_id)
    return room_model.chunks[src["index"][0]].obj.chunks[src["index"][1]].obj


def update_object_model(
    archives: dict[str, Any], scripts: IGameData, room_id: int, object_id: int
):
    src = scripts[room_id]["objects"][object_id]
    object_model: OC = get_object_model(archives, scripts, room_id, object_id)
    object_model.name = src["name"]
    object_model.events = []
    object_model.data = b""
    for verb in src["verbs"].keys():
        object_model.events.append(ObjectEvent())
        object_model.events[-1].verb_id = verb
    start_offset = object_model.get_field_start_offset("data") + 6
    for i, (verb_id, code) in enumerate(src["verbs"].items()):
        code_data = instr_list_to_bytes(code)
        object_model.events[i].code_offset = len(object_model.data) + start_offset
        object_model.data += code_data


def get_entry_model(archives: dict[str, Any], scripts: IGameData, room_id: int):
    src = scripts[room_id]["entry"]
    room_model = get_room_model(archives, scripts, room_id)
    return room_model.chunks[src["index"][0]].obj.chunks[src["index"][1]].obj


def update_entry_model(archives: dict[str, Any], scripts: IGameData, room_id: int):
    src = scripts[room_id]["entry"]
    entry_model = get_entry_model(archives, scripts, room_id)
    # print("Before:")
    # scumm_v4_tokenizer(entry_model.data, print_data=True)
    entry_model.data = instr_list_to_bytes(src["script"])
    # print("After:")
    # scumm_v4_tokenizer(entry_model.data, print_data=True)


def get_exit_model(archives: dict[str, Any], scripts: IGameData, room_id: int):
    src = scripts[room_id]["exit"]
    room_model = get_room_model(archives, scripts, room_id)
    return room_model.chunks[src["index"][0]].obj.chunks[src["index"][1]].obj


def update_exit_model(archives: dict[str, Any], scripts: IGameData, room_id: int):
    src = scripts[room_id]["exit"]
    exit_model = get_exit_model(archives, scripts, room_id)
    exit_model.data = instr_list_to_bytes(src["script"])


def save_all(
    archives: dict[str, Any],
    content: IGameData,
    path: pathlib.Path,
    print_all: bool = False,
) -> None:
    print(f"Updating resource offset tables in 000.LFL...")
    for room_id, room in content.items():
        room_model = (
            archives[room["archive"]]
            .chunks[room["index"][0]]
            .obj.chunks[room["index"][1]]
            .obj
        )

        # fix up top-level offsets table in the LFL
        for global_id, glob in room["globals"].items():
            ref = archives["000.LFL"].chunks[2].obj.items[global_id]
            new_offset = room_model.get_field_start_offset("chunks", glob["index"]) - 2
            if ref.offset != new_offset:
                if print_all:
                    print(
                        f"000.LFL 0S table - global {global_id} - offset {ref.offset} -> {new_offset}"
                    )
                ref.offset = new_offset

        for sound_id, sound in room["sounds"].items():
            ref = archives["000.LFL"].chunks[3].obj.items[sound_id]
            new_offset = room_model.get_field_start_offset("chunks", sound["index"]) - 2
            if ref.offset != new_offset:
                if print_all:
                    print(
                        f"000.LFL 0N table - sound {sound_id} - offset {ref.offset} -> {new_offset}"
                    )
                ref.offset = new_offset

        for costume_id, costume in room["costumes"].items():
            ref = archives["000.LFL"].chunks[4].obj.items[costume_id]
            new_offset = (
                room_model.get_field_start_offset("chunks", costume["index"]) - 2
            )
            if ref.offset != new_offset:
                if print_all:
                    print(
                        f"000.LFL 0C table - costume {costume_id} - offset {ref.offset} -> {new_offset}"
                    )
                ref.offset = new_offset

        # fix up file offsets table
        for fo in archives[room["archive"]].chunks[0].obj.chunks[0].obj.entries:
            if fo.room_id != room_id:
                continue
            new_offset = (
                archives[room["archive"]]
                .chunks[room["index"][0]]
                .obj.get_field_start_offset("chunks", room["index"][1])
                + 6
            )
            if fo.offset != new_offset:
                if print_all:
                    print(
                        f"{room['archive']} FO table - room {room_id}: offset {fo.offset} -> {new_offset}"
                    )
                fo.offset = new_offset

    print("Generating new 000.LFL...")
    with open(path / f"000.LFL", "wb") as f:
        f.write(archives["000.LFL"].export_data())

    for k in ["DISK01.LEC", "DISK02.LEC", "DISK03.LEC", "DISK04.LEC"]:
        print(f"Generating new {k}...")
        with open(path / f"{k}", "wb") as f:
            f.write(bytes(x ^ 0x69 for x in archives[k].export_data()))
