import collections
import random
from typing import List, Tuple, Set, Dict, Optional

from data_structures import Direction, Coord, get_directions_as_list
from Field import Field, SnakeInfo

class BotBrain:
    killer_mode_active = False

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
        
        # 1. Parse Stars, Apples, Bad Apples, Swords, SpeedBoosts, InstantStacks, and Active Effects
        stars = [tuple(item[0]) for item in field.items if item[1] == 'Star']
        apples = [tuple(item[0]) for item in field.items if item[1] == 'Apple']
        bad_apples = [tuple(item[0]) for item in field.items if item[1] == 'BadApple']
        swords = [tuple(item[0]) for item in field.items if item[1] == 'Sword']
        speed_boosts = [tuple(item[0]) for item in field.items if item[1] == 'SpeedBoost']
        instant_stacks = [tuple(item[0]) for item in field.items if item[1] == 'InstantStack']
        
        im_invincible = any(e.effect in ('TouchOfDeath', 'Invincible') for e in my_snake.active_effects)
        im_boosted = any("SpeedBoost" in e.effect for e in my_snake.active_effects)
        
        my_invincible_ticks = 0
        for effect in my_snake.active_effects:
            if effect.effect in ('TouchOfDeath', 'Invincible'):
                my_invincible_ticks = max(my_invincible_ticks, effect.remaining_ticks)

        my_swords_count = my_snake.inventory.count("Sword")
        my_speed_boosts_count = my_snake.inventory.count("SpeedBoost")
        my_instant_stacks_count = my_snake.inventory.count("InstantStack")

        # Terminal log of equipment counter
        print(f"[EQUIPMENT COUNTER] Swords: {my_swords_count} | SpeedBoosts: {my_speed_boosts_count} | InstantStacks: {my_instant_stacks_count} | Killer Mode: {BotBrain.killer_mode_active}")

        # Killer Mode state machine
        if not BotBrain.killer_mode_active:
            if my_swords_count >= 5 and my_speed_boosts_count >= 9 and my_instant_stacks_count >= 4:
                BotBrain.killer_mode_active = True
                print(">>> Entering KILLER MODE! Hunt mode activated! <<<")
        else:
            # Exit Killer Mode only when we run out of essential resources (no swords or no speed boosts left)
            if my_swords_count < 1 or my_speed_boosts_count < 1:
                BotBrain.killer_mode_active = False
                print(">>> Exiting KILLER MODE. Returning to collecting mode. <<<")

        # 2. Dynamic Obstacles & Threat Modeling
        obstacles = BotBrain._get_obstacles(field)
        
        # Always consider bad apples as obstacles (walls) as requested by the user
        for ba in bad_apples:
            obstacles.add(ba)
                
        # Determine 1v1 scenario and opponent
        alive_enemies = [s for name, s in field.snakes.items() if name != team_name and s.alive]
        is_1v1 = (len(alive_enemies) <= 1)
        opponent = alive_enemies[0] if len(alive_enemies) == 1 else None
        
        we_are_longer = False
        opponent_swords = 0
        can_force_collision = False
        opponent_head_threats = set()
        
        if is_1v1 and opponent and opponent.head:
            opponent_swords = opponent.inventory.count("Sword")
            we_are_longer = (my_length > len(opponent.body))
            can_force_collision = (my_swords_count > 0) and (opponent_swords == 0 or we_are_longer)
            
            opp_head = tuple(opponent.head)
            opponent_head_threats.add(opp_head)
            opp_has_boost = opponent.inventory.count("SpeedBoost") > 0
            opp_adj = BotBrain._get_adjacent(opp_head, size)
            for d, c1 in opp_adj.items():
                if c1 not in obstacles:
                    opponent_head_threats.add(c1)
                    if opp_has_boost:
                        c2 = BotBrain._get_adjacent(c1, size)[d]
                        if c2 not in obstacles:
                            opponent_head_threats.add(c2)
                            
        invincible_enemies = []
        enemy_heads = [] # potential next-tick enemy head threat positions
        dead_obstacles = set()
        alive_enemy_segments = set()
        other_snake_segments = set()
        
        for name, snake in field.snakes.items():
            if name != team_name:
                if snake.alive:
                    other_snake_segments.update(tuple(seg) for seg in snake.body)
                if snake.alive and snake.head:
                    e_head = tuple(snake.head)
                    if not (is_1v1 and can_force_collision):
                        enemy_heads.append(e_head)
                    
                    # Next-tick potential head positions (avoiding head-on collisions)
                    has_speed_boost = snake.inventory.count("SpeedBoost") > 0
                    adj = BotBrain._get_adjacent(e_head, size)
                    for d, c1 in adj.items():
                        if c1 not in obstacles:
                            if not (is_1v1 and can_force_collision):
                                enemy_heads.append(c1)
                            if has_speed_boost:
                                c2 = BotBrain._get_adjacent(c1, size)[d]
                                if c2 not in obstacles:
                                    if not (is_1v1 and can_force_collision):
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
                        if not (is_1v1 and can_force_collision):
                            danger_zones.add(c1)
                        if snake.inventory.count("SpeedBoost") > 0 and c1 not in obstacles:
                            c2 = BotBrain._get_adjacent(c1, size)[d]
                            if not (is_1v1 and can_force_collision):
                                danger_zones.add(c2)
                            
        # 3. Item Distance Calculations (BFS + Trap Avoidance)
        actual_enemy_heads = [tuple(s.head) for s in alive_enemies if s.head]
        
        safe_stars = []
        danger_stars = []
        for star in stars:
            my_dist = BotBrain._bfs_distance(head, star, obstacles, size)
            enemy_dists = [BotBrain._bfs_distance(ae_head, star, obstacles, size) for ae_head in actual_enemy_heads]
            
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
            enemy_dists = [BotBrain._bfs_distance(ae_head, sword, obstacles, size) for ae_head in actual_enemy_heads]
            
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
            enemy_dists = [BotBrain._bfs_distance(ae_head, sb, obstacles, size) for ae_head in actual_enemy_heads]
            
            is_trap = False
            if my_dist != 9999:
                space_at_sb = BotBrain._voronoi_space(sb, enemy_heads, obstacles.union(danger_zones), size)
                if space_at_sb < TRAP_THRESHOLD:
                    is_trap = True
                    
            if my_dist != 9999 and (not enemy_dists or my_dist < min(enemy_dists)) and not is_trap:
                safe_speed_boosts.append(sb)

        # 3.4. Safe Instant Stacks
        safe_instant_stacks = []
        for ist in instant_stacks:
            my_dist = BotBrain._bfs_distance(head, ist, obstacles, size)
            enemy_dists = [BotBrain._bfs_distance(ae_head, ist, obstacles, size) for ae_head in actual_enemy_heads]
            
            is_trap = False
            if my_dist != 9999:
                space_at_ist = BotBrain._voronoi_space(ist, enemy_heads, obstacles.union(danger_zones), size)
                if space_at_ist < TRAP_THRESHOLD:
                    is_trap = True
                    
            if my_dist != 9999 and (not enemy_dists or my_dist < min(enemy_dists)) and not is_trap:
                safe_instant_stacks.append(ist)

        # 4. Evaluate Safe Moves (Immediate collision avoidance + Speed Boost + InstantStack options)
        adjacent_cells = BotBrain._get_adjacent(head, size)
        
        neck = my_snake.body[1] if my_length > 1 else None
        backwards_dir = None
        for d, coord in adjacent_cells.items():
            if coord == neck:
                backwards_dir = d
                break

        safe_moves: Dict[Tuple[Direction, Optional[str]], Coord] = {}
        for direction, coord1 in adjacent_cells.items():
            if direction != backwards_dir:
                if im_boosted:
                    # We are boosted, so the normal move moves 2 steps
                    coord2 = BotBrain._get_adjacent(coord1, size)[direction]
                    if coord1 not in obstacles:
                        coord2_is_safe = False
                        if coord2 not in obstacles:
                            coord2_is_safe = True
                        elif (coord2 in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord2 in alive_enemy_segments):
                            coord2_is_safe = True
                        elif (coord2 in my_snake.body) and my_swords_count > 0 and (my_length > 1 and coord2 != my_snake.body[1]):
                            coord2_is_safe = True
                            
                        if coord2_is_safe:
                            # Ensure we don't speed boost head-on into an enemy head
                            if (is_1v1 and can_force_collision) or (coord2 not in enemy_heads_set):
                                safe_moves[(direction, None)] = coord2
                else:
                    # Normal move (1 step)
                    uses_sword = (coord1 in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord1 in alive_enemy_segments)
                    uses_self_sword = (coord1 in my_snake.body) and my_swords_count > 0 and (my_length > 1 and coord1 != my_snake.body[1])
                    if uses_sword:
                        if (is_1v1 and can_force_collision) or (coord1 not in enemy_heads_set):
                            safe_moves[(direction, None)] = coord1
                    elif uses_self_sword:
                        safe_moves[(direction, None)] = coord1
                    elif im_invincible and coord1 in alive_enemy_segments:
                        safe_moves[(direction, None)] = coord1
                    elif coord1 not in obstacles:
                        safe_moves[(direction, None)] = coord1
                    
                    # Speed boost move (2 steps)
                    if my_speed_boosts_count > 0:
                        coord2 = BotBrain._get_adjacent(coord1, size)[direction]
                        if coord1 not in obstacles:
                            coord2_is_safe = False
                            if coord2 not in obstacles:
                                coord2_is_safe = True
                            elif (coord2 in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord2 in alive_enemy_segments):
                                coord2_is_safe = True
                            elif (coord2 in my_snake.body) and my_swords_count > 0 and (my_length > 1 and coord2 != my_snake.body[1]):
                                coord2_is_safe = True
                                
                            if coord2_is_safe:
                                # Ensure we don't speed boost head-on into an enemy head
                                if (is_1v1 and can_force_collision) or (coord2 not in enemy_heads_set):
                                    safe_moves[(direction, "SpeedBoost")] = coord2

                # Instant stack move (1 step with contraction)
                if my_instant_stacks_count > 0:
                    if coord1 not in obstacles or (im_invincible and coord1 in alive_enemy_segments):
                        safe_moves[(direction, "InstantStack")] = coord1

        if not safe_moves:
            print("No safe moves! Trapped! Trying to hit anything but our own neck...")
            possible_crashes = [d for d in adjacent_cells if d != backwards_dir]
            wall_crashes = [d for d in possible_crashes if adjacent_cells[d] not in my_snake.body]
            best_dir = random.choice(wall_crashes) if wall_crashes else (random.choice(possible_crashes) if possible_crashes else backwards_dir)
            
            # Activate sword if we are colliding and have a sword!
            activate_item = None
            next_cell = adjacent_cells[best_dir]
            is_enemy_collision = (next_cell in other_snake_segments) or (next_cell in enemy_heads_set) or (next_cell in opponent_head_threats)
            is_self_cut = (next_cell in my_snake.body) and (my_length > 1 and next_cell != my_snake.body[1])
            if (is_enemy_collision or is_self_cut) and my_swords_count > 0:
                if not (im_invincible and next_cell in alive_enemy_segments):
                    activate_item = "Sword"
            return best_dir, activate_item

        # 5. Lookahead Simulation & Tiered Safety Move Filtering
        move_scores: Dict[Tuple[Direction, Optional[str]], int] = {}
        survival_depths: Dict[Tuple[Direction, Optional[str]], int] = {}
        sim_bodies: Dict[Tuple[Direction, Optional[str]], List[Coord]] = {}
        MAX_DEPTH = 20

        for (direction, action), coord in safe_moves.items():
            # Setup simulated snake state after taking this move
            is_apple = coord in apples
            is_bad_apple = coord in bad_apples
            
            is_two_step = (action == "SpeedBoost") or (action is None and im_boosted)
            
            if is_two_step:
                uses_sword = (coord in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord in alive_enemy_segments)
                uses_self_sword = (coord in my_snake.body) and my_swords_count > 0 and (my_length > 1 and coord != my_snake.body[1])
                
                if uses_sword or uses_self_sword:
                    sim_swords = my_swords_count - 1
                else:
                    sim_swords = my_swords_count
                    
                sim_boosts = (my_speed_boosts_count - 1) if (action == "SpeedBoost") else my_speed_boosts_count
                sim_instant_stacks = my_instant_stacks_count
                
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
                
                if uses_self_sword:
                    cut_idx = my_snake.body.index(coord2)
                    sim_body = [coord2, coord1] + my_snake.body[:cut_idx]
                else:
                    sim_body = [coord2, coord1] + my_snake.body[:shrink_idx]
                sim_invincible_ticks = max(0, my_invincible_ticks - 2)
            elif action == "InstantStack":
                uses_sword = False
                sim_swords = my_swords_count
                sim_boosts = my_speed_boosts_count
                sim_instant_stacks = my_instant_stacks_count - 1
                
                if is_apple:
                    sim_body = [coord] + [head] * my_length
                    sim_apples = set(apples) - {coord}
                else:
                    sim_body = [coord] + [head] * (my_length - 1)
                    sim_apples = set(apples)
                sim_bad_apples = set(bad_apples)
                sim_invincible_ticks = max(0, my_invincible_ticks - 1)
            else:
                sim_boosts = my_speed_boosts_count
                sim_instant_stacks = my_instant_stacks_count
                uses_sword = (coord in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord in alive_enemy_segments)
                uses_self_sword = (coord in my_snake.body) and my_swords_count > 0 and (my_length > 1 and coord != my_snake.body[1])
                
                if uses_sword:
                    sim_body = [coord] + my_snake.body[:-1]
                    sim_apples = set(apples)
                    sim_bad_apples = set(bad_apples)
                    sim_swords = my_swords_count - 1
                elif uses_self_sword:
                    cut_idx = my_snake.body.index(coord)
                    sim_body = [coord] + my_snake.body[:cut_idx]
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
                
            sim_bodies[(direction, action)] = sim_body
            
            # First-step Voronoi space score
            if uses_sword:
                space_obstacles = (obstacles.union(danger_zones)) - {coord}
            elif uses_self_sword:
                cut_idx = my_snake.body.index(coord)
                cut_segments = set(tuple(seg) for seg in my_snake.body[cut_idx:])
                space_obstacles = (obstacles.union(danger_zones)) - cut_segments
            else:
                space_obstacles = obstacles.union(danger_zones)
            move_scores[(direction, action)] = BotBrain._voronoi_space(coord, enemy_heads, space_obstacles, size)
            
            # Run simulation
            limit_tracker = {"visited": 0}
            depth = BotBrain._survival_depth(
                body=sim_body,
                depth=2 if is_two_step else 1,
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
            survival_depths[(direction, action)] = depth

        # OVERRIDE: Check for immediate slice threats and override survival depth
        for k, coord in safe_moves.items():
            dir_val, action_val = k
            sim_body = sim_bodies[k]
            
            # Check if this move is a sword cut (either direct or landing step of SpeedBoost)
            is_sword_move = (coord in other_snake_segments) and my_swords_count > 0
            body_to_check = sim_body[1:] if is_sword_move else sim_body
            
            sword_positions = [tuple(item[0]) for item in field.items if item[1] == 'Sword']
            has_threat = False
            
            for e in alive_enemies:
                if not e.alive or not e.head:
                    continue
                if is_1v1 and can_force_collision:
                    continue
                e_head = tuple(e.head)
                # Check inventory OR active effects for sword
                e_has_sword = (e.inventory.count("Sword") > 0) or any("Sword" in eff.effect for eff in e.active_effects)
                e_near_sword = False
                if not e_has_sword and sword_positions:
                    # Only count as threat if enemy is closer or equal distance to the sword than us
                    for sword in sword_positions:
                        e_dist = BotBrain._manhattan_dist(e_head, sword, size)
                        my_dist = BotBrain._manhattan_dist(head, sword, size)
                        if e_dist <= 2 and e_dist <= my_dist:
                            e_near_sword = True
                            break
                        
                is_sword_threat = e_has_sword or e_near_sword
                e_has_boost = (e.inventory.count("SpeedBoost") > 0) or any("SpeedBoost" in eff.effect for eff in e.active_effects)
                
                # Immediate slice threat range:
                # If enemy has boost, they can reach our body segments from distance 2
                # If enemy has no boost, they can reach our body segments from distance 1
                slice_threat_range = 2 if e_has_boost else 1
                
                if is_sword_threat:
                    for seg in body_to_check:
                        dist = BotBrain._manhattan_dist(seg, e_head, size)
                        
                        # In 1v1 forced collision, we allow our head to collide with their head
                        if seg == sim_body[0] and is_1v1 and can_force_collision:
                            continue
                            
                        if dist <= slice_threat_range:
                            has_threat = True
                            break
                if has_threat:
                    break
            
            if has_threat:
                # Override survival depth to 1 to force safety tiers to avoid this move
                survival_depths[k] = 1

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

        # Separate viable moves into those that don't use sword/boost/instant_stack and those that do
        open_viable_moves = {}
        for (d, action), c in viable_moves_for_pathing.items():
            if action is None:
                uses_sword = (c in other_snake_segments) and my_swords_count > 0 and not (im_invincible and c in alive_enemy_segments)
                if not uses_sword:
                    open_viable_moves[(d, None)] = c

        # Build proximity-safe subset: filter out moves that put ANY body segment within 2 of an enemy head
        alive_enemies_for_prox = [s for name, s in field.snakes.items() if name != team_name and s.alive and s.head]
        proximity_safe_moves = {}
        for k, c in viable_moves_for_pathing.items():
            sim_body = sim_bodies[k]
            body_is_safe = True
            for e in alive_enemies_for_prox:
                e_head = tuple(e.head)
                e_has_sword = e.inventory.count("Sword") > 0
                for seg in sim_body:
                    dist = BotBrain._manhattan_dist(seg, e_head, size)
                    if e_has_sword and dist <= 2:
                        body_is_safe = False
                        break
                    elif dist <= 1:
                        body_is_safe = False
                        break
                if not body_is_safe:
                    break
            if body_is_safe:
                proximity_safe_moves[k] = c
        # Fallback: if every move is "unsafe", use original viable set
        if not proximity_safe_moves:
            proximity_safe_moves = viable_moves_for_pathing
        
        # Also build proximity-safe open (no sword/boost/instant_stack) subset
        prox_safe_open = {k: c for k, c in proximity_safe_moves.items() if k in open_viable_moves}

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
            chosen_dir, action = chosen_move
            print(f"FLEEING! Moving {chosen_dir} (action={action}) to escape invincible enemy. Tier: {safety_tier}")
            BotBrain._log_decision("FLEEING", head, chosen_dir, f"Escaping invincible enemy ({safety_tier})")

        # Priority B: Hunting & Interception (Immediate Cut, distance <= 2 if we have boost)
        intercept_targets = []
        hunt_sword_threshold = 1 if (BotBrain.killer_mode_active or im_boosted) else 3
        if my_swords_count >= hunt_sword_threshold:
            intercept_targets = BotBrain._find_intercept_targets(head, alive_enemies, obstacles, size)

        if chosen_move is None and my_swords_count >= hunt_sword_threshold:
            max_immediate_dist = 1
            if my_speed_boosts_count > 0 or any("SpeedBoost" in eff.effect for eff in my_snake.active_effects):
                max_immediate_dist = 2
            immediate_targets = [t[0] for t in intercept_targets if t[2] <= max_immediate_dist]
            if immediate_targets:
                best_move = None
                
                # For hunting, use speed boost continuously in killer mode, or if we have at least 1 backup (count >= 2)
                allowed_actions = {None}
                if BotBrain.killer_mode_active:
                    allowed_actions.add("SpeedBoost")
                elif my_speed_boosts_count >= 2:
                    allowed_actions.add("SpeedBoost")
                
                # Use tier3 (all survivors) for hunting to allow aggressive attacks in tight spaces
                hunting_candidates = tier3 if tier3 else viable_moves_for_pathing
                pathing_pool = {k: v for k, v in hunting_candidates.items() if k[1] in allowed_actions}
                
                if "SpeedBoost" in allowed_actions:
                    # Sort pathing pool keys so that "SpeedBoost" actions come first, ensuring we dash/speedboost when possible
                    sorted_keys = sorted(pathing_pool.keys(), key=lambda k: 0 if k[1] == "SpeedBoost" else 1)
                    pathing_pool = {k: pathing_pool[k] for k in sorted_keys}
                
                if pathing_pool:
                    best_move = BotBrain._bfs_shortest_path(head, immediate_targets, obstacles.union(danger_zones), size, pathing_pool)
                    if not best_move:
                        best_move = BotBrain._bfs_shortest_path(head, immediate_targets, obstacles, size, pathing_pool)
                
                if best_move:
                    chosen_move = best_move
                    chosen_dir, action = chosen_move
                    print(f"HUNTING (IMMEDIATE CUT)! Moving {chosen_dir} (action={action}) toward intercept target. Tier: {safety_tier}")
                    BotBrain._log_decision("HUNTING (IMMEDIATE CUT)", head, chosen_dir, f"Immediate cut of intercept target ({safety_tier})")

        # Priority B.5: Distant Interception in Killer Mode (actively hunt before collecting stars/items)
        if chosen_move is None and BotBrain.killer_mode_active and my_swords_count >= hunt_sword_threshold:
            distant_targets = [t[0] for t in intercept_targets if t[2] > 1]
            if distant_targets:
                best_move = None
                allowed_actions = {None, "SpeedBoost"}
                
                # Use tier3 (all survivors) for hunting to allow aggressive attacks in tight spaces
                hunting_candidates = tier3 if tier3 else viable_moves_for_pathing
                pathing_pool = {k: v for k, v in hunting_candidates.items() if k[1] in allowed_actions}
                
                # Sort pathing pool keys so that "SpeedBoost" actions come first, ensuring we dash/speedboost to chase
                sorted_keys = sorted(pathing_pool.keys(), key=lambda k: 0 if k[1] == "SpeedBoost" else 1)
                pathing_pool = {k: pathing_pool[k] for k in sorted_keys}
                
                if pathing_pool:
                    best_move = BotBrain._bfs_shortest_path(head, distant_targets, obstacles.union(danger_zones), size, pathing_pool)
                    if not best_move:
                        best_move = BotBrain._bfs_shortest_path(head, distant_targets, obstacles, size, pathing_pool)
                
                if best_move:
                    chosen_move = best_move
                    chosen_dir, action = chosen_move
                    print(f"HUNTING (DISTANT CHASE KILLER)! Moving {chosen_dir} (action={action}) toward intercept target. Tier: {safety_tier}")
                    BotBrain._log_decision("HUNTING (DISTANT CHASE KILLER)", head, chosen_dir, f"Killer mode chasing distant intercept target ({safety_tier})")

        # Priority C: Star Acquisition
        if chosen_move is None and safe_stars and not (is_1v1 and can_force_collision):
            best_move = None
            pathing_pool = prox_safe_open if prox_safe_open else (proximity_safe_moves if proximity_safe_moves else viable_moves_for_pathing)
            if prox_safe_open:
                best_move = BotBrain._bfs_shortest_path(head, safe_stars, obstacles.union(danger_zones), size, prox_safe_open)
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, safe_stars, obstacles, size, prox_safe_open)
            
            if not best_move:
                best_move = BotBrain._bfs_shortest_path(head, safe_stars, obstacles.union(danger_zones), size, proximity_safe_moves)
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, safe_stars, obstacles, size, proximity_safe_moves)
            
            if best_move:
                chosen_move = best_move
                chosen_dir, action = chosen_move
                print(f"CHASING STAR! Moving {chosen_dir} (action={action}). Tier: {safety_tier}")
                BotBrain._log_decision("CHASING STAR", head, chosen_dir, f"Guaranteed first to safe Star ({safety_tier})")

        # Determine priority order of item collection
        if my_swords_count >= 10:
            if my_instant_stacks_count >= 5:
                item_priorities = [
                    ("SpeedBoost", safe_speed_boosts, "CHASING SPEEDBOOST"),
                    ("Sword", safe_swords, "CHASING SWORD"),
                    ("InstantStack", safe_instant_stacks, "CHASING INSTANTSTACK")
                ]
            else:
                item_priorities = [
                    ("SpeedBoost", safe_speed_boosts, "CHASING SPEEDBOOST"),
                    ("InstantStack", safe_instant_stacks, "CHASING INSTANTSTACK"),
                    ("Sword", safe_swords, "CHASING SWORD")
                ]
        else:
            if my_instant_stacks_count >= 5:
                item_priorities = [
                    ("Sword", safe_swords, "CHASING SWORD"),
                    ("SpeedBoost", safe_speed_boosts, "CHASING SPEEDBOOST"),
                    ("InstantStack", safe_instant_stacks, "CHASING INSTANTSTACK")
                ]
            else:
                item_priorities = [
                    ("Sword", safe_swords, "CHASING SWORD"),
                    ("InstantStack", safe_instant_stacks, "CHASING INSTANTSTACK"),
                    ("SpeedBoost", safe_speed_boosts, "CHASING SPEEDBOOST")
                ]

        # Priority C.2 & C.3: Item Acquisition (Sword, SpeedBoost, InstantStack)
        for item_name, targets, log_label in item_priorities:
            if chosen_move is None and targets and not (is_1v1 and can_force_collision):
                best_move = None
                if prox_safe_open:
                    best_move = BotBrain._bfs_shortest_path(head, targets, obstacles.union(danger_zones), size, prox_safe_open)
                    if not best_move:
                        best_move = BotBrain._bfs_shortest_path(head, targets, obstacles, size, prox_safe_open)
                
                if not best_move:
                    best_move = BotBrain._bfs_shortest_path(head, targets, obstacles.union(danger_zones), size, proximity_safe_moves)
                    if not best_move:
                        best_move = BotBrain._bfs_shortest_path(head, targets, obstacles, size, proximity_safe_moves)
                
                if best_move:
                    chosen_move = best_move
                    chosen_dir, action = chosen_move
                    print(f"{log_label}! Moving {chosen_dir} (action={action}). Tier: {safety_tier}")
                    BotBrain._log_decision(log_label, head, chosen_dir, f"Safe path to {item_name} ({safety_tier})")

        # Priority C.4: Distant Interception (distance > 1)
        if chosen_move is None and my_swords_count >= hunt_sword_threshold:
            distant_targets = [t[0] for t in intercept_targets if t[2] > 1]
            if distant_targets:
                best_move = None
                
                # For hunting, use speed boost continuously in killer mode, or if we have at least 1 backup (count >= 2)
                allowed_actions = {None}
                if BotBrain.killer_mode_active:
                    allowed_actions.add("SpeedBoost")
                elif my_speed_boosts_count >= 2:
                    allowed_actions.add("SpeedBoost")
                
                # Use tier3 (all survivors) for hunting to allow aggressive attacks in tight spaces
                hunting_candidates = tier3 if tier3 else viable_moves_for_pathing
                pathing_pool = {k: v for k, v in hunting_candidates.items() if k[1] in allowed_actions}
                
                if "SpeedBoost" in allowed_actions:
                    # Sort pathing pool keys so that "SpeedBoost" actions come first, ensuring we dash/speedboost to chase
                    sorted_keys = sorted(pathing_pool.keys(), key=lambda k: 0 if k[1] == "SpeedBoost" else 1)
                    pathing_pool = {k: pathing_pool[k] for k in sorted_keys}
                
                if pathing_pool:
                    best_move = BotBrain._bfs_shortest_path(head, distant_targets, obstacles.union(danger_zones), size, pathing_pool)
                    if not best_move:
                        best_move = BotBrain._bfs_shortest_path(head, distant_targets, obstacles, size, pathing_pool)
                
                if best_move:
                    chosen_move = best_move
                    chosen_dir, action = chosen_move
                    print(f"HUNTING (DISTANT CHASE)! Moving {chosen_dir} (action={action}) toward intercept target. Tier: {safety_tier}")
                    BotBrain._log_decision("HUNTING (DISTANT CHASE)", head, chosen_dir, f"Chasing distant intercept target ({safety_tier})")

        # Priority D: Diet Manager
        if chosen_move is None and not (is_1v1 and can_force_collision):
            # Grow boldly when we have InstantStacks
            if my_instant_stacks_count > 0:
                target_length = max(45, grid_area * 3 // 4)
            else:
                target_length = max(30, grid_area // 3)
            
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
                    if prox_safe_open:
                        best_move = BotBrain._bfs_shortest_path(head, safe_target_food, obstacles.union(danger_zones), size, prox_safe_open)
                    if not best_move:
                        best_move = BotBrain._bfs_shortest_path(head, safe_target_food, obstacles.union(danger_zones), size, proximity_safe_moves)
                    if best_move:
                        chosen_move = best_move
                        chosen_dir, action = chosen_move
                        print(f"{mode}! Moving {chosen_dir} (action={action}). Tier: {safety_tier}")
                        BotBrain._log_decision(mode, head, chosen_dir, f"Managing size to {target_length} ({safety_tier})")
            
        # Fallback: Survival
        if chosen_move is None:
            def survival_score(k):
                d, action = k
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
                    
                if action is None:
                    uses_sword = (coord in other_snake_segments) and my_swords_count > 0 and not (im_invincible and coord in alive_enemy_segments)
                    uses_self_sword = (coord in my_snake.body) and my_swords_count > 0 and (my_length > 1 and coord != my_snake.body[1])
                    if uses_sword:
                        penalty -= 500
                    elif uses_self_sword:
                        penalty -= 4000
                elif action == "SpeedBoost":
                    penalty -= 500
                elif action == "InstantStack":
                    penalty -= 2000
                    
                # Proximity penalty: Shadow Tracking
                alive_enemies_surv = [s for name, s in field.snakes.items() if name != team_name and s.alive and s.head]
                if alive_enemies_surv:
                    sim_body = sim_bodies[k]
                    is_sword_move = (action is None) and (coord in other_snake_segments) and my_swords_count > 0
                    body_to_check = sim_body[1:] if is_sword_move else sim_body
                    
                    sword_positions = [tuple(item[0]) for item in field.items if item[1] == 'Sword']
                    
                    for e in alive_enemies_surv:
                        e_head = tuple(e.head)
                        # Check inventory OR active effects for sword
                        e_has_sword = (e.inventory.count("Sword") > 0) or any("Sword" in eff.effect for eff in e.active_effects)
                        e_near_sword = False
                        if not e_has_sword and sword_positions:
                            # Only count as threat if enemy is closer or equal distance to the sword than us
                            for sword in sword_positions:
                                e_dist = BotBrain._manhattan_dist(e_head, sword, size)
                                my_dist = BotBrain._manhattan_dist(head, sword, size)
                                if e_dist <= 2 and e_dist <= my_dist:
                                    e_near_sword = True
                                    break
                                
                        is_sword_threat = e_has_sword or e_near_sword
                        e_has_boost = (e.inventory.count("SpeedBoost") > 0) or any("SpeedBoost" in eff.effect for eff in e.active_effects)
                        slice_threat_range = 2 if e_has_boost else 1
                        
                        for seg in body_to_check:
                            dist = BotBrain._manhattan_dist(seg, e_head, size)
                            
                            is_our_head = (seg == sim_body[0])
                            if is_our_head and is_1v1 and can_force_collision:
                                continue
                                
                            if is_sword_threat:
                                if dist <= slice_threat_range:
                                    penalty -= 30000  # Fatal immediate slice threat
                                elif dist <= slice_threat_range + 1:
                                    penalty -= 1500   # High threat
                            else:
                                if dist <= 1:
                                    penalty -= 150    # Minor risk
 
                # Tactical win bonus in 1v1
                if is_1v1 and can_force_collision:
                    if coord in opponent_head_threats:
                        penalty += 10000
                    if action == "SpeedBoost":
                        coord1 = adjacent_cells[d]
                        if coord1 in opponent_head_threats:
                            penalty += 10000
                    
                # Voronoi Territory Difference
                voronoi_diff = BotBrain._voronoi_territory_diff(coord, enemy_heads, obstacles.union(danger_zones), size)
                
                # Tail Chase Bonus
                tail_bonus = 0
                if my_length > 3:
                    tail = my_snake.body[-1]
                    tail_dist = BotBrain._get_tail_distance(coord, tail, obstacles, size)
                    if tail_dist != 9999:
                        tail_bonus = max(0, 200 - tail_dist * 15)
 
                return (survival_depths[k] * 1000 + move_scores[k] + voronoi_diff * 10 + tail_bonus + penalty, free_neighbors)
                
            chosen_move = max(viable_moves_for_pathing.keys(), key=survival_score)
            chosen_dir, action = chosen_move
            print(f"SURVIVING! Moving {chosen_dir} (action={action}) for maximum space ({move_scores[chosen_move]}). Tier: {safety_tier}")
            BotBrain._log_decision("SURVIVING", head, chosen_dir, f"Maintaining size and space ({safety_tier})")
            
        # Determine if we should activate an item for this tick
        chosen_dir, action = chosen_move
        
        activate_item = None
        if action == "SpeedBoost":
            activate_item = "SpeedBoost"
        elif action == "InstantStack":
            activate_item = "InstantStack"
        else:
            if im_boosted:
                coord1 = adjacent_cells[chosen_dir]
                next_cell = BotBrain._get_adjacent(coord1, size)[chosen_dir]
            else:
                next_cell = adjacent_cells[chosen_dir]
            is_enemy_collision = (next_cell in other_snake_segments) or (next_cell in enemy_heads_set) or (next_cell in opponent_head_threats)
            is_self_cut = (next_cell in my_snake.body) and (my_length > 1 and next_cell != my_snake.body[1])
            if (is_enemy_collision or is_self_cut) and my_swords_count > 0:
                if not (im_invincible and next_cell in alive_enemy_segments):
                    activate_item = "Sword"
                
        return chosen_dir, activate_item

    @staticmethod
    def _find_intercept_targets(
        my_head: Coord,
        alive_enemies: List[SnakeInfo],
        obstacles: Set[Coord],
        size: Tuple[int, int]
    ) -> List[Tuple[Coord, int, int]]:
        """
        Identifies opponent body segments we can reach with a sword cut.
        Returns a list of (target_coord, score, distance) tuples.
        """
        intercept_targets = []
        for enemy in alive_enemies:
            if not enemy.alive or not enemy.head:
                continue
            
            enemy_body = enemy.body
            enemy_len = len(enemy_body)
            # Target index 1 (neck) and above to be aggressive when opponents are close
            for i in range(1, enemy_len):
                seg = enemy_body[i]
                
                # Check distance from our head to the segment coord.
                # Exclude the segment itself from obstacles so we can reach it
                obstacles_without_seg = obstacles - {seg}
                d = BotBrain._bfs_distance(my_head, seg, obstacles_without_seg, size)
                
                if d != 9999 and d <= i:
                    damage_score = enemy_len - (i - d)
                    score = damage_score * 10 - d * 2
                    intercept_targets.append((seg, score, d))
                    
        # Sort targets by score descending
        intercept_targets.sort(key=lambda x: x[1], reverse=True)
        return intercept_targets

    @staticmethod
    def _voronoi_territory_diff(my_start: Coord, enemy_heads: List[Coord], obstacles: Set[Coord], size: Tuple[int, int]) -> int:
        from collections import deque
        queue = deque()
        visited = {}
        
        if my_start not in obstacles:
            queue.append((0, 0, my_start))
            visited[my_start] = 0
            
        for i, enemy_head in enumerate(enemy_heads):
            if enemy_head not in visited:
                queue.append((0, i + 1, enemy_head))
                visited[enemy_head] = i + 1
            
        while queue:
            dist, owner, curr = queue.popleft()
            
            adj = BotBrain._get_adjacent(curr, size)
            for neighbor in adj.values():
                if neighbor not in obstacles and neighbor not in visited:
                    visited[neighbor] = owner
                    queue.append((dist + 1, owner, neighbor))
                    
        my_cells = 0
        enemy_cells = collections.defaultdict(int)
        for owner in visited.values():
            if owner == 0:
                my_cells += 1
            else:
                enemy_cells[owner] += 1
                
        max_enemy_cells = max(enemy_cells.values()) if enemy_cells else 0
        return my_cells - max_enemy_cells

    @staticmethod
    def _get_tail_distance(coord: Coord, tail: Coord, obstacles: Set[Coord], size: Tuple[int, int]) -> int:
        # Exclude tail from obstacles so we can reach it
        obstacles_without_tail = obstacles - {tail}
        return BotBrain._bfs_distance(coord, tail, obstacles_without_tail, size)

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
            if neighbor in bad_apples:
                continue
            is_collision_with_other = (neighbor in dead_obstacles or neighbor in alive_enemy_segments)
            if is_collision_with_other:
                if neighbor in alive_enemy_segments and im_invincible:
                    pass
                elif swords_count > 0 and neighbor not in enemy_heads:
                    # Swords can cut through both alive enemy segments and dead obstacles
                    pass
                else:
                    continue
                    
            if neighbor in body_set:
                if swords_count > 0 and (len(body) <= 1 or neighbor != body[1]):
                    pass
                elif neighbor == body[-1]:
                    pass
                else:
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
                
            is_self_cut = (neighbor in body_set and neighbor != body[-1])

            # Sword consumption
            if (is_collision_with_other and not (neighbor in alive_enemy_segments and im_invincible)) or is_self_cut:
                new_swords_count = swords_count - 1
            else:
                new_swords_count = swords_count
                
            # Body growth/shrinkage/shift
            if is_collision_with_other:
                new_body = [neighbor] + body[:-1]
                new_apples = apples
                new_bad_apples = bad_apples
            elif is_self_cut:
                cut_idx = body.index(neighbor)
                new_body = [neighbor] + body[:cut_idx]
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
