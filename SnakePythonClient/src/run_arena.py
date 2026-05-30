import multiprocessing
import time
import random
import sys

from api import SnakeFieldAPI
from data_structures import get_directions_as_list
from bot import BotBrain

def run_bot(team_name, p1_margin, p2_margin):
    # Same configurations as main.py
    base_url = "http://localhost:3030/"
    game_name = "Level3_FreeForAll"
    password = "test"
    
    api = SnakeFieldAPI(base_url, team_name, game_name, password)
    
    # initial posting to register
    initial_direction = random.choice(get_directions_as_list())
    try:
        api.set_direction(initial_direction)
    except Exception:
        pass
        
    alive = True
    while alive:
        time.sleep(0.05)  # poll much faster than the 250ms tick rate!
        try:
            field = api.get_field()
            currentDirection = BotBrain.get_next_move(field, team_name, p1_margin, p2_margin)
            api.set_direction(currentDirection)
        except Exception as e:
            # If server connection fails or game ends, retry silently or loop
            pass

if __name__ == "__main__":
    margins = [
        (2.0, 1.2),  # Bot 0: Main Coward-Scavenger
        (1.0, 1.0),  # Bot 1: Super Aggressive
        (3.0, 2.0),  # Bot 2: Ultra Coward
        (1.5, 1.0),  # Bot 3: Aggressive
        # (2.5, 1.5),  # Bot 4: Cowardly
        # (1.8, 1.1),  # Bot 5: Moderate
        # (1.2, 1.0),  # Bot 6: Aggressive
        # (2.2, 1.3),  # Bot 7: Coward-Scavenger variant
        # (1.7, 1.2),  # Bot 8: Moderate
        # (2.8, 1.8),  # Bot 9: Very Cowardly
        # (1.4, 1.1)   # Bot 10: Slightly Aggressive
    ]

    print("Launching 11 Bot Clones via Multiprocessing...")
    
    processes = []
    
    for i in range(11):
        team_name = "teamea" if i == 0 else f"clone_{i}"
        p1, p2 = margins[i]
        
        print(f"Spawning {team_name} with margins (Phase 1: {p1}, Phase 2: {p2})")
        
        p = multiprocessing.Process(target=run_bot, args=(team_name, p1, p2))
        p.start()
        processes.append(p)
        time.sleep(0.1) # Stagger starts slightly
        
    print("\nAll 11 bots launched! They are running entirely independently of main.py.")
    print("Press Ctrl+C to terminate the simulation.")
    
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\nShutting down bots...")
        for p in processes:
            p.terminate()
        print("All bots terminated.")
