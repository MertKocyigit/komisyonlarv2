from typing import Callable, Dict
from .interfaces import BaseMarketplace

class MarketplaceRegistry:
    def __init__(self):
        self._factories: Dict[str, Callable[[], BaseMarketplace]] = {}

    def register(self, code: str, factory: Callable[[], BaseMarketplace]) -> None:
        self._factories[code] = factory

    def resolve(self, code: str) -> BaseMarketplace:
        if code not in self._factories:
            raise ValueError(f"Unknown marketplace: {code}")
        return self._factories[code]()
