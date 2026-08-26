"""opponents/base.py — semantic base for every sparring opponent."""

from abc import ABC, abstractmethod


class Opponent(ABC):
    """Anything that can act as player 1 in a simulated episode."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def __call__(self, obs: dict) -> dict:
        """Return a Kaggriculture action dict for the given observation."""
        ...
