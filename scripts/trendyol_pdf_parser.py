#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trendyol PDF Parser
-------------------
Trendyol komisyon PDF'lerini parse eder ve standart CSV formatında çıktı verir.
Karmaşık 14-sütunlu tablo yapısını destekler.

Usage:
    python scripts/trendyol_pdf_parser.py --pdf "path/to/trendyol.pdf" --output "output.csv"
"""

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF yüklü değil. Yüklemek için: pip install PyMuPDF")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("trendyol_pdf_parser")


class TrendyolPDFParser:
    """Trendyol PDF komisyon listesini parse eder."""

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

    def extract_table_data_from_page(self, page_num: int) -> List[Dict[str, str]]:
        """Bir sayfadan 14-sütunlu tablo verilerini çıkarır."""
        page = self.doc[page_num]
        text = page.get_text()

        logger.debug(f"Sayfa {page_num + 1} işleniyor...")

        # Tabloyu tablomatik olarak çıkarmaya çalış
        tables = page.find_tables()
        page_data = []

        if tables:
            logger.debug(f"Sayfa {page_num + 1}'de {len(tables)} tablo bulundu")

            for table_idx, table in enumerate(tables):
                try:
                    # Tabloyu pandas DataFrame olarak al
                    df = table.to_pandas()
                    logger.debug(f"Tablo {table_idx + 1}: {df.shape[0]} satır, {df.shape[1]} sütun")

                    # Sütun sayısı kontrolü (14 sütun bekliyoruz)
                    if df.shape[1] >= 10:  # En az 10 sütun olmalı
                        page_data.extend(self.process_table_dataframe(df, page_num))

                except Exception as e:
                    logger.warning(f"Sayfa {page_num + 1}, tablo {table_idx + 1} işlenemedi: {e}")

        # Eğer tablo bulunamazsa, text-based parsing dene
        if not page_data:
            page_data = self.extract_table_from_text(text, page_num)

        logger.debug(f"Sayfa {page_num + 1}'den {len(page_data)} satır çıkarıldı")
        return page_data

    def process_table_dataframe(self, df, page_num: int) -> List[Dict[str, str]]:
        """DataFrame'den komisyon verilerini çıkarır."""
        data = []

        # Sütun isimlerini standardize et
        columns = [str(col).strip() for col in df.columns]

        # Ana sütunları bul
        category_col = None
        subcategory_col = None
        commission_cols = []

        for i, col in enumerate(columns):
            col_lower = col.lower()
            if 'kategori' in col_lower and 'alt' not in col_lower:
                category_col = i
            elif 'alt' in col_lower and 'kategori' in col_lower:
                subcategory_col = i
            elif '%' in col or 'komisyon' in col_lower:
                commission_cols.append(i)

        # Satırları işle
        for idx, row in df.iterrows():
            try:
                row_values = [str(val).strip() if val is not None else "" for val in row]

                # Boş satırları atla
                if all(not val or val == 'nan' for val in row_values):
                    continue

                # Kategori bilgilerini al
                category = ""
                subcategory = ""

                if category_col is not None and category_col < len(row_values):
                    category = self.clean_text(row_values[category_col])

                if subcategory_col is not None and subcategory_col < len(row_values):
                    subcategory = self.clean_text(row_values[subcategory_col])

                # Eğer kategori bilgisi yoksa, satırı atla
                if not category or category == 'nan':
                    continue

                # Komisyon oranlarını bul
                commission_rates = []
                for col_idx in commission_cols:
                    if col_idx < len(row_values):
                        rate = self.parse_commission_rate(row_values[col_idx])
                        if rate is not None:
                            commission_rates.append(rate)

                # En düşük komisyon oranını al (varsa)
                if commission_rates:
                    min_commission = min(commission_rates)

                    # Ürün grubu olarak kategori kullan (subcategory yoksa)
                    product_group = subcategory if subcategory and subcategory != 'nan' else category

                    data.append({
                        'Kategori': category,
                        'Alt Kategori': subcategory if subcategory and subcategory != 'nan' else category,
                        'Ürün Grubu': product_group,
                        'Komisyon_%_KDV_Dahil': f"{min_commission:.2f}"
                    })

            except Exception as e:
                logger.warning(f"Sayfa {page_num + 1}, satır {idx} işlenemedi: {e}")
                continue

        return data

    def extract_table_from_text(self, text: str, page_num: int) -> List[Dict[str, str]]:
        """Text-based parsing (fallback method)."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        data = []

        current_category = ""

        for line in lines:
            line = self.clean_text(line)
            if not line or len(line) < 3:
                continue

            # Komisyon oranı tespit et
            commission_match = re.search(r'(\d+[,.]?\d*)\s*%', line)
            if commission_match:
                commission = self.parse_commission_rate(commission_match.group(1))

                # Komisyon satırından kategori bilgisini çıkar
                category_part = re.sub(r'\d+[,.]?\d*\s*%.*$', '', line).strip()

                if category_part and commission:
                    # Kategori ve alt kategori ayrımı yap
                    parts = category_part.split()
                    if len(parts) >= 2:
                        category = parts[0]
                        subcategory = ' '.join(parts[1:])
                    else:
                        category = category_part
                        subcategory = category_part

                    data.append({
                        'Kategori': category,
                        'Alt Kategori': subcategory,
                        'Ürün Grubu': subcategory,
                        'Komisyon_%_KDV_Dahil': f"{commission:.2f}"
                    })

            # Ana kategori tespiti
            elif line.isupper() and len(line.split()) <= 3:
                current_category = line

        return data

    def parse_all_pages(self) -> None:
        """Tüm sayfaları parse eder."""
        if not self.doc:
            raise RuntimeError("PDF açılmamış")

        all_data = []
        for page_num in range(self.doc.page_count):
            try:
                page_data = self.extract_table_data_from_page(page_num)
                all_data.extend(page_data)
            except Exception as e:
                logger.warning(f"Sayfa {page_num + 1} işlenirken hata: {e}")

        # Tekrar eden verileri temizle
        seen = set()
        self.commission_data = []

        for item in all_data:
            # Benzersizlik anahtarı oluştur
            key = (item['Kategori'], item['Alt Kategori'], item['Ürün Grubu'], item['Komisyon_%_KDV_Dahil'])
            if key not in seen:
                seen.add(key)
                self.commission_data.append(item)

        logger.info(f"Toplam {len(self.commission_data)} benzersiz ürün grubu çıkarıldı")

    def save_to_csv(self, output_path: str) -> None:
        """Standart formatında CSV olarak kaydet."""
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
    parser = argparse.ArgumentParser(description="Trendyol PDF komisyon parser")
    parser.add_argument('--pdf', required=True, help='PDF dosyası yolu')
    parser.add_argument('--output', required=True, help='Çıktı CSV dosyası yolu')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])

    args = parser.parse_args()

    # Log seviyesini ayarla
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # PDF'yi parse et
    pdf_parser = TrendyolPDFParser(args.pdf)

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