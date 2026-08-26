"""opponents/ghosts.py — replay ghosts as semantic opponents."""

import json
from pathlib import Path

from src.simulation.opponents.base import Opponent


class GhostOpponent(Opponent):
    """Replays one side of a recorded ladder episode verbatim."""

    def __init__(self, replay_path: str | Path, player: int = 1):
        replay = json.loads(Path(replay_path).read_text(encoding="utf-8"))
        self.replay_path = str(replay_path)
        self.player = player
        self._name = Path(replay_path).stem.replace("episode-", "")[:8]
        # Resolve display name from TeamNames if available
        names = (replay.get("info") or {}).get("TeamNames") or []
        if len(names) > player:
            self._name = str(names[player])[:20]
        self.actions = [
            step[player].get("action") or {"farmer": ["PASS"], "hands": [], "market": []}
            for step in replay["steps"]
        ]

    @property
    def name(self) -> str:
        return f"ghost:{self._name}"

    def __call__(self, obs: dict) -> dict:
        s = obs.get("step", 0)
        if s < len(self.actions):
            return self.actions[s]
        return {"farmer": ["PASS"], "hands": [], "market": []}
