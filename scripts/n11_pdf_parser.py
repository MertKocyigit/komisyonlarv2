#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
N11 PDF Parser - Kategori yapısını doğru çıkaran versiyon
"""

import re
import pdfplumber
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional


class N11PDFParserFixed:
    def __init__(self):
        self.data_rows = []

    def parse_pdf(self, pdf_path: str) -> pd.DataFrame:
        """PDF'i parse et ve DataFrame döndür"""
        print(f"📄 PDF işleniyor: {pdf_path}")

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"Toplam {total_pages} sayfa")

            for page_num, page in enumerate(pdf.pages, 1):
                if page_num % 10 == 0:
                    print(f"  Sayfa {page_num}/{total_pages} işleniyor...")

                # Tabloları al
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        self._process_table(table)

        # DataFrame oluştur
        if not self.data_rows:
            print("⚠️ Veri çıkarılamadı!")
            return pd.DataFrame()

        df = pd.DataFrame(self.data_rows)

        # Temizlik
        df = df.drop_duplicates()
        df = df.sort_values(by=['Ana Kategori', 'Kategori', 'Alt Kategori', 'Ürün Grubu'])

        print(f"✅ {len(df)} satır veri çıkarıldı")
        return df

    def _process_table(self, table: List[List[str]]):
        """Tabloyu işle"""
        for row in table:
            if not row or not row[0]:
                continue

            cell_text = str(row[0])

            # Başlıkları atla
            if self._is_header(cell_text):
                continue

            # Komisyon verisi var mı kontrol et
            if re.search(r'\d+\s+\d+\s+%[\d,\.]+\s*\+\s*KDV', cell_text):
                parsed = self._parse_row(cell_text)
                if parsed:
                    self.data_rows.append(parsed)

    def _is_header(self, text: str) -> bool:
        """Başlık satırı mı?"""
        headers = ['Kategori Ağacı', 'Komisyon Oranları', 'Kampanyalı',
                   'tarihine kadar', 'Hakediş', 'Pazarlama', 'Pazaryeri']
        return any(h in text for h in headers)

    def _parse_row(self, text: str) -> Optional[Dict]:
        """Satırı parse et"""
        lines = text.strip().split('\n')

        # Komisyon satırını bul (örn: "18 18 %1 + KDV 24")
        data_line = None
        data_index = -1

        for i, line in enumerate(lines):
            # Pattern: sayı sayı %değer+KDV [%değer+KDV] sayı
            if re.search(r'(\d+)\s+(\d+)\s+(%[\d,\.]+\s*\+\s*KDV)', line):
                data_line = line
                data_index = i
                break

        if not data_line:
            return None

        # Komisyon verilerini çıkar
        komisyon_match = re.search(r'(\d+)\s+(\d+)', data_line)
        if not komisyon_match:
            return None

        komisyon = float(komisyon_match.group(1))
        kampanyali = float(komisyon_match.group(2))

        # Pazarlama/Pazaryeri bedellerini çıkar
        fee_matches = re.findall(r'(%[\d,\.]+\s*\+\s*KDV)', data_line)
        pazarlama = fee_matches[0] if len(fee_matches) > 0 else '%1 + KDV'
        pazaryeri = fee_matches[1] if len(fee_matches) > 1 else pazarlama

        # Hakediş gününü çıkar
        gun_match = re.search(r'KDV\s+(\d+)$', data_line)
        gun = int(gun_match.group(1)) if gun_match else 24

        # Kategori bilgilerini çıkar
        categories = self._extract_categories(lines, data_index)

        return {
            'Ana Kategori': categories['ana'],
            'Kategori': categories['kategori'],
            'Alt Kategori': categories['alt'],
            'Ürün Grubu': categories['urun'],
            'Komisyon_%_KDV_Dahil': komisyon,
            'Kampanyalı_Komisyon_%_KDV_Dahil': kampanyali,
            'Pazarlama_Hizmet_Bedeli': pazarlama,
            'Pazaryeri_Hizmet_Bedeli': pazaryeri,
            'Hakediş_İş_Günü': gun
        }

    def _extract_categories(self, lines: List[str], data_index: int) -> Dict[str, str]:
        """Kategori bilgilerini çıkar"""
        # Veri satırından önceki satırları al
        category_lines = lines[:data_index] if data_index > 0 else []

        # Tüm kategori satırlarını birleştir
        full_text = ' '.join(category_lines).strip()

        # Ana kategoriyi tespit et
        ana_kategori = "Ayakkabı & Çanta"  # Default

        # "Ayakkabı & Çanta" ifadesini temizle
        clean_text = full_text.replace('Ayakkabı &', '').replace('Çanta', '').strip()

        # Özel durumları kontrol et
        if 'Bavul' in full_text or 'Valiz' in full_text:
            return self._parse_bavul_categories(full_text)
        elif 'Çocuk Ayakkabı' in full_text:
            return self._parse_cocuk_ayakkabi(full_text)
        elif 'Erkek Ayakkabı' in full_text:
            return self._parse_erkek_ayakkabi(full_text)
        elif 'Kadın Ayakkabı' in full_text:
            return self._parse_kadin_ayakkabi(full_text)
        elif 'Ayakkabı Bakım' in full_text:
            return self._parse_bakim_urunleri(full_text)
        else:
            # Genel parse
            return self._parse_general(clean_text, ana_kategori)

    def _parse_bavul_categories(self, text: str) -> Dict[str, str]:
        """Bavul & Valiz kategorilerini parse et"""
        kategori = "Bavul & Valiz"

        if 'Seyahat Çanta' in text:
            alt = "Seyahat Çantaları"
            urun = "Seyahat Çantaları"
        elif 'Valiz Seti' in text:
            alt = "Valiz Seti"
            urun = "Valiz Seti"
        elif 'Çocuk Valiz' in text:
            alt = "Çocuk Valizleri"
            urun = "Çocuk Valizleri"
        elif 'Kozmetik' in text:
            alt = "Seyahat Kozmetik Çantaları"
            urun = "Seyahat Kozmetik Çantaları"
        elif 'Valiz Kılıf' in text:
            alt = "Valiz Kılıfı & Aksesuar"
            urun = "Valiz Kılıfı & Aksesuar"
        else:
            alt = kategori
            urun = kategori

        return {
            'ana': 'Ayakkabı & Çanta',
            'kategori': kategori,
            'alt': alt,
            'urun': urun
        }

    def _parse_cocuk_ayakkabi(self, text: str) -> Dict[str, str]:
        """Çocuk ayakkabı kategorilerini parse et"""
        kategori = "Çocuk Ayakkabı"

        if 'Erkek Çocuk' in text:
            alt = "Erkek Çocuk Ayakkabı"
            if 'Bot' in text or 'Çizme' in text:
                urun = "Erkek Çocuk Bot & Çizme"
            elif 'Günlük' in text:
                urun = "Erkek Çocuk Günlük Ayakkabı"
            elif 'Terlik' in text:
                urun = "Erkek Çocuk Terlik"
            elif 'Sandalet' in text:
                urun = "Erkek Çocuk Sandalet"
            elif 'Ev Terliği' in text or 'Panduf' in text:
                urun = "Erkek Çocuk Ev Terliği & Panduf"
            else:
                urun = alt

        elif 'Kız Çocuk' in text:
            alt = "Kız Çocuk Ayakkabı"
            if 'Günlük' in text:
                urun = "Kız Çocuk Günlük Ayakkabı"
            elif 'Terlik' in text:
                urun = "Kız Çocuk Terlik"
            elif 'Bot' in text or 'Çizme' in text:
                urun = "Kız Çocuk Bot & Çizme"
            else:
                urun = alt
        else:
            alt = kategori
            urun = kategori

        return {
            'ana': 'Ayakkabı & Çanta',
            'kategori': kategori,
            'alt': alt,
            'urun': urun
        }

    def _parse_erkek_ayakkabi(self, text: str) -> Dict[str, str]:
        """Erkek ayakkabı kategorilerini parse et"""
        kategori = "Erkek Ayakkabı"
        alt = "Erkek Ayakkabı"

        if 'Plaj Terliği' in text:
            urun = "Erkek Plaj Terliği"
        elif 'Deniz Ayakkabı' in text:
            urun = "Erkek Deniz Ayakkabısı"
        elif 'Ev Terliği' in text or 'Panduf' in text:
            urun = "Erkek Ev Terliği & Panduf"
        elif 'Terlik' in text and 'Sandalet' in text:
            urun = "Erkek Terlik & Sandalet"
        elif 'Günlük' in text:
            urun = "Erkek Günlük Ayakkabı"
        elif 'Bot' in text:
            urun = "Erkek Bot"
        else:
            urun = alt

        return {
            'ana': 'Ayakkabı & Çanta',
            'kategori': kategori,
            'alt': alt,
            'urun': urun
        }

    def _parse_kadin_ayakkabi(self, text: str) -> Dict[str, str]:
        """Kadın ayakkabı kategorilerini parse et"""
        kategori = "Kadın Ayakkabı"
        alt = "Kadın Ayakkabı"

        if 'Günlük' in text:
            urun = "Kadın Günlük Ayakkabı"
        elif 'Topuklu' in text:
            urun = "Kadın Topuklu Ayakkabı"
        elif 'Terlik' in text:
            urun = "Kadın Terlik"
        elif 'Bot' in text or 'Çizme' in text:
            urun = "Kadın Bot & Çizme"
        elif 'Spor' in text:
            urun = "Kadın Spor Ayakkabı"
        else:
            urun = alt

        return {
            'ana': 'Ayakkabı & Çanta',
            'kategori': kategori,
            'alt': alt,
            'urun': urun
        }

    def _parse_bakim_urunleri(self, text: str) -> Dict[str, str]:
        """Bakım ürünleri kategorilerini parse et"""
        kategori = "Ayakkabı Bakım Ürünleri"

        if 'Boyası' in text or 'Spreyi' in text:
            alt = "Ayakkabı Boyası & Spreyi"
            urun = "Ayakkabı Boyası & Spreyi"
        elif 'Tamir' in text:
            alt = "Ayakkabı Tamir Malzemeleri"
            urun = "Ayakkabı Tamir Malzemeleri"
        else:
            alt = kategori
            urun = kategori

        return {
            'ana': 'Ayakkabı & Çanta',
            'kategori': kategori,
            'alt': alt,
            'urun': urun
        }

    def _parse_general(self, text: str, ana_kategori: str) -> Dict[str, str]:
        """Genel kategori parse"""
        # Boşluklarla ayır
        parts = [p.strip() for p in re.split(r'\s{2,}', text) if p.strip() and len(p) > 2]

        # Filtreleme
        parts = [p for p in parts if not any(skip in p for skip in ['%', 'KDV', '+'])]

        if len(parts) >= 3:
            return {
                'ana': ana_kategori,
                'kategori': parts[0],
                'alt': parts[1],
                'urun': parts[2]
            }
        elif len(parts) == 2:
            return {
                'ana': ana_kategori,
                'kategori': parts[0],
                'alt': parts[1],
                'urun': parts[1]
            }
        elif len(parts) == 1:
            return {
                'ana': ana_kategori,
                'kategori': parts[0],
                'alt': parts[0],
                'urun': parts[0]
            }
        else:
            return {
                'ana': ana_kategori,
                'kategori': 'Diğer',
                'alt': 'Diğer',
                'urun': 'Diğer'
            }


def main():
    """Ana fonksiyon"""
    pdf_path = r"C:\Users\CASPER\Downloads\n11_Komisyon_Oranlari-2025.pdf"
    output_base = r"C:\Users\CASPER\Downloads\n11_komisyon_fixed"

    parser = N11PDFParserFixed()
    df = parser.parse_pdf(pdf_path)

    if not df.empty:
        # Excel kaydet
        excel_path = Path(output_base).with_suffix('.xlsx')
        df.to_excel(excel_path, index=False)
        print(f"📊 Excel kaydedildi: {excel_path}")

        # CSV kaydet
        csv_path = Path(output_base).with_suffix('.csv')
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"📄 CSV kaydedildi: {csv_path}")

        # İstatistikler
        print(f"\n📈 İstatistikler:")
        print(f"  Toplam satır: {len(df)}")
        print(f"  Benzersiz kategoriler: {df['Kategori'].nunique()}")
        print(f"  Ortalama komisyon: {df['Komisyon_%_KDV_Dahil'].mean():.2f}%")

        # İlk 10 satırı göster
        print(f"\n📋 İlk 10 satır:")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 200)
        pd.set_option('display.max_colwidth', 30)
        print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()