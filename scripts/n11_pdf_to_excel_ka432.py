# -*- coding: utf-8 -*-
r"""
N11 PDF -> Excel (Processed_Data) — "ilk 5 sütunu al" basit dönüştürücü
-----------------------------------------------------------------------
- Her satırda soldan sağa *ilk 5 hücreyi* alır.
- Çıktı sayfası: Processed_Data
  Kolon adları:
    Kategori Ağacı 4, Kategori Ağacı 3, Kategori Ağacı 2, Kategori Ağacı 1,
    Komisyon Oranları (%) (KDV Dahildir)

- Varsayılan olarak *bariz başlık* satırlarını (Kategori/Komisyon/KDV vb.) atlar.
  İstersen başlık filtresini kapatmak için:  --keep-headers

Kullanım (PowerShell):
  python scripts/n11_pdf_to_excel_ka432.py `
    --pdf "C:\Users\CASPER\Downloads\n11_Komisyon_Oranlari-2025.pdf" `
    --out "C:\Users\CASPER\OneDrive\Desktop\proje_structured\data\n11_from_pdf.xlsx" `
    --log INFO
"""

import os, re, argparse, logging
from typing import List, Optional
import pandas as pd

try:
    import pdfplumber
except Exception:
    pdfplumber = None

log = logging.getLogger("n11_pdf2xlsx")

# -------- helpers --------
HDR_KEYWORDS = re.compile(r"(kategori|ağacı|agaci|komisyon|oran|kdv|kampanya|hakedi|bedeli)", re.I)

def _clean(x: Optional[str]) -> str:
    if x is None:
        return ""
    s = str(x).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()

def _extract_tables(page) -> List[List[List[str]]]:
    """Sayfadaki tabloları mümkün olan en iyi ayarlarla çek."""
    tables = []
    for st in (
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text",  "horizontal_strategy": "text"},
        {"vertical_strategy": "lines", "horizontal_strategy": "text"},
        {},  # varsayılan
    ):
        try:
            t = page.extract_tables(table_settings=st) or []
        except Exception:
            t = []
        if t:
            tables = t
            break

    # satırları normalize et (hücre temizliği + pad)
    rows: List[List[str]] = []
    for tbl in tables:
        if not tbl:
            continue
        width = max(len(r) for r in tbl if r)
        for r in tbl:
            r = [(c or "") for c in r]
            if len(r) < width:
                r = r + [""] * (width - len(r))
            rows.append([_clean(c) for c in r])
    return rows

# -------- core --------
def pdf_to_excel(pdf_path: str, out_xlsx: str, keep_headers: bool = False) -> None:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber yüklü değil. Kur: pip install pdfplumber")

    rows_all: List[List[str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        log.info("PDF sayfa sayısı: %d", len(pdf.pages))
        for i, page in enumerate(pdf.pages, start=1):
            if i % 10 == 0:
                log.info("... %d/%d", i, len(pdf.pages))
            rows_all.extend(_extract_tables(page))

    # İlk 5 hücreyi al, tamamen boş olanları ele
    picked: List[List[str]] = []
    for r in rows_all:
        if not r:
            continue
        first5 = [ _clean(c) for c in (r[:5] + ["","","","",""])[:5] ]
        if all(c == "" for c in first5):
            continue
        # Başlık filtresi (varsayılan: açık)
        if not keep_headers:
            header_like = sum(1 for c in first5 if HDR_KEYWORDS.search(c)) >= 2
            if header_like:
                continue
        picked.append(first5)

    # DataFrame ve kolonlar
    cols = [
        "Kategori Ağacı 4",
        "Kategori Ağacı 3",
        "Kategori Ağacı 2",
        "Kategori Ağacı 1",
        "Komisyon Oranları (%) (KDV Dahildir)",
    ]
    df_proc = pd.DataFrame(picked, columns=cols)

    # Ham sayfa (opsiyonel: faydalı olabilir)
    width = max((len(r) for r in rows_all), default=0)
    raw_norm = [r + [""] * (width - len(r)) for r in rows_all] if rows_all else []
    df_raw = pd.DataFrame(raw_norm)

    os.makedirs(os.path.dirname(out_xlsx) or ".", exist_ok=True)
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as xl:
        df_proc.to_excel(xl, index=False, sheet_name="Processed_Data")
        df_raw.to_excel(xl, index=False, sheet_name="Raw")

    log.info("Processed_Data satır sayısı: %d", len(df_proc))
    if len(df_proc) == 0:
        log.warning("Uyarı: Processed_Data boş. (Başlık filtresi fazla agresif olabilir; --keep-headers deneyin.)")

# -------- CLI --------
def main():
    ap = argparse.ArgumentParser(description="N11 PDF -> Excel (ilk 5 sütunu Processed_Data'ya yazar).")
    ap.add_argument("--pdf", required=True, help="PDF dosyası")
    ap.add_argument("--out", required=True, help="Çıkış .xlsx")
    ap.add_argument("--keep-headers", action="store_true", help="Başlık satırlarını eleme (varsayılan: başlıkları at).")
    ap.add_argument("--log", default="INFO", choices=["CRITICAL","ERROR","WARNING","INFO","DEBUG"])
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log, logging.INFO),
                        format="%(levelname)s:%(name)s:%(message)s")
    pdf_to_excel(args.pdf, args.out, keep_headers=args.keep_headers)

if __name__ == "__main__":
    main()
