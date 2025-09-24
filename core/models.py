from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal, TypedDict

MarketplaceCode = Literal["trendyol", "hepsiburada"]

@dataclass(frozen=True)
class CategoryPath:
    category: str
    sub_category: Optional[str] = None
    product_group: Optional[str] = None

    def normalized(self) -> "CategoryPath":
        def _n(x: Optional[str]) -> Optional[str]:
            return None if x is None else str(x).strip().lower()
        return CategoryPath(
            category=_n(self.category) or "",
            sub_category=_n(self.sub_category),
            product_group=_n(self.product_group),
        )

@dataclass(frozen=True)
class Commission:
    rate_percent: float
    vat_included: bool = True
    source: Optional[MarketplaceCode] = None
    note: Optional[str] = None

    def as_ratio(self) -> float:
        return self.rate_percent / 100.0

class MarketplaceColumns(TypedDict, total=True):
    category: str
    sub_category: str
    product_group: str
    commission: str
