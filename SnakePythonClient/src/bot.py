import collections
import random
from typing import List, Tuple, Set, Dict, Optional

from data_structures import Direction, Coord, get_directions_as_list
from Field import Field

class BotBrain:
    @staticmethod
    def get_next_move(field: Field, team_name: str) -> Direction:
        my_snake = field.snakes.get(team_name)
        if not my_snake or not my_snake.alive or not my_snake.head:
            # Fallback if dead or not found
            return random.choice(get_directions_as_list())

        head = my_snake.head
        size = field.size
        
        # 1. Gather constraints
        obstacles = BotBrain._get_obstacles(field)
        danger_zones = BotBrain._get_danger_zones(field, team_name, size)
        
        # 2. Evaluate all 4 possible moves
        adjacent_cells = BotBrain._get_adjacent(head, size)
        
        safe_moves: Dict[Direction, Coord] = {}
        for direction, coord in adjacent_cells.items():
            if coord not in obstacles:
                safe_moves[direction] = coord

        # If no moves are strictly safe, we will just crash. But try to pick something.
        if not safe_moves:
            print("No safe moves! Crashing...")
            return random.choice(get_directions_as_list())

        # 3. Filter out Danger Zones if possible, but keep them as fallback
        safer_moves = {d: c for d, c in safe_moves.items() if c not in danger_zones}
        if not safer_moves:
            # We must step into a danger zone or die
            print("Warning: Forced to step into a danger zone!")
            safer_moves = safe_moves

        # 4. Flood fill to evaluate space
        move_scores: Dict[Direction, int] = {}
        for direction, coord in safer_moves.items():
            # simulate move
            temp_obstacles = set(obstacles)
            score = BotBrain._flood_fill(coord, temp_obstacles, size)
            move_scores[direction] = score

        # Filter out traps (where space < our length)
        # However, if ALL moves are traps, we just pick the one with max space.
        my_length = len(my_snake.body)
        viable_moves = {d: c for d, c in safer_moves.items() if move_scores[d] >= my_length}
        
        if not viable_moves:
            # All moves are traps, pick the one that gives us the most time
            best_dir = max(safer_moves.keys(), key=lambda d: move_scores[d])
            print(f"Trapped! Picking {best_dir} for maximum survival time ({move_scores[best_dir]} spaces).")
            return best_dir

        # 5. BFS Pathfinding to apples
        apples = [tuple(item[0]) for item in field.items if item[1] == 'Apple']
        if apples:
            # Find a path to an apple where the first step is a viable_move.
            best_dir_to_apple = BotBrain._bfs_shortest_path(head, apples, obstacles, danger_zones, size, viable_moves)
            if best_dir_to_apple:
                print(f"Apple found! Moving {best_dir_to_apple} towards it.")
                return best_dir_to_apple

        # 6. Fallback: No reachable apples, just pick the viable move that maximizes space
        best_dir = max(viable_moves.keys(), key=lambda d: move_scores[d])
        print(f"No reachable apples. Moving {best_dir} into open space.")
        return best_dir

    @staticmethod
    def _get_adjacent(coord: Coord, size: Tuple[int, int]) -> Dict[Direction, Coord]:
        x, y = coord
        w, h = size
        return {
            "NORTH": (x, (y - 1) % h),
            "SOUTH": (x, (y + 1) % h),
            "EAST": ((x + 1) % w, y),
            "WEST": ((x - 1) % w, y)
        }

    @staticmethod
    def _get_obstacles(field: Field) -> Set[Coord]:
        obstacles = set()
        for snake in field.snakes.values():
            if snake.alive:
                for segment in snake.body:
                    obstacles.add(segment)
        return obstacles

    @staticmethod
    def _get_danger_zones(field: Field, my_team_name: str, size: Tuple[int, int]) -> Set[Coord]:
        danger = set()
        for team_name, snake in field.snakes.items():
            if team_name != my_team_name and snake.alive and snake.head:
                adj = BotBrain._get_adjacent(snake.head, size)
                for coord in adj.values():
                    danger.add(coord)
        return danger

    @staticmethod
    def _flood_fill(start: Coord, obstacles: Set[Coord], size: Tuple[int, int]) -> int:
        queue = collections.deque([start])
        visited = set([start])
        
        while queue:
            curr = queue.popleft()
            adj = BotBrain._get_adjacent(curr, size)
            for neighbor in adj.values():
                if neighbor not in visited and neighbor not in obstacles:
                    visited.add(neighbor)
                    queue.append(neighbor)
                    
        return len(visited)

    @staticmethod
    def _bfs_shortest_path(start: Coord, targets: List[Coord], obstacles: Set[Coord], danger_zones: Set[Coord], size: Tuple[int, int], viable_moves: Dict[Direction, Coord]) -> Optional[Direction]:
        target_set = set(targets)
        
        # queue stores tuples of (current_coord, first_direction)
        queue = collections.deque()
        visited = set(obstacles)
        visited.add(start)
        
        # Initialize queue with valid first steps
        for direction, coord in viable_moves.items():
            if coord not in visited:
                if coord in target_set:
                    return direction
                queue.append((coord, direction))
                visited.add(coord)
                
        while queue:
            curr, first_dir = queue.popleft()
            
            adj = BotBrain._get_adjacent(curr, size)
            for neighbor in adj.values():
                # Treat danger_zones as obstacles during apple hunting for safety
                if neighbor not in visited and neighbor not in danger_zones:
                    if neighbor in target_set:
                        return first_dir
                    visited.add(neighbor)
                    queue.append((neighbor, first_dir))
                    
        return None
