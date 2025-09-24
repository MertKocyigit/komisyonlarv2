from abc import ABC, abstractmethod
from typing import List, Optional
from .models import CategoryPath, Commission

class BaseMarketplace(ABC):
    code: str

    @abstractmethod
    def list_categories(self) -> List[str]: ...
    @abstractmethod
    def list_subcategories(self, category: str) -> List[str]: ...
    @abstractmethod
    def list_product_groups(self, category: str, sub_category: str) -> List[str]: ...
    @abstractmethod
    def find_commission(self, path: CategoryPath) -> Optional[Commission]: ...
