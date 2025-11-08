#!/usr/bin/env python3

from __future__ import annotations

import argparse
import pathlib

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


if __name__ == "__main__":
    main()
