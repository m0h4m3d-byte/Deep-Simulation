"""
actions.py - Build actions for the Kaggle environment
✅ UPDATED: Added animal and building actions
"""

from typing import Dict, Any, List, Optional
from src.constants import (
    PASS, DIG, FEED, CARE, COLLECT_FERTILIZER,
    BUILD_COOP, BUILD_PASTURE
)


class ActionBuilder:
    """
    Builds actions in the format expected by Kaggle environment.
    """
    
    @staticmethod
    def build(
        farmer_action: List[str],
        hand_actions: Optional[List[List[str]]] = None,
        market_actions: Optional[List[List]] = None
    ) -> Dict[str, Any]:
        """
        Build a complete action dictionary.
        
        Args:
            farmer_action: Main farmer action (e.g., ["PLANT", "WHEAT"])
            hand_actions: List of actions for hired hands
            market_actions: List of market orders
            
        Returns:
            Action dictionary for Kaggle environment
        """
        return {
            "farmer": farmer_action,
            "hands": hand_actions or [],
            "market": market_actions or []
        }
    
    @staticmethod
    def pass_action(market_actions: Optional[List] = None) -> Dict[str, Any]:
        return ActionBuilder.build([PASS], market_actions=market_actions)
    
    # --- Plant Actions ---
    @staticmethod
    def plant(crop: str, market_actions: Optional[List] = None) -> Dict[str, Any]:
        return ActionBuilder.build(["PLANT", crop], market_actions=market_actions)
    
    @staticmethod
    def water(market_actions: Optional[List] = None) -> Dict[str, Any]:
        return ActionBuilder.build(["WATER"], market_actions=market_actions)
    
    @staticmethod
    def harvest(market_actions: Optional[List] = None) -> Dict[str, Any]:
        return ActionBuilder.build(["HARVEST"], market_actions=market_actions)
    
    @staticmethod
    def fertilize(market_actions: Optional[List] = None) -> Dict[str, Any]:
        return ActionBuilder.build(["FERTILIZE"], market_actions=market_actions)
    
    @staticmethod
    def dig(market_actions: Optional[List] = None) -> Dict[str, Any]:
        return ActionBuilder.build([DIG], market_actions=market_actions)
    
    # --- Animal Actions (NEW) ---
    @staticmethod
    def feed(market_actions: Optional[List] = None) -> Dict[str, Any]:
        """Feed an animal (requires wheat in inventory)."""
        return ActionBuilder.build([FEED], market_actions=market_actions)
    
    @staticmethod
    def care(market_actions: Optional[List] = None) -> Dict[str, Any]:
        """Care for an animal (increases production bonus)."""
        return ActionBuilder.build([CARE], market_actions=market_actions)
    
    @staticmethod
    def collect_fertilizer(market_actions: Optional[List] = None) -> Dict[str, Any]:
        """Collect fertilizer from an animal."""
        return ActionBuilder.build([COLLECT_FERTILIZER], market_actions=market_actions)
    
    # --- Building Actions (NEW) ---
    @staticmethod
    def build_coop(market_actions: Optional[List] = None) -> Dict[str, Any]:
        """Build a coop for geese."""
        return ActionBuilder.build([BUILD_COOP], market_actions=market_actions)
    
    @staticmethod
    def build_pasture(market_actions: Optional[List] = None) -> Dict[str, Any]:
        """Build a pasture for cows or sheep."""
        return ActionBuilder.build([BUILD_PASTURE], market_actions=market_actions)
    
    # --- Movement ---
    @staticmethod
    def move(direction: str, market_actions: Optional[List] = None) -> Dict[str, Any]:
        return ActionBuilder.build([direction], market_actions=market_actions)