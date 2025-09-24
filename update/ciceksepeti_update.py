#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÇiçekSepeti komisyon güncelleme (esnek extractor yolu + sağlam import/fallback)

Öncelik sırasıyla extractor yolu:
  1) --extractor parametresi
  2) CICEKSEPETI_EXTRACTOR ortam değişkeni
  3) <bu_dosya_klasörü>\ciceksepeti_extract_commissions.py
  4) <proje_kökü>\scripts\ciceksepeti_extract_commissions.py
  5) <proje_kökü>\ciceksepeti_extract_commissions.py
"""

import argparse
import logging
import os
import sys
import shutil
from pathlib import Path
import subprocess
import importlib.util
import pandas as pd

# Yol/klasörler
BASE_DIR = Path(__file__).resolve().parents[1] if (Path(__file__).parent.name == "update") else Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
TMP_DIR  = DATA_DIR / "tmp"
BK_DIR   = DATA_DIR / "backup"
TMP_DIR.mkdir(parents=True, exist_ok=True)
BK_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("ciceksepeti_update")

EXTRACTOR_FILENAME = "ciceksepeti_extract_commissions.py"

def _resolve_extractor_path(cli_path: str | None) -> Path:
    """Extractor dosya yolunu öncelik sırasıyla çöz."""
    candidates = []
    if cli_path:
        candidates.append(Path(cli_path))
    env_path = os.getenv("CICEKSEPETI_EXTRACTOR")
    if env_path:
        candidates.append(Path(env_path))
    here = Path(__file__).resolve().parent
    candidates.append(here / EXTRACTOR_FILENAME)
    candidates.append(BASE_DIR / "scripts" / EXTRACTOR_FILENAME)  # << senin verdiğin konum
    candidates.append(BASE_DIR / EXTRACTOR_FILENAME)

    for p in candidates:
        if p and p.exists():
            return p

    raise FileNotFoundError(
        "Extractor bulunamadı. Aranan yerler:\n" +
        "\n".join(str(p) for p in candidates)
    )

def _import_module_from_path(path: Path):
    """Verilen dosya yolundan modül yükle."""
    spec = importlib.util.spec_from_file_location("ciceksepeti_extract_commissions", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"spec oluşturulamadı: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    log.info(f"Extractor modülü yüklendi: {path}")
    return mod

def _run_subprocess_fallback(script_path: Path, pdf_path: Path, out_csv: Path, backup: bool) -> dict:
    """Import başarısızsa extractor’ı ayrı süreçte çalıştır."""
    out_lines = TMP_DIR / "ciceksepeti_lines.csv"
    out_raw   = TMP_DIR / "ciceksepeti_raw.csv"

    cmd = [
        sys.executable, str(script_path),
        "--pdf", str(pdf_path),
        "--out-lines-csv", str(out_lines),
        "--out-raw-csv",   str(out_raw),
        "--out-app-csv",   str(out_csv),
        "--log", "INFO",
    ]
    if backup:
        cmd.append("--backup")

    log.info(f"Extractor subprocess başlıyor: {script_path}")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        log.error("Extractor subprocess HATA")
        log.error("STDOUT:\n" + (res.stdout or ""))
        log.error("STDERR:\n" + (res.stderr or ""))
        raise RuntimeError("Extractor subprocess başarısız")

    # Basit özet
    return {
        "mode": "subprocess",
        "lines_csv": str(out_lines),
        "raw_csv": str(out_raw),
        "app_csv": str(out_csv),
    }

def main():
    ap = argparse.ArgumentParser(description="ÇiçekSepeti komisyon güncelleme (esnek extractor yolu)")
    ap.add_argument("--pdf", required=True, help="Kaynak PDF")
    ap.add_argument("--out-csv", default=str(DATA_DIR / "ciceksepeti_commissions.csv"), help="Çıktı CSV (app)")
    ap.add_argument("--extractor", help="Extractor script yolu (ciceksepeti_extract_commissions.py)")
    ap.add_argument("--backup", action="store_true", help="Yazmadan önce mevcut CSV yedeklensin")
    ap.add_argument("--log", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"])
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log))

    pdf_path = Path(args.pdf)
    out_csv  = Path(args.out_csv)

    if not pdf_path.exists():
        log.error(f"PDF bulunamadı: {pdf_path}")
        sys.exit(1)

    # Yazmadan ÖNCE mevcut CSV yedeği
    if args.backup and out_csv.exists():
        bk = BK_DIR / "ciceksepeti_commissions_backup.csv"
        try:
            shutil.copy2(out_csv, bk)
            log.info(f"Mevcut CSV yedeklendi: {bk}")
        except Exception as e:
            log.info(f"Yedek başarısız (devam): {e}")

    # Extractor yolunu çöz
    try:
        extractor_path = _resolve_extractor_path(args.extractor)
    except Exception as e:
        log.error(str(e))
        sys.exit(1)

    # Önce import ile dene
    try:
        ext = _import_module_from_path(extractor_path)
        info = ext.run(
            str(pdf_path),
            TMP_DIR / "ciceksepeti_lines.csv",
            TMP_DIR / "ciceksepeti_raw.csv",
            out_csv,
            backup=args.backup
        )
        info = {"mode": "import", "extractor": str(extractor_path), **info}
    except Exception as e:
        log.error(f"Extractor import edilemedi: {e}")
        # Fallback: subprocess
        try:
            info = _run_subprocess_fallback(extractor_path, pdf_path, out_csv, backup=args.backup)
            info = {"extractor": str(extractor_path), **info}
        except Exception as e2:
            log.error(f"Fallback da başarısız: {e2}")
            sys.exit(1)

    # Özet
    log.info("Çalışma tamam:")
    try:
        print(pd.Series(info).to_string())
    except Exception:
        print(info)

if __name__ == "__main__":
    main()
