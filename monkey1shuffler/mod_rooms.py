from __future__ import annotations

import pathlib
import random
from collections import defaultdict
from typing import Any, Literal, NotRequired, Optional, TypedDict

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
    get_object_model,
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

IScriptType = Literal["object", "local", "global"]


class IScriptRef(TypedDict):
    type: IScriptType
    room: int
    id: int
    verb: int | None


class IRoomLink(TypedDict):
    offset: int
    source: IScriptRef
    target: IScriptRef
    code_room: int
    op: str


def find_room_links(
    room_id: int,
    script_type: IScriptType,
    obj_id: int,
    verb_id: int | None,
    instr_list: list[IDisassembly],
) -> list[IRoomLink]:
    result: list[IRoomLink] = []
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
            result.append(
                {
                    "offset": i,
                    "source": {
                        "type": script_type,
                        "room": room_id,
                        "id": obj_id,
                        "verb": verb_id,
                    },
                    "target": {
                        "type": "object",
                        "room": target,
                        "id": x.args["obj"],
                        "verb": verb_id,
                    },
                    "op": "loadRoomWithEgo",
                    "code_room": room_id,
                }
            )
        elif x.name == "putActorInRoom" and x.args["act"] == V4Var(1, None):
            result.append(
                {
                    "offset": i,
                    "source": {
                        "type": script_type,
                        "room": room_id,
                        "id": obj_id,
                        "verb": verb_id,
                    },
                    "target": {
                        "type": "object",
                        "room": target,
                        "id": -1,
                        "verb": verb_id,
                    },
                    "op": "putActorInRoom",
                    "code_room": room_id,
                }
            )

    return result


# finding inter-room links:
# - we only want to deal with links that happen from the user walking to a hotspot.
# - there will be at least some that get interrupted (e.g. for a cutscene in a different place)
# - find all connections based on objects, use that to produce a linkages map
# - find any secondary conections in the globals/locals which line up with the linkages
# - pick start points (dock, captain's cabin, beach with banana tree)


def generate_room_links(
    archives: dict[str, Any],
    content: IGameData,
) -> list[IRoomLink]:
    result: list[IRoomLink] = []

    for room_id, room in content.items():
        for obj_id, obj in room["objects"].items():
            for verb_id, verb in obj["verbs"].items():
                for match in find_room_links(room_id, "object", obj_id, verb_id, verb):
                    result.append(match)
        for local_id, local in room["locals"].items():
            for match in find_room_links(
                room_id, "local", local_id, None, local["script"]
            ):
                result.append(match)
    #        for global_id, glob in room["globals"].items():
    #            for match in find_room_links(room_id, "global", global_id, None, glob['script']):
    #               result.append(match)
    ROOM_NAMES = get_room_names(archives)
    for x in sorted(result, key=lambda x: (x["source"]["room"], x["target"]["room"])):
        print(
            ROOM_NAMES.get(x["source"]["room"]), ROOM_NAMES.get(x["target"]["room"]), x
        )
    return result


def find_link(links: list[IRoomLink], room: int, obj: int) -> list[IRoomLink]:
    return [
        l for l in links if l["source"]["room"] == room and l["source"]["id"] == obj
    ]


def find_link_inverse(links: list[IRoomLink], room: int, obj: int) -> list[IRoomLink]:
    sources = [
        l for l in links if l["source"]["room"] == room and l["source"]["id"] == obj
    ]
    result: list[IRoomLink] = []
    # find reverse matches for object id
    for x in sources:
        result.extend(find_link(links, x["target"]["room"], x["target"]["id"]))
        # sometimes the game will reference a room from a script
        for link in [
            y
            for y in links
            if y["source"]["room"] == x["target"]["room"]
            and y["source"]["type"] == "local"
        ]:
            result.append(link)
    return result


def find_link_room(links: list[IRoomLink], room_a: int, room_b: int) -> list[IRoomLink]:
    return [
        l
        for l in links
        if l["source"]["room"] == room_a and l["target"]["room"] == room_b
    ]


def find_room_cluster(links: list[IRoomLink], start_room: int) -> set[int]:

    result = set()

    def find_rooms(key):
        for link in [x for x in links if x["source"]["room"] == key]:
            target = link["target"]["room"]
            if target not in result:
                result.add(target)
                find_rooms(target)

    find_rooms(start_room)
    return result


