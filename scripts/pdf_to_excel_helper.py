#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF to Excel Helper - Hepsiburada ve N11 için Uyumlu Versiyon
===========================================================
PDF'deki tablo yapısını koruyarak Excel'e aktarır.
Hem N11 hem Hepsiburada için çalışır.
"""

import os
import re
import logging
from typing import Optional, List, Dict
from pathlib import Path

try:
    import pdfplumber
    import pandas as pd
    from openpyxl import Workbook
    from openpyxl.utils.dataframe import dataframe_to_rows
except ImportError as e:
    raise ImportError(f"Gerekli kütüphaneler eksik: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFToExcelConverter:
    def __init__(self):
        self.logger = logger

    def extract_tables_with_structure(self, pdf_path: str, page_range: Optional[str] = None) -> List[Dict]:
        """PDF'den tablo verilerini yapısal olarak çıkar"""
        tables_data = []

        with pdfplumber.open(pdf_path) as pdf:
            pages = self._get_pages_to_process(pdf, page_range)
            self.logger.info(f"İşlenecek sayfalar: {len(pages)}")

            for page_num in pages:
                try:
                    page = pdf.pages[page_num - 1]
                    if page_num % 10 == 0:
                        self.logger.info(f"Sayfa {page_num}/{len(pages)}")

                    # Önce tabloları dene - birden fazla yöntemle
                    page_tables = self._extract_page_tables(page, page_num)
                    if page_tables:
                        tables_data.extend(page_tables)
                        continue

                    # Tablo bulunamazsa metni satır satır al
                    text_data = self._extract_page_text(page, page_num)
                    if text_data:
                        tables_data.append(text_data)

                except Exception as e:
                    self.logger.warning(f"Sayfa {page_num} işlenirken hata: {e}")

        self.logger.info(f"Toplam {len(tables_data)} veri bloğu bulundu")
        return tables_data

    def _extract_page_tables(self, page, page_num: int) -> List[Dict]:
        """Sayfadan tabloları çıkar - çoklu yöntem"""
        page_tables = []

        # Farklı table extraction ayarları
        table_settings = [
            {},  # Varsayılan
            {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
            {"vertical_strategy": "text", "horizontal_strategy": "text"},
            {"vertical_strategy": "lines", "horizontal_strategy": "text"}
        ]

        for i, settings in enumerate(table_settings):
            try:
                tables = page.extract_tables(table_settings=settings)
                if tables:
                    for table_idx, table in enumerate(tables):
                        if table and len(table) > 1:  # En az 2 satır
                            cleaned_table = self._clean_table(table)
                            if cleaned_table:
                                page_tables.append({
                                    'page': page_num,
                                    'type': 'table',
                                    'method': f'extract_tables_{i}',
                                    'data': cleaned_table
                                })
                    if page_tables:  # İlk başarılı yöntemi kullan
                        break
            except:
                continue

        return page_tables

    def _extract_page_text(self, page, page_num: int) -> Optional[Dict]:
        """Sayfadan metin çıkar"""
        try:
            text = page.extract_text()
            if text:
                lines = text.split('\n')
                structured_lines = self._structure_text_lines(lines)
                if structured_lines:
                    return {
                        'page': page_num,
                        'type': 'text',
                        'method': 'extract_text',
                        'data': structured_lines
                    }
        except:
            pass
        return None

    def _clean_table(self, table: List[List]) -> List[List]:
        """Tabloyu temizle"""
        cleaned = []
        for row in table:
            if not row:
                continue

            cleaned_row = []
            for cell in row:
                if cell is None:
                    cleaned_row.append('')
                else:
                    # Temizlik
                    cell_str = str(cell).strip()
                    cell_str = cell_str.replace('\u00a0', ' ')
                    cell_str = re.sub(r'\s+', ' ', cell_str)
                    cleaned_row.append(cell_str)

            # Boş olmayan satırları ekle
            if any(cell.strip() for cell in cleaned_row):
                cleaned.append(cleaned_row)

        return cleaned

    def _structure_text_lines(self, lines: List[str]) -> List[List[str]]:
        """Metin satırlarını tablo yapısına dönüştür"""
        structured = []

        for line in lines:
            if not line.strip():
                continue

            # Farklı ayırıcıları dene
            parts = None
            separators = [
                r'\s*\|\s*',  # Pipe
                r'\s{3,}',  # 3+ boşluk
                r'\t+',  # Tab
                r'\s{2,}(?=\S)',  # 2+ boşluk, sonrasında karakter
            ]

            for sep in separators:
                test_parts = re.split(sep, line)
                test_parts = [p.strip() for p in test_parts if p.strip()]

                if len(test_parts) > 1:
                    parts = test_parts
                    break

            # Hiçbiri işe yaramazsa tek sütun
            if not parts:
                clean_line = line.strip()
                if clean_line:
                    parts = [clean_line]

            if parts:
                structured.append(parts)

        return structured

    def _get_pages_to_process(self, pdf, page_range: Optional[str]) -> List[int]:
        """İşlenecek sayfa listesini belirle"""
        total_pages = len(pdf.pages)

        if not page_range:
            return list(range(1, total_pages + 1))

        pages = []
        for part in page_range.split(','):
            part = part.strip()
            if '-' in part:
                start, end = map(int, part.split('-'))
                pages.extend(range(max(1, start), min(total_pages + 1, end + 1)))
            else:
                page_num = int(part)
                if 1 <= page_num <= total_pages:
                    pages.append(page_num)

        return sorted(set(pages))

    def convert_to_excel(self, pdf_path: str, excel_path: str,
                         page_range: Optional[str] = None) -> Dict:
        """PDF'i Excel'e dönüştür"""

        # Tabloları çıkar
        tables_data = self.extract_tables_with_structure(pdf_path, page_range)

        if not tables_data:
            raise ValueError("PDF'den veri çıkarılamadı")

        # Excel workbook oluştur
        wb = Workbook()

        # Ana sayfa - işlenmiş veri
        ws_main = wb.active
        ws_main.title = "Processed_Data"

        # Ham veri sayfası
        ws_raw = wb.create_sheet("Raw_Data")

        # Ana sayfa başlıkları (genel format)
        main_headers = [
            "Sayfa_No",
            "Satir_No",
            "Method",
            "Ana_Kategori",
            "Kategori",
            "Alt_Kategori",
            "Urun_Grubu",
            "Komisyon",
            "Marka_Komisyon",
            "Vade",
            "Ham_Veri"
        ]
        ws_main.append(main_headers)

        # Ham veri başlıkları
        raw_headers = ["Sayfa", "Method", "Satir_No", "Ham_Veri"]
        ws_raw.append(raw_headers)

        # Verileri işle
        main_row_count = 0
        raw_row_count = 0

        for table_info in tables_data:
            page_num = table_info['page']
            method = table_info.get('method', 'unknown')
            data = table_info['data']

            # Her satırı işle
            for row_idx, row_data in enumerate(data, 1):
                # Ham veriye ekle
                if isinstance(row_data, list):
                    raw_text = ' | '.join([str(cell) for cell in row_data])
                else:
                    raw_text = str(row_data)

                ws_raw.append([page_num, method, row_idx, raw_text])
                raw_row_count += 1

                # Ana veriye işlenmiş hali ekle
                processed_row = self._process_row_for_excel(
                    row_data, page_num, row_idx, method
                )

                if processed_row:
                    ws_main.append(processed_row)
                    main_row_count += 1

        # Excel'i kaydet
        os.makedirs(os.path.dirname(excel_path) or '.', exist_ok=True)
        wb.save(excel_path)

        self.logger.info(f"Excel dosyası oluşturuldu: {excel_path}")
        self.logger.info(f"İşlenmiş veri: {main_row_count} satır")
        self.logger.info(f"Ham veri: {raw_row_count} satır")

        return {
            'rows_processed': main_row_count,
            'rows_raw': raw_row_count,
            'sheets': ['Processed_Data', 'Raw_Data'],
            'status': 'success'
        }

    def _process_row_for_excel(self, row_data, page_num: int,
                               row_idx: int, method: str) -> Optional[List]:
        """Satırı Excel için işle"""
        if isinstance(row_data, list):
            cells = row_data
            raw_text = ' | '.join([str(cell) for cell in cells])
        else:
            cells = [str(row_data)]
            raw_text = str(row_data)

        # Boş satırları atla
        if not raw_text.strip():
            return None

        # Başlık satırlarını atla
        if self._is_header_row(raw_text):
            return None

        # Kategori ve komisyon bilgilerini çıkarmaya çalış
        ana_kategori = ""
        kategori = ""
        alt_kategori = ""
        urun_grubu = ""
        komisyon = ""
        marka_komisyon = ""
        vade = ""

        # Hücreleri analiz et
        for i, cell in enumerate(cells):
            cell_str = str(cell).strip()
            if not cell_str:
                continue

            # Sayısal değerler (komisyon olabilir)
            if self._is_commission_value(cell_str):
                if not komisyon:
                    komisyon = cell_str
                elif not marka_komisyon:
                    marka_komisyon = cell_str

            # Vade (gün sayısı)
            elif self._is_vade_value(cell_str):
                vade = cell_str

            # Kategori bilgileri (sayı içermeyenler)
            elif not re.search(r'\d', cell_str) and len(cell_str) > 2:
                if not ana_kategori:
                    ana_kategori = cell_str
                elif not kategori:
                    kategori = cell_str
                elif not alt_kategori:
                    alt_kategori = cell_str
                elif not urun_grubu:
                    urun_grubu = cell_str

        return [
            page_num,
            row_idx,
            method,
            ana_kategori,
            kategori,
            alt_kategori,
            urun_grubu,
            komisyon,
            marka_komisyon,
            vade,
            raw_text
        ]

    def _is_header_row(self, text: str) -> bool:
        """Başlık satırı mı kontrol et"""
        text_lower = text.lower()
        header_keywords = [
            'kategori', 'komisyon', 'kdv', 'pazarlama', 'pazaryeri',
            'hakediş', 'vade', 'marka', 'ürün grup', 'ana kategori'
        ]
        return sum(1 for kw in header_keywords if kw in text_lower) >= 2

    def _is_commission_value(self, text: str) -> bool:
        """Komisyon değeri mi kontrol et"""
        patterns = [
            r'\d+[,.]?\d*\s*%',  # Yüzde
            r'\d+[,.]?\d*\s*\+\s*KDV',  # Sayı + KDV
            r'%\s*\d+[,.]?\d*',  # % + Sayı
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

    def _is_vade_value(self, text: str) -> bool:
        """Vade değeri mi kontrol et (gün sayısı)"""
        # Sadece sayı ve "gün" içeriyorsa
        pattern = r'^\d+(\s*(gün|gun|iş\s*gün|is\s*gun))?\s*$'
        return bool(re.match(pattern, text.lower()))


def pdf_to_excel(pdf_path: str, out_xlsx_path: str,
                 page_range: Optional[str] = None, **kwargs) -> dict:
    """Ana fonksiyon - mevcut kodla uyumluluk için"""
    converter = PDFToExcelConverter()
    return converter.convert_to_excel(pdf_path, out_xlsx_path, page_range)


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="PDF to Excel Converter - Universal")
    parser.add_argument("--pdf", required=True, help="PDF dosya yolu")
    parser.add_argument("--out", required=True, help="Excel çıktı yolu")
    parser.add_argument("--page-range", default=None, help="Sayfa aralığı")
    parser.add_argument("--debug", action="store_true", help="Debug modu")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        result = pdf_to_excel(args.pdf, args.out, args.page_range)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"❌ Hata: {e}")
        sys.exit(1)