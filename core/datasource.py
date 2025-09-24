import pandas as pd
from typing import Dict, Optional

class CSVDataSource:
    def __init__(self, csv_path: str, mapping: Dict[str, str]):
        self.csv_path = csv_path
        self.mapping = mapping
        self._df: Optional[pd.DataFrame] = None

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            df = pd.read_csv(self.csv_path)
            rename_map = {v: k for k, v in self.mapping.items() if v in df.columns}
            df = df.rename(columns=rename_map)
            for col in ("category", "sub_category", "product_group"):
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip().str.lower()
            if "rate" in df.columns:
                df["rate"] = (df["rate"].astype(str)
                                         .str.replace("%","", regex=False)
                                         .str.replace(",",".", regex=False))
                # Convert non-numeric safely
                try:
                    df["rate"] = df["rate"].astype(float)
                except Exception:
                    pass
            self._df = df
        return self._df

    def uniques(self, col: str, **filters) -> list[str]:
        sel = self._filter(**filters)
        if col not in sel.columns:
            return []
        vals = sel[col].dropna().unique().tolist()
        vals = [v for v in vals if isinstance(v, str) and v]
        return sorted(vals)

    def select_one(self, **filters) -> Optional[dict]:
        sel = self._filter(**filters)
        if sel.empty:
            return None
        return sel.iloc[0].to_dict()

    def _filter(self, **filters) -> pd.DataFrame:
        df = self.df
        for k, v in filters.items():
            if v is None or k not in df.columns:
                continue
            df = df[df[k] == str(v).strip().lower()]
        return df
