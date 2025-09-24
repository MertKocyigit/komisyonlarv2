# -*- coding: utf-8 -*-
"""
N11 Komisyon Extractor (Excel/PDF) — Tam “örnek cümle” kuralına göre
--------------------------------------------------------------------
Çıktı kolonları (app.py ile uyumlu):
  - Kategori
  - Alt Kategori
  - Ürün Grubu
  - komisyon                 (metin, ör. "16%")
  - Komisyon_%_KDV_Dahil     (float, ör. 16.0)

Kural (yalnız N11 için):
- Kategori           = ilk maddenin ilk kelimesi
- Alt Kategori       = ilk virgülden (",") sonraki ilk kelime (yoksa Kategori)
- Komisyon_%         = ilk "+" işaretinden sonra gelen ilk SAF SAYI (içinde "%" olmayacak)
- Ürün Grubu         = ilk "+"tan sonra, ilk sayıya kadar olan ifade
                       (tekrarlar temizlenir: "Kara Avı Kara Avı..." → "Kara Avı")

Notlar:
- Komisyon metninde "%" bulunuyorsa o değer ASLA alınmaz (yalnız saf sayı kabul).
- Çok kolonlu satır geldiyse satır birleştirilip tek çizgi gibi ayrıştırılır.
- CSV yazımı atomik yapılır (tmp→replace).

Kullanım:
  python scripts/n11_extract_commissions.py --excel "...\n11_from_pdf.xlsx" --out-csv "...\n11_commissions.csv" --sheet "Processed_Data" --log INFO
  # veya PDF:
  python scripts/n11_extract_commissions.py --pdf   "...\n11.pdf"          --out-csv "...\n11_commissions.csv" --log INFO
"""

import os, re, sys, json, argparse, logging
from typing import Dict, List, Optional
import pandas as pd

try:
    import pdfplumber
except Exception:
    pdfplumber = None

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("n11_extractor")

# ---------- yardımcılar ----------
WORD_RE  = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]+")
NUM_ONLY = re.compile(r"^\d+(?:[.,]\d+)?$")  # yüzde işareti YOK

def _clean(s: Optional[str]) -> str:
    if s is None: return ""
    s = str(s).replace("\xa0"," ")
    return re.sub(r"\s+"," ", s).strip()

def _join_row_to_line(row_vals: List[str]) -> str:
    # Çok kolonlu satırları tek satır metne çevir (virgülle birleştir)
    vals = [_clean(v) for v in row_vals if _clean(v)]
    return ", ".join(vals)

def _format_tr_pct(x: Optional[float]) -> str:
    if x is None: return ""
    s = f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{s}%"

def _first_word(text: str) -> str:
    m = WORD_RE.search(text)
    return m.group(0) if m else ""

def _first_word_after_comma(text: str) -> str:
    if "," not in text:
        return ""
    after = text.split(",", 1)[1]
    return _first_word(after)

def _first_plus_index(text: str) -> int:
    try:
        return text.index("+")
    except ValueError:
        return -1

def _first_pure_number(s: str) -> Optional[str]:
    """
    s içinde geçen ilk 'saf sayı' (içinde % olmayacak).
    """
    # Token taraması (kelime/sayı/% ayrımı)
    for tok in re.findall(r"[0-9]+(?:[.,][0-9]+)?|%|[A-Za-zÇĞİÖŞÜçğıöşü&]+", s):
        t = tok.strip()
        if not t:
            continue
        if "%" in t:
            continue  # yüzde geçen hiçbir aday kabul edilmez
        if NUM_ONLY.fullmatch(t):
            return t
    # Ek güvenlik: doğrudan regex (yine %'süz)
    m = re.search(r"(?<!%)\b(\d+(?:[.,]\d+)?)\b", s)
    if m:
        return m.group(1)
    return None

def _to_float(num_txt: Optional[str]) -> Optional[float]:
    if not num_txt: return None
    try:
        return float(num_txt.replace(",", "."))
    except Exception:
        return None

def _collapse_repeated_bigrams(phrase: str) -> str:
    """
    'Kara Avı Kara Avı Kara Avı' -> 'Kara Avı'
    basit bigram tekrarı bastırma
    """
    toks = phrase.split()
    if len(toks) < 4:
        return phrase.strip()
    res: List[str] = []
    i = 0
    while i < len(toks):
        if i+1 < len(toks) and len(res) >= 2 and toks[i] == res[-2] and toks[i+1] == res[-1]:
            # aynı bigram tekrar ediyorsa atla
            i += 2
            continue
        res.append(toks[i])
        i += 1
    return " ".join(res).strip()

def _parse_line_by_explicit_rules(line: str) -> Optional[Dict[str, Optional[str]]]:
    """
    Tam istenen kurala göre tek bir satırı ayrıştır.
    - Kategori  : ilk kelime
    - Alt Kat.  : ilk virgülden sonraki ilk kelime (yoksa Kategori)
    - Komisyon  : '+' sonrası ilk SAF sayı (%'süz)
    - Ürün Grubu: '+' sonrası, ilk sayıya kadar olan ifade (tekrarlar temizlenir)
    """
    s = _clean(line)
    if not s:
        return None

    # 1) kategori
    category = _first_word(s)

    # 2) alt kategori
    sub_category = _first_word_after_comma(s) or category  # yoksa kategori

    # 3) '+' sonrası parça
    plus_idx = _first_plus_index(s)
    product = ""
    commission_val: Optional[float] = None

    if plus_idx >= 0:
        after_plus = s[plus_idx+1:].strip()

        # 3a) komisyon (ilk saf sayı)
        num_txt = _first_pure_number(after_plus)
        commission_val = _to_float(num_txt)

        # 3b) ürün grubu: '+' ile ilk sayı arasındaki metin
        if num_txt:
            num_match = re.search(re.escape(num_txt), after_plus)
            product_raw = after_plus[:num_match.start()].strip() if num_match else after_plus
        else:
            product_raw = after_plus  # sayı yoksa tüm after_plus

        # gürültü temizliği
        product_raw = re.sub(r"\b(KDV|kdv)\b", "", product_raw)
        product_raw = re.sub(r"\s+", " ", product_raw).strip()

        # tekrarları bastır
        product = _collapse_repeated_bigrams(product_raw).strip(" &").strip()

    # Fallback'ler
    if not product:
        product = ""  # boş bırak

    if not (category or sub_category or product or commission_val is not None):
        return None

    return {
        "Kategori": category,
        "Alt Kategori": sub_category,
        "Ürün Grubu": product if product else (sub_category or category),
        "Komisyon_%_KDV_Dahil": commission_val
    }

