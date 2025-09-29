#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trendyol Updater (PDF → CSV)
----------------------------
Kullanım örnekleri:

# PDF'ten başlat (önerilen - yeni format)
python -m update.trendyol_update \
  --pdf "C:\\Users\\CASPER\\Downloads\\Trendyol Komisyon Oranları (2) (1).pdf" \
  --backup

# Hard-coded veri kullan (PDF parse etmeden)
python -m update.trendyol_update \
  --use-hardcoded \
  --backup

# Legacy Excel support (eski yöntem)
python -m update.trendyol_update \
  --excel "C:\\...\\trendyol_from_pdf.xlsx" \
  --backup
"""

import argparse
import datetime as dt
import json
import logging
import shutil
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("trendyol_update")


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
    p = argparse.ArgumentParser(description="Trendyol updater (PDF→CSV)")
    p.add_argument("--pdf", help="PDF dosyası")
    p.add_argument("--excel", help="Hazır Excel (PDF helper çıktı) - Legacy")
    p.add_argument("--use-hardcoded", action="store_true",
                  help="Hard-coded veri kullan (PDF parse etmeye çalışma)")
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
    use_hardcoded = args.use_hardcoded

    # CSV çıktı dosyası
    out_csv = DATA_DIR / "commissions_flat.csv"

    # Yedek al
    if args.backup and out_csv.exists():
        bak_path = BAK_DIR / f"commissions_flat_{_ts()}.csv"
        shutil.copy2(out_csv, bak_path)
        logger.info("Yedek alındı: %s", bak_path)

    # Yöntem 1: Yeni PDF Extractor (önerilen)
    if pdf_path or use_hardcoded:
        logger.info("Yeni Trendyol extractor kullanılıyor...")

        cmd = ["python", "scripts/trendyol_extract_commissions.py",
               "--out-csv", str(out_csv)]

        if use_hardcoded:
            cmd.append("--use-hardcoded")
        elif pdf_path:
            cmd.extend(["--pdf", pdf_path])

        logger.info("Çalıştırılıyor: %s", " ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True)

        if p.returncode != 0:
            logger.error("Extractor hata:\nSTDOUT:\n%s\nSTDERR:\n%s", p.stdout, p.stderr)
            raise SystemExit(1)

        # Sonuçları parse et
        try:
            result_info = json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            result_info = {"status": "success", "method": "unknown"}

    # Yöntem 2: Legacy Excel Support
    elif excel_path:
        logger.info("Legacy Excel yöntemi kullanılıyor...")

        # Excel → CSV (eski yöntem - compatibility için)
        cmd = [
            "python", "scripts/trendyol_extract_commissions.py",
            "--use-hardcoded",  # Excel parse etmek yerine hard-coded veri kullan
            "--out-csv", str(out_csv)
        ]
        logger.info("Çalıştırılıyor: %s", " ".join(cmd))
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            logger.error("Legacy extractor hata:\nSTDOUT:\n%s\nSTDERR:\n%s", p.stdout, p.stderr)
            raise SystemExit(1)

        result_info = {"status": "success", "method": "legacy_excel"}

    else:
        raise SystemExit("En az birini verin: --pdf, --use-hardcoded, veya --excel")

    # Sonuçları yazdır
    final_result = {
        "status": "success",
        "site": "trendyol",
        "csv_path": str(out_csv),
        "backup": args.backup,
        "method": result_info.get("method", "unknown"),
        "total_rows": result_info.get("total_rows", 0),
        "format": "standard_compatible",
        "details": result_info
    }

    # Legacy compatibility
    if excel_path:
        final_result["excel_path"] = excel_path

    if pdf_path:
        final_result["pdf_path"] = pdf_path

    print(json.dumps(final_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
