# -*- coding: utf-8 -*-
"""
Trendyol Komisyon Extractor (PDF veya Excel)
--------------------------------------------
Çıktı:
  ["Ana Kategori","Kategori","Ürün Grubu","Komisyon_%_KDV_Dahil"]
  (+ bilgi amaçlı "komisyon","vade")

Kullanım:
  python scripts/trendyol_extract_commissions.py --pdf   "C:\path\Trendyol.pdf"   --out-csv ".\data\commissions_flat.csv"
  python scripts/trendyol_extract_commissions.py --excel "C:\path\from_pdf.xlsx" --out-csv ".\data\commissions_flat.csv"
"""

import os, re, sys, json, argparse, logging
from typing import Dict, List, Optional
import pandas as pd

try:
    import pdfplumber
except Exception:
    pdfplumber = None

# ---------- yardımcılar ----------
def _normalize_header(s: str) -> str:
    if s is None: return ""
    s = str(s).lower().replace("\xa0"," ")
    s = re.sub(r"\s+"," ", s).strip()
    s = s.replace("("," ").replace(")"," ")
    s = re.sub(r"[\/\-\_\|\:\;\,]+"," ", s)
    return re.sub(r"\s+"," ", s).strip()

def _split_outside_parens(text: str) -> List[str]:
    if text is None: return []
    s = str(text).replace("\xa0", " ").strip()
    if not s or s.lower()=="nan": return []
    items, buf, depth = [], [], 0
    opens, closes = "([{", ")]}"
    delims = {",",";","|","\n","\r"}
    for ch in s:
        if ch in opens: depth += 1; buf.append(ch)
        elif ch in closes: depth = max(0, depth-1); buf.append(ch)
        elif ch in delims and depth==0:
            t = "".join(buf).strip()
            if t: items.append(" ".join(t.split()))
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail: items.append(" ".join(tail.split()))
    return [x for x in items if x and x.lower()!="nan"]

def _parse_percent_to_float(val: Optional[str]) -> Optional[float]:
    if val is None: return None
    s = str(val).strip().replace("%"," ").replace(",",".")
    m = re.search(r"(-?\d+(?:\.\d+)?)", s)
    try: return float(m.group(1)) if m else None
    except: return None

def _format_percent_tr(x: Optional[float]) -> str:
    if x is None: return ""
    s = f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{s}%"

