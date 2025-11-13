from __future__ import annotations

import random
from collections import defaultdict
from typing import NotRequired, TypedDict

from disasm import V4_VERBS, V4Instr, V4Var
from resources import (
    ROOM_NAMES,
    IDisassembly,
    IGameData,
    dump_all,
    update_global_model,
    update_local_model,
    update_object_model,
)

# classification of game rooms

# for now exclude the follow autorun script ones from the shuffle
# - 51 is inside the circus tent
# - 37 is inside meathook's house
# - 60 is inside smirk's gym
#
MI1EGA_ROOM_CLASS: dict[str, set[int]] = {
    "card": {90, 96, 10, 97, 98, 95, 94},
    "map": {63, 85, 2, 3, 4, 5, 6},
    "outdoors": {
        38,
        33,
        61,
        35,
        32,
        34,
        57,
        36,
        59,
        58,
        43,
        52,
        48,
        64,
        15,
        19,
        17,
        12,
        69,
        21,
        18,
        11,
        16,
        40,
        25,
        80,
    },
    "indoors": {
        28,
        41,
        29,
        53,
        31,
        30,
        78,
        7,
        8,
        9,
        14,
        65,
        70,
        39,
        71,
        72,
        73,
        74,
        75,
        77,
        27,
    },
    "closeup": {
        44,
        83,
        42,
        79,
        82,
        81,
        23,
        45,
        89,
        62,
        49,
        60,
        76,
        88,
        51,
        37,
        50,
        84,
        87,
        86,
    },
    "beach": {20, 1},
}
MI1EGA_ROOM_CLUSTER: dict[str, set[int]] = {
    "melee": {
        63,
        85,
        38,
        33,
        61,
        35,
        32,
        34,
        57,
        36,
        59,
        58,
        43,
        52,
        48,
        64,
        28,
        41,
        29,
        53,
        31,
        30,
        78,
        44,
        83,
        42,
        79,
        82,
        81,
        23,
        45,
        89,
        62,
        49,
        60,
        76,
        88,
        51,
        37,
        50,
        15,
    },
    "ship": {7, 8, 9, 14, 19, 17, 84, 87},
    "monkey": {
        12,
        69,
        65,
        70,
        39,
        71,
        72,
        73,
        74,
        75,
        77,
        20,
        1,
        2,
        3,
        4,
        5,
        6,
        21,
        18,
        11,
        16,
        40,
        25,
        27,
        80,
    },
}


def find_room_links(room_id: int, instr_list: list[tuple[int, V4Instr]]):
    result = []
    for i, (off, x) in enumerate(instr_list):
        target = x.args.get("room")
        if not isinstance(target, int):
            continue
        if target == room_id:
            continue
        if target == 0:
            continue
        if target >= 200:
            continue
        if room_id in MI1EGA_ROOM_CLASS["closeup"]:
            return []
        if target in MI1EGA_ROOM_CLASS["closeup"]:
            continue
        if room_id in MI1EGA_ROOM_CLASS["card"]:
            return []
        if target in MI1EGA_ROOM_CLASS["card"]:
            continue
        if x.name == "loadRoomWithEgo":
            result.append({"offset": off, "room": target, "op": "loadRoomWithEgo"})
        elif (
            x.name == "putActorInRoom"
            and isinstance(x.args["act"], V4Var)
            and x.args["act"].id == 1
        ):
            result.append({"offset": off, "room": target, "op": "putActorInRoom"})

    return result


def find_forest_links(instr_list: list[tuple[int, V4Instr]]):
    result = []
    for off, x in instr_list:
        if x.name == "loadRoomWithEgo" and x.args["room"] >= 200:
            result.append(
                {"offset": off, "room": x.args["room"], "op": "loadRoomWithEgo"}
            )
    return result


# finding inter-room links:
# - we only want to deal with links that happen from the user walking to a hotspot.
# - there will be at least some that get interrupted (e.g. for a cutscene in a different place)
# - find all connections based on objects, use that to produce a linkages map
# - find any secondary conections in the globals/locals which line up with the linkages
# - pick start points (dock, captain's cabin, beach with banana tree)


class IRoomLink(TypedDict):
    room_src: int
    room_dest: int
    offset: int
    op: str
    type: str
    obj_id: NotRequired[int]
    verb_id: NotRequired[int]
    local_id: NotRequired[int]
    global_id: NotRequired[int]


