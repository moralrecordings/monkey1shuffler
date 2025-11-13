#!/usr/bin/env python3

from __future__ import annotations

import argparse
import pathlib
import random

VERSION = "0.1"


def main():
    parser = argparse.ArgumentParser(
        description="Secret of Monkey Island (EGA) Randomiser"
    )
    parser.add_argument(
        "SOURCE", type=pathlib.Path, help="Path containing input MI1 source files."
    )
    parser.add_argument("DEST", type=pathlib.Path, help="Path to output patched files.")
    parser.add_argument(
        "--shuffle-rooms",
        action="store_true",
        help="Randomise the exit links between the game's rooms.",
    )
    parser.add_argument(
        "--keep-transitions",
        action="store_true",
        help="Ensure that links which connect an indoor to an outdoor area reflect this transition.",
    )
    parser.add_argument(
        "--shuffle-objects",
        action="store_true",
        help="Randomise which objects you receive when picking things up.",
    )
    parser.add_argument(
        "--shuffle-forest",
        action="store_true",
        help="Rearrange the subroom links of the Mêlée Island™ forest.",
    )
    parser.add_argument(
        "--non-sequitur-swordfighting",
        action="store_true",
        help="Shuffle the mapping of insults to retorts for the insult swordfighting section. Sword Master insults will respect the new ordering.",
    )
    parser.add_argument(
        "--change-insult-order",
        action="store_true",
        help="Randomise the order of insults as they appear in the dialog menu.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        help="Number to use for initializing the random number generator.",
    )
    parser.add_argument(
        "--skip-code-wheel",
        action="store_true",
        help="Bypass the copy-protection code wheel screen.",
    )
    parser.add_argument(
        "--debug-mode",
        action="store_true",
        help="Enable the original debugging features.",
    )
    parser.add_argument(
        "--turbo-mode",
        action="store_true",
        help="Force the game to run at a much faster framerate.",
    )
    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {VERSION}"
    )
    args = parser.parse_args()

    if args.SOURCE == args.DEST:
        parser.exit(1, "Source and destination paths must be different\n")

    use_random = (
        args.shuffle_rooms
        or args.shuffle_objects
        or args.shuffle_forest
        or args.non_sequitur_swordfighting
    )
    random_seed = args.random_seed
    if not random_seed:
        random_seed = random.randint(0, 2**32)
    if use_random:
        print(f"Using random seed {random_seed}")


if __name__ == "__main__":
    main()
