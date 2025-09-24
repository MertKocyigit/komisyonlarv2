#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTTAVM PDF → CSV çıkarıcı (pdfplumber, tablo tabanlı)

- PTTAVM komisyon PDF'lerindeki "KATEGORİ / ALT KATEGORİ / KOMİSYON" tablolarını okur.
- app.py'nin beklediği şemaya çevirir:
    Kategori | Alt Kategori | Ürün Grubu | Komisyon_%_KDV_Dahil
- Aynı Ürün Grubu için birden çok satır varsa EN YÜKSEK komisyonu bırakır.
- Çıktılar: lines dump (debug), raw birleşik ve app.csv

Kullanım (doğrudan):
  py -3 scripts/pttavm_extract_commissions.py --pdf "C:\...\pttavmkomisyon.pdf" --out-app-csv "C:\...\data\pttavm_commissions.csv" --backup

Kullanım (wrapper ile):
  py -3 update\pttavm_update.py --pdf ... --out-csv ... --backup --log INFO
"""

from pathlib import Path
from typing import List, Tuple, Optional, Dict
import re, os, shutil, unicodedata
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1] if (Path(__file__).parent.name == "scripts") else Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
TMP_DIR  = DATA_DIR / "tmp"
BK_DIR   = DATA_DIR / "backup"
TMP_DIR.mkdir(parents=True, exist_ok=True)
BK_DIR.mkdir(parents=True, exist_ok=True)

# -------------- helpers --------------
def _norm(s: Optional[str]) -> str:
    if s is None: return ""
    s = str(s).replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _tr_simplify(s: Optional[str]) -> str:
    """Türkçe karakterleri sadeleştir + birleşik noktaları temizle + lower."""
    if s is None: return ""
    s = str(s).translate(str.maketrans("ğĞüÜşŞıİöÖçÇ", "gGuUsSiIoOcC"))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _pct_to_float(x: Optional[str]) -> Optional[float]:
    """'12', '12,5', '12.5%' gibi değerleri float(0-100) yap."""
    if x is None: return None
    s = str(x).strip().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None

def _looks_like_header(row: List[str]) -> bool:
    j = " ".join(_tr_simplify(c) for c in row)
    return ("kategori" in j) and ("komisyon" in j)

# -------------- pdf → tables --------------
def _pdf_tables(pdf_path: str) -> List[pd.DataFrame]:
    try:
        import pdfplumber  # type: ignore
    except Exception as e:
        raise RuntimeError(f"pdfplumber gerekli: {e}")

    out: List[pd.DataFrame] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for settings in (
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
                {"vertical_strategy": "text",  "horizontal_strategy": "text"},
            ):
                try:
                    tables = page.extract_tables(table_settings=settings) or []
                    for t in tables:
                        df = pd.DataFrame(t)
                        if df.shape[0] >= 2 and df.shape[1] >= 3:
                            out.append(df)
                except Exception:
                    pass
    return out

# -------------- normalize one table --------------
def _normalize_one(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    # header satırını bul
    header_idx = None
    for i in range(min(5, len(df))):
        row = [str(x) for x in df.iloc[i].tolist()]
        if _looks_like_header(row):
            header_idx = i
            break
    if header_idx is None:
        # bazen ilk satır header gibidir
        row0 = [str(x) for x in df.iloc[0].tolist()]
        if _looks_like_header(row0):
            header_idx = 0
    if header_idx is None:
        return None

    header = [_norm(c) for c in df.iloc[header_idx].tolist()]
    body   = df.iloc[header_idx+1:].reset_index(drop=True).copy()
    body.columns = [
        header[j] if (j < len(header) and header[j] not in (None, "")) else f"c{j}"
        for j in range(body.shape[1])
    ]

    # kolon eşle
    col_kat = None; col_sub = None; col_kom = None
    for c in body.columns:
        lo = _tr_simplify(c)
        if col_kom is None and "komisyon" in lo:
            col_kom = c
        if col_sub is None and ("alt kategori" in lo or ("alt" in lo and "kategori" in lo)):
            col_sub = c
        if col_kat is None and "kategori" in lo and "alt" not in lo:
            col_kat = c

    # emniyet: alt kategori yoksa 2. sütunu varsay, komisyon yoksa son sütun
    if col_kat is None: col_kat = body.columns[0]
    if col_sub is None: col_sub = body.columns[1] if body.shape[1] >= 2 else col_kat
    if col_kom is None: col_kom = body.columns[-1]

    out = pd.DataFrame({
        "Kategori":      body[col_kat].map(_norm),
        "Alt Kategori":  body[col_sub].map(_norm),
        "Komisyon":      body[col_kom].map(_norm),
    })

    # gürültü satırlarını ele
    mask_bad = out["Kategori"].str.contains(r"www\.|Komisyon Oranlar", case=False, regex=True) | \
               out["Alt Kategori"].str.contains(r"www\.|Komisyon Oranlar", case=False, regex=True)
    out = out[~mask_bad]

    # boşları at
    out = out[(out["Kategori"]!="") | (out["Alt Kategori"]!="") | (out["Komisyon"]!="")]
    if out.empty: return None
    return out.reset_index(drop=True)

# -------------- all tables → raw df --------------
def _combine_to_raw(tables: List[pd.DataFrame]) -> pd.DataFrame:
    parts: List[pd.DataFrame] = []
    for t in tables:
        n = _normalize_one(t)
        if n is not None and not n.empty:
            parts.append(n)
    if not parts:
        return pd.DataFrame(columns=["Kategori","Alt Kategori","Komisyon"])
    raw = pd.concat(parts, ignore_index=True)

    # Komisyon'u sayıya çevir
    raw["Komisyon"] = raw["Komisyon"].apply(_pct_to_float)
    raw = raw[raw["Komisyon"].notna()].copy()
    raw["Alt Kategori"] = raw["Alt Kategori"].fillna("")
    return raw.drop_duplicates().reset_index(drop=True)

# -------------- app schema --------------
def _to_app_df(raw: pd.DataFrame) -> pd.DataFrame:
    # Ürün Grubu = Alt Kategori varsa o, yoksa Kategori
    pg = raw["Alt Kategori"].where(raw["Alt Kategori"].str.strip()!="", raw["Kategori"])
    app_df = pd.DataFrame({
        "Kategori": raw["Kategori"].astype(str).str.strip(),
        "Alt Kategori": raw["Alt Kategori"].astype(str).str.strip(),
        "Ürün Grubu": pg.astype(str).str.strip(),
        "Komisyon_%_KDV_Dahil": pd.to_numeric(raw["Komisyon"], errors="coerce")
    })
    app_df = app_df[app_df["Komisyon_%_KDV_Dahil"].notna()]
    app_df = app_df[app_df["Ürün Grubu"]!=""]

    # Aynı Ürün Grubu'nda MAX komisyonu bırak
    if not app_df.empty:
        idx = app_df.groupby("Ürün Grubu")["Komisyon_%_KDV_Dahil"].idxmax()
        app_df = app_df.loc[idx].sort_values("Ürün Grubu").reset_index(drop=True)
    return app_df

# -------------- public API (wrapper uyumlu) --------------
def run(pdf_path: str,
        out_lines_csv: Path,
        out_raw_csv: Path,
        out_app_csv: Path,
        backup: bool = False) -> dict:
    # 1) tabloları çıkar
    tables = _pdf_tables(pdf_path)

    # 2) debug lines dump
    lines_dump: List[Tuple[int,str]] = []
    for ti, t in enumerate(tables):
        for ri in range(len(t)):
            rowtxt = " | ".join([_norm(x) for x in t.iloc[ri].tolist()])
            lines_dump.append((ti, rowtxt))
    out_lines_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(lines_dump, columns=["table_index","row_text"]).to_csv(out_lines_csv, index=False, encoding="utf-8-sig")

    # 3) raw birleşik
    raw = _combine_to_raw(tables)
    out_raw_csv.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(out_raw_csv, index=False, encoding="utf-8-sig")

    # 4) app şeması
    app_df = _to_app_df(raw)

    # yedek
    if backup and out_app_csv.exists():
        bk = BK_DIR / "pttavm_commissions_backup.csv"
        try: shutil.copy2(out_app_csv, bk)
        except Exception: pass

    out_app_csv.parent.mkdir(parents=True, exist_ok=True)
    app_df.to_csv(out_app_csv, index=False, encoding="utf-8-sig")

    return {
        "tables": len(tables),
        "raw_rows": int(raw.shape[0]),
        "app_rows": int(app_df.shape[0]),
        "lines_csv": str(out_lines_csv),
        "raw_csv": str(out_raw_csv),
        "app_csv": str(out_app_csv),
    }

# -------------- CLI --------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="PTTAVM PDF → CSV (tablo tabanlı)")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--out-lines-csv", default=str(TMP_DIR / "pttavm_lines.csv"))
    ap.add_argument("--out-raw-csv",   default=str(TMP_DIR / "pttavm_raw.csv"))
    ap.add_argument("--out-app-csv",   default=str(DATA_DIR / "pttavm_commissions.csv"))
    args = ap.parse_args()

    info = run(args.pdf, Path(args.out_lines_csv), Path(args.out_raw_csv), Path(args.out_app_csv), backup=args.backup)
    print(pd.Series(info).to_string())
