#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hepsiburada PDF Parser
----------------------
Hepsiburada komisyon PDF'lerini parse eder ve Trendyol formatında CSV çıktısı verir.

Usage:
    python scripts/hepsiburada_pdf_parser.py --pdf "path/to/hepsiburada.pdf" --output "output.csv"
"""

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# PDF parsing için gerekli import'lar
try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF yüklü değil. Yüklemek için: pip install PyMuPDF")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("hepsi_pdf_parser")


class HepsiburadaPDFParser:
    """Hepsiburada PDF komisyon listesini parse eder."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = None
        self.commission_data = []

    def open_pdf(self) -> None:
        """PDF dosyasını açar."""
        try:
            self.doc = fitz.open(self.pdf_path)
            logger.info(f"PDF açıldı: {self.pdf_path} ({self.doc.page_count} sayfa)")
        except Exception as e:
            logger.error(f"PDF açılamadı: {e}")
            raise

    def close_pdf(self) -> None:
        """PDF dosyasını kapatır."""
        if self.doc:
            self.doc.close()

    def clean_text(self, text: str) -> str:
        """Metni temizler ve normalizasyon yapar."""
        if not text:
            return ""

        # Çoklu boşlukları tek boşluk yap
        text = re.sub(r'\s+', ' ', text.strip())

        # Özel karakterleri düzelt
        replacements = {
            '&': '&',
            'ı': 'ı',
            'İ': 'İ',
            'ş': 'ş',
            'Ş': 'Ş',
            'ğ': 'ğ',
            'Ğ': 'Ğ',
            'ü': 'ü',
            'Ü': 'Ü',
            'ö': 'ö',
            'Ö': 'Ö',
            'ç': 'ç',
            'Ç': 'Ç'
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def parse_commission_rate(self, text: str) -> Optional[float]:
        """Komisyon oranını parse eder."""
        if not text:
            return None

        # % işaretini kaldır ve sayıyı çıkar
        rate_match = re.search(r'(\d+[,.]?\d*)\s*%?', text.replace(',', '.'))
        if rate_match:
            try:
                return float(rate_match.group(1))
            except ValueError:
                return None
        return None

    def split_product_groups(self, product_groups_text: str) -> List[str]:
        """Virgülle ayrılmış ürün gruplarını böler."""
        if not product_groups_text:
            return []

        # Virgül ile böl ve temizle
        groups = [self.clean_text(group) for group in product_groups_text.split(',')]
        return [group for group in groups if group]

    def extract_table_from_page(self, page_num: int) -> List[Dict[str, str]]:
        """Bir sayfadan tablo verilerini çıkarır."""
        page = self.doc[page_num]
        text = page.get_text()

        logger.debug(f"Sayfa {page_num + 1} işleniyor...")

        # Tabloyu satırlara böl
        lines = text.split('\n')
        table_data = []

        # Ana başlıkları bul (Ana Kategori, Kategori, Ürün Grubu Detayı, Komisyon)
        header_patterns = [
            'Ana Kategori',
            'Kategori',
            'Ürün Grubu Detayı',
            'Komisyon'
        ]

        current_row = {}
        current_category = ""
        current_subcategory = ""

        for i, line in enumerate(lines):
            line = self.clean_text(line)
            if not line or len(line) < 3:
                continue

            # Komisyon oranı tespit et
            if '%' in line or re.search(r'^\d+[,.]?\d*$', line):
                commission = self.parse_commission_rate(line)
                if commission and current_row:
                    current_row['komisyon'] = commission
                    table_data.append(current_row.copy())
                    current_row = {}
                continue

            # Ana kategori tespit et (genelde büyük harfle başlar)
            if line.isupper() or (line[0].isupper() and len(line.split()) <= 3):
                # Bilinen ana kategoriler
                known_categories = [
                    'ALTIN', 'AKSESUAR', 'ÇANTA', 'AYAKKABI', 'GİYİM', 'PARFÜM',
                    'OUTDOOR', 'SPOR', 'TARAFTAR', 'CEP TELEFONU', 'BİLGİSAYAR',
                    'FOTO-KAMERA', 'OTO AKSESUAR', 'SDA', 'MDA', 'TV', 'ANNE BEBEK',
                    'CİLT BAKIMI', 'SAÇ BAKIM', 'MAKYAJ', 'PETSHOP', 'SAĞLIK',
                    'EV BAKIM', 'TEMEL TÜKETİM', 'BAHÇE', 'YAPI MARKET',
                    'EV TEKSTİLİ', 'MOBİLYA', 'ZÜCCACİYE', 'OYUNCAK', 'KIRTASIYE',
                    'FİLM', 'KİTAP', 'MÜZİK', 'DİJİTAL ÜRÜNLER', 'OYUN KONSOL', 'NONTV', 'HOBİ'
                ]

                for cat in known_categories:
                    if cat in line.upper():
                        current_category = line
                        current_row = {'ana_kategori': current_category}
                        break
                continue

            # Alt kategori ve ürün grupları
            if current_category and line:
                # Eğer satırda virgül varsa, muhtemelen ürün grupları listesi
                if ',' in line and len(line.split(',')) > 2:
                    if 'urun_gruplari' not in current_row:
                        current_row['urun_gruplari'] = line
                elif not current_row.get('kategori'):
                    current_row['kategori'] = line
                elif current_row.get('kategori') and not current_row.get('urun_gruplari'):
                    current_row['urun_gruplari'] = line

        logger.info(f"Sayfa {page_num + 1}'den {len(table_data)} satır çıkarıldı")
        return table_data

    def parse_all_pages(self) -> None:
        """Tüm sayfaları parse eder."""
        if not self.doc:
            raise RuntimeError("PDF açılmamış")

        all_data = []
        for page_num in range(self.doc.page_count):
            try:
                page_data = self.extract_table_from_page(page_num)
                all_data.extend(page_data)
            except Exception as e:
                logger.warning(f"Sayfa {page_num + 1} işlenirken hata: {e}")

        # Verileri işle ve normalize et
        self.commission_data = []

        for row in all_data:
            if not all(k in row for k in ['ana_kategori', 'kategori', 'urun_gruplari', 'komisyon']):
                continue

            # Ürün gruplarını böl
            product_groups = self.split_product_groups(row['urun_gruplari'])

            for product_group in product_groups:
                self.commission_data.append({
                    'Kategori': row['ana_kategori'],
                    'Alt Kategori': row['kategori'],
                    'Ürün Grubu': product_group,
                    'Komisyon_%_KDV_Dahil': f"{row['komisyon']:.2f}"
                })

        logger.info(f"Toplam {len(self.commission_data)} ürün grubu çıkarıldı")

    def save_to_csv(self, output_path: str) -> None:
        """Trendyol formatında CSV olarak kaydet."""
        if not self.commission_data:
            raise RuntimeError("Parse edilmiş veri bulunamadı")

        headers = ['Kategori', 'Alt Kategori', 'Ürün Grubu', 'Komisyon_%_KDV_Dahil']

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(self.commission_data)

        logger.info(f"CSV kaydedildi: {output_path} ({len(self.commission_data)} satır)")

    def get_statistics(self) -> Dict[str, int]:
        """İstatistik bilgilerini döner."""
        if not self.commission_data:
            return {}

        categories = set(row['Kategori'] for row in self.commission_data)
        subcategories = set(row['Alt Kategori'] for row in self.commission_data)

        return {
            'total_rows': len(self.commission_data),
            'total_categories': len(categories),
            'total_subcategories': len(subcategories),
            'categories': list(categories)
        }


def main():
    parser = argparse.ArgumentParser(description="Hepsiburada PDF komisyon parser")
    parser.add_argument('--pdf', required=True, help='PDF dosyası yolu')
    parser.add_argument('--output', required=True, help='Çıktı CSV dosyası yolu')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])

    args = parser.parse_args()

    # Log seviyesini ayarla
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # PDF'yi parse et
    pdf_parser = HepsiburadaPDFParser(args.pdf)

    try:
        pdf_parser.open_pdf()
        pdf_parser.parse_all_pages()
        pdf_parser.save_to_csv(args.output)

        # İstatistikleri yazdır
        stats = pdf_parser.get_statistics()
        logger.info(f"İstatistikler: {stats}")

        return 0

    except Exception as e:
        logger.error(f"Hata oluştu: {e}")
        return 1

    finally:
        pdf_parser.close_pdf()


if __name__ == '__main__':
    sys.exit(main())