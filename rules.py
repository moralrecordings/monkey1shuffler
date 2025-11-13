from __future__ import annotations

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

# - native village needs oars
# - inside monkey head needs key
# - ghost ship gangplank needs head

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
# - change the references in the conversation with the troll
