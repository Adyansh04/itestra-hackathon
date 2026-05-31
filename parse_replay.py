import json

with open('/home/adyansh/Downloads/22UhrBracketB.json') as f:
    data = json.load(f)

insts = data['instructions']
size = data['size']

# Reconstruct game state tick by tick
# Initial snake bodies from config
snake_names_order = []  # Map index to name
snakes_state = {}  # name -> {body, alive, effects}
items_on_board = []

# Parse initial snake positions
initial_bodies = [s['body'] for s in data['snakes']]

# We need to figure out which snake is which
# The replay has OrientSnake before AddBot... Let's trace the names
# From the instructions: teamea, Hacklachapelle, 42, Bot-3 are the players

# Let me simulate tick by tick
tick_num = 0
orient_queue = {}  # name -> direction (set before each tick)

print(f"Grid: {size[0]}x{size[1]}")
print(f"Bad apple every {data['bad_apple_every_ticks']} ticks, Star every {data['star_every_ticks']} ticks")
print()

# Just track orient commands per tick for our snake (teamea)
teamea_orients = []
all_ticks = []

current_orients = {}
game_started = False

for inst in insts:
    if 'OrientSnake' in inst:
        name, direction = inst['OrientSnake']
        current_orients[name] = direction
    elif 'StartGame' in inst:
        game_started = True
        print("=== GAME STARTED ===")
    elif 'MovementTick' in inst:
        tick_num += 1
        all_ticks.append({
            'tick': tick_num,
            'orients': dict(current_orients),
            'type': 'movement'
        })
        # Reset orients after tick
    elif 'PowerupTick' in inst:
        all_ticks.append({
            'tick': tick_num,
            'orients': dict(current_orients),
            'type': 'powerup'
        })
    elif 'StopGame' in inst:
        print(f"=== GAME STOPPED at tick {tick_num} ===")

print(f"Total movement ticks: {sum(1 for t in all_ticks if t['type'] == 'movement')}")
print(f"Total powerup ticks: {sum(1 for t in all_ticks if t['type'] == 'powerup')}")
print()

# Show all ticks with teamea's moves
print("=== ALL TICKS WITH TEAMEA MOVES ===")
for t in all_ticks:
    tick = t['tick']
    orients = t['orients']
    ttype = t['type']
    teamea_dir = orients.get('teamea', '(no orient)')
    others = {k: v for k, v in orients.items() if k != 'teamea'}
    others_str = ", ".join(f"{k}={v}" for k, v in others.items())
    if ttype == 'movement':
        print(f"Tick {tick:3d} [MOV] | teamea={teamea_dir:6s} | {others_str}")
    else:
        print(f"Tick {tick:3d} [PWR] | {others_str}")

# Count how many times teamea sent an orient vs how many movement ticks
teamea_orient_count = sum(1 for t in all_ticks if t['type'] == 'movement' and 'teamea' in t['orients'])
total_mov_ticks = sum(1 for t in all_ticks if t['type'] == 'movement')
print(f"\nteamea sent orients for {teamea_orient_count}/{total_mov_ticks} movement ticks")

# Check if teamea stopped sending after some point
print("\n=== LAST TEAMEA ORIENTS ===")
last_teamea_ticks = [t for t in all_ticks if 'teamea' in t['orients']]
for t in last_teamea_ticks[-10:]:
    print(f"  Tick {t['tick']}: {t['orients']['teamea']}")
