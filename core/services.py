from typing import Optional, List
from .models import CategoryPath, Commission
from .registry import MarketplaceRegistry

class CommissionService:
    def __init__(self, registry: MarketplaceRegistry):
        self._reg = registry

    def categories(self, code: str) -> List[str]:
        return self._reg.resolve(code).list_categories()

    def subcategories(self, code: str, category: str) -> List[str]:
        return self._reg.resolve(code).list_subcategories(category)

    def product_groups(self, code: str, category: str, sub_category: str) -> List[str]:
        return self._reg.resolve(code).list_product_groups(category, sub_category)

    def commission_of(self, code: str, path: CategoryPath) -> Optional[Commission]:
        return self._reg.resolve(code).find_commission(path)
