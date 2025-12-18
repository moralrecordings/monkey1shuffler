from __future__ import annotations

import random
from typing import Any

from .disasm import V4Instr, V4TextToken, V4Var, scumm_v4_tokenizer
from .resources import (
    IDisassembly,
    IGameData,
    get_global_model,
    get_object_model,
    update_global_model,
    update_local_model,
    update_object_model,
)
from .version import __version__


def add_version_tag(archives: dict[str, Any], scripts: IGameData, random_seed: int):
    vx = scripts[10]["globals"][149]["script"]
    for i, (off, instr) in enumerate(vx):
        if (
            instr.name == "print"
            and len(instr.args["ops"]) == 4
            and instr.args["ops"][3][0] == "SO_TEXTSTRING"
            and isinstance(instr.args["ops"][3][1]["str"][0], V4TextToken)
            and instr.args["ops"][3][1]["str"][0].data.startswith(b"TM ")
        ):
            copy_notice = instr.args["ops"][3][1]["str"]
            copy_notice.append(V4TextToken(name="newline", data=None))
            copy_notice.append(
                V4TextToken(
                    name="text",
                    data=f"MI1S v{__version__} seed #{random_seed}".encode("ascii"),
                )
            )
    update_global_model(archives, scripts, 10, 149)


def test_mod_intro(archives: dict[str, Any], scripts: IGameData):

    replace = V4Instr(
        0xD8,
        "printEgo",
        args={
            "string": [
                (
                    "SO_TEXTSTRING",
                    {
                        "str": [
                            V4TextToken(name="text", data=b"I have bad news^"),
                            V4TextToken(name="wait"),
                            V4TextToken(
                                name="text", data=b"^the recompiler sort of works??"
                            ),
                        ]
                    },
                )
            ]
        },
    )
    vx = scripts[38]["locals"][203]["script"]
    vx[17] = (vx[17][0], replace)

    # local = get_local_model(scripts, 38, 203)
    # print("\nBefore:")
    # scumm_v4_tokenizer(local.data, print_data=True)
    update_local_model(archives, scripts, 38, 203)

    # print("\nAfter:")
    # scumm_v4_tokenizer(local.data, print_data=True)


def test_mod_dock_poster(archives: dict[str, Any], content: IGameData):
    replace = V4Instr(
        0xD8,
        "printEgo",
        args={
            "string": [
                (
                    "SO_TEXTSTRING",
                    {
                        "str": [
                            V4TextToken(
                                name="text",
                                data=b"It says 'Your shonky recompiler works perfectly'^",
                            ),
                            V4TextToken(name="wait"),
                            V4TextToken(name="text", data=b"^but that can't be right?"),
                        ]
                    },
                )
            ]
        },
    )
    # can only run pickupObject on same room as object
    # replace = V4Instr(0x50, "pickupObject", args={"obj": 321})
    vx = content[33]["objects"][438]["verbs"][9]
    replace = [
        (0, V4Instr(0x72, "loadRoom", args={"room": 27})),
        # (vx[-5][0], V4Instr(0x37, "startObject", args={"obj": 321, "script": 0xb, "args": []})),
        (0, V4Instr(0x50, "pickupObject", args={"obj": 321})),
        (0, V4Instr(0x72, "loadRoom", args={"room": 33})),
        (0, V4Instr(0x00, "stopObjectCode")),
    ]

    vx[:] = replace

    script_model = get_object_model(archives, content, 33, 438)
    # print("Before:")
    # scumm_v4_tokenizer(script_model.data, print_data=True)

    update_object_model(archives, content, 33, 438)
    # print("After:")
    # scumm_v4_tokenizer(script_model.data, print_data=True)


def debug_mode(archives: dict[str, Any], content: IGameData):
    script_model = get_global_model(archives, content, 10, 1)
    # print("Before:")
    # scumm_v4_tokenizer(script_model.data, print_data=True)

    script = content[10]["globals"][1]["script"]
    script.insert(
        0, (0, V4Instr(0x19, "move", args={"value": 1}, target=V4Var(39, None)))
    )  # VAR_DEBUGMODE
    update_global_model(archives, content, 10, 1)
    # print("After:")
    # scumm_v4_tokenizer(script_model.data, print_data=True)


def turbo_mode(archives: dict[str, Any], content: IGameData, timer_interval: int = 2):
    # scrub through every script and replace the VAR_TIMER_NEXT set statements

    def mod_script(script: list[IDisassembly]) -> bool:
        modded = False
        for _, instr in script:
            if (
                instr.name == "move"
                and isinstance(instr.target, V4Var)
                and instr.target.id == 19
                and isinstance(instr.args["value"], int)
            ):
                instr.args["value"] = timer_interval
                modded = True
        return modded

    for room_id, room in content.items():
        for global_id, glob in room["globals"].items():
            if mod_script(glob["script"]):
                update_global_model(archives, content, room_id, global_id)

        for local_id, local in room["locals"].items():
            if mod_script(local["script"]):
                update_local_model(archives, content, room_id, local_id)


def skip_code_wheel(archives: dict[str, Any], content: IGameData):
    script = content[10]["globals"][1]["script"]
    i = 0
    while i < len(script):
        if script[i][1].name == "startScript" and script[i][1].args["script"] == 152:
            del script[i : i + 4]
            break
        i += 1
    update_global_model(archives, content, 10, 1)