def write_changes_from_links(
    archives: dict[str, Any], scripts: IGameData, links: list[IRoomLink]
):
    for link in links:
        if link["source"]["type"] == "object":
            update_object_model(
                archives, scripts, link["source"]["room"], link["source"]["id"]
            )
        elif link["source"]["type"] == "local":
            update_local_model(
                archives, scripts, link["source"]["room"], link["source"]["id"]
            )
        elif link["source"]["type"] == "global":
            update_global_model(
                archives, scripts, link["source"]["room"], link["source"]["id"]
            )


def get_code(content: IGameData, link: IRoomLink) -> list[IDisassembly]:
    if link["source"]["type"] == "object":
        return content[link["code_room"]]["objects"][link["source"]["id"]]["verbs"][
            link["source"]["verb"]
        ]
    elif link["source"]["type"] == "local":
        return content[link["code_room"]]["locals"][link["source"]["id"]]["script"]
    elif link["source"]["type"] == "global":
        return content[link["code_room"]]["globals"][link["source"]["id"]]["script"]
    return []


def get_code_instr(content: IGameData, link: IRoomLink) -> V4Instr:
    code = get_code(content, link)
    return code[link["offset"]][1]


def set_code_instr(content: IGameData, link: IRoomLink, instr: V4Instr) -> None:
    code = get_code(content, link)
    code[link["offset"]] = (code[link["offset"]][0], instr)


def exchange_links(content: IGameData, a: IRoomLink, b: IRoomLink) -> None:
    src_code = get_code(content, a)
    dest_code = get_code(content, b)
    tmp = src_code[a["offset"]]
    src_code[a["offset"]] = (src_code[a["offset"]][0], dest_code[b["offset"]][1])
    dest_code[b["offset"]] = (dest_code[b["offset"]][0], tmp[1])

    a_target = a["target"]
    b_target = b["target"]
    a["target"] = b_target
    b["target"] = a_target


def exchange_multilinks(
    content: IGameData, a: list[IRoomLink], b: list[IRoomLink]
) -> None:
    assert len(a)
    assert len(b)

    # assume the instruction for jumping between rooms is going to be basically the same
    src_instr = get_code(content, a[0])[a[0]["offset"]][1]
    dest_instr = get_code(content, b[0])[b[0]["offset"]][1]
    src_target: IScriptRef = {**a[0]["target"]}
    dest_target: IScriptRef = {**b[0]["target"]}
    for link in a:

        src_code = get_code(content, link)
        src_code[link["offset"]] = (src_code[link["offset"]][0], dest_instr)
        link["target"] = dest_target
    for link in b:
        dest_code = get_code(content, link)
        dest_code[link["offset"]] = (dest_code[link["offset"]][0], src_instr)
        link["target"] = src_target


def move_passage(
    content: IGameData,
    links: list[IRoomLink],
    a: IRoomLink,
    b: IRoomLink,
    c: IRoomLink,
    d: IRoomLink,
) -> None:
    # remove passage from old segment and join ends
    left = find_link(links, a["target"]["room"], a["target"]["id"])[0]
    right = find_link(links, b["target"]["room"], b["target"]["id"])[0]
    a_code = get_code_instr(content, a)
    b_code = get_code_instr(content, b)
    left_code = get_code_instr(content, left)
    right_code = get_code_instr(content, right)
    set_code_instr(content, left, b_code)
    set_code_instr(content, right, a_code)
    left["target"]["room"] = right["source"]["room"]
    left["target"]["id"] = right["source"]["id"]
    right["target"]["room"] = left["source"]["room"]
    right["target"]["id"] = left["source"]["id"]

    # attach passage to new segment
    c_code = get_code_instr(content, c)
    d_code = get_code_instr(content, d)
    set_code_instr(content, a, d_code)
    set_code_instr(content, b, c_code)
    a["target"]["room"] = d["target"]["room"]
    a["target"]["id"] = d["target"]["id"]
    b["target"]["room"] = c["target"]["room"]
    b["target"]["id"] = c["target"]["id"]

    # adjust segment to point to passage
    set_code_instr(content, c, left_code)
    set_code_instr(content, d, right_code)
    c["target"]["room"] = a["source"]["room"]
    c["target"]["id"] = a["source"]["id"]
    d["target"]["room"] = b["source"]["room"]
    d["target"]["id"] = b["source"]["id"]


def room_link_swap(
    content: IGameData,
    links: list[IRoomLink],
    src_room: int,
    src_obj: int,
    dest_room: int,
    dest_obj: int,
) -> None:
    src_link = find_link(links, src_room, src_obj)[0]
    dest_link = find_link(links, dest_room, dest_obj)[0]
    src_end_link = find_link(
        links, src_link["target"]["room"], src_link["target"]["id"]
    )[0]
    dest_end_link = find_link(
        links, dest_link["target"]["room"], dest_link["target"]["id"]
    )[0]

    exchange_links(content, src_link, dest_link)
    exchange_links(content, src_end_link, dest_end_link)


