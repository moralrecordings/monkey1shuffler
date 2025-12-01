from __future__ import annotations
from collections import defaultdict
from typing import Any

from .disasm import V4Var, V4Instr
from .resources import IGameData, update_global_model

def find_pick_up_object(instr_list: list[tuple[int, V4Instr]]):
    result = []
    for off, x in instr_list:
        if x.name == "pickupObject":
            result.append({"offset": off, "op": "pickupObject", "obj": x.args["obj"]})
        elif x.name == "setOwner" and x.args["owner"] == V4Var(1, None):
            result.append({"offset": off, "op": "setOwner", "obj": x.args["obj"]})
    return result


def shuffle_objects(archives: dict[str, Any], content: IGameData):
    # there's pickupObject, which removes the item from the scene and changes ownership
    # we would need to change this to setOwner?

    # we have a big problem. the SCUMM engine will only let you interact
    # with an object if you are on the right screen.
    # and objects are the same thing as hotspots, so you can't just
    # move them to a different room.
    # an update to do this would need to:
    # - split the hotspot object into a room-local thing that picks up the real object.
    # - somehow don't have the object images break
    # - change all the target references? (or not, if the real object is the same as the room hotspot)

    obj_list = []
    obj_loc: defaultdict[int, set[int]] = defaultdict(set)

    for room_id, room in content.items():
        print(f'room {room_id} ({room["name"]})')
        for global_id, glob in room["globals"].items():
            for res in find_pick_up_object(glob["script"]):
                print(f"- global {global_id} - [{res['offset']:04x}] {res}")
                obj_list.append(res)
        for local_id, local in room["locals"].items():
            for res in find_pick_up_object(local["script"]):
                print(f"- local {local_id} - [{res['offset']:04x}] {res}")
                obj_list.append(res)
        for object_id, obj in room["objects"].items():
            for verb_id, verb in obj["verbs"].items():
                for res in find_pick_up_object(verb):
                    print(
                        f"- object {object_id} ({obj['name']}) verb {verb_id} - [{res['offset']:04x}] {res}"
                    )
                    obj_list.append(res)
                    if res['op'] == 'pickupObject':
                        if res['obj'] == V4Var(7, None):
                            obj_loc[room_id].add(object_id)
                        elif isinstance(res['obj'], int):
                            obj_loc[room_id].add(res['obj'])

    # there is no global index for objects; SCUMM learns about them
    # each time you visit a room. which means we need to pre-visit all
    # the rooms for the item-switching hack to work.
    print(obj_loc) 
    
    room_mod = [V4Instr(0x72, "loadRoom", {"room": k}) for k in obj_loc]
    script = content[10]['globals'][1]['script']
    i = 0
    while i < len(script):
        if script[i][1].name == "actorOps" and script[i][1].args['act'] == 1:
            script[i+1:i+1] = [(script[i][0], m) for m in room_mod]
            break
        i += 1
    update_global_model(archives, content, 10, 1) 
    
