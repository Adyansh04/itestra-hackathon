import argparse
import random
import time

from api import SnakeFieldAPI
from data_structures import Direction, get_directions_as_list
from bot import BotBrain

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Snake game bot client")
    parser.add_argument("team_name", help="Name of the team/snake", default="teamea")
    # parser.add_argument("game_name", help="Name of the game to join")
    # parser.add_argument("--password", default="test", help="Password for server")
    # parser.add_argument("--base_url", default="http://localhost:3030",
    #                     help="Base URL of the game server (default: http://localhost:3030)")
    args = parser.parse_args()

    # team_name = args.team_name
    # base_url = args.base_url
    # game_name = args.game_name
    # password = args.password

    # team_name = "teamea"
    team_name = args.team_name

    # base_url = "http://192.168.7.211:3030/"
    # base_url = "http://192.168.3.13:3030/"
    base_url = "http://localhost:3030/"

    game_name = "Level5_Star"
    # game_name = "FreeForAll"

    # game_name = "Final"

    # password = "handycomputeripad"
    password = "test"

    alive = True

    api = SnakeFieldAPI(base_url, team_name, game_name, password)

    # initial posting to register
    initial_direction = random.choice(get_directions_as_list())
    api.set_direction(initial_direction)

    while alive:
        time.sleep(0.9)  # avoid rate limiting error
        try:
            field = api.get_field()
            print(field)
            
            start_time = time.time()
            currentDirection = BotBrain.get_next_move(field, team_name, 1.5, 1.0)
            elapsed_ms = (time.time() - start_time) * 1000
            
            print(f"Tick completed in {elapsed_ms:.2f} ms. Moving {currentDirection}")
            # api.set_direction(currentDirection)
        except Exception as e:
            print(f"Server connection error: {e}. Retrying next tick...")
