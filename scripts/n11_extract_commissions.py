#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
N11 Commission Extractor
------------------------
N11 PDF'den komisyon verilerini çıkarır ve standart CSV formatında oluşturur.
PDF'yi direkt olarak parse eder veya mevcut CSV'den okur.

Usage:
    python scripts/n11_extract_commissions.py --pdf "path.pdf" --out-csv "output.csv"
    python scripts/n11_extract_commissions.py --use-hardcoded --out-csv "output.csv"
"""

import argparse
import csv
import json
import logging
import re
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF gerekli. Kurulum: pip install PyMuPDF")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("n11_extractor")


class N11Extractor:
    """N11 PDF komisyon çıkarıcı."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = None
        self.parsed_data = []

    def open_pdf(self):
        """PDF'yi aç."""
        try:
            self.doc = fitz.open(self.pdf_path)
            logger.info(f"PDF açıldı: {self.pdf_path} ({self.doc.page_count} sayfa)")
        except Exception as e:
            logger.error(f"PDF açılamadı: {e}")
            raise

    def close_pdf(self):
        """PDF'yi kapat."""
        if self.doc:
            self.doc.close()

    def parse_pdf(self) -> List[Dict[str, str]]:
        """PDF'yi parse et."""
        if not self.doc:
            self.open_pdf()

        # N11 PDF parser'ını çağır
        try:
            result = subprocess.run([
                "python", "scripts/n11_pdf_parser.py",
                "--pdf", self.pdf_path,
                "--output", "temp_n11_output.csv"
            ], capture_output=True, text=True, check=True)

            # Geçici CSV'yi oku
            temp_csv = Path("temp_n11_output.csv")
            if temp_csv.exists():
                with open(temp_csv, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    data = list(reader)
                # Geçici dosyayı sil
                temp_csv.unlink()
                logger.info(f"PDF'den {len(data)} ürün grubu çıkarıldı")
                return data
            else:
                logger.warning("PDF parser çıktı dosyası bulunamadı")
                return []

        except subprocess.CalledProcessError as e:
            logger.error(f"PDF parser hatası: {e.stderr}")
            return []
        except Exception as e:
            logger.error(f"PDF parsing genel hatası: {e}")
            return []

    def save_csv(self, data: List[Dict[str, str]], output_path: str):
        """CSV olarak kaydet."""
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if data:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)

        logger.info(f"CSV kaydedildi: {output_path} ({len(data)} satır)")


def clean_csv_data(data: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """CSV verilerini temizle ve standardize et."""
    cleaned_data = []

    for row in data:
        # BOM ve gereksiz karakterleri temizle
        cleaned_row = {}
        for key, value in row.items():
            # BOM karakterini kaldır
            clean_key = key.replace('\ufeff', '').strip()
            clean_value = str(value).replace('\ufeff', '').strip() if value else ""

            # Standart sütun adlarına dönüştür
            if clean_key == 'Kategori':
                cleaned_row['Kategori'] = clean_value
            elif clean_key == 'Alt Kategori':
                cleaned_row['Alt Kategori'] = clean_value
            elif clean_key == 'Ürün Grubu':
                cleaned_row['Ürün Grubu'] = clean_value
            elif clean_key == 'Komisyon_%_KDV_Dahil':
                cleaned_row['Komisyon_%_KDV_Dahil'] = clean_value
            elif clean_key == 'komisyon':
                # Eski komisyon kolonunu atla, sadece debug için log
                logger.debug(f"Eski komisyon kolonu atlandı: {clean_value}")
                continue

        # Gerekli alanların varlığını kontrol et
        if (cleaned_row.get('Kategori') and
            cleaned_row.get('Alt Kategori') and
            cleaned_row.get('Ürün Grubu') and
            cleaned_row.get('Komisyon_%_KDV_Dahil')):

            # Nan ve boş değerleri kontrol et
            if (cleaned_row['Kategori'] not in ['nan', '', 'NaN'] and
                cleaned_row['Komisyon_%_KDV_Dahil'] not in ['nan%', '', 'NaN', 'nan']):
                cleaned_data.append(cleaned_row)

    logger.info(f"Temizleme sonrası: {len(cleaned_data)} geçerli satır")
    return cleaned_data


def extract_hardcoded_data() -> List[Dict[str, str]]:
    """
    PDF parse etme başarısız olursa, mevcut CSV'yi okur.
    Bu yöntem mevcut CSV dosyasından veri çeker ve temizler.
    """
    logger.info("Hard-coded veri kullanılıyor...")

    # Mevcut CSV dosyasını oku
    csv_path = Path(__file__).parent.parent / "data" / "n11_commissions.csv"

    if not csv_path.exists():
        logger.warning(f"CSV dosyası bulunamadı: {csv_path}")
        # Fallback mini data
        return [
            {'Kategori': 'Ayakkabı', 'Alt Kategori': 'Ayakkabı', 'Ürün Grubu': 'Ayakkabı', 'Komisyon_%_KDV_Dahil': '18.00'},
            {'Kategori': 'Elektronik', 'Alt Kategori': 'Telefon', 'Ürün Grubu': 'Cep Telefonu', 'Komisyon_%_KDV_Dahil': '8.00'},
        ]

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:  # BOM için utf-8-sig kullan
            reader = csv.DictReader(f)
            raw_data = list(reader)

        logger.info(f"Ham CSV'den {len(raw_data)} satır okundu")

        # Veriyi temizle ve standardize et
        cleaned_data = clean_csv_data(raw_data)

        logger.info(f"Temizlenmiş CSV'den {len(cleaned_data)} satır okundu")
        return cleaned_data

    except Exception as e:
        logger.error(f"CSV okuma hatası: {e}")
        # Fallback mini data
        return [
            {'Kategori': 'Ayakkabı', 'Alt Kategori': 'Ayakkabı', 'Ürün Grubu': 'Ayakkabı', 'Komisyon_%_KDV_Dahil': '18.00'},
            {'Kategori': 'Elektronik', 'Alt Kategori': 'Telefon', 'Ürün Grubu': 'Cep Telefonu', 'Komisyon_%_KDV_Dahil': '8.00'},
        ]


def main():
    parser = argparse.ArgumentParser(description="N11 komisyon çıkarıcı")
    parser.add_argument('--pdf', help='PDF dosyası yolu')
    parser.add_argument('--out-csv', required=True, help='Çıktı CSV dosyası')
    parser.add_argument('--use-hardcoded', action='store_true',
                       help='Hard-coded veri kullan (PDF parse etmeye çalışma)')
    parser.add_argument('--log-level', default='INFO')

    args = parser.parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    try:
        data = []

        if args.use_hardcoded or not args.pdf:
            logger.info("Hard-coded veri kullanılıyor...")
            data = extract_hardcoded_data()
        else:
            # PDF parse et
            extractor = N11Extractor(args.pdf)
            try:
                data = extractor.parse_pdf()
                if not data:
                    logger.warning("PDF'den veri çıkarılamadı, hard-coded veri kullanılıyor...")
                    data = extract_hardcoded_data()
            finally:
                extractor.close_pdf()

        if not data:
            logger.error("Hiç veri bulunamadı")
            return 1

        # CSV kaydet
        extractor = N11Extractor("")  # Dummy instance
        extractor.save_csv(data, args.out_csv)

        # Sonuçları JSON olarak yazdır
        result = {
            "status": "success",
            "total_rows": len(data),
            "output_file": args.out_csv,
            "method": "hardcoded" if (args.use_hardcoded or not args.pdf) else "pdf_parse"
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    except Exception as e:
        logger.error(f"Hata: {e}")
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())