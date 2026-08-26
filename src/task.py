"""
task.py - Task definitions for the agent's action planning
✅ UPDATED: Added animal and building tasks
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Task:
    """
    A task represents an action the agent plans to perform.
    """
    action: str  # "PLANT", "WATER", "HARVEST", "FERTILIZE", "DIG", 
                 # "MOVE", "PASS", "FEED", "CARE", "COLLECT_FERTILIZER",
                 # "BUILD_COOP", "BUILD_PASTURE"
    crop: Optional[str] = None
    target: Optional[Tuple[int, int]] = None
    
    def __repr__(self) -> str:
        if self.crop:
            return f"Task({self.action}, {self.crop})"
        if self.target:
            return f"Task({self.action}, {self.target})"
        return f"Task({self.action})"


class TaskBuilder:
    """Helper for creating common tasks."""
    
    # --- Plant Tasks ---
    @staticmethod
    def plant(crop: str) -> Task:
        return Task("PLANT", crop=crop)
    
    @staticmethod
    def water() -> Task:
        return Task("WATER")
    
    @staticmethod
    def harvest() -> Task:
        return Task("HARVEST")
    
    @staticmethod
    def fertilize() -> Task:
        return Task("FERTILIZE")
    
    @staticmethod
    def dig() -> Task:
        return Task("DIG")
    
    # --- Animal Tasks (NEW) ---
    @staticmethod
    def feed() -> Task:
        """Feed an animal (requires wheat in inventory)."""
        return Task("FEED")
    
    @staticmethod
    def care() -> Task:
        """Care for an animal (increases production bonus)."""
        return Task("CARE")
    
    @staticmethod
    def collect_fertilizer() -> Task:
        """Collect fertilizer from an animal."""
        return Task("COLLECT_FERTILIZER")
    
    # --- Building Tasks (NEW) ---
    @staticmethod
    def build_coop() -> Task:
        """Build a coop for geese."""
        return Task("BUILD_COOP")
    
    @staticmethod
    def build_pasture() -> Task:
        """Build a pasture for cows or sheep."""
        return Task("BUILD_PASTURE")
    
    # --- Movement ---
    @staticmethod
    def move_to(x: int, y: int) -> Task:
        return Task("MOVE", target=(x, y))
    
    @staticmethod
    def pass_action() -> Task:
        return Task("PASS")