def forest_room_link_swap(
    content: IGameData,
    links: list[IRoomLink],
    src_room: int,
    src_obj: int,
    dest_room: int,
    dest_obj: int,
) -> None:
    src_link = find_link(links, src_room, src_obj)[0]
    dest_link = find_link(links, dest_room, dest_obj)[0]
    src_end_link = find_link(
        links, src_link["target"]["room"], src_link["target"]["id"]
    )[0]
    dest_end_link = find_link(
        links, dest_link["target"]["room"], dest_link["target"]["id"]
    )[0]

    exchange_links(content, src_link, dest_link)
    exchange_links(content, src_end_link, dest_end_link)


def room_link_inject(
    content: IGameData,
    links: list[IRoomLink],
    src_room: int,
    src_obj_left: int,
    src_obj_right: int,
    dest_room: int,
    dest_obj: int,
) -> None:
    src_link_left = find_link(links, src_room, src_obj_left)[0]
    src_link_right = find_link(links, src_room, src_obj_right)[0]

    dest_link = find_link(links, dest_room, dest_obj)[0]
    dest_link_end = find_link(
        links, dest_link["target"]["room"], dest_link["target"]["id"]
    )[0]

    move_passage(
        content, links, src_link_left, src_link_right, dest_link, dest_link_end
    )


def get_rooms_and_exits(links: list[IRoomLink]) -> tuple[set[int], dict[int, set[int]]]:
    room_nodes: set[int] = {x["source"]["room"] for x in links} | {
        x["target"]["room"] for x in links
    }
    exit_nodes: dict[int, set[int]] = {x: set() for x in room_nodes}
    for x in links:
        exit_nodes[x["source"]["room"]].add(x["source"]["id"])
        # exit_nodes[x["target"]["room"]].add(x["target"]["id"])
    return room_nodes, exit_nodes


def draw_forest(
    room_nodes: set[int],
    exit_nodes: dict[int, set[int]],
    links: list[IRoomLink],
    filename: pathlib.Path,
):
    try:
        import graphviz
    except ImportError:
        return
    g = graphviz.Digraph(
        edge_attr={"fontsize": "12"}, engine="neato", graph_attr={"layout": "neato"}
    )
    for r in room_nodes:
        g.node(f"room_{r}", shape="circle")

    for ex_room, srcset in exit_nodes.items():
        for ex_src in srcset:
            g.node(f"exit_{ex_room}_{ex_src}", shape="rectangle")
            g.edge(f"room_{ex_room}", f"exit_{ex_room}_{ex_src}")

    for l in links:
        g.edge(
            f"exit_{l['source']['room']}_{l['source']['id']}",
            f"exit_{l['target']['room']}_{l['target']['id']}",
        )
    g.render(format="dot", engine="neato", filename=str(filename))


