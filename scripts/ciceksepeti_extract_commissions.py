#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÇiçekSepeti PDF → CSV çıkarıcı (metin tabanlı)
- Sizin verdiğiniz iki scriptin (parse_row/split_categories mantığı) birleştirilmiş ve
  update wrapper'ınızla uyumlu hale getirilmiş sürümü.
- Poppler/pdftotext opsiyonel; pdfplumber ile metin çıkarımı yapılır.
- Çıktılar:
    1) out_lines_csv: data/tmp/ciceksepeti_lines.csv (page, raw_line)
    2) out_raw_csv  : data/tmp/ciceksepeti_raw.csv   (Ana Kategori, Kategori, Komisyon Oranı, Revize Komisyon Oranı, Azami..., Revize Azami...)
    3) out_app_csv  : data/ciceksepeti_commissions.csv (Kategori, Alt Kategori, Ürün Grubu, Komisyon_%_KDV_Dahil)
"""

import re
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Dict

import pandas as pd

# Proje dizinleri (DATA_DIR otomatik)
BASE_DIR = Path(__file__).resolve().parents[1] if (Path(__file__).parent.name == "scripts") else Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
TMP_DIR  = DATA_DIR / "tmp"
BK_DIR   = DATA_DIR / "backup"
TMP_DIR.mkdir(parents=True, exist_ok=True)
BK_DIR.mkdir(parents=True, exist_ok=True)

# ------------------ Yardımcılar ------------------
def _norm(s: Optional[str]) -> str:
    if s is None:
        return ""
    s = str(s).replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _pct_to_float(x: Optional[str]) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None

# ------------------ PDF → Metin -------------------
def extract_text_lines(pdf_path: str) -> List[Tuple[int, str]]:
    """
    pdfplumber ile sayfa sayfa düz metin alır, satır listesi döndürür.
    """
    try:
        import pdfplumber  # type: ignore
    except Exception as e:
        raise RuntimeError(f"pdfplumber gerekiyor: {e}")

    lines: List[Tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            for raw in txt.splitlines():
                line = _norm(raw)
                if line:
                    lines.append((page.page_number, line))
    return lines

# --------------- Satır Ayrıştırma -----------------
ANA_PATTERNS = [
    "2. El, Yenilenmiş", "Anne & Bebek", "Elektronik", "Ev & Yaşam",
    "Evcil Hayvan Ürünleri", "Hobi", "Moda", "Oto Aksesuar", "Oyuncak",
    "Parfüm & Kişisel Bakım", "Spor&Outdoor", "Süpermarket",
    "Yapı Market, Hırdavat & Bahçe"
]

HEADER_TOKENS = {
    "ana kategori", "kategori", "komisyon orani", "komisyon oranı",
    "revize komisyon orani", "revize komisyon oranı",
    "azami ödeme süresi", "revize azami ödeme süresi"
}

def split_categories(text: str) -> Tuple[str, str]:
    """
    Kategori metnini Ana Kategori ve Ürün Grubu olarak böler.
    Önce bilinen pattern'lere bakar; yoksa ilk kelimeyi Ana varsayar.
    """
    t = _norm(text)
    for pat in ANA_PATTERNS:
        if t.startswith(pat):
            ana = pat
            kategori = t[len(pat):].strip()
            return ana, kategori
    parts = t.split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return t, ""

def parse_row(line: str) -> Optional[List[str]]:
    """
    Tek bir veriye karşılık geliyorsa satırı parse eder:
    [Ana Kategori, Kategori, Komisyon Oranı, Revize Komisyon Oranı, Azami Ödeme Süresi, Revize Azami Ödeme Süresi]
    """
    if "%" not in line:
        return None

    # Başlık satırlarını ele
    low = line.lower()
    if any(tok in low for tok in HEADER_TOKENS):
        return None

    parts = line.split()
    if len(parts) < 3:
        return None

    rev_azami = ""
    azami = ""
    rev_komisyon = ""
    komisyon = ""

    idx = len(parts) - 1

    # Revize Azami: "Değişiklik Yok" olabilir
    if idx >= 1 and parts[idx] == "Yok" and parts[idx-1] == "Değişiklik":
        rev_azami = "Değişiklik Yok"
        idx -= 2
    elif idx >= 0 and re.fullmatch(r"\d+", parts[idx]):
        # sonda sayı → azami (veya rev_azami)
        azami = parts[idx]
        idx -= 1

    if not azami and idx >= 0 and re.fullmatch(r"\d+", parts[idx]):
        azami = parts[idx]
        idx -= 1

    # Revize komisyon (varsa)
    if idx >= 0 and re.fullmatch(r"\d+%?", parts[idx]):
        rev_komisyon = parts[idx]
        idx -= 1

    # Komisyon
    if idx >= 0 and re.fullmatch(r"\d+%?", parts[idx]):
        komisyon = parts[idx]
        idx -= 1

    if not komisyon and not rev_komisyon:
        return None

    # Kalan parça: "Ana + Kategori"
    name_chunk = " ".join(parts[: idx + 1]).strip()
    ana, kategori = split_categories(name_chunk)
    return [ana, kategori, komisyon, rev_komisyon, azami, "" if rev_azami == "Değişiklik Yok" else rev_azami]

# --------------- Parse + Temizlik -----------------
def parse_lines_to_raw_df(lines: List[Tuple[int, str]]) -> pd.DataFrame:
    rows: List[List[str]] = []
    for _, line in lines:
        r = parse_row(line)
        if r:
            rows.append(r)
    if not rows:
        return pd.DataFrame(columns=[
            "Ana Kategori","Kategori","Komisyon Oranı","Revize Komisyon Oranı",
            "Azami Ödeme Süresi","Revize Azami Ödeme Süresi"
        ])
    df = pd.DataFrame(rows, columns=[
        "Ana Kategori","Kategori","Komisyon Oranı","Revize Komisyon Oranı",
        "Azami Ödeme Süresi","Revize Azami Ödeme Süresi"
    ])
    # Temizlik
    for c in df.columns:
        df[c] = df[c].map(_norm)

    # Yüzdeleri sayısal stringe indir
    for col in ["Komisyon Oranı", "Revize Komisyon Oranı"]:
        df[col] = df[col].str.replace("%", "", regex=False).str.strip()

    # Azami'ler
    df["Azami Ödeme Süresi"] = pd.to_numeric(df["Azami Ödeme Süresi"], errors="coerce")
    df.loc[df["Revize Azami Ödeme Süresi"].str.lower() == "değişiklik yok", "Revize Azami Ödeme Süresi"] = ""
    df["Revize Azami Ödeme Süresi"] = pd.to_numeric(df["Revize Azami Ödeme Süresi"], errors="coerce")

    df = df[(df["Kategori"] != "")]
    df = df.drop_duplicates().reset_index(drop=True)
    return df

def to_app_csv_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    App şeması:
      Kategori         = Ana Kategori
      Alt Kategori     = ""
      Ürün Grubu       = Kategori
      Komisyon_%_KDV_Dahil = Revize Komisyon Oranı (varsa), yoksa Komisyon Oranı
    + Aynı Ürün Grubu için EN YÜKSEK komisyon
    """
    if df.empty:
        return pd.DataFrame(columns=["Kategori","Alt Kategori","Ürün Grubu","Komisyon_%_KDV_Dahil"])

    app_df = pd.DataFrame({
        "Kategori": df["Ana Kategori"].astype(str).str.strip(),
        "Alt Kategori": "",
        "Ürün Grubu": df["Kategori"].astype(str).str.strip(),
    })

    def choose(row):
        rv = _pct_to_float(row["Revize Komisyon Oranı"])
        if rv is not None: return rv
        return _pct_to_float(row["Komisyon Oranı"])

    app_df["Komisyon_%_KDV_Dahil"] = df.apply(choose, axis=1)
    app_df = app_df[app_df["Ürün Grubu"] != ""]
    app_df = app_df[app_df["Komisyon_%_KDV_Dahil"].notna()]

    # Aynı Ürün Grubu için max komisyon
    if not app_df.empty:
        idx = app_df.groupby("Ürün Grubu")["Komisyon_%_KDV_Dahil"].idxmax()
        app_df = app_df.loc[idx].sort_values("Ürün Grubu").reset_index(drop=True)
    return app_df

