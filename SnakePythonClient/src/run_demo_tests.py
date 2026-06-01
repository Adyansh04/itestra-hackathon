import time
import sys
from api import SnakeFieldAPI

def print_snake_status(field, label):
    print(f"\n--- Snake Status: {label} ---")
    for name, snake in field.snakes.items():
        if name in ("teamea", "test"):
            print(f"Snake [{name}]: Alive={snake.alive}, Head={snake.head}, Inventory={snake.inventory}, ActiveEffects={[e.effect for e in snake.active_effects]}")

def run_double_activation():
    print("\n=== STARTING TEST: DOUBLE ACTIVATION ===")
    print("Pre-requisite: LevelTest_DoubleActivation must be running on the server.")
    
    api_a = SnakeFieldAPI("http://localhost:3030/", "teamea", "LevelTest_DoubleActivation", "test")
    api_b = SnakeFieldAPI("http://localhost:3030/", "test", "LevelTest_DoubleActivation", "test")
    
    # Tick 0: Register and check starting state
    api_a.set_direction("NORTH")
    api_b.set_direction("EAST")
    time.sleep(1.0)
    
    field = api_a.get_field()
    print_snake_status(field, "Tick 0 (Start)")
    
    print("\nTick 1: Sending SpeedBoost + Sword and moving NORTH for teamea...")
    try:
        api_a.activate_item("SpeedBoost")
        print("  - Sent activate SpeedBoost")
    except Exception as e:
        print(f"  - Failed to activate SpeedBoost: {e}")
        
    try:
        api_a.activate_item("Sword")
        print("  - Sent activate Sword")
    except Exception as e:
        print(f"  - Failed to activate Sword: {e}")
        
    api_a.set_direction("NORTH")
    api_b.set_direction("EAST")
    
    time.sleep(1.2) # Wait for tick to execute
    
    field = api_a.get_field()
    print_snake_status(field, "Tick 1 (After moves)")

def run_head_on(both_swords=True):
    mode = "BOTH_SWORDS" if both_swords else "ONE_SWORD"
    print(f"\n=== STARTING TEST: HEAD ON COLLISION ({mode}) ===")
    print("Pre-requisite: LevelTest_HeadOn must be running on the server.")
    
    api_a = SnakeFieldAPI("http://localhost:3030/", "teamea", "LevelTest_HeadOn", "test")
    api_b = SnakeFieldAPI("http://localhost:3030/", "test", "LevelTest_HeadOn", "test")
    
    # Tick 0: Register
    api_a.set_direction("NORTH")
    api_b.set_direction("SOUTH")
    time.sleep(1.0)
    
    field = api_a.get_field()
    print_snake_status(field, "Tick 0 (Start)")
    
    print(f"\nTick 1: Moving heads to meet at (5,4). both_swords={both_swords}...")
    
    # Snake A always activates sword and moves NORTH
    api_a.activate_item("Sword")
    api_a.set_direction("NORTH")
    
    # Snake B moves SOUTH, activates sword only if both_swords is True
    if both_swords:
        api_b.activate_item("Sword")
    api_b.set_direction("SOUTH")
    
    time.sleep(1.2)
    
    field = api_a.get_field()
    print_snake_status(field, "Tick 1 (After head-on collision)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_demo_tests.py [double | head_on_both | head_on_one]")
        sys.exit(1)
        
    scenario = sys.argv[1]
    if scenario == "double":
        run_double_activation()
    elif scenario == "head_on_both":
        run_head_on(both_swords=True)
    elif scenario == "head_on_one":
        run_head_on(both_swords=False)
    else:
        print(f"Unknown scenario: {scenario}")
