from __future__ import annotations

from typing import Dict, Tuple, TypedDict
import random

from mrcrowbar.common import BytesReadType
from mrcrowbar.transforms import TransformResult
from mrcrowbar import models as mrc, utils

from disasm import V4_VERBS, scumm_v4_tokenizer, instr_list_to_bytes, V4Instr, V4Var, V4TextToken


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
    height = mrc.Bits(0x0b, 0b01111111)
    actor_dir = mrc.Bits(0x0b, 0b10000000)

    @property
    def name_offset(self):
        return self.get_field_end_offset("events") + 0x06
    

    name_raw_offset = mrc.Pointer( mrc.UInt8( 0x0c ), mrc.Ref("name_offset") )
    events = mrc.BlockField(ObjectEvent, 0x0d, stream=True, stream_end=b'\x00')
    name = mrc.CString(encoding='cp437')
    data = mrc.Bytes()
    
    def get_instr(self):
        return scumm_v4_tokenizer(self.data)


class RO(mrc.Block):
    chunks = mrc.ChunkField({b'LS': LS, b'OC': OC}, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)


class FOEntry(mrc.Block):
    room_id = mrc.UInt8()
    offset = mrc.UInt32_LE()


class FO(mrc.Block):
    count = mrc.UInt8()
    entries = mrc.BlockField(FOEntry, count=mrc.Ref('count'))


class LF(mrc.Block):
    id = mrc.UInt16_LE()
    chunks = mrc.ChunkField({
        b'RO': RO,
        b'SC': SC,
        b'SO': SO,
        b'CO': CO
    }, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)



class LE(mrc.Block):
    chunks = mrc.ChunkField({b'FO': FO, b'LF': LF}, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)


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
    entries = mrc.BlockField(RNEntry, stream=True, stream_end=b'\x00')


class GlobalIndexItem(mrc.Block):
    room_id = mrc.UInt8()
    offset = mrc.UInt32_LE()

class GlobalIndex(mrc.Block):
    num_items = mrc.UInt16_LE()
    items = mrc.BlockField(GlobalIndexItem, count=mrc.Ref('num_items'))


class LFL(mrc.Block):
    chunks = mrc.ChunkField({
        b'RN': RN,
        b'0S': GlobalIndex, # lookup for SC chunks
        b'0N': GlobalIndex, # lookup for SO chunks
        b'0C': GlobalIndex  # lookup for CO chunks
    }, id_size=2, length_field=mrc.UInt32_LE, default_klass=mrc.Unknown, length_before_id=True, length_inclusive=True)




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

GLOBAL_SOUND_MAP: dict[tuple[int, int], int] = {
    (gi.room_id, gi.offset + 2): i for i, gi in enumerate(lfl.chunks[3].obj.items)
}

GLOBAL_COSTUME_MAP: dict[tuple[int, int], int] = {
    (gi.room_id, gi.offset + 2): i for i, gi in enumerate(lfl.chunks[4].obj.items)
}

IDisassembly = Tuple[int, V4Instr]

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

IGameData = Dict[int, IRoomData]

def dump_all(print_data: bool=False) -> IGameData:
    results: dict[int, IRoomData] = {}
    for key, disk in DISKS.items():
        if print_data:
            print(f"- {key}")
        for i, le in enumerate(disk.chunks):
            if le.id != b'LE':
                continue
            for j, lf in enumerate(le.obj.chunks):
                if lf.id != b'LF':
                    continue
                results[lf.obj.id] = {"name": ROOM_NAMES.get(lf.obj.id), "archive": key, "index": (i, j), "globals": {}, "objects": {}, "locals": {}, "costumes": {}, "sounds": {}}
                if print_data:
                    print(f"  - room {lf.obj.id} ({ROOM_NAMES.get(lf.obj.id)})")
                for k, ro in enumerate(lf.obj.chunks):
                    if ro.id == b'SC':
                        global_idx = (lf.obj.id, lf.obj.get_field_start_offset('chunks', k))
                        global_id = GLOBAL_SCRIPT_MAP.get(global_idx)
                        if global_id is None:
                            print(f"WARNING: could not find global matching {global_idx}")
                            continue
                        if print_data:
                            print(f"    - global script {global_id} ({len(ro.obj.data)} bytes)")
                        results[lf.obj.id]["globals"][global_id] = {"index": k, "script": scumm_v4_tokenizer(ro.obj.data, 0, dump_all=True, print_data=print_data, print_prefix="    ")}
                        continue
                    elif ro.id == b'CO':
                        costume_idx = (lf.obj.id, lf.obj.get_field_start_offset('chunks', k))
                        costume_id = GLOBAL_COSTUME_MAP[costume_idx]
                        results[lf.obj.id]['costumes'][costume_id] = {"index": k}
                        continue
                    elif ro.id == b'SO':
                        sound_idx = (lf.obj.id, lf.obj.get_field_start_offset('chunks', k))
                        sound_id = GLOBAL_SOUND_MAP[sound_idx]
                        results[lf.obj.id]['sounds'][sound_id] = {"index": k}
                        continue
                    elif ro.id != b'RO':
                        continue
                    for l, o in enumerate(ro.obj.chunks):
                        if o.id == b'OC':
                            if print_data:
                                print(f"    - object script {o.obj.id} ({o.obj.name}) ({len(o.obj.events)} events, {len(o.obj.data)} bytes)")
                            results[lf.obj.id]["objects"][o.obj.id] = {"name": o.obj.name, "index": (k, l), "verbs": {}}
                            for ev in o.obj.events:
                                verb_name = V4_VERBS.get(ev.verb_id)
                                if print_data:
                                    print(f"        - verb {ev.verb_id} ({verb_name})")
                                start_offset =o .obj.get_field_start_offset("data")+6 
                                results[lf.obj.id]["objects"][o.obj.id]["verbs"][ev.verb_id] = scumm_v4_tokenizer(o.obj.data, ev.code_offset - start_offset, dump_all=False, print_offset=start_offset, print_data=print_data, print_prefix="        ")
                        elif o.id == b'LS':
                            if print_data:
                                print(f"    - local script {o.obj.id} ({len(o.obj.data)} bytes)")
                            
                            results[lf.obj.id]["locals"][o.obj.id] = {"index": (k, l), "script": scumm_v4_tokenizer(o.obj.data, 0, dump_all=True, print_data=print_data, print_prefix="    ")}
    return results