def shuffle_rooms(
        archives: dict[str, Any], content: IGameData, print_all: bool = False, output_maps: pathlib.Path | None = None
):
    links = generate_room_links(archives, content)
    start_room = 33
    room_cluster = find_room_cluster(links, start_room)
    room_links = [x for x in links if x["code_room"] in room_cluster]
    # exclude the one-way link to get to the dock from the map
    room_links = [
        *filter(
            lambda x: not (x["source"]["room"] == 85 and x["target"]["room"] == 33),
            room_links,
        )
    ]
    # exclude the troll bridge, we want to make it a passage
    room_links = [
        *filter(
            lambda x: not (x["source"]["room"] == 57 or x["target"]["room"] == 57),
            room_links,
        )
    ]

    room_nodes, exit_nodes = get_rooms_and_exits(room_links)

    if output_maps:
        draw_forest(room_nodes, exit_nodes, room_links, output_maps / "rooms_before.dot")

    # start from the dock
    # - start from the first room
    # - for each of the hub rooms
    #   - pick an exit, connect it up
    #   - after connecting a hub room, add the unbound exits to the randomiser
    # - when no hub rooms left, go through remainder and hook up dead ends
    dest_rooms = lambda r: {
        x["target"]["room"] for x in links if r == x["source"]["room"]
    }

    hubs = {
        k: v
        for k, v in exit_nodes.items()
        if len(dest_rooms(k)) > 1 and k in room_cluster
    }
    dead_ends = {
        k: v
        for k, v in exit_nodes.items()
        if len(dest_rooms(k)) == 1 and k in room_cluster
    }

    nodes = set(room_cluster)
    nodes_to_test = {start_room}
    nodes_done = set()
    edges = set()
    while nodes_to_test:
        node = nodes_to_test.pop()
        nodes_done.add(node)
        link_subset = [x for x in room_links if x["source"]["room"] == node]
        dest = {
            x["target"]["room"]
            for x in link_subset
            if x["target"]["room"] not in nodes_done
        }
        edges.update([(node, x) for x in dest])
        nodes_to_test.update(dest)

    # import pdb; pdb.set_trace()

    start_hub = hubs.pop(start_room)
    edges_left = sorted((start_room, x) for x in start_hub)

    links_to_write: list[IRoomLink] = []

    count = 0
    while edges_left:
        orig_edge = random.choice(edges_left)
        edges_left.remove(orig_edge)
        if print_all:
            print(f"--- orig_edge: {orig_edge}, edges_left: {edges_left}")
        if hubs:
            hub_id = random.choice(list(hubs.keys()))
            hub = hubs.pop(hub_id)

            hub_edges = [(hub_id, h) for h in hub]
            new_edge = random.choice(hub_edges)
            hub_edges.remove(new_edge)
            orig_link = find_link(room_links, orig_edge[0], orig_edge[1])
            hub_link = find_link(room_links, new_edge[0], new_edge[1])
            orig_link_end = find_link_inverse(room_links, orig_edge[0], orig_edge[1])
            hub_link_end = find_link_inverse(room_links, new_edge[0], new_edge[1])
            # orig_link_end = find_link_room(room_links, orig_link[0]["target"]["room"], orig_link[0]["source"]["room"])
            # hub_link_end = find_link_room(room_links, hub_link[0]["target"]["room"], hub_link[0]["source"]["room"])

            print(orig_link)
            print(hub_link)
            print(orig_link_end)
            print(hub_link_end)
            exchange_multilinks(content, orig_link, hub_link_end)
            exchange_multilinks(content, hub_link, orig_link_end)
            links_to_write.extend(
                [*orig_link, *hub_link, *hub_link_end, *orig_link_end]
            )
            # for hl in list(hub_edges):
            #    if (hl[1], hl[0]) in MI1EGA_UNUSUABLE_ROOM_LINK or (
            #        hl[1],
            #        hl[0],
            #    ) == (hub_link[0]["source"]["room"], hub_link[0]["source"]["id"]):
            #        edges_left.append(hl)
            #        hub_edges.remove(hl)
            # if print_all:
            #    print(f"--- new_edge: {new_edge}, hubs: {hubs}")

            edges_left.extend(hub_edges)
        elif dead_ends:
            orig_link = find_link(room_links, orig_edge[0], orig_edge[1])
            dead_end_options = [
                x for x in dead_ends.keys() if x != orig_link[0]["target"]["room"]
            ]
            if not dead_end_options:
                break
            dead_end_room = random.choice(dead_end_options)
            dead_end_id = dead_ends.pop(dead_end_room).pop()

            dead_end_link = find_link(room_links, dead_end_room, dead_end_id)

            orig_link_end = find_link_inverse(room_links, orig_edge[0], orig_edge[1])
            dead_end_link_end = find_link_inverse(
                room_links, dead_end_room, dead_end_id
            )

            print(orig_link)
            print(dead_end_link)
            print(orig_link_end)
            print(dead_end_link_end)
            #            import pdb; pdb.set_trace()

            exchange_multilinks(content, orig_link, dead_end_link_end)
            exchange_multilinks(content, dead_end_link, orig_link_end)
            links_to_write.extend(
                [*orig_link, *dead_end_link, *dead_end_link_end, *orig_link_end]
            )
    #            count += 1
    #            if count == 1:
    #                break

    write_changes_from_links(archives, content, links_to_write)

    if output_maps:
        draw_forest(room_nodes, exit_nodes, room_links, output_maps / "rooms_after.dot")

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


def fix_low_street(archives: dict[str, Any], content: IGameData):
    # room 35 (low street) has an entry script with fancy animations depending
    # on which room you arrive from.
    # we don't want this because it sets the player start position
    src = content[35]["entry"]["script"]

    modded = False
    for i, (_, instr) in enumerate(src):
        if (
            instr.name == "isEqual"
            and isinstance(instr.args["a"], V4Var)
            and instr.args["a"].id == 101
            and instr.args["b"] in (34, 33)
        ):
            # replace the if statement with always false
            src[i][1].args["b"] = 0
            modded = True

    if modded:
        update_entry_model(archives, content, 35)


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
    fix_low_street(archives, content)
    fix_bridge_on_map(archives, content)