def _lines_from_df(df: pd.DataFrame) -> List[str]:
    cols = list(df.columns)
    if "Ham_Veri" in cols:
        return df["Ham_Veri"].astype(str).tolist()
    if len(cols) == 1:
        return df.iloc[:,0].astype(str).tolist()
    return df.apply(lambda r: _join_row_to_line(r.tolist()), axis=1).tolist()

def _explode_products(df: pd.DataFrame) -> pd.DataFrame:
    col = "Ürün Grubu"
    parts = df[col].astype(str).str.split(r"\s*[;,\|\n\r]\s*", regex=True)
    out = df.drop(columns=[col]).join(parts.explode().rename(col))
    out[col] = out[col].astype(str).str.replace(r"\s+"," ", regex=True).str.strip()
    out = out[out[col] != ""]
    return out

# ---------- loader'lar ----------
def _promote_header_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.dropna(how="all").dropna(axis=1, how="all")
    try:
        df = df.map(lambda x: "" if x is None else str(x))
    except Exception:
        df = df.applymap(lambda x: "" if x is None else str(x))
    return df.dropna(how="all").dropna(axis=1, how="all")

def _load_pdf(path: str) -> pd.DataFrame:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber eksik. pip install pdfplumber")
    rows: List[List[str]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = []
            for settings in (
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
                {"vertical_strategy": "text", "horizontal_strategy": "text"},
                {"vertical_strategy": "lines", "horizontal_strategy": "text"},
                {},
            ):
                try:
                    t = page.extract_tables(table_settings=settings) or []
                except Exception:
                    t = []
                if t:
                    tables = t
                    break
            for tbl in tables:
                for raw in tbl:
                    if not raw:
                        continue
                    rows.append([(c or "").strip() for c in raw])
    if not rows:
        raise RuntimeError("PDF'den tablo okunamadı.")
    w = max(len(r) for r in rows)
    rows = [r + [""]*(w-len(r)) for r in rows]
    return _promote_header_df(pd.DataFrame(rows))

def _load_excel(path: str, sheet: Optional[str]) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    target = sheet or ("Processed_Data" if "Processed_Data" in xls.sheet_names else xls.sheet_names[0])
    df = pd.read_excel(xls, sheet_name=target, engine="openpyxl")
    return _promote_header_df(df)

# ---------- çekirdek ----------
def n11_to_csv_from_df(df: pd.DataFrame, out_csv: str) -> Dict:
    lines = _lines_from_df(df)

    out_rows: List[Dict[str, Optional[str]]] = []
    for line in lines:
        parsed = _parse_line_by_explicit_rules(line)
        if parsed:
            out_rows.append(parsed)

    out = pd.DataFrame(out_rows)
    if out.empty:
        # yine de kolonları yazalım
        out = pd.DataFrame(columns=["Kategori","Alt Kategori","Ürün Grubu","komisyon","Komisyon_%_KDV_Dahil"])
    else:
        # komisyon metni (ör. "16%")
        out["komisyon"] = out["Komisyon_%_KDV_Dahil"].map(_format_tr_pct)

        # Ürün grubu boşsa doldur
        mask_pg = out["Ürün Grubu"].astype(str).str.strip() == ""
        out.loc[mask_pg, "Ürün Grubu"] = out.loc[mask_pg, "Alt Kategori"].where(
            out["Alt Kategori"].astype(str).str.strip() != "", out["Kategori"]
        )

        # Çoklu ürünleri ayır
        out = _explode_products(out)

        # Kolon sırası
        out = out[["Kategori","Alt Kategori","Ürün Grubu","komisyon","Komisyon_%_KDV_Dahil"]]

    # atomik yazım
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    tmp = out_csv + ".tmp"
    out.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, out_csv)

    log.info("Çıktı satırı: %s", len(out))
    return {"rows_out": int(out.shape[0]), "csv_path": out_csv}

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="N11 Excel/PDF → normalize komisyon CSV (tam örnek kuralı).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pdf", help="Girdi PDF")
    g.add_argument("--excel", help="Girdi Excel (Processed_Data)")
    ap.add_argument("--out-csv", required=True, help="Çıkış CSV")
    ap.add_argument("--sheet", default=None, help="Excel sayfa adı (vars: Processed_Data)")
    ap.add_argument("--log", default="INFO", choices=["CRITICAL","ERROR","WARNING","INFO","DEBUG"])
    args = ap.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log, logging.INFO))
    try:
        if args.pdf:
            log.info("PDF okunuyor: %s", args.pdf)
            df = _load_pdf(args.pdf)
        else:
            log.info("Excel okunuyor: %s", args.excel)
            df = _load_excel(args.excel, args.sheet)

        log.info("Girdi tablo: %s satır, %s sütun", df.shape[0], df.shape[1])
        res = n11_to_csv_from_df(df, args.out_csv)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    except Exception as e:
        log.exception("İşleme hatası:")
        print(f"Hata: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
