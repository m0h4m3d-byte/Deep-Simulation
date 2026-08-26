"""
gamestate.py - Parse raw observation into structured state
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from src.constants import (
    DEFAULT_BOARD_SIZE, TILE_EMPTY, TILE_LOCKED, TILE_PLANT,
    TILE_WEED, TILE_COOP, TILE_PASTURE
)


Position = Tuple[int, int]


@dataclass
class Tile:
    """Represents a single tile on the farm."""
    x: int
    y: int
    kind: str
    crop: Optional[str] = None
    planted_day: int = -1
    yield_units: int = 0
    watered_today: bool = False
    consecutive_unwatered: int = 0
    fertilized_until_day: int = -1
    max_lifespan_step: int = -1
    animal: Optional[str] = None
    placed_day: int = -1
    fed_today: bool = False
    consecutive_unfed: int = 0
    cared_today: bool = False
    fertilizer_available: bool = False
    pending_care_bonus: int = 0
    
    @property
    def is_empty(self) -> bool:
        return self.kind == TILE_EMPTY
    
    @property
    def is_plant(self) -> bool:
        return self.kind == TILE_PLANT
    
    @property
    def is_locked(self) -> bool:
        return self.kind == TILE_LOCKED
    
    @property
    def is_weed(self) -> bool:
        return self.kind == TILE_WEED
    
    @property
    def is_coop(self) -> bool:
        return self.kind == TILE_COOP
    
    @property
    def is_pasture(self) -> bool:
        return self.kind == TILE_PASTURE
    
    @property
    def is_structure(self) -> bool:
        return self.kind in (TILE_COOP, TILE_PASTURE)
    
    @property
    def is_animal(self) -> bool:
        return self.is_structure and self.animal is not None
    
    @property
    def is_occupied(self) -> bool:
        return self.is_plant or self.is_animal or self.is_weed or self.is_structure
    
    @property
    def is_fertilized(self) -> bool:
        return self.fertilized_until_day >= 0


@dataclass
class GameState:
    """
    Structured representation of the game state.
    Parsed from the raw observation.
    """
    player: int
    day: int
    hour: int
    step: int
    money: float
    farmer_pos: Position
    tiles: List[List[Tile]]
    seeds: Dict[str, int]
    shed: Dict[str, int]
    prices: Dict[str, int]
    unlocked_quadrants: List[str]
    hires_today: int
    
    @classmethod
    def from_obs(cls, obs: Dict[str, Any], step: int) -> "GameState":
        """
        Parse raw observation into GameState.
        
        Args:
            obs: Raw observation from Kaggle environment
            step: Current step number
            
        Returns:
            GameState instance
        """
        player = obs.get("player", 0)
        day = obs.get("day", 0)
        hour = obs.get("hour", 0)
        
        farms = obs.get("farms", [{}, {}])
        private = obs.get("private", {})
        market = obs.get("market", {})
        
        me = farms[player]
        tiles_raw = me.get("tiles", [])
        tiles = cls._parse_tiles(tiles_raw)
        
        return cls(
            player=player,
            day=day,
            hour=hour,
            step=step,
            money=me.get("money", 0),
            farmer_pos=tuple(me.get("farmer", [4, 4])),
            tiles=tiles,
            seeds=private.get("seeds", {}),
            shed=private.get("shed", {}),
            prices=market.get("prices", {}),
            unlocked_quadrants=me.get("unlocked_quadrants", []),
            hires_today=me.get("hires_today", 0),
        )
    
    @staticmethod
    def _parse_tiles(tiles_raw: List[List[Any]]) -> List[List[Tile]]:
        """Parse raw tile data into Tile objects."""
        result = []
        for y, row in enumerate(tiles_raw):
            tile_row = []
            for x, data in enumerate(row):
                if data is None:
                    tile_row.append(Tile(x=x, y=y, kind=TILE_EMPTY))
                elif data == TILE_LOCKED:
                    tile_row.append(Tile(x=x, y=y, kind=TILE_LOCKED))
                elif isinstance(data, dict):
                    kind = data.get("kind", "")
                    if kind == TILE_WEED:
                        tile_row.append(Tile(x=x, y=y, kind=TILE_WEED))
                    elif kind == TILE_PLANT:
                        tile_row.append(Tile(
                            x=x, y=y, kind=TILE_PLANT,
                            crop=data.get("crop"),
                            planted_day=data.get("planted_day", 0),
                            yield_units=data.get("yield_units", 0),
                            watered_today=data.get("watered_today", False),
                            consecutive_unwatered=data.get("consecutive_unwatered", 0),
                            fertilized_until_day=data.get("fertilized_until_day", -1),
                            max_lifespan_step=data.get("max_lifespan_step", -1),
                        ))
                    elif kind in (TILE_COOP, TILE_PASTURE):
                        tile_row.append(Tile(
                            x=x, y=y, kind=kind,
                            animal=data.get("animal"),
                            placed_day=data.get("placed_day", 0),
                            yield_units=data.get("yield_units", 0),
                            fed_today=data.get("fed_today", False),
                            consecutive_unfed=data.get("consecutive_unfed", 0),
                            cared_today=data.get("cared_today", False),
                            fertilizer_available=data.get("fertilizer_available", False),
                            pending_care_bonus=data.get("pending_care_bonus", 0),
                        ))
                    else:
                        tile_row.append(Tile(x=x, y=y, kind=TILE_EMPTY))
                else:
                    tile_row.append(Tile(x=x, y=y, kind=TILE_EMPTY))
            result.append(tile_row)
        return result
    
    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        """Get tile at position (x, y)."""
        if 0 <= y < len(self.tiles) and 0 <= x < len(self.tiles[0]):
            return self.tiles[y][x]
        return None
    
    def get_current_tile(self) -> Optional[Tile]:
        """Get tile at farmer's current position."""
        x, y = self.farmer_pos
        return self.get_tile(x, y)
    
    @property
    def farmer_x(self) -> int:
        return self.farmer_pos[0]
    
    @property
    def farmer_y(self) -> int:
        return self.farmer_pos[1]
    
    @property
    def width(self) -> int:
        return len(self.tiles[0]) if self.tiles else 0
    
    @property
    def height(self) -> int:
        return len(self.tiles)
    
    def is_inside_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height
    
    def iter_plants(self):
        """Iterate over all plant tiles."""
        for y, row in enumerate(self.tiles):
            for x, tile in enumerate(row):
                if tile.is_plant:
                    yield x, y, tile
    
    def iter_tiles(self):
        """Iterate over all tiles."""
        for y, row in enumerate(self.tiles):
            for x, tile in enumerate(row):
                yield x, y, tile
    
    def get_plant_count(self) -> int:
        """Get number of plants on the farm."""
        return sum(1 for _, _, _ in self.iter_plants())