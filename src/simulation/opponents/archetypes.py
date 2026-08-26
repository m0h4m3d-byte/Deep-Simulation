"""opponents/archetypes.py — plan-swapped archetype opponents."""

from src.simulation.opponents.base import Opponent


class PlanSwappedOpponent(Opponent):
    """Wraps our production Agent but runs under a different PLAN.

    This reproduces the *strategy* of a ladder archetype that beat us
    (e.g. kshitiz's strawberry-heavy field) while staying fully competent
    — unlike ghosts, it never goes off-script when the board diverges.
    """

    # Archetypes distilled from the 14-game live analysis that beat v18.
    ARCHETYPES: dict[str, dict] = {
        "kshitiz":  {"COW": 4,  "SHEEP": 6, "GOOSE": 0, "WHEAT": 20,
                     "STRAWBERRY": 60, "MELON": 12},
        "aibaba":   {"COW": 5,  "SHEEP": 3, "GOOSE": 2, "WHEAT": 200,
                     "STRAWBERRY": 10, "MELON": 8},
        "dairy":    {"COW": 15, "SHEEP": 3, "GOOSE": 0, "WHEAT": 140,
                     "STRAWBERRY": 45, "MELON": 12},
        "balanced": {"COW": 13, "SHEEP": 5, "GOOSE": 0, "WHEAT": 30,
                     "STRAWBERRY": 45, "MELON": 12},
    }

    def __init__(self, archetype: str = "kshitiz"):
        if archetype not in self.ARCHETYPES:
            raise ValueError(f"unknown archetype {archetype!r}; choose from {list(self.ARCHETYPES)}")
        self.archetype = archetype
        self._overrides = self.ARCHETYPES[archetype]
        self._name = f"arch:{archetype}"
        self._inner = None  # lazy Agent instance

    @property
    def name(self) -> str:
        return self._name

    def _get_inner(self):
        if self._inner is None:
            from main import Agent
            self._inner = Agent()
        return self._inner

    def __call__(self, obs: dict) -> dict:
        import src.economy as E
        saved = dict(E.PLAN)
        E.PLAN.update(self._overrides)
        try:
            return self._get_inner()(obs)
        finally:
            E.PLAN.clear()
            E.PLAN.update(saved)
