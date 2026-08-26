"""opponents/__init__.py — re-exports."""

from src.simulation.opponents.archetypes import PlanSwappedOpponent
from src.simulation.opponents.base import Opponent
from src.simulation.opponents.ghosts import GhostOpponent
from src.simulation.opponents.pool import OpponentPool

__all__ = ["Opponent", "GhostOpponent", "PlanSwappedOpponent", "OpponentPool"]
