import argparse
import random
import time

from api import SnakeFieldAPI
from data_structures import Direction, get_directions_as_list
from bot import BotBrain

if __name__ == "__main__":
    # parser = argparse.ArgumentParser(description="Snake game bot client")
    # parser.add_argument("team_name", help="Name of the team/snake")
    # parser.add_argument("game_name", help="Name of the game to join")
    # parser.add_argument("--password", default="test", help="Password for server")
    # parser.add_argument("--base_url", default="http://localhost:3030",
    #                     help="Base URL of the game server (default: http://localhost:3030)")
    # args = parser.parse_args()

    # team_name = args.team_name
    # base_url = args.base_url
    # game_name = args.game_name
    # password = args.password
    team_name = "teamea"

    base_url = "http://192.168.7.211:3030/"
    # base_url = "http://192.168.3.13:3030/"

    game_name = "Teamea"
    # game_name = "turnier"

    password = "handycomputeripad"


    alive = True

    api = SnakeFieldAPI(base_url, team_name, game_name, password)

    # initial posting to register
    initial_direction = random.choice(get_directions_as_list())
    api.set_direction(initial_direction)

    while alive:
        time.sleep(0.4)  # avoid rate limiting error
        field = api.get_field()
        
        start_time = time.time()
        currentDirection = BotBrain.get_next_move(field, team_name)
        elapsed_ms = (time.time() - start_time) * 1000
        
        print(f"Tick completed in {elapsed_ms:.2f} ms. Moving {currentDirection}")
        api.set_direction(currentDirection)