def generate_room_links(
    content: IGameData,
) -> defaultdict[tuple[int, int], list[IRoomLink]]:
    result: defaultdict[tuple[int, int], list[IRoomLink]] = defaultdict(list)

    for room_id, room in content.items():
        for obj_id, obj in room["objects"].items():
            for verb_id, verb in obj["verbs"].items():
                for match in find_room_links(room_id, verb):
                    key: tuple[int, int] = (
                        (room_id, match["room"])
                        if room_id < match["room"]
                        else (match["room"], room_id)
                    )
                    result[key].append(
                        {
                            "room_src": room_id,
                            "room_dest": match["room"],
                            "type": "object",
                            "obj_id": obj_id,
                            "verb_id": verb_id,
                            "offset": match["offset"],
                            "op": match["op"],
                        }
                    )
        for local_id, local in room["locals"].items():
            for match in find_room_links(room_id, local["script"]):
                key: tuple[int, int] = (
                    (room_id, match["room"])
                    if room_id < match["room"]
                    else (match["room"], room_id)
                )
                result[key].append(
                    {
                        "room_src": room_id,
                        "room_dest": match["room"],
                        "type": "local",
                        "local_id": local_id,
                        "offset": match["offset"],
                        "op": match["op"],
                    }
                )
    #        for global_id, glob in room["globals"].items():
    #            for match in find_room_links(room_id, glob['script']):
    #                key: tuple[int, int] = (room_id, match["room"]) if room_id < match["room"] else (match["room"], room_id)
    #                result[key].append(
    #                    {
    #                        "room_src": room_id,
    #                        "room_dest": match["room"],
    #                        "type": "global",
    #                        "global_id": global_id,
    #                    }
    #                )

    for k in sorted(result.keys()):
        print(k, (ROOM_NAMES.get(k[0]), ROOM_NAMES.get(k[1])))
        for x in result[k]:
            print(f"- {x}")
    return result


def ruin_scumm_bar(content: IGameData):
    # content[33]["objects"][437]["verbs"][10][1][1].args['room'] = 78
    # content[33]["objects"][437]["verbs"][10][1][1].args['obj'] = 819
    # update_object_model(content, 33, 437)
    import pdb

    pdb.set_trace()
    swap_room_links(content, (33, 28), (34, 78))


def swap_room_links(
    content: IGameData,
    link_src: tuple[int, int],
    link_dest: tuple[int, int],
    room_links=None,
    half=False,
):
    room_links = room_links if room_links else generate_room_links(content)

    src = room_links[tuple(sorted(link_src))]
    dest = room_links[tuple(sorted(link_dest))]

    print(f"Swap room links {link_src} {link_dest}")

    code_snippets = {}

    def get_snippet(link: IRoomLink) -> list[IDisassembly]:
        code = None
        result: list[IDisassembly] = []
        if link["type"] == "object":
            code = content[link["room_src"]]["objects"][link["obj_id"]]["verbs"][
                link["verb_id"]
            ]
        elif link["type"] == "global":
            code = content[link["room_src"]]["globals"][link["global_id"]]["script"]
        elif link["type"] == "local":
            code = content[link["room_src"]]["locals"][link["local_id"]]["script"]
        if not code:
            return result
        i = 0
        while i < len(code):
            if code[i][0] == link["offset"]:
                if link["op"] == "loadRoomWithEgo":
                    # one instruction, that's all we need
                    return [(0, code[i][1])]
                elif link["op"] == "putActorInRoom":
                    result.append((0, code[i][1]))
                    i += 1
                    if code[i][1].name == "putActor":
                        result.append((0, code[i][1]))

                    result.append(
                        (0, V4Instr(0xD2, "actorFollowCamera", {"act": V4Var(1, 0)}))
                    )
                    return result
            i += 1
        return result

    # overwrite an existing link with some replacement code
    def inject_snippet(link: IRoomLink, snippet: list[IDisassembly]):
        code = None
        if link["type"] == "object":
            code = content[link["room_src"]]["objects"][link["obj_id"]]["verbs"][
                link["verb_id"]
            ]
        elif link["type"] == "global":
            code = content[link["room_src"]]["globals"][link["global_id"]]["script"]
        elif link["type"] == "local":
            code = content[link["room_src"]]["locals"][link["local_id"]]["script"]
        if not code:
            return

        start = 0
        while start < len(code):
            if code[start][0] == link["offset"]:
                if link["op"] == "loadRoomWithEgo":
                    code[start : start + 1] = [(link["offset"], c) for o, c in snippet]
                    break
                elif link["op"] == "putActorInRoom":
                    if code[start + 1][1].name == "putActor":
                        code[start : start + 2] = [
                            (link["offset"], c) for o, c in snippet
                        ]
                    else:
                        code[start : start + 1] = [
                            (link["offset"], c) for o, c in snippet
                        ]
                    break
            start += 1

        if link["type"] == "object":
            update_object_model(content, link["room_src"], link["obj_id"])
        elif link["type"] == "global":
            update_global_model(content, link["room_src"], link["global_id"])
        elif link["type"] == "local":
            update_local_model(content, link["room_src"], link["local_id"])

    # get code snippets for existing links
    for link in [*src, *dest]:
        link_test = (link["room_src"], link["room_dest"])
        if link_test == (link_src[0], link_src[1]):
            code_snippets[(link_src[0], link_src[1])] = get_snippet(link)
        elif link_test == (link_src[1], link_src[0]):
            code_snippets[(link_src[1], link_src[0])] = get_snippet(link)
        elif link_test == (link_dest[0], link_dest[1]):
            code_snippets[(link_dest[0], link_dest[1])] = get_snippet(link)
        elif link_test == (link_dest[1], link_dest[0]):
            code_snippets[(link_dest[1], link_dest[0])] = get_snippet(link)

    # inject code snippets over links
    for link in [*src, *dest]:
        link_test = (link["room_src"], link["room_dest"])
        if link_test == (link_src[0], link_src[1]):
            # change to link_src[0], link_dest[1]
            print(f"Swapping {link_test} -> {(link_dest[0], link_dest[1])} ")
            inject_snippet(link, code_snippets[link_dest[0], link_dest[1]])

        elif link_test == (link_src[1], link_src[0]) and not half:
            print(f"Swapping {link_test} -> {(link_dest[1], link_dest[0])}")
            inject_snippet(link, code_snippets[link_dest[1], link_dest[0]])

            # change to link_dest[1], link_src[0]
        elif link_test == (link_dest[0], link_dest[1]) and not half:
            print(f"Swapping {link_test} -> {(link_src[0], link_src[1])}")
            inject_snippet(link, code_snippets[link_src[0], link_src[1]])
            # change to link_dest[0], link_src[1]
        elif link_test == (link_dest[1], link_dest[0]):
            print(f"Swapping {link_test} -> {(link_src[1], link_src[0])}")
            inject_snippet(link, code_snippets[link_src[1], link_src[0]])
            # change to link_src[1], link_dest[0]


