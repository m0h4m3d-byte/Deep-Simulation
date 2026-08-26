"""brain/registry.py — سجل الاستراتيجيات، إضافة = سطر واحد."""

from src.brain.interface import BrainStrategy


class BrainRegistry:
    def __init__(self):
        self._strategies: list[BrainStrategy] = []

    def register(self, strategy: BrainStrategy):
        self._strategies.append(strategy)
        return strategy

    def all(self) -> list[BrainStrategy]:
        return list(self._strategies)


REGISTRY = BrainRegistry()