def find_forest_links(
    obj_id: int, verb_id: int, instr_list: list[IDisassembly]
) -> list[IRoomLink]:
    result: list[IRoomLink] = []
    off = 0
    while off < len(instr_list):
        _, w = instr_list[off]
        if w.name == "isEqual" and w.args["a"] == V4Var(4, None):
            src_room = w.args["b"]
            # if src_room == 215:
            #    import pdb; pdb.set_trace()
            off += 1
            while off < len(instr_list):
                _, x = instr_list[off]
                if x.name == "loadRoomWithEgo":
                    result.append(
                        {
                            "offset": off,
                            "source": {
                                "type": "object",
                                "room": src_room,
                                "id": obj_id,
                                "verb": verb_id,
                            },
                            "target": {
                                "type": "object",
                                "room": x.args["room"],
                                "id": x.args["obj"],
                                "verb": verb_id,
                            },
                            "op": "loadRoomWithEgo",
                            "code_room": 58,
                        }
                    )
                    break
                off += 1
        off += 1
    return result


def shuffle_forest(archives: dict[str, Any], content: IGameData, output_maps: pathlib.Path | None=None) -> None:
    EXIT_OBJS = [666, 668, 669]
    links: list[IRoomLink] = []
    for obj_id in EXIT_OBJS:
        obj = content[58]["objects"][obj_id]
        for verb_id, verb in obj["verbs"].items():
            for match in find_forest_links(obj_id, verb_id, verb):
                links.append(match)

    # for x in links:
    #    print(x)
    room_nodes, exit_nodes = get_rooms_and_exits(links)
    
    if output_maps:
        draw_forest(room_nodes, exit_nodes, links, output_maps / "forest_before.dot")

    # the forest is connected together as 3 intersecting loops with 3 entry/exit paths.
    # we want to keep the basic loop structure, but randomise a few things:
    # - the hub nodes in the forest (i.e. 3 exits) should be swapped
    #   - pick two hubs
    #   - determine replacement exit mapping
    #   - for each src, target exit in source
    #       - swap src exit dest and target exit dest
    #       - swap links of other side
    # - passage segments between hubs should be randomised
    #   - pick a passage segment
    #   - pick a random hub and exit
    #   - join two ends of passage
    #   - inject ends in between hub and exit

    # rooms 201, 206, 209 and 218 are links to outside the forest and should be preserved
    FOREST_SKIP = {201, 206, 209, 218}
    FOREST_HUBS = {
        r
        for r in room_nodes
        if r >= 200 and r not in FOREST_SKIP and len(exit_nodes[r]) > 2
    }
    FOREST_PASSAGES = {
        r
        for r in room_nodes
        if r >= 200 and r not in FOREST_SKIP and len(exit_nodes[r]) == 2
    }
    for src_hub in sorted(FOREST_HUBS):
        dest_hub = random.choice(list(sorted(FOREST_HUBS ^ {src_hub})))
        src_choices = list(sorted(exit_nodes[src_hub]))
        dest_choices = list(exit_nodes[dest_hub])
        random.shuffle(dest_choices)

        for i in range(3):
            forest_room_link_swap(
                content, links, src_hub, src_choices[i], dest_hub, dest_choices[i]
            )

    for src_passage in sorted(FOREST_PASSAGES):
        dest = random.choice(list(sorted(FOREST_HUBS)))
        dest_obj = random.choice(list(exit_nodes[dest]))
        src_choices = list(sorted(exit_nodes[src_passage]))
        random.shuffle(src_choices)
        src_a_obj, src_b_obj = src_choices[0], src_choices[1]

        room_link_inject(
            content, links, src_passage, src_a_obj, src_b_obj, dest, dest_obj
        )

    for obj in EXIT_OBJS:
        #    print(f"Before {obj}:")
        #    scumm_v4_tokenizer(
        #        get_object_model(archives, content, 58, obj).data, print_data=True
        #    )
        update_object_model(archives, content, 58, obj)
    #    print(f"After {obj}:")
    #    scumm_v4_tokenizer(
    #        get_object_model(archives, content, 58, obj).data, print_data=True
    #    )
    if output_maps:
        draw_forest(room_nodes, exit_nodes, links, output_maps / "forest_after.dot")


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
