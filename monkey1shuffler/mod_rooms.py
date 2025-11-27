from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, NotRequired, TypedDict

from .disasm import (
    V4_VERBS,
    V4Instr,
    V4Var,
    instr_list_to_bytes,
    nop,
    scumm_v4_tokenizer,
)
from .resources import (
    IDisassembly,
    IGameData,
    dump_all,
    get_room_names,
    update_entry_model,
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

MI1EGA_UNUSUABLE_ROOM_LINK = [
    (53, 36),  # foyer -> mansion-e
]


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
    archives: dict[str, Any],
    content: IGameData,
) -> defaultdict[tuple[int, int], list[IRoomLink]]:
    result: defaultdict[tuple[int, int], list[IRoomLink]] = defaultdict(list)
    key: tuple[int, int]

    for room_id, room in content.items():
        for obj_id, obj in room["objects"].items():
            for verb_id, verb in obj["verbs"].items():
                for match in find_room_links(room_id, verb):
                    key = (
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
                key = (
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
    ROOM_NAMES = get_room_names(archives)
    for k in sorted(result.keys()):
        print(k, (ROOM_NAMES.get(k[0]), ROOM_NAMES.get(k[1])))
        for x in result[k]:
            print(f"- {x}")
    return result


def ruin_scumm_bar(archives: dict[str, Any], content: IGameData):
    # content[33]["objects"][437]["verbs"][10][1][1].args['room'] = 78
    # content[33]["objects"][437]["verbs"][10][1][1].args['obj'] = 819
    # update_object_model(content, 33, 437)
    swap_room_links(archives, content, (33, 28), (34, 78))


def swap_room_links(
    archives: dict[str, Any],
    content: IGameData,
    link_src: tuple[int, int],
    link_dest: tuple[int, int],
    room_links: defaultdict[tuple[int, int], list[IRoomLink]] | None = None,
    half: bool = False,
    print_all: bool = False,
):
    # import pdb; pdb.set_trace()
    room_links = room_links if room_links else generate_room_links(archives, content)

    src = room_links[tuple(sorted(link_src))]
    dest = room_links[tuple(sorted(link_dest))]

    ROOM_NAMES = get_room_names(archives)
    if print_all:
        print(
            f"Swap room links {link_src} ({ROOM_NAMES[link_src[0]]} -> {ROOM_NAMES[link_src[1]]}) and {link_dest} ({ROOM_NAMES[link_dest[0]]} -> {ROOM_NAMES[link_dest[1]]})"
        )

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
        if print_all:
            print(f"Injecting {link} with {snippet}")
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

        if print_all:
            print("Disasm before:")
            scumm_v4_tokenizer(instr_list_to_bytes(code), print_data=True)

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

        if print_all:
            print("Disasm after:")
            scumm_v4_tokenizer(instr_list_to_bytes(code), print_data=True)

        if link["type"] == "object":
            update_object_model(archives, content, link["room_src"], link["obj_id"])
        elif link["type"] == "global":
            update_global_model(archives, content, link["room_src"], link["global_id"])
        elif link["type"] == "local":
            update_local_model(archives, content, link["room_src"], link["local_id"])

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

    if print_all:
        print("Code snippets:")
        for k, v in code_snippets.items():
            print(k, v)

    # inject code snippets over links
    for link in [*src, *dest]:
        link_test = (link["room_src"], link["room_dest"])
        if link_test == (link_src[0], link_src[1]):
            # change to link_src[0], link_dest[1]
            if print_all:
                print(f"Swapping {link_test} -> {(link_dest[0], link_dest[1])} ")
            inject_snippet(link, code_snippets[link_dest[0], link_dest[1]])

        elif link_test == (link_src[1], link_src[0]) and not half:
            if print_all:
                print(f"Swapping {link_test} -> {(link_dest[1], link_dest[0])}")
            inject_snippet(link, code_snippets[link_dest[1], link_dest[0]])

            # change to link_dest[1], link_src[0]
        elif link_test == (link_dest[0], link_dest[1]) and not half:
            if print_all:
                print(f"Swapping {link_test} -> {(link_src[0], link_src[1])}")
            inject_snippet(link, code_snippets[link_src[0], link_src[1]])
            # change to link_dest[0], link_src[1]
        elif link_test == (link_dest[1], link_dest[0]):
            if print_all:
                print(f"Swapping {link_test} -> {(link_src[1], link_src[0])}")
            inject_snippet(link, code_snippets[link_src[1], link_src[0]])
            # change to link_src[1], link_dest[0]


def generate_room_linkmap(archives: dict[str, Any], content: IGameData):
    room_links = generate_room_links(archives, content)
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


def find_room_cluster(archives: dict[str, Any], content: IGameData, start_room: int):
    room_linkmap = generate_room_linkmap(archives, content)

    result = set()

    def find_rooms(key):
        for target in room_linkmap[key]:
            if target not in result:
                result.add(target)
                find_rooms(target)

    find_rooms(start_room)
    return result


def shuffle_rooms(
    archives: dict[str, Any], content: IGameData, print_all: bool = False
):
    room_links = generate_room_links(archives, content)
    room_linkmap = generate_room_linkmap(archives, content)
    # start from the dock
    room_cluster = find_room_cluster(archives, content, 33)
    # - start from the first room
    # - for each of the hub rooms
    #   - pick an exit, connect it up
    #   - after connecting a hub room, add the unbound exits to the randomiser
    # - when no hub rooms left, go through remainder and hook up dead ends
    hubs = {k: v for k, v in room_linkmap.items() if len(v) > 1 and k in room_cluster}
    dead_ends = {
        k: v for k, v in room_linkmap.items() if len(v) == 1 and k in room_cluster
    }

    import pdb

    pdb.set_trace()
    ORIGIN = 33
    nodes = set(room_linkmap.keys())
    nodes_to_test = {ORIGIN}
    nodes_done = set()
    edges = set()
    while nodes_to_test:
        node = nodes_to_test.pop()
        nodes_done.add(node)
        edges.update([(node, x) for x in room_linkmap[node] if x not in nodes_done])
        nodes_to_test.update([x for x in room_linkmap[node] if x not in nodes_done])

    start_hub = hubs.pop(ORIGIN)
    links = {(ORIGIN, x) for x in start_hub}

    # we need to generate the new map first, then use that information to rewire the links.
    # doing it progressively will lead to double handling and errors.

    while links:
        orig_link = random.choice(list(links))
        links.remove(orig_link)
        if print_all:
            print(f"--- orig_link: {orig_link}, links: {links}")
        if hubs:
            hub_id = random.choice(list(hubs.keys()))
            hub = hubs.pop(hub_id)
            hub_links = [(hub_id, h) for h in hub]
            for hl in list(hub_links):
                if (hl[1], hl[0]) in MI1EGA_UNUSUABLE_ROOM_LINK or (
                    hl[1],
                    hl[0],
                ) == orig_link:
                    links.add(hl)
                    hub_links.remove(hl)
            new_link = random.choice(hub_links)
            hub_links.remove(new_link)
            new_link = (new_link[1], new_link[0])
            if print_all:
                print(f"--- new_link: {new_link}, hubs: {hubs}")
            swap_room_links(
                archives,
                content,
                orig_link,
                new_link,
                room_links,
                True,
                print_all=print_all,
            )
            links.update(hub_links)
        else:
            dead_end_id = random.choice(list(dead_ends.keys()))
            dead_end = dead_ends.pop(dead_end_id)
            new_link = (dead_end.pop(), dead_end_id)
            if print_all:
                print(f"--- FAKE new_link: {new_link}, dead_ends: {dead_ends}")
            swap_room_links(
                archives, content, orig_link, new_link, room_links, True, print_all=True
            )

    return


def fix_high_street(archives: dict[str, Any], content: IGameData):
    # room 34 (high street) has an entry script that checks if the player
    # is arriving from room 38 (lookout) and moves ego to in front of the store.
    # no idea why this is here, maybe a debug leftover?
    src = content[34]["entry"]["script"]

    modded = False
    for i, (_, instr) in enumerate(src):
        if (
            instr.name == "isEqual"
            and isinstance(instr.args["a"], V4Var)
            and instr.args["a"].id == 101
            and instr.args["b"] == 38
        ):
            # because this is in a big pile of ifs, it's easier to keep the indexes
            src[i] = (src[i][0], nop())
            src[i + 1] = (src[i + 1][0], nop())
            src[i + 2] = (src[i + 2][0], nop())
            modded = True
            break

    # it also makes the screen scroll, which we don't want
    for i, (_, instr) in enumerate(src):
        if instr.name == "roomOps" and instr.args["op"] == "SO_ROOM_SCROLL":
            src[i] = (src[i][0], nop())
            modded = True

    if modded:
        update_entry_model(archives, content, 34)


def fix_bridge_on_map(archives: dict[str, Any], content: IGameData):
    # the map screen has a bridge on it, blocked by a troll. normally this
    # prevents you from walking to stan's and the gym. to simplify things:
    # - treat the bridge as a hub screen with an entrance and an exit
    # - rig the map screen to never block movement
    # - treat the bridge hotspot on the map as a hub exit, like any other map hotspot

    # map screen runs local script 200 if we haven't got rid of the troll, which
    # polls how close we are to the bridge and auto-boots us to the room.
    src = content[85]["entry"]["script"]
    modded = False
    for i, (_, instr) in enumerate(src):
        if instr.name == "startScript" and instr.args["script"] == 200:
            src[i] = (src[i][0], nop())
            modded = True

    if modded:
        update_entry_model(archives, content, 85)


def fix_damn_forest_block(archives: dict[str, Any], content: IGameData):
    # the game tries to be helpful and blocks you from entering the forest unless
    # you have a map or are stalking the storekeeper. making this work with the randomiser
    # sounds painful, so instead we just disable the check. enjoy the damn forest!

    # left hand exit
    src = content[58]["objects"][669]["verbs"][10]
    modded = False
    for i, (_, instr) in enumerate(src):
        if instr.name == "getObjectOwner" and instr.args["obj"] == 449:
            src[i] = (src[i][0], nop())
            src[i + 1] = (src[i + 1][0], nop())
            src[i + 2] = (src[i + 2][0], nop())
            src[i + 3] = (src[i + 3][0], nop())
            src[i + 4] = (src[i + 4][0], nop())
            src[i + 5] = (src[i + 5][0], nop())
            modded = True
            break

    if modded:
        update_object_model(archives, content, 58, 669)

    # top exit
    src = content[58]["objects"][666]["verbs"][10]
    modded = False
    for i, (_, instr) in enumerate(src):
        if instr.name == "getObjectOwner" and instr.args["obj"] == 449:
            src[i] = (src[i][0], nop())
            src[i + 1] = (src[i + 1][0], nop())
            src[i + 2] = (src[i + 2][0], nop())
            src[i + 3] = (src[i + 3][0], nop())
            src[i + 4] = (src[i + 4][0], nop())
            src[i + 5] = (src[i + 5][0], nop())
            src[i + 6] = (src[i + 5][0], nop())
            src[i + 7] = (src[i + 5][0], nop())
            src[i + 8] = (src[i + 5][0], nop())
            modded = True
            break

    if modded:
        update_object_model(archives, content, 58, 666)


def fix_cutscene_links(archive: dict[str, Any], content: IGameData):
    # the game has a few cutscenes triggered by leaving an area, which (after all the rooms
    # are shuffled) need to be rewired to match the destination.
    pass


def room_script_fixups(archives: dict[str, Any], content: IGameData):
    fix_high_street(archives, content)
    fix_bridge_on_map(archives, content)
    fix_damn_forest_block(archives, content)

    # the game tries to be helpful and blocks you from entering the forest unless
    # you have a map or are stalking the storekeeper. making this work with the randomiser
    # sounds painful, so instead we just disable the check.


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
