from __future__ import annotations

import random

from disasm import V4Instr, V4TextToken
from resources import (
    IDisassembly,
    IGameData,
    update_global_model,
    update_local_model,
    update_object_model,
)


def test_mod_intro(scripts: IGameData):

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
    update_local_model(scripts, 38, 203)

    # print("\nAfter:")
    # scumm_v4_tokenizer(local.data, print_data=True)


def test_mod_dock_poster(content: IGameData):
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
    vx = content[33]["objects"][438]["verbs"][9]
    vx[-5] = (vx[-5][0], replace)

    update_object_model(content, 33, 438)


def turbo_mode(content: IGameData, timer_interval: int = 2):
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
                update_global_model(content, room_id, global_id)

        for local_id, local in room["locals"].items():
            if mod_script(local["script"]):
                update_local_model(content, room_id, local_id)
