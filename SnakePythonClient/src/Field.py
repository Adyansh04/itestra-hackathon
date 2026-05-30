from dataclasses import dataclass
from typing import Dict, List, Tuple

from data_structures import Coord, TeamName


@dataclass
class ActiveEffectInfo:
    effect: str
    remaining_ticks: int


@dataclass
class SnakeInfo:
    body: List[Coord]
    alive: bool
    inventory: List[str]
    active_effects: List[ActiveEffectInfo]


def fill_info_from_source(source) -> [SnakeInfo]:
    snakes = {
        team: SnakeInfo(
            body=[tuple(coord) for coord in info["body"]],
            alive=info["alive"],
            inventory=list(info["inventory"]),
            active_effects=[
                ActiveEffectInfo(
                    effect=effect["effect"],
                    remaining_ticks=effect["remaining_ticks"],
                )
                for effect in info["active_effects"]
            ],
        )
        for team, info in source.items()
    }
    return snakes


@dataclass
class Field:
    size: Tuple[int, int]
    snakes: Dict[TeamName, SnakeInfo]

    @staticmethod
    def from_dict(raw: dict) -> "Field":
        size = tuple(raw["size"])
        snakes = ""
        if "snake" in raw:
            source = raw["snake"]
            snakes = fill_info_from_source(source)
        elif "snakes" in raw:
            source = raw["snakes"]
            snakes = fill_info_from_source(source)

        return Field(size=size, snakes=snakes)
