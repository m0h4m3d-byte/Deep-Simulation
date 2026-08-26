"""brain/strategies/spatial.py — أين نزرع (تكلفة الحركة)."""

from src.brain.interface import BrainStrategy


class SpatialStrategy(BrainStrategy):
    @property
    def name(self) -> str:
        return "spatial"

    def choose(self, obs: dict, sim) -> dict | None:
        # v1: محايد — الهيكل جاهز، المنطق المكاني يُضاف هنا لاحقاً
        # دون لمس أي ملف آخر. يحسب: مسافة البلاطة × محصول مقترح → تكلفة.
        return None