def get_room_model(scripts: IGameData, room_id: int):
    room = scripts[room_id]
    room_model = DISKS[room["archive"]].chunks[room["index"][0]].obj.chunks[room["index"][1]].obj
    return room_model
   

def get_local_model(scripts: IGameData, room_id: int, script_id: int):
    src = scripts[room_id]['locals'][script_id]
    room_model = get_room_model(scripts, room_id)
    return room_model.chunks[src["index"][0]].obj.chunks[src["index"][1]].obj


def update_local_model(scripts: IGameData, room_id: int, script_id: int):
    src = scripts[room_id]['locals'][script_id]
    local_model = get_local_model(scripts, room_id, script_id)
    local_model.data = instr_list_to_bytes(src["script"])


def get_global_model(scripts: IGameData, room_id: int, script_id: int):
    src = scripts[room_id]['globals'][script_id]
    room_model = get_room_model(scripts, room_id)
    return room_model.chunks[src["index"]].obj


def update_global_model(scripts: IGameData, room_id: int, script_id: int):
    src = scripts[room_id]['globals'][script_id]
    global_model = get_global_model(scripts, room_id, script_id)
    global_model.data = instr_list_to_bytes(src["script"])



def test_mod_intro(scripts: IGameData):

    replace = V4Instr(0xd8, "printEgo", args={"string": [('SO_TEXTSTRING', {'str': [V4TextToken(name="text", data=b"I have bad news^"), V4TextToken(name="wait"), V4TextToken(name="text", data=b"^the recompiler sort of works??")]})]})
    vx = scripts[38]['locals'][203]['script']
    vx[17] = (vx[17][0], replace)

    #local = get_local_model(scripts, 38, 203)
    #print("\nBefore:")
    #scumm_v4_tokenizer(local.data, print_data=True)
    update_local_model(scripts, 38, 203)

    #print("\nAfter:")
    #scumm_v4_tokenizer(local.data, print_data=True)
    

def test_mod_dock_poster():
    replace = V4Instr(0xd8, "printEgo", args={"string": [('SO_TEXTSTRING', {'str': [V4TextToken(name="text", data=b"It says 'Your shonky recompiler works perfectly'^"), V4TextToken(name="wait"), V4TextToken(name="text", data=b"^but that can't be right?")]})]})
    vx = list(ax[33]['objects'][438]['verbs'][9])
    vx[-5] = (vx[-5][0], replace)
    

def turbo_mode(content: IGameData, timer_interval: int=2):
    # scrub through every script and replace the VAR_TIMER_NEXT set statements

    def mod_script(script: list[IDisassembly]) -> bool:
        modded = False
        for _, instr in script:
            if instr.name == "move" and isinstance(instr.target, V4Var) and instr.target.id == 19 and isinstance(instr.args['value'], int):
                instr.args['value'] = timer_interval
                modded = True
        return modded

    for room_id, room in content.items():
        for global_id, glob in room['globals'].items():
            if mod_script(glob['script']):
                update_global_model(content, room_id, global_id)

        for local_id, local in room['locals'].items():
            if mod_script(local['script']):
                update_local_model(content, room_id, local_id)
                    

