import collections
import random
from typing import List, Tuple, Set, Dict, Optional

from data_structures import Direction, Coord, get_directions_as_list
from Field import Field

class BotBrain:
    @staticmethod
    def get_next_move(field: Field, team_name: str, phase1_margin: float = 1.0, phase2_margin: float = 1.0) -> Direction:
        my_snake = field.snakes.get(team_name)
        if not my_snake or not my_snake.alive or not my_snake.head:
            return random.choice(get_directions_as_list())

        head = my_snake.head
        size = field.size
        
        # 1. Parse Stars and Active Effects
        stars = [tuple(item[0]) for item in field.items if item[1] == 'Star']
        apples = [tuple(item[0]) for item in field.items if item[1] == 'Apple']
        bad_apples = [tuple(item[0]) for item in field.items if item[1] == 'BadApple']
        
        im_invincible = any(e.effect in ('TouchOfDeath', 'Invincible') for e in my_snake.active_effects)
        
        invincible_enemies = []
        enemy_heads = []
        all_enemy_segments = set()
        
        for name, snake in field.snakes.items():
            if name != team_name and snake.alive and snake.head:
                enemy_heads.append(tuple(snake.head))
                all_enemy_segments.update(tuple(seg) for seg in snake.body)
                if any(e.effect in ('TouchOfDeath', 'Invincible') for e in snake.active_effects):
                    invincible_enemies.append(snake)

        # 2. Dynamic Obstacles and Danger Zones
        obstacles = BotBrain._get_obstacles(field)
        # Avoid bad apples strictly
        for ba in bad_apples:
            obstacles.add(ba)
            
        danger_zones = set()
        for name, snake in field.snakes.items():
            if name != team_name and snake.alive and snake.head:
                is_enemy_invincible = any(e.effect in ('TouchOfDeath', 'Invincible') for e in snake.active_effects)
                if is_enemy_invincible:
                    # Enemy is invincible: Their entire body and a 2-tile radius around their head is a Danger Zone
                    for segment in snake.body:
                        danger_zones.add(tuple(segment))
                    danger_zones.update(BotBrain._get_radius(snake.head, size, radius=2))
                else:
                    # Normal enemy: head adjacent tiles are Danger Zones (any collision is lethal)
                    adj = BotBrain._get_adjacent(snake.head, size)
                    for c in adj.values():
                        danger_zones.add(c)
        
        # 3. Evaluate Safe Moves
        adjacent_cells = BotBrain._get_adjacent(head, size)
        
        # Find backwards direction to prevent instant suicide
        neck = my_snake.body[1] if len(my_snake.body) > 1 else None
        backwards_dir = None
        for d, coord in adjacent_cells.items():
            if coord == neck:
                backwards_dir = d
                break

        safe_moves: Dict[Direction, Coord] = {}
        for direction, coord in adjacent_cells.items():
            if direction != backwards_dir:
                # If we are invincible, we can safely step on ALIVE enemy segments
                if im_invincible and coord in all_enemy_segments:
                    safe_moves[direction] = coord
                elif coord not in obstacles:
                    safe_moves[direction] = coord

        if not safe_moves:
            print("No safe moves! Crashing...")
            return backwards_dir if backwards_dir else random.choice(get_directions_as_list())

        safer_moves = {}
        for d, c in safe_moves.items():
            if c not in danger_zones:
                safer_moves[d] = c
                
        viable_moves_for_pathing = safer_moves if safer_moves else safe_moves

        # Evaluate voronoi space for survival
        move_scores: Dict[Direction, int] = {}
        for direction, coord in viable_moves_for_pathing.items():
            move_scores[direction] = BotBrain._voronoi_space(coord, enemy_heads, obstacles.union(danger_zones), size)

        # Priority A: Fleeing
        if invincible_enemies and not im_invincible:
            # We want to maximize distance from the closest invincible enemy's head
            def evasion_score(d):
                c = viable_moves_for_pathing[d]
                min_dist = min(BotBrain._manhattan_dist(c, tuple(e.head), size) for e in invincible_enemies)
                return (min_dist, move_scores[d])
            
            best_dir = max(viable_moves_for_pathing.keys(), key=evasion_score)
            print(f"FLEEING! Moving {best_dir} to escape invincible enemy.")
            BotBrain._log_decision("FLEEING", head, best_dir, "Escaping invincible enemy")
            return best_dir

        # Priority B: Hunting
        if im_invincible and enemy_heads:
            # Ignore danger zones for hunting
            hunting_moves = {d: c for d, c in safe_moves.items()}
            # Find shortest path to closest living enemy (head or body)
            best_dir_to_kill = BotBrain._bfs_shortest_path(head, list(all_enemy_segments), obstacles, size, hunting_moves)
            if best_dir_to_kill:
                print(f"HUNTING! Moving {best_dir_to_kill} to kill enemy.")
                BotBrain._log_decision("HUNTING", head, best_dir_to_kill, "Chasing enemy")
                return best_dir_to_kill

        # Priority C: Star Acquisition
        if stars:
            # We want to reach the star, we can risk danger zones if it guarantees the star
            best_dir_to_star = BotBrain._bfs_shortest_path(head, stars, obstacles.union(danger_zones), size, viable_moves_for_pathing)
            if not best_dir_to_star:
                best_dir_to_star = BotBrain._bfs_shortest_path(head, stars, obstacles, size, safe_moves)
            
            if best_dir_to_star:
                print(f"CHASING STAR! Moving {best_dir_to_star}.")
                BotBrain._log_decision("CHASING STAR", head, best_dir_to_star, "Found a path to a Star")
                return best_dir_to_star

        # Priority D: Normal Survival & Farming
        safe_apples = [a for a in apples if a not in danger_zones]
        best_dir_to_apple = BotBrain._bfs_shortest_path(head, safe_apples, obstacles.union(danger_zones), size, viable_moves_for_pathing)
        
        if best_dir_to_apple:
            print(f"FARMING! Moving {best_dir_to_apple} towards safe apple.")
            BotBrain._log_decision("FARMING", head, best_dir_to_apple, "Safe apple found")
            return best_dir_to_apple
            
        # No safe apples, just survive by taking the move that gives the most space
        def survival_score(d):
            coord = viable_moves_for_pathing[d]
            adj = BotBrain._get_adjacent(coord, size)
            free_neighbors = sum(1 for n in adj.values() if n not in obstacles and n not in danger_zones)
            return (move_scores[d], free_neighbors)
            
        best_dir = max(viable_moves_for_pathing.keys(), key=survival_score)
        print(f"SURVIVING! Moving {best_dir} for maximum space ({move_scores[best_dir]}).")
        BotBrain._log_decision("SURVIVING", head, best_dir, "Taking max Voronoi space")
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
    def _get_radius(coord: Coord, size: Tuple[int, int], radius: int) -> Set[Coord]:
        cells = set()
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if abs(dx) + abs(dy) <= radius:
                    cells.add(((coord[0] + dx) % size[0], (coord[1] + dy) % size[1]))
        return cells

    @staticmethod
    def _get_obstacles(field: Field) -> Set[Coord]:
        obstacles = set()
        for snake in field.snakes.values():
            for segment in snake.body:
                obstacles.add(segment)
        return obstacles

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
    def _bfs_shortest_path(start: Coord, targets: List[Coord], obstacles: Set[Coord], size: Tuple[int, int], viable_moves: Dict[Direction, Coord]) -> Optional[Direction]:
        if not targets:
            return None
        target_set = set(targets)
        
        queue = collections.deque()
        visited = set(obstacles)
        visited.difference_update(target_set) # Allow stepping onto targets
        visited.add(start)
        
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
                if neighbor not in visited:
                    if neighbor in target_set:
                        return first_dir
                    visited.add(neighbor)
                    queue.append((neighbor, first_dir))
                    
        return None
        
    @staticmethod
    def _log_decision(mode: str, head: Coord, direction: Direction, reason: str):
        log_str = f"[{mode}] Head: {head} | Move: {direction} | {reason}\n"
        try:
            with open('bot_decisions.log', 'a') as f:
                f.write(log_str)
        except Exception:
            pass
