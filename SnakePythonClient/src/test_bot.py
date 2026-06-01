import unittest
from bot import BotBrain
from Field import Field, SnakeInfo

class TestBotBrain(unittest.TestCase):
    def test_get_adjacent(self):
        size = (10, 10)
        
        # Test middle
        adj = BotBrain._get_adjacent((5, 5), size)
        self.assertEqual(adj["NORTH"], (5, 4))
        self.assertEqual(adj["SOUTH"], (5, 6))
        self.assertEqual(adj["EAST"], (6, 5))
        self.assertEqual(adj["WEST"], (4, 5))
        
        # Test wrap-around edges
        adj = BotBrain._get_adjacent((0, 0), size)
        self.assertEqual(adj["NORTH"], (0, 9))
        self.assertEqual(adj["SOUTH"], (0, 1))
        self.assertEqual(adj["EAST"], (1, 0))
        self.assertEqual(adj["WEST"], (9, 0))

    def test_voronoi_space(self):
        size = (5, 5)
        # Empty board, we get all 25 squares
        self.assertEqual(BotBrain._voronoi_space((2, 2), [], set(), size), 25)
        
        # Board with an enemy at (0, 0), and we are at (4, 4)
        # They will split the board
        space = BotBrain._voronoi_space((4, 4), [(0, 0)], set(), size)
        self.assertTrue(0 < space < 25)

        # Make a box around (0,0) with wrapping
        # 0,0 is adjacent to 1,0 and 4,0 and 0,1 and 0,4
        obstacles2 = {(1, 0), (4, 0), (0, 1), (0, 4)}
        self.assertEqual(BotBrain._voronoi_space((0, 0), [], obstacles2, size), 1)

    def test_survival_depth(self):
        size = (10, 10)
        # 1. Open space survival: should survive to max depth (20)
        body = [(5, 5), (5, 6), (5, 7)]
        limit_tracker = {"visited": 0}
        depth = BotBrain._survival_depth(
            body=body,
            depth=1,
            max_depth=20,
            dead_obstacles=set(),
            alive_enemy_segments=set(),
            enemy_heads=set(),
            apples=set(),
            bad_apples=set(),
            stars=set(),
            invincible_ticks=0,
            star_duration=4,
            swords_count=0,
            size=size,
            limit_tracker=limit_tracker
        )
        self.assertEqual(depth, 20)
        
        # 2. Room survival: Room of size 4 (5,5), (5,6), (6,5), (6,6)
        # Surrounded by walls:
        dead_room_walls = {
            (4, 4), (4, 5), (4, 6), (4, 7),
            (7, 4), (7, 5), (7, 6), (7, 7),
            (5, 4), (6, 4), (5, 7), (6, 7)
        }
        limit_tracker = {"visited": 0}
        depth_trapped = BotBrain._survival_depth(
            body=[(5, 5), (5, 6), (6, 6), (6, 5), (5, 5)],
            depth=1,
            max_depth=20,
            dead_obstacles=dead_room_walls,
            alive_enemy_segments=set(),
            enemy_heads=set(),
            apples=set(),
            bad_apples=set(),
            stars=set(),
            invincible_ticks=0,
            star_duration=4,
            swords_count=0,
            size=size,
            limit_tracker=limit_tracker
        )
        # It must die before depth 20 because the room is fully enclosed and has only 4 cells
        self.assertTrue(depth_trapped < 20)

    def test_lookahead_dynamics(self):
        size = (10, 10)
        
        # Test Star Invincibility: 
        # An alive enemy segment blocks us normally, but if we are invincible, we can step on it.
        alive_enemy_segments = {(5, 4)}
        dead_obstacles = {(4, 5), (6, 5), (5, 6)} # block left, right, and tail
        
        # Scenario A: Not invincible -> should only survive 1 step (blocked everywhere)
        limit_tracker = {"visited": 0}
        depth_blocked = BotBrain._survival_depth(
            body=[(5, 5), (5, 6)],
            depth=1,
            max_depth=5,
            dead_obstacles=dead_obstacles,
            alive_enemy_segments=alive_enemy_segments,
            enemy_heads=set(),
            apples=set(),
            bad_apples=set(),
            stars=set(),
            invincible_ticks=0,
            star_duration=4,
            swords_count=0,
            size=size,
            limit_tracker=limit_tracker
        )
        self.assertEqual(depth_blocked, 1)
        
        # Scenario B: Invincible (starting with invincible_ticks=2) -> should step on (5,4) and survive
        limit_tracker = {"visited": 0}
        depth_invincible = BotBrain._survival_depth(
            body=[(5, 5), (5, 6)],
            depth=1,
            max_depth=5,
            dead_obstacles=dead_obstacles,
            alive_enemy_segments=alive_enemy_segments,
            enemy_heads=set(),
            apples=set(),
            bad_apples=set(),
            stars=set(),
            invincible_ticks=2,
            star_duration=4,
            swords_count=0,
            size=size,
            limit_tracker=limit_tracker
        )
        self.assertTrue(depth_invincible > 1)

    def test_sword_acquisition(self):
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": [
                [[5, 4], "Sword"]
            ]
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "NORTH")
        self.assertIsNone(activate)

    def test_sword_defensive_escape(self):
        # Trapped!
        # Head at (5,5), body at (5,6)
        # NORTH is enemy body segment at (5,4) (head is at 5,3)
        # EAST (6,5) and WEST (4,5) are blocked by dead_guy body.
        # We also block exits of EAST and WEST so their lookahead survival depth is 1.
        raw_field_with_sword = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 3], [5, 4]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "dead_guy": {
                    "body": [
                        [6, 5], [4, 5],          # immediate east and west
                        [7, 5], [6, 4], [6, 6],  # block east exits
                        [3, 5], [4, 4], [4, 6]   # block west exits
                    ],
                    "alive": False,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field_with_sword)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "NORTH")
        self.assertEqual(activate, "Sword")

        raw_field_no_sword = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 3], [5, 4]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "dead_guy": {
                    "body": [
                        [6, 5], [4, 5],
                        [7, 5], [6, 4], [6, 6],
                        [3, 5], [4, 4], [4, 6]
                    ],
                    "alive": False,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field_no_sword = Field.from_dict(raw_field_no_sword)
        direction, activate = BotBrain.get_next_move(field_no_sword, "teamea")
        self.assertIsNone(activate)

    def test_lookahead_with_sword(self):
        size = (10, 10)
        dead_obstacles = {(4, 5), (6, 5), (5, 6)}
        alive_enemy_segments = {(5, 4)}
        
        limit_tracker = {"visited": 0}
        depth_no_sword = BotBrain._survival_depth(
            body=[(5, 5), (5, 6)],
            depth=1,
            max_depth=5,
            dead_obstacles=dead_obstacles,
            alive_enemy_segments=alive_enemy_segments,
            enemy_heads=set(),
            apples=set(),
            bad_apples=set(),
            stars=set(),
            invincible_ticks=0,
            star_duration=4,
            swords_count=0,
            size=size,
            limit_tracker=limit_tracker
        )
        self.assertEqual(depth_no_sword, 1)
        
        limit_tracker = {"visited": 0}
        depth_with_sword = BotBrain._survival_depth(
            body=[(5, 5), (5, 6)],
            depth=1,
            max_depth=5,
            dead_obstacles=dead_obstacles,
            alive_enemy_segments=alive_enemy_segments,
            enemy_heads=set(),
            apples=set(),
            bad_apples=set(),
            stars=set(),
            invincible_ticks=0,
            star_duration=4,
            swords_count=1,
            size=size,
            limit_tracker=limit_tracker
        )
        self.assertTrue(depth_with_sword > 1)

    def test_sword_head_on_collision(self):
        # Trapped!
        # Head at (5,5), body at (5,6)
        # NORTH is alive enemy head at (5,4)
        # EAST and WEST are blocked by our own body, which we cannot cut
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [
                        [5, 5], [5, 6], [6, 6], [6, 5], [7, 5], 
                        [7, 6], [7, 7], [6, 7], [5, 7], [4, 7], 
                        [4, 6], [4, 5]
                    ],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 4]], # Occupies NORTH (head)
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        # Since NORTH is an alive enemy head, it is a head-on collision threat.
        # Under the new rules, if forced to go NORTH, we activate the sword for safety.
        self.assertEqual(direction, "NORTH")
        self.assertEqual(activate, "Sword")

    def test_sword_optimal_breakout(self):
        # We are at (5,5) with 1 sword.
        # EAST (6,5) is open, but leads to a dead end / trap (blocked by our own body, which we cannot cut).
        # WEST (4,5) is a dead_guy segment, but behind it is completely open space.
        # So moving EAST has survival depth of 1, while moving WEST (cutting dead obstacle) has survival depth of 20.
        # The bot should choose WEST and activate the sword.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [
                        [5, 5], [5, 6], [6, 6], [7, 6], [7, 5], 
                        [7, 4], [6, 4], [5, 4]
                    ],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                },
                "dead_guy": {
                    "body": [
                        [4, 5]                  # Obstacle at WEST
                    ],
                    "alive": False,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        # The bot should choose WEST to cut the obstacle and escape, rather than EAST (which is open but a trap)
        self.assertEqual(direction, "WEST")
        self.assertEqual(activate, "Sword")

    def test_speed_boost_acquisition(self):
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": [
                [[5, 4], "SpeedBoost"]
            ]
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "NORTH")
        self.assertIsNone(activate)

    def test_speed_boost_breakout(self):
        # We are trapped at (5,5) with body at (5,6)
        # EAST (6,5) and WEST (4,5) are blocked by dead obstacles.
        # NORTH (5,4) is open, but has neighbors blocked except (5,3).
        # (5,4) is in the danger/threat zone of an enemy at (6,4).
        # (5,3) is outside the enemy's threat zone.
        # Normal move to (5,4) gets penalized because it is in a danger zone.
        # SpeedBoost to (5,3) lands on (5,3), which is safe and has open exits,
        # resulting in a higher overall score and triggering the SpeedBoost.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["SpeedBoost"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[6, 4]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "dead_guy": {
                    "body": [
                        [6, 5], [4, 5],  # Block EAST/WEST of head
                        [4, 4]   # Block WEST of (5,4) (EAST is blocked by enemy head at (6,4))
                    ],
                    "alive": False,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "NORTH")
        self.assertEqual(activate, "SpeedBoost")

    def test_speed_boost_safety(self):
        # We have a SpeedBoost, but the 2-step cell is blocked.
        # Head at (5,5). NORTH is (5,4). NORTH-NORTH is (5,3).
        # If (5,3) is blocked, we cannot speed boost.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["SpeedBoost"],
                    "active_effects": []
                },
                "dead_guy": {
                    "body": [
                        [5, 3]  # Obstacle at final speed boost cell (5,3)
                    ],
                    "alive": False,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        # Should not activate speed boost
        self.assertNotEqual(activate, "SpeedBoost")

    def test_opponent_speed_boost_threat(self):
        # Our head at (5,5). Enemy head at (5,2).
        # We want to go NORTH to (5,4) to eat an apple.
        # Scenario A: Enemy has NO speed boost.
        # (5,4) is safe because it's 2 steps away from enemy head (5,2).
        # Bot should choose NORTH.
        raw_field_no_boost = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 2]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": [
                [[5, 4], "Apple"]
            ]
        }
        field_no_boost = Field.from_dict(raw_field_no_boost)
        direction, activate = BotBrain.get_next_move(field_no_boost, "teamea")
        self.assertEqual(direction, "NORTH")

        # Scenario B: Enemy HAS speed boost.
        # Threat zone of enemy extends 2 steps SOUTH to (5,4).
        # So moving NORTH to (5,4) is dangerous (score 0 / penalized).
        # Bot should choose EAST or WEST to avoid the threat.
        raw_field_with_boost = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 2]],
                    "alive": True,
                    "inventory": ["SpeedBoost"],
                    "active_effects": []
                }
            },
            "items": [
                [[5, 4], "Apple"]
            ]
        }
        field_with_boost = Field.from_dict(raw_field_with_boost)
        direction, activate = BotBrain.get_next_move(field_with_boost, "teamea")
        self.assertIn(direction, ["EAST", "WEST"])

    def test_spawn_stretching_phase(self):
        # We spawn at (5,5) with all segments on the same cell.
        # Opponent spawns at (5,0).
        # We should move to one of the adjacent free cells (NORTH, SOUTH, EAST, WEST) without crashing.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 5], [5, 5], [5, 5], [5, 5], [5, 5]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 0]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertIn(direction, ["NORTH", "SOUTH", "EAST", "WEST"])

    def test_play_safe_proximity_avoidance(self):
        # Multi-player lobby (3 snakes).
        # We are at (5,5).
        # Enemy 1 is at (5,2) (NORTH is 5,4, which is dist 2 from 5,2).
        # Enemy 2 is at (7,5) (EAST is 6,5, which is dist 1 from 7,5).
        # SOUTH (5,6) and WEST (4,5) are completely safe (dist > 2).
        # The bot should choose SOUTH or WEST to avoid the proximity penalty.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy1": {
                    "body": [[5, 2]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy2": {
                    "body": [[7, 5]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertIn(direction, ["SOUTH", "WEST"])

    def test_1v1_win_by_length(self):
        # 1v1 lobby. We are at (5,5), length 6, 1 Sword.
        # Enemy at (5,3), length 4.
        # We are longer than the enemy, so we want to force a head-on collision.
        # Moving NORTH to (5,4) meets their head South move.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6], [5, 7], [5, 8], [5, 9], [6, 9]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 3], [5, 2], [5, 1], [5, 0]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        # Should choose NORTH and activate Sword to force the win
        self.assertEqual(direction, "NORTH")
        self.assertEqual(activate, "Sword")

    def test_1v1_win_by_disarmed_opponent(self):
        # 1v1 lobby. We are at (5,5), length 4, 1 Sword.
        # Enemy is at (5,3), length 6 (Enemy is longer!).
        # However, enemy has NO Swords. We have 1 Sword.
        # Since they are disarmed, we can force a head-on collision at (5,4) and survive.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6], [5, 7], [5, 8]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 3], [5, 2], [5, 1], [5, 0], [4, 0], [3, 0]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        # Should choose NORTH and activate Sword
        self.assertEqual(direction, "NORTH")
        self.assertEqual(activate, "Sword")

    def test_hunt_intercept_basic(self):
        # We are at (5,5), body length 2, holding a Sword.
        # Enemy is at (3,2), body segments at (3,2), (3,3), (3,4), (3,5), (3,6).
        # Enemy head is at (3,2). Segment at index 3 is at (3,5).
        # Our distance to (3,5) is 2 steps (West to (4,5) then West to (3,5)).
        # Since d=2 <= i=3, we can intercept.
        # First move should be WEST towards the intercept target.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword", "Sword", "Sword"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[3, 2], [3, 3], [3, 4], [3, 5], [3, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "WEST")

    def test_hunt_avoids_unsafe_cut(self):
        # We have a sword and can intercept an enemy at (3,5).
        # However, the space around (3,5) is walled off by dead snake segments,
        # meaning if we step there we get trapped immediately (low survival depth).
        # We should prioritize survival and avoid the cut.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword", "Sword", "Sword"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[3, 2], [3, 3], [3, 4], [3, 5], [3, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "dead": {
                    "body": [[4, 4], [3, 4], [2, 4], [2, 5], [2, 6], [3, 6], [4, 6]], # walls enclosing (3,5)
                    "alive": False,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        # Should choose a safe move (EAST, NORTH, or SOUTH) instead of WEST
        self.assertNotEqual(direction, "WEST")

    def test_territory_maximization(self):
        # We are at (5,5), no items. Enemy head is at (8,5).
        # Moving WEST (4,5) moves us away from enemy and expands our space.
        # Moving EAST (6,5) moves us closer to enemy, shrinking our relative space.
        # Voronoi territory diff should prefer WEST.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[8, 5], [9, 5]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "WEST")

    def test_tail_chase_fallback(self):
        # Trapped in a loop, but tail is at (5,6) and moving.
        # Moving NORTH to (5,4) has a clear path to tail.
        # The bot should stay compact by moving towards its tail.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [6, 5], [6, 6], [5, 6]], # tail is (5,6)
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        # Head is (5,5). Tail is (5,6). Adjacent to head are (5,4)[N], (4,5)[W].
        # We can reach tail from WEST (4,5) or NORTH (5,4).
        # Both are safe, but moving WEST brings head to (4,5) which is adjacent to tail (5,6).
        # Let's verify that the move chosen is safe.
        self.assertIn(direction, ["WEST", "NORTH"])

    def test_body_shadow_tracking(self):
        # Enemy is right behind us at (5,7) with a sword, moving towards our tail/body.
        # We have two moves:
        # Move WEST to (4,5) -> pulls our body away from the enemy.
        # Move EAST to (6,5) -> keeps our body in the threat zone.
        # Shadow tracking proximity penalty should prefer WEST.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 7], [6, 7]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertNotEqual(direction, "EAST")

    def test_instant_stack_acquisition(self):
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": [
                [[5, 4], "InstantStack"]
            ]
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "NORTH")
        self.assertIsNone(activate)

    def test_instant_stack_defensive_escape(self):
        # We are at (5, 5), body of length 6.
        # Surrounded except for WEST (4, 5) which goes into a small pocket.
        # Pocket has size 3. Normally, length 6 snake cannot survive in a size 3 pocket (depth < 20).
        # But if we use InstantStack, we contract to size 2 and can easily survive (depth = 20).
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6], [6, 6], [7, 6], [7, 5], [7, 4]],
                    "alive": True,
                    "inventory": ["InstantStack"],
                    "active_effects": []
                },
                "dead": {
                    "body": [
                        [5, 4], [6, 4], [6, 5], # block north and east exits
                        [4, 4], [3, 4], [3, 5], [3, 6], [4, 6] # pocket walls around (4,5)
                    ],
                    "alive": False,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "WEST")
        self.assertEqual(activate, "InstantStack")

    def test_instant_stack_slice_evasion(self):
        # Head at (5, 5), trailing body down the line.
        # Enemy at (6, 7) has a Sword.
        # Moving WEST normally leaves our tail segments exposed.
        # Moving WEST with InstantStack contracts us to [(4, 5), (5, 5)], evading the threat.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6], [5, 7], [5, 8], [5, 9]],
                    "alive": True,
                    "inventory": ["InstantStack"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[6, 7], [7, 7]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertIn(direction, ["NORTH", "WEST", "EAST"])
        self.assertEqual(activate, "InstantStack")

    def test_instant_stack_stacking(self):
        # We are already contracted. We have another InstantStack and a Sword in inventory.
        # We can activate InstantStack again while in a contracted state.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6], [5, 6], [5, 6], [5, 6]],
                    "alive": True,
                    "inventory": ["InstantStack"],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        # Should not crash and should allow moving in safe directions
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertIn(direction, ["NORTH", "SOUTH", "EAST", "WEST"])

    def test_item_safety_close_proximity(self):
        # Head at (5, 5). Sword at (5, 4) (dist 1).
        # Enemy head at (5, 2) (dist 2).
        # Under the old code, this sword was marked unsafe because the enemy's next-tick cell (5, 3) has distance 1.
        # Under the fixed code, we compare against actual enemy head (5, 2) which has distance 2, so the sword is safe and we go NORTH to collect it.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[5, 2], [6, 2]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": [
                [[5, 4], "Sword"]
            ]
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "NORTH")
        self.assertIsNone(activate)

    def test_item_safety_priority_over_distant_hunt(self):
        # Head at (5, 5). Sword at (6, 5) (dist 1, safe).
        # Enemy is at (3, 2), body segments at (3, 2), (3, 3), (3, 4), (3, 5), (3, 6).
        # We can intercept segment (3, 5) (index 3) with distance 2.
        # But we have a safe sword at (6, 5) (distance 1).
        # The bot should prioritize collecting the safe sword (moving EAST) over distant hunting (moving WEST).
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword", "Sword", "Sword"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[3, 2], [3, 3], [3, 4], [3, 5], [3, 6]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                }
            },
            "items": [
                [[6, 5], "Sword"]
            ]
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "EAST")
        self.assertIsNone(activate)

    def test_self_cut_survival(self):
        # Head at (5, 5). Neck at (5, 6).
        # Adjacent cells: NORTH (5, 4), SOUTH (5, 6)[neck], EAST (6, 5)[body segment at index 3], WEST (4, 5).
        # We block NORTH and WEST with a thick dead guy wall, so cutting them leads to dead ends.
        # The only escape to open space is EAST (our own body) by self-cutting.
        # If we have a sword, we should cut ourselves at (6, 5) and survive.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6], [6, 6], [6, 5], [7, 5], [7, 6], [7, 7]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                },
                "dead_guy": {
                    "body": [
                        [5, 4], [4, 4], [6, 4], [5, 3], [4, 3], [6, 3],
                        [4, 5], [3, 5], [3, 4], [3, 6], [3, 7], [4, 7]
                    ],
                    "alive": False,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "EAST")
        self.assertEqual(activate, "Sword")

    def test_killer_mode_activation_and_deactivation(self):
        # Reset state
        BotBrain.killer_mode_active = False
        
        # Test activation: 5 swords, 9 speed boosts, 4 instant stacks
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"] * 5 + ["SpeedBoost"] * 9 + ["InstantStack"] * 4,
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        BotBrain.get_next_move(field, "teamea")
        self.assertTrue(BotBrain.killer_mode_active)

        # Drop to 1 sword and 1 speed boost - should STILL remain in Killer Mode
        raw_field_still_active = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"] * 1 + ["SpeedBoost"] * 1 + ["InstantStack"] * 0,
                    "active_effects": []
                }
            },
            "items": []
        }
        field_still_active = Field.from_dict(raw_field_still_active)
        BotBrain.get_next_move(field_still_active, "teamea")
        self.assertTrue(BotBrain.killer_mode_active)

        # Drop to 0 swords - should deactivate
        raw_field_deact = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"] * 0 + ["SpeedBoost"] * 1 + ["InstantStack"] * 0,
                    "active_effects": []
                }
            },
            "items": []
        }
        field_deact = Field.from_dict(raw_field_deact)
        BotBrain.get_next_move(field_deact, "teamea")
        self.assertFalse(BotBrain.killer_mode_active)

    def test_priority_swap_at_five_instant_stacks(self):
        # Scenario A: We have 1 InstantStack (< 5).
        # We should prioritize InstantStack (EAST) over SpeedBoost (NORTH).
        raw_field_a = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["InstantStack"],
                    "active_effects": []
                }
            },
            "items": [
                [[5, 3], "SpeedBoost"],
                [[7, 5], "InstantStack"]
            ]
        }
        field_a = Field.from_dict(raw_field_a)
        direction_a, _ = BotBrain.get_next_move(field_a, "teamea")
        self.assertEqual(direction_a, "EAST")

        # Scenario B: We have 5 InstantStacks (>= 5).
        # We should swap priorities and target SpeedBoost (NORTH) over InstantStack (EAST).
        raw_field_b = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["InstantStack"] * 5,
                    "active_effects": []
                }
            },
            "items": [
                [[5, 3], "SpeedBoost"],
                [[7, 5], "InstantStack"]
            ]
        }
        field_b = Field.from_dict(raw_field_b)
        direction_b, _ = BotBrain.get_next_move(field_b, "teamea")
        self.assertEqual(direction_b, "NORTH")

    def test_killer_mode_continuous_speed_boost(self):
        # We manually set killer_mode_active = True
        BotBrain.killer_mode_active = True
        
        # We have 4 swords, 4 speed boosts, and 1 instant stack (satisfies exit thresholds).
        # We should use SpeedBoost to hunt a distant intercept target.
        # Head at (5, 5). Target at (5, 2) is segment index 3 of enemy snake.
        # BFS distance is 3 (NORTH, NORTH, NORTH).
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"] * 4 + ["SpeedBoost"] * 4 + ["InstantStack"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[8, 2], [7, 2], [6, 2], [5, 2], [4, 2]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        
        # Since we are in killer mode, we should use the SpeedBoost to close the gap to the intercept target
        self.assertEqual(direction, "NORTH")
        self.assertEqual(activate, "SpeedBoost")
        
        # Reset state after test
        BotBrain.killer_mode_active = False

    def test_trapped_fallback_sword_activation(self):
        # All directions NORTH (5,4), EAST (6,5), WEST (4,5) are blocked by enemy heads.
        # This makes safe_moves completely empty.
        # We have a sword, so the fallback path should activate it.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                },
                "enemy1": {
                    "body": [[5, 4]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy2": {
                    "body": [[6, 5]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                },
                "enemy3": {
                    "body": [[4, 5]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        
        # We should choose one of the non-neck directions and activate the Sword
        self.assertIn(direction, ["NORTH", "EAST", "WEST"])
        self.assertEqual(activate, "Sword")

    def test_no_preemptive_instant_stack(self):
        # Head at (5, 5), body of length 5 trailing down y-axis.
        # Enemy at (7, 7) has a Sword but no boost.
        # Manhattan distance from (7, 7) to closest segment (5, 7) is 2.
        # Since enemy has no boost, they cannot cut us this tick.
        # We should NOT preemptively activate InstantStack.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6], [5, 7], [5, 8], [5, 9]],
                    "alive": True,
                    "inventory": ["InstantStack"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[7, 7], [8, 7]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        
        # We should move safely but NOT activate InstantStack
        self.assertIn(direction, ["NORTH", "WEST", "EAST"])
        self.assertIsNone(activate)

    def test_priority_swap_at_ten_swords(self):
        # We have 10 swords.
        # We should prioritize SpeedBoost (NORTH) over Sword (EAST).
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"] * 10,
                    "active_effects": []
                }
            },
            "items": [
                [[5, 3], "SpeedBoost"],
                [[7, 5], "Sword"]
            ]
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "NORTH")
        self.assertIsNone(activate)

    def test_killer_mode_dash_attack(self):
        # We have 10 swords and 8 speed boosts (Killer Mode active)
        BotBrain.killer_mode_active = True
        # Target at (5, 3) is distance 2 from head (5, 5).
        # We should use SpeedBoost to cut it immediately.
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"] * 10 + ["SpeedBoost"] * 8 + ["InstantStack"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[8, 3], [7, 3], [6, 3], [5, 3], [4, 3]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        self.assertEqual(direction, "NORTH")
        self.assertEqual(activate, "SpeedBoost")
        BotBrain.killer_mode_active = False

    def test_killer_mode_hunt_over_star(self):
        # In Killer Mode, we should prioritize distant hunt over collecting a Star.
        BotBrain.killer_mode_active = True
        # Head at (5, 5). Distant target at (5, 2) (distance 3).
        # Star is at (7, 5) (distance 2).
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword"] * 10 + ["SpeedBoost"] * 8 + ["InstantStack"],
                    "active_effects": []
                },
                "enemy": {
                    "body": [[8, 2], [7, 2], [6, 2], [5, 2], [4, 2]],
                    "alive": True,
                    "inventory": ["Sword"],
                    "active_effects": []
                }
            },
            "items": [
                [[7, 5], "Star"]
            ]
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        # Should go NORTH to hunt instead of EAST to collect star.
        self.assertEqual(direction, "NORTH")
        # Since we are in killer mode and hunting, we should also speedboost
        self.assertEqual(activate, "SpeedBoost")
        BotBrain.killer_mode_active = False

    def test_active_speed_boost_simulation(self):
        # We are already speed boosted.
        # Moving NORTH by 2 steps (direction=NORTH, action=None) lands on (5, 3).
        # At (5, 3) is an enemy body segment, so we should activate Sword on collision!
        BotBrain.killer_mode_active = True
        raw_field = {
            "size": [10, 10],
            "snakes": {
                "teamea": {
                    "body": [[5, 5], [5, 6]],
                    "alive": True,
                    "inventory": ["Sword", "SpeedBoost"],
                    "active_effects": [{"effect": "SpeedBoost", "remaining_ticks": 3}]
                },
                "enemy": {
                    "body": [[8, 3], [7, 3], [6, 3], [5, 3], [4, 3]],
                    "alive": True,
                    "inventory": [],
                    "active_effects": []
                }
            },
            "items": []
        }
        field = Field.from_dict(raw_field)
        direction, activate = BotBrain.get_next_move(field, "teamea")
        
        # We should go NORTH and activate the Sword
        self.assertEqual(direction, "NORTH")
        self.assertEqual(activate, "Sword")
        BotBrain.killer_mode_active = False

if __name__ == "__main__":
    unittest.main()

