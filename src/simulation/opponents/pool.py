"""opponents/pool.py — curated pool of ladder-faithful sparring opponents."""

import glob
from pathlib import Path

from src.simulation.opponents.archetypes import PlanSwappedOpponent
from src.simulation.opponents.ghosts import GhostOpponent


class OpponentPool:
    """Holds every opponent we can spar against, searchable by name."""

    def __init__(self, ghosts_dir: str | Path = "replays/LIVE/v18_all"):
        self.opponents: list = []
        # Archetypes first (always available, fully competent)
        for name in PlanSwappedOpponent.ARCHETYPES:
            self.opponents.append(PlanSwappedOpponent(name))
        # Ghosts from downloaded ladder replays (diverse, scripted openings)
        for path in sorted(glob.glob(f"{ghosts_dir}/*.json"))[:12]:
            try:
                self.opponents.append(GhostOpponent(path, player=1))
                self.opponents.append(GhostOpponent(path, player=0))
            except Exception:
                continue

    def __len__(self) -> int:
        return len(self.opponents)

    def __iter__(self):
        return iter(self.opponents)

    def sample(self, k: int = 1, seed: int | None = None) -> list:
        """Random sample without replacement (deterministic if seed given)."""
        import random
        rnd = random.Random(seed)
        return rnd.sample(self.opponents, k=min(k, len(self.opponents)))

    def by_name(self, name: str):
        for o in self.opponents:
            if name in o.name:
                return o
        raise KeyError(f"no opponent matching {name!r}")
