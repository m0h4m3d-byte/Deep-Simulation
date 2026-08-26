"""brain/interface.py — عقد واحد لكل استراتيجية مستقبلية."""

from abc import ABC, abstractmethod


class BrainStrategy(ABC):
    """أي فكرة جديدة تطبق هذه الواجهة — لا حاجة للمس أي ملف آخر."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def choose(self, obs: dict, sim) -> dict | None:
        """ترجع تعديلاً على القرار أو None لترك القرار للاستراتيجية التالية."""
        ...
