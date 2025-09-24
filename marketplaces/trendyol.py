from typing import List, Optional
from core.interfaces import BaseMarketplace
from core.models import CategoryPath, Commission
from core.datasource import CSVDataSource

class TrendyolMarketplace(BaseMarketplace):
    code = "trendyol"
    def __init__(self, csv_path: str):
        mapping = {
            "category": "Kategori",
            "sub_category": "Alt Kategori",
            "product_group": "Ürün Grubu",
            "rate": "Komisyon_%_KDV_Dahil",
        }
        self.ds = CSVDataSource(csv_path, mapping)

    def list_categories(self) -> List[str]:
        return self.ds.uniques("category")

    def list_subcategories(self, category: str) -> List[str]:
        return self.ds.uniques("sub_category", category=category)

    def list_product_groups(self, category: str, sub_category: str) -> List[str]:
        return self.ds.uniques("product_group", category=category, sub_category=sub_category)

    def find_commission(self, path: CategoryPath) -> Optional[Commission]:
        row = self.ds.select_one(category=path.category, sub_category=path.sub_category, product_group=path.product_group)
        if not row or "rate" not in row:
            return None
        try:
            rate = float(row["rate"])
        except Exception:
            return None
        return Commission(rate_percent=rate, source="trendyol", note=None)
