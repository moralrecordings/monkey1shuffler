#!/usr/bin/env python3

from __future__ import annotations

import argparse
import pathlib
import random

from .mod_misc import debug_mode, skip_code_wheel, turbo_mode
from .mod_rooms import room_script_fixups, shuffle_rooms
from .mod_sword import non_sequitur_swordfighting
from .resources import dump_all, get_archives, save_all
from .version import __version__


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
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show verbose logging output."
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

    archives = get_archives(args.SOURCE)
    content = dump_all(archives, print_data=args.verbose)
    if args.shuffle_rooms:
        random.seed(random_seed)
        room_script_fixups(archives, content)
        shuffle_rooms(archives, content, print_all=args.verbose)
    if args.non_sequitur_swordfighting:
        random.seed(random_seed)
        non_sequitur_swordfighting(archives, content, args.change_insult_order)
    if args.skip_code_wheel:
        skip_code_wheel(archives, content)
    if args.debug_mode:
        debug_mode(archives, content)
    if args.turbo_mode:
        turbo_mode(archives, content)
    save_all(archives, content, args.DEST, print_all=args.verbose)


if __name__ == "__main__":
    main()