def non_sequitur_swordfighting(content: IGameData, shuffle_order: bool):
    INSULT_COUNT = 16
    INSULT_FARMER = 7
    INSULT_SHISH = 1

    fight_room = content[88]
    jab_ids = [i for i in range(INSULT_COUNT)]
    retort_ids = [i for i in range(INSULT_COUNT)]
    if shuffle_order:
        random.shuffle(jab_ids)
    random.shuffle(retort_ids)

    jab_script = fight_room['globals'][82]['script']
    retort_script = fight_room['globals'][83]['script']
    jabs = [jab_script[2+ 3*i][1].args['args']['string'][0].data for i in range(INSULT_COUNT)]
    sm_jabs = [jab_script[50+ 3*i][1].args['args']['string'][0].data for i in range(INSULT_COUNT)]
    retorts = [retort_script[2+ 3*i][1].args['args']['string'][0].data for i in range(INSULT_COUNT)]
    for i, x in enumerate(jab_ids):
        jab_script[2+3*i][1].args['args']['string'][0].data = jabs[x]
        jab_script[50+3*i][1].args['args']['string'][0].data = sm_jabs[x]
    for i, x in enumerate(retort_ids):
        retort_script[2+ 3*i][1].args['args']['string'][0].data = retorts[x]
    
    update_global_model(content, 88, 82)
    update_global_model(content, 88, 83)

    convo_script = fight_room['globals'][79]['script']
    convo_script[10][1].args['ops'][0][1]['str'][0].data = b'What an amateur non-sequitur!'
    convo_script[19][1].args['ops'][0][1]['str'][0].data = b"I'm non-sequitured that you'd even try to use that non-sequitur on me!"
    convo_script[25][1].args['args']['string'][0].data = b"That's not fair, you're using the Sword Master's non-sequiturs, I see."
    update_global_model(content, 88, 79)


    smirk_room = content[43]
    training = smirk_room['globals'][57]
    training['script'][513][1].args['ops'][0][1]['str'][0].data = b'^they know just when to throw their opponent with a non-sequitur^'
    training['script'][517][1].args['ops'][0][1]['str'][0].data = b"Let's try a couple of non-sequiturs out, shall we?"
    training['script'][521][1].args['ops'][0][1]['str'][0].data = b"^'" + jabs[jab_ids[INSULT_FARMER]] + b"'"
    training['script'][543][1].args['ops'][1][1]['text'][0].data = retorts[jab_ids[INSULT_FARMER]]
    training['script'][558][1].args['ops'][0][1]['str'][2].data = b"^'"+retorts[retort_ids[INSULT_FARMER]] +b"'"
    training['script'][567][1].args['ops'][0][1]['str'][0].data = b"^'"+jabs[jab_ids[INSULT_SHISH]] +b"'"
    training['script'][591][1].args['ops'][1][1]['text'][0].data = retorts[retort_ids[INSULT_FARMER]]
    training['script'][612][1].args['ops'][0][1]['str'][2].data = b"That was the response from the last non-sequitur."
    training['script'][619][1].args['ops'][0][1]['str'][2].data = b"^'" +jabs[jab_ids[INSULT_SHISH]] + b"'^"
    training['script'][622][1].args['ops'][0][1]['str'][0].data = b"^'" +retorts[retort_ids[INSULT_SHISH]] + b"'"
    training['script'][626][1].args['ops'][0][1]['str'][0].data = b"Now I suggest you go out there and learn some non-sequiturs."
    update_global_model(content, 43, 57)

    
    print("\nAfter:")
    model = get_global_model(content, 43, 57)
    scumm_v4_tokenizer(model.data, print_data=True)


ax = dump_all(True)


def save_all(content):
    for room_id, room in content.items():
        room_model = DISKS[room["archive"]].chunks[room["index"][0]].obj.chunks[room["index"][1]].obj

        # fix up top-level offsets table in the LFL
        for global_id, glob in room["globals"].items():
            ref = lfl.chunks[2].obj.items[global_id]
            new_offset = room_model.get_field_start_offset('chunks', glob["index"]) - 2
            if ref.offset != new_offset:
                print(f"000.LFL 0S table - global {global_id} - offset {ref.offset} -> {new_offset}")
                ref.offset = new_offset

        for sound_id, sound in room["sounds"].items():
            ref = lfl.chunks[3].obj.items[sound_id]
            new_offset = room_model.get_field_start_offset('chunks', sound["index"]) - 2
            if ref.offset != new_offset:
                print(f"000.LFL 0N table - sound {sound_id} - offset {ref.offset} -> {new_offset}")
                ref.offset = new_offset

        for costume_id, costume in room["costumes"].items():
            ref = lfl.chunks[4].obj.items[costume_id]
            new_offset = room_model.get_field_start_offset('chunks', costume["index"]) - 2
            if ref.offset != new_offset:
                print(f"000.LFL 0C table - costume {costume_id} - offset {ref.offset} -> {new_offset}")
                ref.offset = new_offset

        # fix up file offsets table
        for fo in DISKS[room["archive"]].chunks[0].obj.chunks[0].obj.entries:
            if fo.room_id != room_id:
                continue
            new_offset = DISKS[room["archive"]].chunks[room["index"][0]].obj.get_field_start_offset('chunks', room["index"][1]) + 6
            if fo.offset != new_offset:
                print(f"{room['archive']} FO table - room {room_id}: offset {fo.offset} -> {new_offset}")
                fo.offset = new_offset
    

    with open(f"output/000.LFL", "wb") as f:
        f.write(lfl.export_data())

    for k, v in DISKS.items():
        with open(f"output/{k}", "wb") as f:
            f.write(bytes(x^0x69 for x in v.export_data()))


