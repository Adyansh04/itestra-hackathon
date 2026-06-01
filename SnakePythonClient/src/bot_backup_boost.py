import collections
import random
from typing import List, Tuple, Set, Dict, Optional

from data_structures import Direction, Coord, get_directions_as_list
from Field import Field

class BotBrain:
    @staticmethod
    def get_next_move(field: Field, team_name: str, is_round_2: bool = False, *args, **kwargs) -> Tuple[Direction, Optional[str]]:
        my_snake = field.snakes.get(team_name)
        if not my_snake or not my_snake.alive or not my_snake.head:
            return random.choice(get_directions_as_list()), None

        head = my_snake.head
        size = field.size
        my_length = len(my_snake.body)
        grid_area = size[0] * size[1]
        
        # Adaptive thresholds based on grid size
        TRAP_THRESHOLD = max(3, grid_area // 30)       # ~15 for 21x21
        TIGHT_SPACE_THRESHOLD = max(5, grid_area // 18) # ~25 for 21x21
        DANGER_ZONE_RANGE = 4
        STAR_DURATION = 4
        INVINCIBLE_DANGER_RADIUS = STAR_DURATION
        MAX_FOOD_SAFETY_CHECKS = 6
        MAX_HUNT_ENEMIES = 3
        
        # 1. Parse Stars, Apples, Bad Apples, Swords, SpeedBoosts, and Active Effects
        stars = [tuple(item[0]) for item in field.items if item[1] == 'Star']
        apples = [tuple(item[0]) for item in field.items if item[1] == 'Apple']
        bad_apples = [tuple(item[0]) for item in field.items if item[1] == 'BadApple']
        swords = [tuple(item[0]) for item in field.items if item[1] == 'Sword']
        speed_boosts = [tuple(item[0]) for item in field.items if item[1] == 'SpeedBoost']
        
        im_invincible = any(e.effect in ('TouchOfDeath', 'Invincible') for e in my_snake.active_effects)
        
        my_invincible_ticks = 0
        for effect in my_snake.active_effects:
            if effect.effect in ('TouchOfDeath', 'Invincible'):
                my_invincible_ticks = max(my_invincible_ticks, effect.remaining_ticks)

        my_swords_count = my_snake.inventory.count("Sword")
        my_speed_boosts_count = my_snake.inventory.count("SpeedBoost")

        # 2. Dynamic Obstacles & Threat Modeling
        obstacles = BotBrain._get_obstacles(field)
        
        if my_length <= 1:
            for ba in bad_apples:
                obstacles.add(ba)
                
        invincible_enemies = []
        enemy_heads = [] # potential next-tick enemy head threat positions
        dead_obstacles = set()
        alive_enemy_segments = set()
        other_snake_segments = set()
        
        for name, snake in field.snakes.items():
            if name != team_name:
                other_snake_segments.update(tuple(seg) for seg in snake.body)
                if snake.alive and snake.head:
                    e_head = tuple(snake.head)
                    enemy_heads.append(e_head)
                    
                    # Next-tick potential head positions (avoiding head-on collisions)
                    has_speed_boost = snake.inventory.count("SpeedBoost") > 0
                    adj = BotBrain._get_adjacent(e_head, size)
                    for d, c1 in adj.items():
                        if c1 not in obstacles:
                            enemy_heads.append(c1)
                            if has_speed_boost:
                                c2 = BotBrain._get_adjacent(c1, size)[d]
                                if c2 not in obstacles:
                                    enemy_heads.append(c2)
                                    
                    alive_enemy_segments.update(tuple(seg) for seg in snake.body)
                    if any(e.effect in ('TouchOfDeath', 'Invincible') for e in snake.active_effects):
                        invincible_enemies.append(snake)
                else:
                    dead_obstacles.update(tuple(seg) for seg in snake.body)
                    
        # Make threat positions unique
        enemy_heads = list(set(enemy_heads))
        enemy_heads_set = set(enemy_heads)

        # Dynamic danger zones based on opponent range & speed boost
        danger_zones = set()
        for name, snake in field.snakes.items():
            if name != team_name and snake.alive and snake.head:
                enemy_dist_to_us = BotBrain._manhattan_dist(head, tuple(snake.head), size)
                is_enemy_invincible = any(e.effect in ('TouchOfDeath', 'Invincible') for e in snake.active_effects)
                if is_enemy_invincible:
                    for segment in snake.body:
                        danger_zones.add(tuple(segment))
                    danger_zones.update(BotBrain._get_radius(snake.head, size, radius=INVINCIBLE_DANGER_RADIUS))
                elif enemy_dist_to_us <= DANGER_ZONE_RANGE:
                    e_head = tuple(snake.head)
                    adj = BotBrain._get_adjacent(e_head, size)
                    for d, c1 in adj.items():
                        danger_zones.add(c1)
                        if snake.inventory.count("SpeedBoost") > 0 and c1 not in obstacles:
                            c2 = BotBrain._get_adjacent(c1, size)[d]
                            danger_zones.add(c2)
                            
        # 3. Item Distance Calculations (BFS + Trap Avoidance)
        safe_stars = []
        danger_stars = []
        for star in stars:
            my_dist = BotBrain._bfs_distance(head, star, obstacles, size)
            enemy_dists = [BotBrain._bfs_distance(e_head, star, obstacles, size) for e_head in enemy_heads]
            
            is_trap = False
            if my_dist != 9999:
                space_at_star = BotBrain._voronoi_space(star, enemy_heads, obstacles.union(danger_zones), size)
                if space_at_star < TRAP_THRESHOLD:
                    is_trap = True
                    
            if my_dist != 9999 and (not enemy_dists or my_dist < min(enemy_dists)) and not is_trap:
                safe_stars.append(star)
            else:
                danger_stars.append(star)
                
        for d_star in danger_stars:
            danger_zones.add(d_star)
            adj = BotBrain._get_adjacent(d_star, size)
            for c in adj.values():
                danger_zones.add(c)

        # 3.2. Safe Swords
        safe_swords = []
        for sword in swords:
            my_dist = BotBrain._bfs_distance(head, sword, obstacles, size)
            enemy_dists = [BotBrain._bfs_distance(e_head, sword, obstacles, size) for e_head in enemy_heads]
            
            is_trap = False
            if my_dist != 9999:
                space_at_sword = BotBrain._voronoi_space(sword, enemy_heads, obstacles.union(danger_zones), size)
                if space_at_sword < TRAP_THRESHOLD:
                    is_trap = True
                    
            if my_dist != 9999 and (not enemy_dists or my_dist < min(enemy_dists)) and not is_trap:
                safe_swords.append(sword)

        # 3.3. Safe Speed Boosts
        safe_speed_boosts = []
        for sb in speed_boosts:
            my_dist = BotBrain._bfs_distance(head, sb, obstacles, size)
            enemy_dists = [BotBrain._bfs_distance(e_head, sb, obstacles, size) for e_head in enemy_heads]
            
            is_trap = False
            if my_dist != 9999:
                space_at_sb = BotBrain._voronoi_space(sb, enemy_heads, obstacles.union(danger_zones), size)
                if space_at_sb < TRAP_THRESHOLD:
                    is_trap = True
                    
            if my_dist != 9999 and (not enemy_dists or my_dist < min(enemy_dists)) and not is_trap:
                safe_speed_boosts.append(sb)

        # 4. Evaluate Safe Moves (Immediate collision avoidance + Speed Boost options)
        adjacent_cells = BotBrain._get_adjacent(head, size)
        
        neck = my_snake.body[1] if my_length > 1 else None
        backwards_dir = None
        for d, coord in adjacent_cells.items():
            if coord == neck:
                backwards_dir = d
                break

        safe_moves: Dict[Tuple[Direction, bool], Coord] = {}
        for direction, coord1 in adjacent_cells.items():
            if direction != backwards_dir:
                # Normal move
                uses_sword = (coord1 in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord1 in alive_enemy_segments)
                if uses_sword:
                    if coord1 not in enemy_heads_set:
                        safe_moves[(direction, False)] = coord1
                elif im_invincible and coord1 in alive_enemy_segments:
                    safe_moves[(direction, False)] = coord1
                elif coord1 not in obstacles:
                    safe_moves[(direction, False)] = coord1
                
                # Speed boost move (2 steps)
                if my_speed_boosts_count > 0:
                    coord2 = BotBrain._get_adjacent(coord1, size)[direction]
                    if coord1 not in obstacles and coord2 not in obstacles:
                        # Ensure we don't speed boost head-on into an enemy head
                        if coord2 not in enemy_heads_set:
                            safe_moves[(direction, True)] = coord2

        if not safe_moves:
            print("No safe moves! Trapped! Trying to hit anything but our own neck...")
            possible_crashes = [d for d in adjacent_cells if d != backwards_dir]
            wall_crashes = [d for d in possible_crashes if adjacent_cells[d] not in my_snake.body]
            best_dir = random.choice(wall_crashes) if wall_crashes else (random.choice(possible_crashes) if possible_crashes else backwards_dir)
            return best_dir, None

        # 5. Lookahead Simulation & Tiered Safety Move Filtering
        move_scores: Dict[Tuple[Direction, bool], int] = {}
        survival_depths: Dict[Tuple[Direction, bool], int] = {}
        MAX_DEPTH = 20

        for (direction, is_boost), coord in safe_moves.items():
            # Setup simulated snake state after taking this move
            is_apple = coord in apples
            is_bad_apple = coord in bad_apples
            
            if is_boost:
                uses_sword = False
                sim_swords = my_swords_count
                sim_boosts = my_speed_boosts_count - 1
                
                coord1 = adjacent_cells[direction]
                coord2 = coord
                
                apples_eaten = 0
                bad_apples_eaten = 0
                sim_apples = set(apples)
                sim_bad_apples = set(bad_apples)
                
                if coord1 in apples:
                    apples_eaten += 1
                    sim_apples.discard(coord1)
                elif coord1 in bad_apples:
                    bad_apples_eaten += 1
                    sim_bad_apples.discard(coord1)
                    
                if coord2 in apples:
                    apples_eaten += 1
                    sim_apples.discard(coord2)
                elif coord2 in bad_apples:
                    bad_apples_eaten += 1
                    sim_bad_apples.discard(coord2)
                
                net_shrinkage = 2 - apples_eaten + bad_apples_eaten
                shrink_idx = max(1, len(my_snake.body) - net_shrinkage)
                sim_body = [coord2, coord1] + my_snake.body[:shrink_idx]
                sim_invincible_ticks = max(0, my_invincible_ticks - 2)
            else:
                sim_boosts = my_speed_boosts_count
                uses_sword = (coord in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord in alive_enemy_segments)
                if uses_sword:
                    sim_body = [coord] + my_snake.body[:-1]
                    sim_apples = set(apples)
                    sim_bad_apples = set(bad_apples)
                    sim_swords = my_swords_count - 1
                else:
                    sim_swords = my_swords_count
                    if is_apple:
                        sim_body = [coord] + my_snake.body
                        sim_apples = set(apples) - {coord}
                        sim_bad_apples = set(bad_apples)
                    elif is_bad_apple:
                        sim_body = [coord] + my_snake.body[:-2] if len(my_snake.body) > 2 else [coord]
                        sim_apples = set(apples)
                        sim_bad_apples = set(bad_apples) - {coord}
                    else:
                        sim_body = [coord] + my_snake.body[:-1]
                        sim_apples = set(apples)
                        sim_bad_apples = set(bad_apples)
                sim_invincible_ticks = max(0, my_invincible_ticks - 1)
                
            # First-step Voronoi space score
            if uses_sword:
                space_obstacles = (obstacles.union(danger_zones)) - {coord}
            else:
                space_obstacles = obstacles.union(danger_zones)
            move_scores[(direction, is_boost)] = BotBrain._voronoi_space(coord, enemy_heads, space_obstacles, size)
            
            # Run simulation
            limit_tracker = {"visited": 0}
            depth = BotBrain._survival_depth(
                body=sim_body,
                depth=2 if is_boost else 1,
                max_depth=MAX_DEPTH,
                dead_obstacles=dead_obstacles.union(danger_zones),
                alive_enemy_segments=alive_enemy_segments,
                enemy_heads=enemy_heads_set,
                apples=sim_apples,
                bad_apples=sim_bad_apples,
                stars=set(stars),
                invincible_ticks=sim_invincible_ticks,
                star_duration=STAR_DURATION,
                swords_count=sim_swords,
                size=size,
                limit_tracker=limit_tracker
            )
            survival_depths[(direction, is_boost)] = depth

        # Filter candidate moves based on safety tiers
        tier1 = {k: c for k, c in safe_moves.items() if survival_depths[k] >= MAX_DEPTH and move_scores[k] >= TIGHT_SPACE_THRESHOLD}
        tier2 = {k: c for k, c in safe_moves.items() if survival_depths[k] >= MAX_DEPTH and move_scores[k] >= TRAP_THRESHOLD}
        tier3 = {k: c for k, c in safe_moves.items() if survival_depths[k] >= MAX_DEPTH}
        
        if tier1:
            viable_moves_for_pathing = tier1
            safety_tier = "Tier 1 (Fully Safe)"
        elif tier2:
            viable_moves_for_pathing = tier2
            safety_tier = "Tier 2 (Highly Safe)"
        elif tier3:
            viable_moves_for_pathing = tier3
            safety_tier = "Tier 3 (Survivable)"
        else:
            max_surv = max(survival_depths.values())
            viable_moves_for_pathing = {k: c for k, c in safe_moves.items() if survival_depths[k] == max_surv}
            safety_tier = f"Tier 4 (Best effort depth {max_surv})"

        # Separate viable moves into those that don't use sword/boost and those that do
        open_viable_moves = {}
        for (d, is_boost), c in viable_moves_for_pathing.items():
            if not is_boost:
                uses_sword = (c in other_snake_segments) and my_swords_count > 0 and not (im_invincible and c in alive_enemy_segments)
                if not uses_sword:
                    open_viable_moves[(d, False)] = c

        chosen_move = None

        # Priority A: Fleeing
        if invincible_enemies and not im_invincible:
            fleeing_moves = open_viable_moves if open_viable_moves else viable_moves_for_pathing
            def evasion_score(k):
                c = fleeing_moves[k]
                min_dist = min(BotBrain._manhattan_dist(c, tuple(e.head), size) for e in invincible_enemies)
                is_safe_space = 1 if move_scores[k] >= TIGHT_SPACE_THRESHOLD else 0
                return (is_safe_space, min_dist, move_scores[k])
            
            chosen_move = max(fleeing_moves.keys(), key=evasion_score)
            chosen_dir, is_boost = chosen_move
            print(f"FLEEING! Moving {chosen_dir} (boost={is_boost}) to escape invincible enemy. Tier: {safety_tier}")
            BotBrain._log_decision("FLEEING", head, chosen_dir, f"Escaping invincible enemy ({safety_tier})")

        # Note: Priority B (Hunting) is disabled because Stars no longer allow killing opponents.

        # Priority C: Star Acquisition
        if chosen_move is None and safe_stars:
            best_move = None
            if open_viable_moves:
                best_move = BotBrain._bfs_shortest_path(head, safe_stars, obstacles.union(danger_zones), size, open_viable_moves)
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, safe_stars, obstacles, size, open_viable_moves)
            
            if not best_move:
                best_move = BotBrain._bfs_shortest_path(head, safe_stars, obstacles.union(danger_zones), size, viable_moves_for_pathing)
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, safe_stars, obstacles, size, viable_moves_for_pathing)
            
            if best_move:
                chosen_move = best_move
                chosen_dir, is_boost = chosen_move
                print(f"CHASING STAR! Moving {chosen_dir} (boost={is_boost}). Tier: {safety_tier}")
                BotBrain._log_decision("CHASING STAR", head, chosen_dir, f"Guaranteed first to safe Star ({safety_tier})")

        # Priority C.2: Sword Acquisition
        if chosen_move is None and safe_swords and my_swords_count < 2:
            best_move = None
            if open_viable_moves:
                best_move = BotBrain._bfs_shortest_path(head, safe_swords, obstacles.union(danger_zones), size, open_viable_moves)
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, safe_swords, obstacles, size, open_viable_moves)
            
            if not best_move:
                best_move = BotBrain._bfs_shortest_path(head, safe_swords, obstacles.union(danger_zones), size, viable_moves_for_pathing)
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, safe_swords, obstacles, size, viable_moves_for_pathing)
            if best_move:
                chosen_move = best_move
                chosen_dir, is_boost = chosen_move
                print(f"CHASING SWORD! Moving {chosen_dir} (boost={is_boost}). Tier: {safety_tier}")
                BotBrain._log_decision("CHASING SWORD", head, chosen_dir, f"Safe path to Sword ({safety_tier})")

        # Priority C.3: Speed Boost Acquisition
        if chosen_move is None and safe_speed_boosts and my_speed_boosts_count < 2:
            best_move = None
            if open_viable_moves:
                best_move = BotBrain._bfs_shortest_path(head, safe_speed_boosts, obstacles.union(danger_zones), size, open_viable_moves)
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, safe_speed_boosts, obstacles, size, open_viable_moves)
            
            if not best_move:
                best_move = BotBrain._bfs_shortest_path(head, safe_speed_boosts, obstacles.union(danger_zones), size, viable_moves_for_pathing)
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, safe_speed_boosts, obstacles, size, viable_moves_for_pathing)
            if best_move:
                chosen_move = best_move
                chosen_dir, is_boost = chosen_move
                print(f"CHASING SPEEDBOOST! Moving {chosen_dir} (boost={is_boost}). Tier: {safety_tier}")
                BotBrain._log_decision("CHASING SPEEDBOOST", head, chosen_dir, f"Safe path to SpeedBoost ({safety_tier})")

        # Priority D: Diet Manager
        if chosen_move is None:
            alive_snakes_count = sum(1 for s in field.snakes.values() if s.alive)
            if alive_snakes_count <= 2:
                # In 1v1, if we have swords, we can safely grow much larger (using swords as a safety escape)
                if my_swords_count >= 2:
                    target_length = max(45, grid_area * 2 // 3)  # Large size (e.g. 66 on 10x10) to trap opponent
                elif my_swords_count == 1:
                    target_length = max(35, grid_area // 2)      # Medium-large size (e.g. 50 on 10x10)
                else:
                    target_length = max(25, grid_area // 3)      # Safe baseline (e.g. 33 on 10x10)
            elif alive_snakes_count <= 5:
                target_length = max(15, grid_area // 6)
            else:
                target_length = max(10, grid_area // 10)
            
            target_food = []
            mode = "SURVIVING"
            
            if my_length > target_length:
                target_food = [ba for ba in bad_apples if ba not in danger_zones]
                mode = "DIETING (Shrinking)"
            elif my_length < target_length:
                target_food = [a for a in apples if a not in danger_zones]
                mode = "EATING (Growing)"
                
            if target_food:
                target_food_sorted = sorted(target_food, key=lambda f: BotBrain._manhattan_dist(head, f, size))
                safe_target_food = []
                for f in target_food_sorted[:MAX_FOOD_SAFETY_CHECKS]:
                    space_at_food = BotBrain._voronoi_space(f, enemy_heads, obstacles.union(danger_zones), size)
                    if space_at_food >= TRAP_THRESHOLD:
                        safe_target_food.append(f)
                        
                if safe_target_food:
                    best_move = None
                    if open_viable_moves:
                        best_move = BotBrain._bfs_shortest_path(head, safe_target_food, obstacles.union(danger_zones), size, open_viable_moves)
                    if not best_move:
                        best_move = BotBrain._bfs_shortest_path(head, safe_target_food, obstacles.union(danger_zones), size, viable_moves_for_pathing)
                    if best_move:
                        chosen_move = best_move
                        chosen_dir, is_boost = chosen_move
                        print(f"{mode}! Moving {chosen_dir} (boost={is_boost}). Tier: {safety_tier}")
                        BotBrain._log_decision(mode, head, chosen_dir, f"Managing size to {target_length} ({safety_tier})")
            
        # Fallback: Survival
        if chosen_move is None:
            def survival_score(k):
                d, is_boost = k
                coord = viable_moves_for_pathing[k]
                adj = BotBrain._get_adjacent(coord, size)
                free_neighbors = sum(1 for n in adj.values() if n not in obstacles and n not in danger_zones)
                
                penalty = 0
                if coord in bad_apples:
                    if my_length == target_length: penalty = -10
                    elif my_length > target_length: penalty = 0
                    elif my_length < target_length: penalty = -20
                if coord in apples:
                    if my_length == target_length: penalty = -10
                    elif my_length > target_length: penalty = -20
                    elif my_length < target_length: penalty = 0
                    
                if move_scores[k] < TIGHT_SPACE_THRESHOLD:
                    penalty -= 1000
                    
                # Penalize using a sword/boost to save it if possible
                if not is_boost:
                    uses_sword = (coord in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord in alive_enemy_segments)
                    if uses_sword:
                        penalty -= 500
                else:
                    penalty -= 500
                    
                return (survival_depths[k] * 1000 + move_scores[k] + penalty, free_neighbors)
                
            chosen_move = max(viable_moves_for_pathing.keys(), key=survival_score)
            chosen_dir, is_boost = chosen_move
            print(f"SURVIVING! Moving {chosen_dir} (boost={is_boost}) for maximum space ({move_scores[chosen_move]}). Tier: {safety_tier}")
            BotBrain._log_decision("SURVIVING", head, chosen_dir, f"Maintaining size and space ({safety_tier})")
            
        # Determine if we should activate an item for this tick
        chosen_dir, is_boost = chosen_move
        
        activate_item = None
        if is_boost:
            activate_item = "SpeedBoost"
        else:
            next_cell = adjacent_cells[chosen_dir]
            is_enemy_collision = (next_cell in other_snake_segments)
            if is_enemy_collision and my_swords_count > 0:
                if not (im_invincible and next_cell in alive_enemy_segments):
                    if next_cell not in enemy_heads_set:
                        activate_item = "Sword"
                
        return chosen_dir, activate_item

    @staticmethod
    def _manhattan_dist(p1: Coord, p2: Coord, size: Tuple[int, int]) -> int:
        dx = min(abs(p1[0] - p2[0]), size[0] - abs(p1[0] - p2[0]))
        dy = min(abs(p1[1] - p2[1]), size[1] - abs(p1[1] - p2[1]))
        return dx + dy

    @staticmethod
    def _bfs_distance(start: Coord, target: Coord, obstacles: Set[Coord], size: Tuple[int, int]) -> int:
        if start == target: return 0
        queue = collections.deque([(start, 0)])
        visited = set(obstacles)
        visited.add(start)
        while queue:
            curr, dist = queue.popleft()
            adj = BotBrain._get_adjacent(curr, size)
            for neighbor in adj.values():
                if neighbor == target:
                    return dist + 1
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))
        return 9999

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
                obstacles.add(tuple(segment))
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
    def _bfs_shortest_path(start: Coord, targets: List[Coord], obstacles: Set[Coord], size: Tuple[int, int], viable_moves: Dict[Tuple[Direction, bool], Coord]) -> Optional[Tuple[Direction, bool]]:
        if not targets:
            return None
        target_set = set(targets)
        
        queue = collections.deque()
        visited = set(obstacles)
        visited.difference_update(target_set)
        visited.add(start)
        
        for key, coord in viable_moves.items():
            if coord not in visited:
                if coord in target_set:
                    return key
                queue.append((coord, key))
                visited.add(coord)
                
        while queue:
            curr, first_key = queue.popleft()
            
            adj = BotBrain._get_adjacent(curr, size)
            for neighbor in adj.values():
                if neighbor not in visited:
                    if neighbor in target_set:
                        return first_key
                    visited.add(neighbor)
                    queue.append((neighbor, first_key))
                    
        return None
        
    @staticmethod
    def _log_decision(mode: str, head: Coord, direction: Direction, reason: str):
        log_str = f"[{mode}] Head: {head} | Move: {direction} | {reason}\n"
        try:
            with open('bot_decisions.log', 'a') as f:
                f.write(log_str)
        except Exception:
            pass

    @staticmethod
    def _survival_depth(
        body: List[Coord],
        depth: int,
        max_depth: int,
        dead_obstacles: Set[Coord],
        alive_enemy_segments: Set[Coord],
        enemy_heads: Set[Coord],
        apples: Set[Coord],
        bad_apples: Set[Coord],
        stars: Set[Coord],
        invincible_ticks: int,
        star_duration: int,
        swords_count: int,
        size: Tuple[int, int],
        limit_tracker: Dict[str, int]
    ) -> int:
        if depth >= max_depth:
            return max_depth
            
        limit_tracker["visited"] += 1
        if limit_tracker["visited"] >= 1000:
            return depth
            
        head = body[0]
        adjacent = BotBrain._get_adjacent(head, size)
        
        neighbors_with_scores = []
        body_set = set(body)
        im_invincible = (invincible_ticks > 0)
        
        for direction, neighbor in adjacent.items():
            is_collision_with_other = (neighbor in dead_obstacles or neighbor in alive_enemy_segments)
            if is_collision_with_other:
                if neighbor in alive_enemy_segments and im_invincible:
                    pass
                elif swords_count > 0 and neighbor not in enemy_heads:
                    pass
                else:
                    continue
                    
            if neighbor in body_set and neighbor != body[-1]:
                continue
                
            free_count = 0
            neighbor_adj = BotBrain._get_adjacent(neighbor, size)
            for n_adj in neighbor_adj.values():
                if n_adj not in dead_obstacles and n_adj not in body_set:
                    if not (n_adj in alive_enemy_segments and not im_invincible):
                        free_count += 1
            neighbors_with_scores.append((free_count, neighbor))
            
        neighbors_with_scores.sort(key=lambda x: x[0], reverse=True)
        
        max_d = depth
        for _, neighbor in neighbors_with_scores:
            is_apple = neighbor in apples
            is_bad_apple = neighbor in bad_apples
            is_star = neighbor in stars
            is_collision_with_other = (neighbor in dead_obstacles or neighbor in alive_enemy_segments)
            
            # Invincibility updates
            if is_star:
                new_invincible_ticks = star_duration
                new_stars = stars - {neighbor}
            else:
                new_invincible_ticks = max(0, invincible_ticks - 1)
                new_stars = stars
                
            # Sword consumption
            if is_collision_with_other and not (neighbor in alive_enemy_segments and im_invincible):
                new_swords_count = swords_count - 1
            else:
                new_swords_count = swords_count
                
            # Body growth/shrinkage/shift
            if is_collision_with_other:
                new_body = [neighbor] + body[:-1]
                new_apples = apples
                new_bad_apples = bad_apples
            elif is_apple:
                if neighbor in body_set:
                    continue
                new_body = [neighbor] + body
                new_apples = apples - {neighbor}
                new_bad_apples = bad_apples
            elif is_bad_apple:
                if len(body) <= 1:
                    continue
                if neighbor in body_set and neighbor != body[-1] and neighbor != body[-2]:
                    continue
                new_body = [neighbor] + body[:-2] if len(body) > 2 else [neighbor]
                new_apples = apples
                new_bad_apples = bad_apples - {neighbor}
            else:
                if neighbor in body_set and neighbor != body[-1]:
                    continue
                new_body = [neighbor] + body[:-1]
                new_apples = apples
                new_bad_apples = bad_apples
                
            d = BotBrain._survival_depth(
                body=new_body,
                depth=depth + 1,
                max_depth=max_depth,
                dead_obstacles=dead_obstacles,
                alive_enemy_segments=alive_enemy_segments,
                enemy_heads=enemy_heads,
                apples=new_apples,
                bad_apples=new_bad_apples,
                stars=new_stars,
                invincible_ticks=new_invincible_ticks,
                star_duration=star_duration,
                swords_count=new_swords_count,
                size=size,
                limit_tracker=limit_tracker
            )
            if d > max_d:
                max_d = d
                if max_d >= max_depth:
                    return max_depth
                    
        return max_d
