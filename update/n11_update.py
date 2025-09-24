#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
N11 Updater (PDF → Excel → CSV)
-------------------------------
Hepsiburada/Trendyol ile aynı akış:
- --pdf verildiyse önce PDF→Excel (Processed_Data) DENER
  - pdf_to_excel_helper import/subprocess ile
  - Başarısız olursa doğrudan extractor'ı --pdf ile çalıştırır (fallback)
- --excel verildiyse direkt extractor'ı --excel ile çalıştırır
- Çıkış: <data>/n11_commissions.csv
- Backup: <data>/backup/n11_commissions_YYYY-MM-DD_HHMMSS.csv
"""

import argparse
import datetime as dt
import json
import logging
import shutil
import subprocess
from pathlib import Path
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("n11_update")


def _ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _import_pdf_helper():
    """scripts/pdf_to_excel_helper.py içe aktar; olmazsa subprocess kullan."""
    try:
        from scripts.pdf_to_excel_helper import pdf_to_excel
        return pdf_to_excel
    except Exception as e:
        logger.warning(f"pdf_to_excel import edilemedi ({e}); subprocess ile denenecek.")
        return None


def _run_pdf_helper_subprocess(pdf_path: str, out_xlsx: str) -> dict:
    cmd = [sys.executable, "scripts/pdf_to_excel_helper.py", "--pdf", pdf_path, "--out", out_xlsx]
    logger.info("Çalıştırılıyor: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"PDF helper hata: {p.stderr or p.stdout}")
    # JSON yakalamaya çalış; olmazsa geç
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        logger.info("PDF helper çıktısı JSON değil, devam ediliyor.")
        return {"status": "ok", "out": out_xlsx}


def main():
    ap = argparse.ArgumentParser(description="N11 updater (PDF→Excel→CSV)")
    ap.add_argument("--pdf", help="Kaynak PDF")
    ap.add_argument("--excel", help="Kaynak Excel (PDF helper çıktısı)")
    ap.add_argument("--data-dir", default=None, help="Vars: <repo>/data")
    ap.add_argument("--backup", action="store_true", help="Mevcut CSV yedeğini al")
    ap.add_argument("--log", default="INFO", choices=["CRITICAL","ERROR","WARNING","INFO","DEBUG"])
    args = ap.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log, logging.INFO))

    REPO_ROOT = Path(__file__).resolve().parent.parent     # <repo>/update/.. = <repo>
    DATA_DIR = Path(args.data_dir) if args.data_dir else (REPO_ROOT / "data")
    TMP_DIR = DATA_DIR / "tmp"
    BAK_DIR = DATA_DIR / "backup"
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    BAK_DIR.mkdir(parents=True, exist_ok=True)

    source_pdf = args.pdf
    source_xlsx = args.excel

    if not source_pdf and not source_xlsx:
        raise SystemExit("Ne --pdf ne de --excel verildi. En az birini verin.")

    out_csv = DATA_DIR / "n11_commissions.csv"

    # Yedek
    if args.backup and out_csv.exists():
        bak_path = BAK_DIR / f"n11_commissions_{_ts()}.csv"
        shutil.copy2(out_csv, bak_path)
        logger.info("Yedek alındı: %s", bak_path)

    # Eğer PDF verildiyse önce PDF→Excel dene (Processed_Data hedefi)
    used_excel = None
    if source_pdf and not source_xlsx:
        out_xlsx = TMP_DIR / f"n11_{_ts()}_from_pdf.xlsx"
        try:
            pdf_to_excel_func = _import_pdf_helper()
            if pdf_to_excel_func:
                logger.info("PDF helper (import) çağrılıyor…")
                _ = pdf_to_excel_func(source_pdf, str(out_xlsx))
            else:
                logger.info("PDF helper (subprocess) çağrılıyor…")
                _ = _run_pdf_helper_subprocess(source_pdf, str(out_xlsx))
            used_excel = str(out_xlsx)
            logger.info("Excel hazır: %s", used_excel)
        except Exception as e:
            logger.warning(f"PDF→Excel aşaması başarısız (devam için doğrudan PDF parse): {e}")

    # Extractor komutu
    extractor = REPO_ROOT / "scripts" / "n11_extract_commissions.py"
    if (source_xlsx or used_excel):
        cmd = [
            sys.executable, str(extractor),
            "--excel", (source_xlsx or used_excel),
            "--out-csv", str(out_csv),
            "--sheet", "Processed_Data",
            "--log", args.log
        ]
    elif source_pdf:
        cmd = [
            sys.executable, str(extractor),
            "--pdf", source_pdf,
            "--out-csv", str(out_csv),
            "--log", args.log
        ]
    else:
        raise SystemExit("Beklenmedik durum: girdi bulunamadı.")

    logger.info("Çalıştırılıyor: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        logger.error("Extractor hata:\nSTDOUT:\n%s\nSTDERR:\n%s", p.stdout, p.stderr)
        raise SystemExit(1)

    # Sonuç yazdır
    try:
        info = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        info = {"site": "n11", "csv": str(out_csv)}

    print(json.dumps({
        "status": "ok",
        "site": "n11",
        "csv_path": str(out_csv),
        "backup": args.backup,
        "details": info
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
