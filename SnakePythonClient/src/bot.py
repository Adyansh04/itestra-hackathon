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

        enemy_heads = []
        for name, snake in field.snakes.items():
            if name != team_name and snake.alive and snake.head:
                enemy_heads.append(tuple(snake.head))

        # 4. Evaluate safer moves using Voronoi Territory Control
        move_scores: Dict[Direction, int] = {}
        for direction, coord in safer_moves.items():
            move_scores[direction] = BotBrain._voronoi_space(coord, enemy_heads, obstacles, size)

        # Filter out traps (where space < our length)
        # However, if ALL moves are traps, we just pick the one with max space.
        my_length = len(my_snake.body)
        viable_moves = {d: c for d, c in safer_moves.items() if move_scores[d] >= my_length}
        
        if not viable_moves:
            # All moves are traps, pick the one that gives us the most time
            best_dir = max(safer_moves.keys(), key=lambda d: move_scores[d])
            decision_log = (
                f"--- Decision Log ---\n"
                f"Head: {head}, Length: {my_length}\n"
                f"Voronoi Scores: {move_scores}\n"
                f"Result: TRAPPED! Picking {best_dir} for maximum survival time.\n\n"
            )
            with open('bot_decisions.log', 'a') as f:
                f.write(decision_log)
            print(f"Trapped! Picking {best_dir} for maximum survival time ({move_scores[best_dir]} spaces).")
            return best_dir

        apples = [tuple(item[0]) for item in field.items if item[1] == 'Apple']
        
        other_bots_info = []
        for name, snake in field.snakes.items():
            if name != team_name and snake.alive:
                other_bots_info.append(f"{name} (Head: {snake.head}, Len: {len(snake.body)})")
        other_bots_str = ", ".join(other_bots_info) if other_bots_info else "None"
        
        # Filter Contested Apples
        safe_apples = []
        for apple in apples:
            my_dist = BotBrain._manhattan_dist(head, apple, size)
            is_safe = True
            for enemy_head in enemy_heads:
                if BotBrain._manhattan_dist(enemy_head, apple, size) <= my_dist:
                    is_safe = False
                    break
            if is_safe:
                safe_apples.append(apple)

        decision_log = (
            f"--- Decision Log ---\n"
            f"Head: {head}, Length: {my_length}\n"
            f"Other Bots: {other_bots_str}\n"
            f"All Apples: {apples}\n"
            f"Safe Apples: {safe_apples}\n"
            f"Safe Moves: {list(safe_moves.keys())}\n"
            f"Danger Zones: {danger_zones}\n"
            f"Safer Moves: {list(safer_moves.keys())}\n"
            f"Voronoi Scores: {move_scores}\n"
            f"Viable Moves (score >= length): {list(viable_moves.keys())}\n"
        )

        best_dir_to_apple = None
        if safe_apples:
            # Find a path to a safe apple where the first step is a viable_move, and the destination is safe
            best_dir_to_apple = BotBrain._bfs_shortest_path(head, safe_apples, enemy_heads, obstacles, size, viable_moves, my_length)
            if best_dir_to_apple:
                decision_log += f"Result: Safe apple found! Moving {best_dir_to_apple} towards it.\n\n"
                print(f"Safe apple found! Moving {best_dir_to_apple} towards it.")
                with open('bot_decisions.log', 'a') as f:
                    f.write(decision_log)
                return best_dir_to_apple

        # 6. Fallback: No reachable apples, just pick the viable move that maximizes space
        best_dir = max(viable_moves.keys(), key=lambda d: move_scores[d])
        decision_log += f"Result: No reachable apples. Moving {best_dir} into open space.\n\n"
        print(f"No reachable apples. Moving {best_dir} into open space.")
        with open('bot_decisions.log', 'a') as f:
            f.write(decision_log)
        return best_dir

    @staticmethod
    def _manhattan_dist(p1: Coord, p2: Coord, size: Tuple[int, int]) -> int:
        dx = min(abs(p1[0] - p2[0]), size[0] - abs(p1[0] - p2[0]))
        dy = min(abs(p1[1] - p2[1]), size[1] - abs(p1[1] - p2[1]))
        return dx + dy

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
    def _voronoi_space(my_start: Coord, enemy_heads: List[Coord], obstacles: Set[Coord], size: Tuple[int, int]) -> int:
        from collections import deque
        queue = deque()
        visited = {}
        
        if my_start not in obstacles:
            queue.append((0, 0, my_start))
            visited[my_start] = 0
            
        for i, enemy_head in enumerate(enemy_heads):
            queue.append((0, i + 1, enemy_head))
            visited[enemy_head] = i + 1
            
        while queue:
            dist, owner, curr = queue.popleft()
            
            adj = BotBrain._get_adjacent(curr, size)
            for neighbor in adj.values():
                if neighbor not in obstacles and neighbor not in visited:
                    visited[neighbor] = owner
                    queue.append((dist + 1, owner, neighbor))
                    
        return sum(1 for owner in visited.values() if owner == 0)

    @staticmethod
    def _bfs_shortest_path(start: Coord, targets: List[Coord], enemy_heads: List[Coord], obstacles: Set[Coord], size: Tuple[int, int], viable_moves: Dict[Direction, Coord], my_length: int) -> Optional[Direction]:
        target_set = set(targets)
        
        # queue stores tuples of (current_coord, first_direction)
        queue = collections.deque()
        visited = set(obstacles)
        visited.add(start)
        
        # Initialize queue with valid first steps
        for direction, coord in viable_moves.items():
            if coord not in visited:
                if coord in target_set:
                    # Destination Safety Check: Ensure eating this apple doesn't trap us
                    if BotBrain._voronoi_space(coord, enemy_heads, obstacles, size) >= my_length + 1:
                        return direction
                queue.append((coord, direction))
                visited.add(coord)
                
        while queue:
            curr, first_dir = queue.popleft()
            
            adj = BotBrain._get_adjacent(curr, size)
            for neighbor in adj.values():
                # We ignore danger_zones in deep search so we don't get paralyzed
                if neighbor not in visited:
                    if neighbor in target_set:
                        # Destination Safety Check: Ensure eating this apple doesn't trap us
                        if BotBrain._voronoi_space(neighbor, enemy_heads, obstacles, size) >= my_length + 1:
                            return first_dir
                        # If it's a trap, we still mark it visited and continue searching
                    visited.add(neighbor)
                    queue.append((neighbor, first_dir))
                    
        return None