# ---------- başlık terfisi / tekrar temizliği ----------
def _promote_trendyol_header(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    if df is None or df.empty: return df
    df = df.copy()
    df.columns = [str(c) if c is not None else "" for c in df.columns]
    df = df.applymap(lambda x: "" if x is None else str(x))

    # "Kolon No" satırları
    drop = []
    for i in range(min(10, len(df))):
        txt = " ".join(df.iloc[i].tolist()).lower()
        if "kolon" in txt and "no" in txt:
            drop.append(i)
    if drop:
        logger.debug(f"'Kolon No' drop: {drop}")
        df = df.drop(index=drop).reset_index(drop=True)

    # başlık satırını yakala
    targets = ["kategori","alt","ürün","vade","komisyon"]
    hdr_idx = None
    for i in range(min(20, len(df))):
        row = [v.strip().lower() for v in df.iloc[i].tolist()]
        score = sum(any(t in v for v in row) for t in targets)
        if score >= 3:
            hdr_idx = i; break
    if hdr_idx is None:
        logger.debug("Başlık satırı bulunamadı.")
        return df

    new_cols = [" ".join(str(v).replace("\n"," ").split()) for v in df.iloc[hdr_idx].tolist()]
    df = df.iloc[hdr_idx+1:].reset_index(drop=True)
    df.columns = new_cols
    return df.dropna(how="all").dropna(axis=1, how="all")

CANDIDATES = {
    "ana_kategori": ["ana kategori","ana kat","kategori üst","ana","main category","kategori (üst)"],
    "kategori":     ["kategori","alt kategori","kategori adı","kategori ismi","kategori (alt)"],
    "urun_grubu":   ["ürün grubu","urun grubu detayı","ürün alt grubu","ürün grubu / detay","ürün detay","urun grubu"],
    "komisyon":     ["komisyon","komisyon %","kategori komisyon %","kategori komisyon % (kdv dahil)","komisyon oranı","komisyon (%)"],
    "vade":         ["vade","vade (iş günü)","ödeme vadesi","ödeme süresi","vade süresi"],
}

def _guess_column_mapping(df: pd.DataFrame, logger: logging.Logger) -> Dict[str,str]:
    cols = list(df.columns)
    norm_map = {_normalize_header(c): c for c in cols}
    mapping: Dict[str,str] = {}
    for key, cand_list in CANDIDATES.items():
        found = None
        for cand in cand_list:
            nc = _normalize_header(cand)
            if nc in norm_map:
                found = norm_map[nc]; break
            for nk, orig in norm_map.items():
                if nc in nk: found = orig; break
            if found: break
        if found: mapping[key] = found
        else: logger.warning(f"Sütun bulunamadı: {key} (aranan: {cand_list})")
    for req in ["urun_grubu","komisyon"]:
        if req not in mapping:
            raise RuntimeError(f"Gerekli sütun bulunamadı: {req}. Mevcut: {cols}")
    return mapping

def _drop_repeated_headers(df: pd.DataFrame, mapping: Dict[str,str]) -> pd.DataFrame:
    df = df.copy()
    def _norm(x: str) -> str: return _normalize_header(x or "")
    pg, km = mapping.get("urun_grubu"), mapping.get("komisyon")
    mask = pd.Series(False, index=df.index)
    if pg in df.columns: mask |= df[pg].astype(str).map(lambda x: "urun grubu" in _norm(x))
    if km in df.columns: mask |= df[km].astype(str).map(lambda x: "komisyon" in _norm(x))
    return df[~mask].reset_index(drop=True)

def _explode_product_groups(df: pd.DataFrame, product_col: str, logger: logging.Logger) -> pd.DataFrame:
    base = df.dropna(subset=[product_col]).copy()
    if base.empty:
        logger.warning("Ürün grubu sütunu boş."); return base
    base[product_col] = base[product_col].astype(str)
    base = base[(base[product_col].str.strip()!="") & (base[product_col].str.lower()!="nan")]
    exploded = base.drop(columns=[product_col]).join(
        base[product_col].apply(_split_outside_parens).explode().rename(product_col)
    )
    exploded[product_col] = (exploded[product_col].astype(str)
                             .str.replace(r"\s+"," ",regex=True).str.strip())
    return exploded[(exploded[product_col]!="") & (exploded[product_col].str.lower()!="nan")]

# ---------- yükleyiciler ----------
def _load_excel(path: str, sheet: Optional[str], logger: logging.Logger) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    target = sheet or ("Data" if "Data" in xls.sheet_names else xls.sheet_names[0])
    df = pd.read_excel(xls, sheet_name=target, engine="openpyxl", dtype=str)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [re.sub(r"\s+"," ",str(c).replace("\xa0"," ")).strip() for c in df.columns]
    df = _promote_trendyol_header(df, logger)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [re.sub(r"\s+"," ",str(c).replace("\xa0"," ")).strip() for c in df.columns]
    return df

def _load_pdf(path: str, logger: logging.Logger) -> pd.DataFrame:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber eksik. Kurulum: pip install pdfplumber")
    rows: List[List[str]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = []
            for settings in ({},
                             {"vertical_strategy":"lines","horizontal_strategy":"lines"},
                             {"vertical_strategy":"text","horizontal_strategy":"text"},
                             {"vertical_strategy":"lines","horizontal_strategy":"text"}):
                try:
                    t = page.extract_tables(table_settings=settings) or []
                except Exception:
                    t = []
                if t: tables = t; break
            for tbl in tables:
                for raw in tbl:
                    if not raw: continue
                    cells = [(c or "").strip() for c in raw]
                    rows.append(cells)
    if not rows:
        raise RuntimeError("PDF'den tablo okunamadı.")
    w = max(len(r) for r in rows)
    rows = [r + [""]*(w-len(r)) for r in rows]
    df = pd.DataFrame(rows)
    df = _promote_trendyol_header(df, logger)
    return df

# ---------- çekirdek ----------
def trendyol_to_csv_from_df(df: pd.DataFrame, out_csv: str, logger: logging.Logger) -> Dict:
    mapping = _guess_column_mapping(df, logger)
    df = _drop_repeated_headers(df, mapping)
    for _, col in mapping.items():
        df[col] = df[col].astype(str).str.replace("\xa0"," ").str.replace(r"\s+"," ",regex=True).str.strip()
    df = _explode_product_groups(df, mapping["urun_grubu"], logger)

    col_ana = mapping.get("ana_kategori")
    col_kat = mapping.get("kategori")
    col_urun = mapping["urun_grubu"]
    col_kom = mapping["komisyon"]
    col_vade = mapping.get("vade")

    kom_num = df[col_kom].apply(_parse_percent_to_float)
    out = pd.DataFrame({
        "Ana Kategori": df[col_ana] if col_ana else "",
        "Kategori": df[col_kat] if col_kat else "",
        "Ürün Grubu": df[col_urun],
        "komisyon": df[col_kom],
        "vade": df[col_vade] if col_vade else "",
        "Komisyon_%_KDV_Dahil": kom_num
    })

    # tekilleştir
    before = len(out)
    out = out.drop_duplicates(subset=["Ana Kategori","Kategori","Ürün Grubu","komisyon","vade"]).reset_index(drop=True)
    logger.info(f"Tekilleştirme: {before} -> {len(out)}")

    # komisyon metnini doldur
    need_fill = (out["komisyon"].astype(str).str.strip()=="") & out["Komisyon_%_KDV_Dahil"].notna()
    out.loc[need_fill, "komisyon"] = out.loc[need_fill,"Komisyon_%_KDV_Dahil"].apply(_format_percent_tr)

    # ölçek: 0..1 yoğunsa %'ye çevir
    if out["Komisyon_%_KDV_Dahil"].notna().sum() and (out["Komisyon_%_KDV_Dahil"].quantile(0.95) <= 1.0):
        out["Komisyon_%_KDV_Dahil"] = out["Komisyon_%_KDV_Dahil"] * 100.0

    # atomik yazım
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    tmp = out_csv + ".tmp"
    out.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, out_csv)

    return {
        "rows_out": int(out.shape[0]),
        "csv_path": out_csv,
        "columns_mapped": mapping,
    }

# ---------- CLI ----------
def main():
    p = argparse.ArgumentParser(description="Trendyol PDF/Excel'den normalize komisyon CSV üretir (atomik yazım).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pdf", help="Girdi PDF yolu")
    g.add_argument("--excel", help="Girdi Excel (PDF->Excel sonrası)")
    p.add_argument("--out-csv", required=True, help="Çıkış CSV yolu")
    p.add_argument("--sheet", default=None, help="Excel sayfa adı (vars: 'Data' varsa o)")
    p.add_argument("--log", default="INFO", choices=["CRITICAL","ERROR","WARNING","INFO","DEBUG"])
    args = p.parse_args()

    logging.basicConfig(level=getattr(logging, args.log, logging.INFO),
                        format="%(levelname)s:%(name)s:%(message)s")
    lg = logging.getLogger("trendyol_extractor")

    try:
        if args.pdf:
            if pdfplumber is None:
                raise RuntimeError("pdfplumber eksik. Kurulum: pip install pdfplumber")
            lg.info(f"PDF okunuyor: {args.pdf}")
            df = _load_pdf(args.pdf, lg)
        else:
            lg.info(f"Excel okunuyor: {args.excel}")
            df = _load_excel(args.excel, args.sheet, lg)

        lg.info(f"Tablo: {df.shape[0]} satır, {df.shape[1]} sütun")
        res = trendyol_to_csv_from_df(df, args.out_csv, lg)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    except Exception as e:
        lg.exception("İşleme hatası:")
        print(f"❌ Hata: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