def generate_room_linkmap(content: IGameData):
    room_links = generate_room_links(content)
    room_linkmap = defaultdict(set)

    all_links = set()
    for k, v in room_links.items():
        for entry in v:
            all_links.add((entry["room_src"], entry["room_dest"]))

    for k, v in room_links.items():
        for entry in v:
            if ((entry["room_src"], entry["room_dest"]) in all_links) and (
                (entry["room_dest"], entry["room_src"]) in all_links
            ):
                room_linkmap[entry["room_src"]].add(entry["room_dest"])

    return room_linkmap


def find_room_cluster(content: IGameData, start_room: int):
    room_linkmap = generate_room_linkmap(content)

    result = set()

    def find_rooms(key):
        for target in room_linkmap[key]:
            if target not in result:
                result.add(target)
                find_rooms(target)

    find_rooms(start_room)
    return result


def shuffle_room_links(content: IGameData):
    room_links = generate_room_links(content)
    room_linkmap = generate_room_linkmap(content)
    # start from the dock
    room_cluster = find_room_cluster(content, 33)
    # - start from the first room
    # - for each of the hub rooms
    #   - pick an exit, connect it up
    #   - after connecting a hub room, add the unbound exits to the randomiser
    # - when no hub rooms left, go through remainder and hook up dead ends
    hubs = {k: v for k, v in room_linkmap.items() if len(v) > 1 and k in room_cluster}
    dead_ends = {
        k: v for k, v in room_linkmap.items() if len(v) == 1 and k in room_cluster
    }
    random.seed(999)

    start_hub = hubs.pop(33)
    links = {(33, x) for x in start_hub}
    while links:
        orig_link = random.choice(list(links))
        links.remove(orig_link)
        print(f"--- orig_link: {orig_link}, links: {links}")
        if hubs:
            hub_id = random.choice(list(hubs.keys()))
            hub = hubs.pop(hub_id)
            hub_links = [(hub_id, h) for h in hub]
            new_link = random.choice(hub_links)
            hub_links.remove(new_link)
            new_link = (new_link[1], new_link[0])
            print(f"--- new_link: {new_link}, hubs: {hubs}")
            swap_room_links(content, orig_link, new_link, room_links, True)
            links.update(hub_links)
        else:
            dead_end_id = random.choice(list(dead_ends.keys()))
            dead_end = dead_ends.pop(dead_end_id)
            new_link = (dead_end.pop(), dead_end_id)
            print(f"--- new_link: {new_link}, dead_ends: {dead_ends}")
            swap_room_links(content, orig_link, new_link, room_links, True)

    return


