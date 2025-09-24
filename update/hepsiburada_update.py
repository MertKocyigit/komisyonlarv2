#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hepsiburada Updater (PDF → Excel → CSV)
---------------------------------------
Kullanım örnekleri:

# PDF'ten başlat (önerilen)
python -m update.hepsiburada_update \
  --pdf "C:\\Users\\CASPER\\Downloads\\1625757354638_kategori-bazli-komisyon-oranlari-listesi.pdf" \
  --backup

# Elinde Excel varsa
python -m update.hepsiburada_update \
  --excel "C:\\...\\hepsiburada_from_pdf.xlsx" \
  --backup
"""

import argparse
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("hepsi_update")


def _ts():
    return dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _import_pdf_helper():
    # scripts/pdf_to_excel_helper.py içe aktarımı; olmazsa subprocess
    try:
        from scripts.pdf_to_excel_helper import pdf_to_excel
        return pdf_to_excel
    except Exception as e:
        logger.warning(f"pdf_to_excel import edilemedi ({e}); subprocess ile denenecek.")
        return None


def _run_pdf_helper_subprocess(pdf_path: str, out_xlsx: str) -> dict:
    cmd = ["python", "scripts/pdf_to_excel_helper.py", "--pdf", pdf_path, "--out", out_xlsx]
    logger.info("Çalıştırılıyor: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"PDF helper hata: {p.stderr or p.stdout}")
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        logger.info("PDF helper çıktısı JSON değil, devam ediliyor.")
        return {"status": "ok", "out": out_xlsx}


def main():
    p = argparse.ArgumentParser(description="Hepsiburada updater (PDF→Excel→CSV)")
    p.add_argument("--pdf", help="PDF dosyası")
    p.add_argument("--excel", help="Hazır Excel (PDF helper çıktı)")
    p.add_argument("--data-dir", default=None, help="Vars: <repo>/data")
    p.add_argument("--backup", action="store_true", help="Mevcut CSV yedeğini al")
    p.add_argument("--log", default="INFO", choices=["CRITICAL","ERROR","WARNING","INFO","DEBUG"])
    args = p.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log, logging.INFO))

    REPO_ROOT = Path(__file__).resolve().parent.parent  # <repo>/update/.. = <repo>
    DATA_DIR = Path(args.data_dir) if args.data_dir else (REPO_ROOT / "data")
    TMP_DIR = DATA_DIR / "tmp"
    BAK_DIR = DATA_DIR / "backup"
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    BAK_DIR.mkdir(parents=True, exist_ok=True)

    excel_path = args.excel
    pdf_path = args.pdf

    # 1) PDF → Excel (gerekliyse)
    if pdf_path and not excel_path:
        out_xlsx = TMP_DIR / f"hepsiburada_{_ts()}_from_pdf.xlsx"
        pdf_to_excel_func = _import_pdf_helper()
        if pdf_to_excel_func:
            logger.info("PDF helper (import) çağrılıyor…")
            _ = pdf_to_excel_func(pdf_path, str(out_xlsx))
        else:
            logger.info("PDF helper (subprocess) çağrılıyor…")
            _ = _run_pdf_helper_subprocess(pdf_path, str(out_xlsx))
        excel_path = str(out_xlsx)
        logger.info("Excel hazır: %s", excel_path)

    if not excel_path:
        raise SystemExit("Ne --pdf ne de --excel verildi. En az birini verin.")

    # 2) Excel → CSV
    out_csv = DATA_DIR / "hepsiburada_commissions.csv"

    # yedek al
    if args.backup and out_csv.exists():
        bak_path = BAK_DIR / f"hepsiburada_commissions_{_ts()}.csv"
        shutil.copy2(out_csv, bak_path)
        logger.info("Yedek alındı: %s", bak_path)

    # normalizer çalıştır
    cmd = [
        "python", "scripts/hepsiburada_extract_commissions.py",
        "--excel", excel_path,
        "--out-csv", str(out_csv),
        "--sheet", "Processed_Data"
    ]
    logger.info("Çalıştırılıyor: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        logger.error("Normalizer hata:\nSTDOUT:\n%s\nSTDERR:\n%s", p.stdout, p.stderr)
        raise SystemExit(1)

    # Sonuçları yazdır
    try:
        info = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        info = {"site": "hepsiburada", "csv": str(out_csv)}

    print(json.dumps({
        "status": "ok",
        "site": "hepsiburada",
        "excel_path": excel_path,
        "csv_path": str(out_csv),
        "backup": args.backup,
        "details": info
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
