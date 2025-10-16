from __future__ import annotations

# classification of game rooms

# for now exclude the follow autorun script ones from the shuffle
# - 51 is inside the circus tent
# - 37 is inside meathook's house
# - 60 is inside smirk's gym
# 
M1EGA_ROOM_CLASS = {
    "card": {90, 96, 10, 97, 98, 95, 94},
    "map": {63, 85, 2, 3, 4, 5, 6},
    "outdoors": {38, 33, 61, 35, 32, 34, 57, 36, 59, 58, 43, 52, 48, 64, 15,
		 19, 17, 
		 12, 69, 21, 18, 11, 16, 40, 25, 80},
    "indoors": {28, 41, 29, 53, 31, 30, 78, 
		7, 8, 9, 14,
		65, 70, 39, 71, 72, 73, 74, 75, 77, 27,},
    "closeup": {44, 83, 42, 79, 82, 81, 23, 45, 89, 62, 49, 60, 76, 88, 51, 37, 50,
		84, 87, 86},
    "beach": {20, 1},
}
M1EGA_ROOM_CLUSTER = {
    "melee": {63, 85, 38, 33, 61, 35, 32, 34, 57, 36, 59, 58, 43, 52, 48, 64, 28, 41, 29, 53, 31, 30, 78, 44, 83, 42, 79, 82, 81, 23, 45, 89, 62, 49, 60, 76, 88, 51, 37, 50, 15},
    "ship": {7, 8, 9, 14, 19, 17, 84, 87},
    "monkey": {12, 69, 65, 70, 39, 71, 72, 73, 74, 75, 77, 20, 1, 2, 3, 4, 5, 6, 21, 18, 11, 16, 40, 25, 27, 80},
}

# object constraints:
# 

# room constraints:

# 57 (bridge): 
# - need to start on first exit side
# - need fish to access second exit
# 15 (fork):
# - need either:
#   - store + sword
#   - treasure map

# area randomization
# linking methodology from dashrando.net
# - hubs have 3 or more exits
# - duo have 2 exits
# - dead have 1 exit

# - at most 1 original connection may occur
# - all duo areas cannot be chained together
# - 

# room constraints:
# - mansion front door needs meat and flower
# - troll bridge needs fish
# - hook crossing needs chicken
# - woods crossing to swordmaster/treasure needs map or storekeeper


# item randomization
# - regenerating items: meat, business cards, mugs
# ^ meat and mugs need to be mapped either to the original, or static items that don't disappear

# non-sequitur sword fighting
# room 88, 
# global script 082 for insults, stores string in res 24
# global script 083 for retorts, stores string in res 25
# - shuffle the regular insults and swordmaster insults (same pattern), shuffle the retorts.
# - include the crap insults and the yield words? don't include "I give up"
# - change the dialogue with smirk to swap out the shish-kabob and dairy farmer retorts
