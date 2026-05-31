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
        # Since NORTH is an alive enemy head, we CANNOT cut it with a sword.
        # Even if we are forced to go NORTH, we must not activate the sword.
        self.assertEqual(direction, "NORTH")
        self.assertIsNone(activate)

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

if __name__ == "__main__":
    unittest.main()

