#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hepsiburada Excel -> CSV (DÜZ 4 SÜTUN)
--------------------------------------
PDF helper'ın ürettiği Excel'den (Processed_Data sayfası) şu 4 sütunu üretir:

  Kategori
  Alt Kategori
  Ürün Grubu
  Komisyon_%_KDV_Dahil

Not:
PDF helper'ın 'Processed_Data' sayfasında tipik kolonlar:
  Sayfa_No, Satir_No, Method, Ana_Kategori, Kategori, Alt_Kategori,
  Urun_Grubu, Komisyon, Marka_Komisyon, Vade, Ham_Veri
"""

import argparse
import json
import logging
import os
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger("hepsi_norm4")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


def _percent_to_float(s):
    """'%18', '18%', '% 12,5', '18,0% + KDV' -> 18.0"""
    if s is None:
        return None
    txt = str(s).strip().replace(",", ".")
    # yüzde içeren kalıp
    m = re.search(r'(\d+(?:\.\d+)?)\s*%|%\s*(\d+(?:\.\d+)?)', txt)
    if m:
        grp = m.group(1) or m.group(2)
        try:
            return float(grp)
        except:
            return None
    # çıplak sayı fallback
    m2 = re.search(r'(\d+(?:\.\d+)?)', txt)
    if m2:
        try:
            return float(m2.group(1))
        except:
            return None
    return None


def hepsi_excel_to_csv_flat4(excel_path: str, out_csv: str, sheet: str | None = "Processed_Data") -> dict:
    excel_path = str(excel_path)
    out_csv = str(out_csv)

    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel bulunamadı: {excel_path}")

    xls = pd.ExcelFile(excel_path)
    if sheet not in xls.sheet_names:
        sheet = xls.sheet_names[0]
        logger.info(f"'Processed_Data' yok, '{sheet}' kullanılacak.")

    df = pd.read_excel(excel_path, sheet_name=sheet)
    if df.empty:
        raise RuntimeError("Excel boş geldi.")

    # kolon adlarını normalize et
    norm = {c: re.sub(r'[^a-z0-9]+', '', str(c).lower()) for c in df.columns}
    inv  = {v: k for k, v in norm.items()}

    col_ana   = inv.get('ana_kategori') or inv.get('anakategori') or inv.get('ana')
    col_kat   = inv.get('kategori')
    col_alt   = inv.get('alt_kategori') or inv.get('altkategori')
    col_ugrp  = inv.get('urun_grubu') or inv.get('urungrubu')
    col_kom   = inv.get('komisyon')
    col_raw   = inv.get('ham_veri') or inv.get('hamveri')

    # kaynak alanlardan ham dataframe kur (önce geniş çıkar)
    wide = pd.DataFrame()
    wide['Ana Kategori'] = df[col_ana] if col_ana in df.columns else ""
    wide['Kategori']     = df[col_kat] if col_kat in df.columns else ""
    wide['Alt Kategori'] = df[col_alt] if col_alt in df.columns else ""
    wide['Ürün Grubu']   = df[col_ugrp] if col_ugrp in df.columns else ""
    wide['komisyon_txt'] = df[col_kom].astype(str).str.strip() if col_kom in df.columns else ""

    # komisyonu float'a çevir
    kom_f = wide['komisyon_txt'].map(_percent_to_float)

    # komisyon boşsa Ham_Veri'den yakalamayı dene
    if kom_f.isna().any() and col_raw in df.columns:
        raw_series = df[col_raw].astype(str)
        def _recover(idx, cur_val):
            if pd.notna(cur_val):
                return cur_val
            raw = raw_series.iat[idx]
            m = re.search(r'(%\s*\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?\s*%)', raw)
            if m:
                return _percent_to_float(m.group(0))
            return None
        kom_f = pd.Series([_recover(i, v) for i, v in enumerate(kom_f)], index=kom_f.index)

    # === DÜZ 4 SÜTUN ÇIKIŞ ===
    out = pd.DataFrame()
    # App beklenen eşleme:
    #   Kategori      := Ana Kategori
    #   Alt Kategori  := Kategori  (HB tarafında en mantıklı ikili)
    out['Kategori'] = wide['Ana Kategori'].astype(str).str.strip()
    out['Alt Kategori'] = wide['Kategori'].astype(str).str.strip()
    # Ürün Grubu zaten net
    out['Ürün Grubu'] = wide['Ürün Grubu'].astype(str).str.strip()
    # Komisyon numerik
    out['Komisyon_%_KDV_Dahil'] = kom_f.astype(float)

    # satır temizlikleri
    out = out[ (out['Kategori'] != "") | (out['Alt Kategori'] != "") | (out['Ürün Grubu'] != "") ]
    out = out.drop_duplicates().reset_index(drop=True)

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False, encoding='utf-8-sig')

    logger.info(f"CSV (4 sütun) yazıldı: {out_csv} (satır: {len(out)})")
    return {
        "site": "hepsiburada",
        "rows": int(len(out)),
        "csv": out_csv,
        "sheet": sheet,
        "columns": ["Kategori", "Alt Kategori", "Ürün Grubu", "Komisyon_%_KDV_Dahil"]
    }


def main():
    p = argparse.ArgumentParser(description="Hepsiburada Excel -> CSV (4 sütun) normalizer")
    p.add_argument("--excel", required=True, help="PDF helper çıktısı Excel")
    p.add_argument("--out-csv", required=True, help="Üretilecek CSV yolu (ör. data/hepsiburada_commissions.csv)")
    p.add_argument("--sheet", default="Processed_Data")
    p.add_argument("--log", default="INFO", choices=["CRITICAL","ERROR","WARNING","INFO","DEBUG"])
    a = p.parse_args()

    logging.getLogger().setLevel(getattr(logging, a.log, logging.INFO))
    try:
        info = hepsi_excel_to_csv_flat4(a.excel, a.out_csv, sheet=a.sheet)
        print(json.dumps(info, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.exception("Normalize hatası")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