def room_links_1():
    g = graphviz.Digraph(
        edge_attr={"fontsize": "12"},
        graph_attr={"compound": "true", "rankdir": "LR", "pack": "16"},
    )
    data = dump_all()
    room_idx = {}

    for room_id, room in data.items():
        room_idx[room_id] = f"Room {room_id} {room['name']}"
        with g.subgraph(
            name=f"cluster_room_{room_id}", graph_attr={"rankdir": "LR"}
        ) as sub:
            sub.attr(margin="8")
            with sub.subgraph(name=f"cluster_inv_room_{room_id}") as inv:
                inv.attr(peripheries="0", margin="0")
                inv.node(f"inv_room_{room_id}", shape="point", style="invis")
            sub.attr(
                label=room_idx[room_id],
                shape="rectangle",
                style="filled, rounded",
                fillcolor="lightgray",
            )
            # for glob_id, glob in room["globals"].items():
            #    links = find_leave_room(glob)
            #    if links:
            #        sub.node(f"glob_{glob_id}", label=f"Global {glob_id}", shape="rectangle", style="rounded, filled", fillcolor="lightblue")
            #        for link in links:
            #            if link["room"] in room_idx and link["room"] != room_id:
            #                g.edge(f"glob_{glob_id}", f"inv_room_{link['room']}", lhead=f"cluster_room_{link['room']}")

            # for local_id, local in room["locals"].items():
            #    links = find_leave_room(local)
            #    if links:
            #        sub.node(f"room_{room_id}_local_{local_id}", label=f"Local {local_id}", shape="rectangle", style="rounded, filled", fillcolor="lightgreen")
            #        for link in links:
            #            if link["room"] in room_idx and link["room"] != room_id:
            #                g.edge(f"room_{room_id}_local_{local_id}", f"inv_room_{link['room']}", lhead=f"cluster_room_{link['room']}")

            for obj_id, obj in room["objects"].items():
                for verb_id, verb in obj["verbs"].items():
                    links = find_leave_room(verb)
                    if links:
                        verb_name = V4_VERBS.get(verb_id, f"(verb {verb_id})")
                        desc = f"[obj {obj_id}] {verb_name} {obj['name']}"
                        sub.node(
                            f"obj_{obj_id}_verb_{verb_id}",
                            label=desc,
                            shape="rectangle",
                            style="rounded, filled",
                            fillcolor="khaki",
                        )
                        for link in links:
                            if link["room"] in room_idx and link["room"] != room_id:
                                g.edge(
                                    f"obj_{obj_id}_verb_{verb_id}",
                                    f"inv_room_{link['room']}",
                                    lhead=f"cluster_room_{link['room']}",
                                )

    g.render(engine="dot", filename="test.dot")

    return g
    # iterate through the entire script library
    # find scripts which call loadRoomWithEgo
    # join them up on a graph


def room_links_2():
    g = graphviz.Digraph(
        edge_attr={"fontsize": "12"}, graph_attr={"rankdir": "LR", "overlap": "false"}
    )
    data = dump_all()
    room_idx = {}

    for room_id, room in data.items():
        room_idx[room_id] = f"[room {room_id}] {room['name']}"
        g.node(
            f"room_{room_id}",
            label=room_idx[room_id],
            shape="rectangle",
            style="filled, rounded",
            fillcolor="khaki",
        )

    for room_id, room in data.items():
        links = []
        # for glob_id, glob in room["globals"].items():
        #    new_links = find_leave_room(glob)
        #    for l in new_links:
        #        l["desc"] = f"[global {glob_id} 0x{l['offset']:04x}]"
        #    links.extend(new_links)

        # for local_id, local in room["locals"].items():
        #    new_links = find_leave_room(local)
        #    for l in new_links:
        #        l['desc'] = f"[local {local_id} 0x{l['offset']:04x}]"
        #    links.extend(new_links)

        for obj_id, obj in room["objects"].items():
            for verb_id, verb in obj["verbs"].items():
                new_links = find_leave_room(verb)
                verb_name = V4_VERBS.get(verb_id, f"(verb {verb_id})")
                for l in new_links:
                    desc = (
                        f"[obj {obj_id} 0x{l['offset']:04x}] {verb_name} {obj['name']}"
                    )
                    l["desc"] = desc
                links.extend(new_links)

        for l in links:
            if l["room"] in room_idx:
                g.edge(f"room_{room_id}", f"room_{l['room']}", label=l["desc"])

    g.render(engine="dot", filename="test.dot")

    return g
    # iterate through the entire script library
    # find scripts which call loadRoomWithEgo
    # join them up on a graph
