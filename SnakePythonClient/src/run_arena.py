import multiprocessing
import time
import random
import sys

from api import SnakeFieldAPI
from data_structures import get_directions_as_list
from bot import BotBrain

def run_bot(team_name, p1_margin, p2_margin):
    base_url = "http://192.168.3.95:3030/"
    game_name = "Level8_1V1B"
    
    # Password mapping for each team/robot
    passwords = {
        "teamea": "handycomputeripad",
        "test": "test"
    }
    password = passwords.get(team_name, "test")
    
    api = SnakeFieldAPI(base_url, team_name, game_name, password)
    
    # initial posting to register
    initial_direction = random.choice(get_directions_as_list())
    print(f"[{team_name}] Registering with initial direction: {initial_direction}")
    try:
        api.set_direction(initial_direction)
    except Exception as e:
        print(f"[{team_name}] Registration failed: {e}", file=sys.stderr)
        
    alive = True
    while alive:
        time.sleep(0.2)  # avoid rate limiting error (poll slightly faster than 250ms tick rate)
        try:
            field = api.get_field()
            currentDirection, activate_item = BotBrain.get_next_move(field, team_name, False)
            if activate_item:
                try:
                    api.activate_item(activate_item)
                    print(f"[{team_name}] Activated {activate_item}!")
                except Exception as e:
                    print(f"[{team_name}] Failed to activate {activate_item}: {e}", file=sys.stderr)
            api.set_direction(currentDirection)
            print(f"[{team_name}] Moved {currentDirection}")
        except Exception as e:
            print(f"[{team_name}] Loop exception: {e}", file=sys.stderr)

if __name__ == "__main__":
    margins = [
        (2.0, 1.2),  # Bot 0: Main Coward-Scavenger
        (1.0, 1.0),  # Bot 1: Super Aggressive
        # (3.0, 2.0),  # Bot 2: Ultra Coward
        # (1.5, 1.0),  # Bot 3: Aggressive
        # (2.5, 1.5),  # Bot 4: Cowardly
        # (1.8, 1.1),  # Bot 5: Moderate
        # (1.2, 1.0),  # Bot 6: Aggressive
        # (2.2, 1.3),  # Bot 7: Coward-Scavenger variant
        # (1.7, 1.2),  # Bot 8: Moderate
        # (2.8, 1.8),  # Bot 9: Very Cowardly
        # (1.4, 1.1)   # Bot 10: Slightly Aggressive
    ]

    print("Launching 2 Bot Clones via Multiprocessing...")
    
    processes = []
    
    for i in range(2):
        team_name = "teamea" if i == 0 else "test"
        p1, p2 = margins[i]
        
        print(f"Spawning {team_name} with margins (Phase 1: {p1}, Phase 2: {p2})")
        
        p = multiprocessing.Process(target=run_bot, args=(team_name, p1, p2))
        p.start()
        processes.append(p)
        time.sleep(0.1) # Stagger starts slightly
        
    print("\nAll 2 bots launched! They are running entirely independently of main.py.")
    print("Press Ctrl+C to terminate the simulation.")
    
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\nShutting down bots...")
        for p in processes:
            p.terminate()
        print("All bots terminated.")
