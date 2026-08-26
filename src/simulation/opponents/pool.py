"""opponents/pool.py — curated pool of ladder-faithful sparring opponents."""

import glob
from pathlib import Path

from src.simulation.opponents.archetypes import PlanSwappedOpponent
from src.simulation.opponents.ghosts import GhostOpponent


class OpponentPool:
    """Holds every opponent we can spar against, searchable by name.

    Two views:
      .opponents — everyone (for exploration)
      .strong()  — only archetypes + ghosts who BEAT us on the ladder
                   (the realistic pressure bench — 66% winrate, not 100%)
    """

    # Ghosts who beat us in their recorded episode — curated from 26-game analysis.
    STRONG_GHOST_IDS = {
        "99844808", "99856322", "99870107", "99947797",  # deep milk crashes where we lost
        "99847101", "99833364", "99821980",              # healthy-world execution losses
    }

    def __init__(self, ghosts_dir: str | Path = "replays/LIVE/v18_all"):
        self.opponents: list = []
        self._strong: list = []
        # Archetypes first (always available, fully competent) — all are strong
        for name in PlanSwappedOpponent.ARCHETYPES:
            opp = PlanSwappedOpponent(name)
            self.opponents.append(opp)
            self._strong.append(opp)
        # Ghosts: keep all, but tag strong ones separately
        for path in sorted(glob.glob(f"{ghosts_dir}/*.json")):
            ghost_id = Path(path).stem.split("-")[1] if "-" in Path(path).stem else ""
            try:
                for player in (0, 1):
                    g = GhostOpponent(path, player=player)
                    self.opponents.append(g)
                    if ghost_id in self.STRONG_GHOST_IDS:
                        self._strong.append(g)
            except Exception:
                continue

    def strong(self) -> list:
        """The ladder-faithful bench — use this for realistic evaluation.

        Excludes our own ghosts (M0h4m3d-Byte) which are just recordings of
        ourselves and collapse in foreign seeds.
        """
        return [o for o in self._strong if "m0h4m3d" not in o.name.lower()]

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
