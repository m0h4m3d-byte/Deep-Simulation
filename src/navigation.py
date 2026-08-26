"""
navigation.py - Navigation utilities for finding targets and directions
✅ UPDATED: Added find_nearest_animal()
"""

from typing import Optional, Tuple
from src.gamestate import GameState, Position
from src.constants import EAST, WEST, NORTH, SOUTH


def find_nearest_empty(state: GameState) -> Optional[Position]:
    """
    Find the nearest empty tile to the farmer's current position.
    
    Args:
        state: Current game state
        
    Returns:
        (x, y) of nearest empty tile, or None if not found
    """
    fx, fy = state.farmer_pos
    
    for radius in range(1, 8):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if abs(dx) != radius and abs(dy) != radius:
                    continue
                x, y = fx + dx, fy + dy
                if state.is_inside_bounds(x, y):
                    tile = state.get_tile(x, y)
                    if tile and tile.is_empty:
                        return (x, y)
    return None


def find_nearest_weed(state: GameState) -> Optional[Position]:
    """Find the nearest weed tile."""
    fx, fy = state.farmer_pos
    best = None
    best_dist = float('inf')
    
    for y, row in enumerate(state.tiles):
        for x, tile in enumerate(row):
            if tile.is_weed:
                dist = abs(x - fx) + abs(y - fy)
                if dist < best_dist:
                    best_dist = dist
                    best = (x, y)
    return best


def find_nearest_plant_with_yield(state: GameState) -> Optional[Position]:
    """Find the nearest plant with yield_units > 0."""
    fx, fy = state.farmer_pos
    best = None
    best_dist = float('inf')
    
    for x, y, tile in state.iter_plants():
        if tile.yield_units > 0:
            dist = abs(x - fx) + abs(y - fy)
            if dist < best_dist:
                best_dist = dist
                best = (x, y)
    return best


def find_nearest_animal(state: GameState) -> Optional[Position]:
    """
    ✅ NEW: Find the nearest animal that needs attention.
    Priority: unfed > uncared > has yield > has fertilizer
    """
    fx, fy = state.farmer_pos
    best = None
    best_score = -999
    
    for y, row in enumerate(state.tiles):
        for x, tile in enumerate(row):
            if tile.is_animal:
                # Calculate priority score
                score = 0
                if not tile.fed_today:
                    score += 100  # Highest priority - prevent escape
                if not tile.cared_today:
                    score += 50
                if tile.yield_units > 0:
                    score += 25
                if tile.fertilizer_available:
                    score += 10
                
                # Distance penalty
                dist = abs(x - fx) + abs(y - fy)
                score -= dist * 2
                
                if score > best_score:
                    best_score = score
                    best = (x, y)
    
    return best


def get_direction(fx: int, fy: int, tx: int, ty: int) -> Optional[str]:
    """
    Get the direction from (fx, fy) to (tx, ty).
    
    Args:
        fx, fy: Current position
        tx, ty: Target position
        
    Returns:
        Direction string (EAST, WEST, NORTH, SOUTH) or None
    """
    if fx == tx and fy == ty:
        return None
    
    dx, dy = tx - fx, ty - fy
    
    if abs(dx) >= abs(dy):
        return EAST if dx > 0 else WEST
    return SOUTH if dy > 0 else NORTH