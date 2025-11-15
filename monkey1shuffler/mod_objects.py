from __future__ import annotations

from .resources import IGameData

def find_pick_up_object(instr_list: list[tuple[int, V4Instr]]):
    result = []
    for off, x in instr_list:
        if x.name == "pickupObject":
            result.append({"offset": off, "obj": x.args["obj"]})
    return result


def shuffle_objects(content: IGameData):
    # there's pickupObject, which removes the item from the scene and changes ownership
    # we would need to change this to setOwner?

    for room_id, room in content.items():
        print(f'room {room_id} ({room["name"]})')
        for global_id, glob in room["globals"].items():
            for res in find_pick_up_object(glob["script"]):
                print(f"- global {global_id} - [{res['offset']:04x}] {res['obj']}")
        for local_id, local in room["locals"].items():
            for res in find_pick_up_object(local["script"]):
                print(f"- local {local_id} - [{res['offset']:04x}] {res['obj']}")
        for object_id, obj in room["objects"].items():
            for verb_id, verb in obj["verbs"].items():
                for res in find_pick_up_object(verb):
                    print(
                        f"- object {object_id} ({obj['name']}) verb {verb_id} - [{res['offset']:04x}] {res['obj']}"
                    )




