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

if __name__ == "__main__":
    unittest.main()
