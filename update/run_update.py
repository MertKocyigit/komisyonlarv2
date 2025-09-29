import argparse
import json
import sys
import logging
from pathlib import Path

# Absolute imports for module execution (python -m update.run_update)
from update.n11_update import N11Update
from update.hepsiburada_update import HepsiburadaUpdate
from update.trendyol_update import TrendyolUpdate

# Site registry
SITES = {
    "n11": N11Update(),
    "hepsiburada": HepsiburadaUpdate(),
    "trendyol": TrendyolUpdate(),
}

def setup_logging(level: str) -> None:
    """Logging yapılandırması"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

def main():
    """CLI ana fonksiyon"""
    parser = argparse.ArgumentParser(
        description="PDF/Excel ile CSV güncelle (atomik)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Kullanım örnekleri:

  # N11 PDF'den güncelle (backup ile)
  python -m update.run_update --site n11 --pdf komisyon.pdf --backup

  # Hepsiburada Excel'den güncelle (dry-run)
  python -m update.run_update --site hepsiburada --excel data.xlsx --dry-run

  # Trendyol Camelot motor ile
  python -m update.run_update --site trendyol --pdf data.pdf --prefer camelot
        """
    )

    # Zorunlu parametreler
    parser.add_argument("--site", required=True, choices=list(SITES.keys()),
                        help="Güncellenecek site")

    # Girdi dosyası (sadece biri zorunlu)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--pdf", help="PDF girdi dosyası yolu")
    input_group.add_argument("--excel", help="Excel girdi dosyası yolu")

    # PDF işleme opsiyonları
    parser.add_argument("--prefer", default="auto",
                        choices=["auto", "pdfplumber", "camelot", "tabula"],
                        help="PDF motor tercihi (default: auto)")
    parser.add_argument("--page-range", default=None,
                        help='Sayfa aralığı (örn: "1-99" veya "1,3,5")')
    parser.add_argument("--ocr", action="store_true",
                        help="Gerekirse OCR kullan")

    # Genel opsiyonlar
    parser.add_argument("--backup", action="store_true",
                        help="Mevcut CSV'yi backup'la")
    parser.add_argument("--dry-run", action="store_true",
                        help="Sadece simüle et, değişiklik yapma")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Geçici dosyaları sakla (debug için)")
    parser.add_argument("--log", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log seviyesi")

    args = parser.parse_args()

    # Logging setup
    setup_logging(args.log)

    # Updater seç
    updater = SITES[args.site]

    # Girdi yolu belirle
    input_path = Path(args.pdf if args.pdf else args.excel)

    try:
        # Ana işlemi çalıştır
        result = updater.run(
            input_path=input_path,
            prefer=args.prefer,
            page_range=args.page_range,
            ocr=args.ocr,
            backup=args.backup,
            dry_run=args.dry_run,
            keep_temp=args.keep_temp
        )

        # Sonucu JSON olarak yazdır
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        logging.error(f"İşlem başarısız: {e}")
        print(f"❌ {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
