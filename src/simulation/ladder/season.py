"""ladder/season.py — full ladder season simulation.

Runs N episodes where every episode shares the market between two competent
farmers (us vs a sampled opponent). Ratings evolve with Elo, matchmaking
stays near our current rating — exactly like Kaggle's ladder.

    from src.simulation.ladder.season import LadderSeason
    LadderSeason(agent_factory=lambda: Agent(), episodes=20).run()
"""

import random

from src.simulation.ladder.matchmaking import pick_opponent
from src.simulation.ladder.rating import EloRating
from src.simulation.opponents.pool import OpponentPool


class LadderSeason:
    def __init__(
        self,
        agent_factory,
        episodes: int = 20,
        pool: OpponentPool | None = None,
        seed: int = 0,
        opponent_name: str = "us",
        strong_only: bool = True,
    ):
        self.agent_factory = agent_factory
        self.episodes = episodes
        _pool = pool or OpponentPool()
        # Default to the STRONG bench — the full pool is 100% winrate and meaningless.
        self.pool = _pool.strong() if strong_only else list(_pool)
        self.seed = seed
        self.opponent_name = opponent_name
        self.ratings = EloRating()
        self.history: list[dict] = []

    def run(self, verbose: bool = True) -> dict:
        from src.simulator import Simulator

        rnd = random.Random(self.seed)
        our_name = "ours"
        for ep in range(self.episodes):
            opp = pick_opponent(self.ratings.get(our_name), self.pool, self.ratings)
            seed = rnd.randrange(2**31)
            # Fresh agent per episode (state reset matters)
            ours = self.agent_factory()
            sim = Simulator(seed=seed)
            # opp is stateful (ghost index); wrap to be safe
            res = sim.run([ours, opp])
            mine, theirs = res["money"]
            if mine > theirs:
                self.ratings.update(our_name, opp.name)
                result = "W"
            elif mine < theirs:
                self.ratings.update(opp.name, our_name)
                result = "L"
            else:
                self.ratings.update_tie(our_name, opp.name)
                result = "T"
            rec = {
                "episode": ep,
                "seed": seed,
                "opponent": opp.name,
                "ours": mine,
                "theirs": theirs,
                "result": result,
                "rating": self.ratings.get(our_name),
            }
            self.history.append(rec)
            if verbose:
                print(f"ep{ep:02d} {result} vs {opp.name:<22} "
                      f"${mine:,.0f}:${theirs:,.0f}  rating {rec['rating']:.0f}")
        final = self.ratings.get(our_name)
        wins = sum(1 for r in self.history if r["result"] == "W")
        print(f"\nseason {wins}/{self.episodes}  final rating {final:.0f}")
        return {"rating": final, "wins": wins, "history": self.history}
