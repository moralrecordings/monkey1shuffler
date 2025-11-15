from __future__ import annotations

import random
from typing import Any

from .disasm import scumm_v4_tokenizer
from .resources import IGameData, get_global_model, update_global_model


def non_sequitur_swordfighting(archives: dict[str, Any], content: IGameData, shuffle_order: bool) -> None:
    INSULT_COUNT = 16
    INSULT_FARMER = 7
    INSULT_SHISH = 1

    fight_room = content[88]
    jab_ids = [i for i in range(INSULT_COUNT)]
    retort_ids = [i for i in range(INSULT_COUNT)]
    if shuffle_order:
        random.shuffle(jab_ids)
    random.shuffle(retort_ids)

    jab_script = fight_room["globals"][82]["script"]
    retort_script = fight_room["globals"][83]["script"]
    jabs = [
        jab_script[2 + 3 * i][1].args["args"]["string"][0].data
        for i in range(INSULT_COUNT)
    ]
    sm_jabs = [
        jab_script[50 + 3 * i][1].args["args"]["string"][0].data
        for i in range(INSULT_COUNT)
    ]
    retorts = [
        retort_script[2 + 3 * i][1].args["args"]["string"][0].data
        for i in range(INSULT_COUNT)
    ]
    for i, x in enumerate(jab_ids):
        jab_script[2 + 3 * i][1].args["args"]["string"][0].data = jabs[x]
        jab_script[50 + 3 * i][1].args["args"]["string"][0].data = sm_jabs[x]
    for i, x in enumerate(retort_ids):
        retort_script[2 + 3 * i][1].args["args"]["string"][0].data = retorts[x]

    update_global_model(archives, content, 88, 82)
    update_global_model(archives, content, 88, 83)

    convo_script = fight_room["globals"][79]["script"]
    convo_script[10][1].args["ops"][0][1]["str"][
        0
    ].data = b"What an amateur non-sequitur!"
    convo_script[19][1].args["ops"][0][1]["str"][
        0
    ].data = b"I'm non-sequitured that you'd even try to use that non-sequitur on me!"
    convo_script[25][1].args["args"]["string"][
        0
    ].data = b"That's not fair, you're using the Sword Master's non-sequiturs, I see."
    update_global_model(archives, content, 88, 79)

    smirk_room = content[43]
    training = smirk_room["globals"][57]
    training["script"][513][1].args["ops"][0][1]["str"][
        0
    ].data = b"^they know just when to throw their opponent with a non-sequitur^"
    training["script"][517][1].args["ops"][0][1]["str"][
        0
    ].data = b"Let's try a couple of non-sequiturs out, shall we?"
    training["script"][521][1].args["ops"][0][1]["str"][0].data = (
        b"^'" + jabs[jab_ids[INSULT_FARMER]] + b"'"
    )
    training["script"][543][1].args["ops"][1][1]["text"][0].data = retorts[
        jab_ids[INSULT_FARMER]
    ]
    training["script"][558][1].args["ops"][0][1]["str"][2].data = (
        b"^'" + retorts[retort_ids[INSULT_FARMER]] + b"'"
    )
    training["script"][567][1].args["ops"][0][1]["str"][0].data = (
        b"^'" + jabs[jab_ids[INSULT_SHISH]] + b"'"
    )
    training["script"][591][1].args["ops"][1][1]["text"][0].data = retorts[
        retort_ids[INSULT_FARMER]
    ]
    training["script"][612][1].args["ops"][0][1]["str"][
        2
    ].data = b"That was the response from the last non-sequitur."
    training["script"][619][1].args["ops"][0][1]["str"][2].data = (
        b"^'" + jabs[jab_ids[INSULT_SHISH]] + b"'^"
    )
    training["script"][622][1].args["ops"][0][1]["str"][0].data = (
        b"^'" + retorts[retort_ids[INSULT_SHISH]] + b"'"
    )
    training["script"][626][1].args["ops"][0][1]["str"][
        0
    ].data = b"Now I suggest you go out there and learn some non-sequiturs."
    update_global_model(archives, content, 43, 57)

    #print("\nAfter:")
    #model = get_global_model(archives, content, 43, 57)
    #scumm_v4_tokenizer(model.data, print_data=True)
