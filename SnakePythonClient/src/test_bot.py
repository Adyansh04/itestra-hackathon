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

    def test_flood_fill(self):
        size = (5, 5)
        # Empty board
        self.assertEqual(BotBrain._flood_fill((2, 2), set(), size), 25)
        
        # Board with a wall blocking the middle column completely
        obstacles = {(2, 0), (2, 1), (2, 2), (2, 3), (2, 4)}
        # Flood fill from left side should only reach left side (2 * 5 = 10 squares)
        # Wait, if size is 5x5, columns are 0, 1, 2, 3, 4. 
        # Column 2 is obstacles. Remaining are 0, 1 (left) and 3, 4 (right). 
        # Since board wraps around horizontally, column 0 and 4 are adjacent!
        # So it's still fully connected!
        self.assertEqual(BotBrain._flood_fill((0, 0), obstacles, size), 20)

        # Make a box around (0,0) with wrapping
        # 0,0 is adjacent to 1,0 and 4,0 and 0,1 and 0,4
        obstacles2 = {(1, 0), (4, 0), (0, 1), (0, 4)}
        self.assertEqual(BotBrain._flood_fill((0, 0), obstacles2, size), 1)

if __name__ == "__main__":
    unittest.main()