# --------------- Public API (wrapper uyumlu) ---------------
def run(pdf_path: str,
        out_lines_csv: Path,
        out_raw_csv: Path,
        out_app_csv: Path,
        backup: bool = False) -> Dict[str, object]:
    """
    update\ciceksepeti_update.py'nin çağırdığı fonksiyon imzası.
    """
    lines = extract_text_lines(pdf_path)

    # 1) debug satır dökümü
    out_lines_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(lines, columns=["page","raw_line"]).to_csv(out_lines_csv, index=False, encoding="utf-8-sig")

    # 2) raw df
    raw_df = parse_lines_to_raw_df(lines)
    out_raw_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_df.to_csv(out_raw_csv, index=False, encoding="utf-8-sig")

    # 3) app df (+ backup)
    app_df = to_app_csv_df(raw_df)

    if backup and out_app_csv.exists():
        bk = BK_DIR / f"ciceksepeti_commissions_backup.csv"
        try:
            shutil.copy2(out_app_csv, bk)
        except Exception:
            pass

    out_app_csv.parent.mkdir(parents=True, exist_ok=True)
    app_df.to_csv(out_app_csv, index=False, encoding="utf-8-sig")

    return {
        "lines": len(lines),
        "raw_rows": int(raw_df.shape[0]),
        "app_rows": int(app_df.shape[0]),
        "lines_csv": str(out_lines_csv),
        "raw_csv": str(out_raw_csv),
        "app_csv": str(out_app_csv),
    }

# --------------- CLI (opsiyonel tek başına kullanım) ---------------
if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser(description="ÇiçekSepeti PDF → CSV (metin tabanlı)")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--out-lines-csv", default=str(TMP_DIR / "ciceksepeti_lines.csv"))
    ap.add_argument("--out-raw-csv",   default=str(TMP_DIR / "ciceksepeti_raw.csv"))
    ap.add_argument("--out-app-csv",   default=str(DATA_DIR / "ciceksepeti_commissions.csv"))
    args = ap.parse_args()

    try:
        info = run(args.pdf, Path(args.out_lines_csv), Path(args.out_raw_csv), Path(args.out_app_csv), backup=args.backup)
        print(pd.Series(info).to_string())
        sys.exit(0)
    except Exception as e:
        print(f"HATA: {e}")
        sys.exit(1)
