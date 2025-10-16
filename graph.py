from __future__ import annotations

import graphviz

from disasm import V4Instr, dump_all, verbs4

def find_leave_room(instr_list: list[tuple[int, V4Instr]]):
    result = []
    for off, x in instr_list:
        if x.name == "loadRoomWithEgo":
            result.append({"offset": off, "room": x.args["room"]})
        elif x.name == "putActorInRoom" and x.args["act"] == "VAR_EGO":
            result.append({"offset": off, "room": x.args["room"]})
    return result

def room_links_1():
    g = graphviz.Digraph(edge_attr={"fontsize": "12"}, graph_attr={"compound": "true", "rankdir": "LR", "pack": "16"})
    data = dump_all()
    room_idx = {}

    for room_id, room in data.items():
        room_idx[room_id] = f"Room {room_id} {room['name']}"
        with g.subgraph(name=f"cluster_room_{room_id}", graph_attr={"rankdir": "LR"}) as sub:
            sub.attr(margin="8")
            with sub.subgraph(name=f"cluster_inv_room_{room_id}") as inv:
                inv.attr(peripheries="0", margin="0")
                inv.node(f"inv_room_{room_id}", shape="point",  style="invis")
            sub.attr(label=room_idx[room_id], shape="rectangle", style="filled, rounded", fillcolor="lightgray")
            #for glob_id, glob in room["globals"].items():
            #    links = find_leave_room(glob)
            #    if links:
            #        sub.node(f"glob_{glob_id}", label=f"Global {glob_id}", shape="rectangle", style="rounded, filled", fillcolor="lightblue")
            #        for link in links:
            #            if link["room"] in room_idx and link["room"] != room_id:
            #                g.edge(f"glob_{glob_id}", f"inv_room_{link['room']}", lhead=f"cluster_room_{link['room']}")

            #for local_id, local in room["locals"].items():
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
                        verb_name = verbs4.get(verb_id, f"(verb {verb_id})")
                        desc = f"[obj {obj_id}] {verb_name} {obj['name']}"
                        sub.node(f"obj_{obj_id}_verb_{verb_id}", label=desc, shape="rectangle", style="rounded, filled", fillcolor="khaki")
                        for link in links:
                            if link["room"] in room_idx and link["room"] != room_id:
                                g.edge(f"obj_{obj_id}_verb_{verb_id}", f"inv_room_{link['room']}", lhead=f"cluster_room_{link['room']}")

    g.render(engine="dot", filename="test.dot")

    return g
    # iterate through the entire script library
    # find scripts which call loadRoomWithEgo
    # join them up on a graph


def room_links_2():
    g = graphviz.Digraph(edge_attr={"fontsize": "12"}, graph_attr={ "rankdir": "LR",  "overlap": "false"})
    data = dump_all()
    room_idx = {}

    for room_id, room in data.items():
        room_idx[room_id] = f"[room {room_id}] {room['name']}"
        g.node(f"room_{room_id}", label=room_idx[room_id], shape="rectangle", style="filled, rounded", fillcolor="khaki")
    
    for room_id, room in data.items():
        links = []
        #for glob_id, glob in room["globals"].items():
        #    new_links = find_leave_room(glob)
        #    for l in new_links:
        #        l["desc"] = f"[global {glob_id} 0x{l['offset']:04x}]"
        #    links.extend(new_links)

        #for local_id, local in room["locals"].items():
        #    new_links = find_leave_room(local)
        #    for l in new_links:
        #        l['desc'] = f"[local {local_id} 0x{l['offset']:04x}]"
        #    links.extend(new_links)

        for obj_id, obj in room["objects"].items():
            for verb_id, verb in obj["verbs"].items():
                new_links = find_leave_room(verb)
                verb_name = verbs4.get(verb_id, f"(verb {verb_id})")
                for l in new_links:
                    desc = f"[obj {obj_id} 0x{l['offset']:04x}] {verb_name} {obj['name']}"
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


