#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
from typing import Optional, List, Tuple, Dict
from difflib import get_close_matches
from functools import lru_cache
import pandas as pd

# Local imports
try:
    from config import *
    from utils import *
except ImportError:
    print("HATA: config.py ve utils.py dosyaları gerekli!")
    print("Lütfen tüm dosyaları aynı klasöre yerleştirin.")
    sys.exit(1)


class TrendyolCommissionLookup:
    def __init__(self):
        self.logger = setup_logging(str(LOG_PATH), LOG_LEVEL)
        self.df = None
        self.search_cache = {}
        self.load_data()

    def load_data(self) -> None:
        """CSV dosyasını yükler ve normalize eder"""
        try:
            if not CSV_PATH.exists():
                raise FileNotFoundError(f"CSV dosyası bulunamadı: {CSV_PATH}")

            self.df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
            self.logger.info(f"CSV yüklendi: {len(self.df)} satır")

            required_columns = ["Kategori", "Alt Kategori", "Ürün Grubu", "Komisyon_%_KDV_Dahil"]
            missing = [col for col in required_columns if col not in self.df.columns]
            if missing:
                raise ValueError(f"CSV'de eksik sütunlar: {', '.join(missing)}")

            # CRITICAL FIX: Ensure all text columns are strings before normalization
            self.df["Kategori"] = self.df["Kategori"].astype(str)
            self.df["Alt Kategori"] = self.df["Alt Kategori"].astype(str)
            self.df["Ürün Grubu"] = self.df["Ürün Grubu"].astype(str)

            # Create normalized search columns
            self.df["_kategori_norm"] = self.df["Kategori"].apply(normalize_text)
            self.df["_alt_kategori_norm"] = self.df["Alt Kategori"].apply(normalize_text)
            self.df["_urun_grubu_norm"] = self.df["Ürün Grubu"].apply(normalize_text)

            self.logger.info(f"Kategoriler: {self.df['Kategori'].nunique()}")
            self.logger.info(f"Alt kategoriler: {self.df['Alt Kategori'].nunique()}")
            self.logger.info(f"Ürün grupları: {self.df['Ürün Grubu'].nunique()}")

        except Exception as e:
            self.logger.error(f"Veri yüklenemedi: {e}")
            raise

    @lru_cache(maxsize=CACHE_SIZE)
    def search_products(self, query: str) -> pd.DataFrame:
        """Ürün arama fonksiyonu"""
        query_norm = normalize_text(query)
        self.logger.debug(f"Arama yapılıyor: '{query}' -> '{query_norm}'")

        if not query_norm:
            return pd.DataFrame(columns=self.df.columns)

        # 1. Exact word match in product groups
        exact_word_pattern = create_search_pattern(query_norm, exact_word=True)
        mask_exact = self.df["_urun_grubu_norm"].str.contains(exact_word_pattern, regex=True, na=False)
        exact_results = self.df[mask_exact]

        if not exact_results.empty:
            self.logger.debug(f"Tam kelime eşleşmesi bulundu: {len(exact_results)} sonuç")
            return exact_results

        # 2. Partial match in product groups
        partial_pattern = create_search_pattern(query_norm, exact_word=False)
        mask_partial = self.df["_urun_grubu_norm"].str.contains(partial_pattern, regex=True, na=False)
        partial_results = self.df[mask_partial]

        if not partial_results.empty:
            self.logger.debug(f"Kısmi eşleşme bulundu: {len(partial_results)} sonuç")
            return partial_results

        # 3. Category and subcategory search
        mask_category = (
                self.df["_kategori_norm"].str.contains(partial_pattern, regex=True, na=False) |
                self.df["_alt_kategori_norm"].str.contains(partial_pattern, regex=True, na=False)
        )
        category_results = self.df[mask_category]

        if not category_results.empty:
            self.logger.debug(f"Kategori eşleşmesi bulundu: {len(category_results)} sonuç")
            return category_results

        # 4. Fuzzy matching
        all_product_groups = get_unique_values_from_column(self.df, "Ürün Grubu")
        fuzzy_matches = get_close_matches(
            query, all_product_groups,
            n=MAX_FUZZY_RESULTS,
            cutoff=MIN_SIMILARITY_THRESHOLD
        )

        if fuzzy_matches:
            self.logger.debug(f"Fuzzy eşleşme bulundu: {fuzzy_matches}")
            fuzzy_results = self.df[self.df["Ürün Grubu"].isin(fuzzy_matches)]
            return fuzzy_results

        # 5. Broad search across all text fields
        broad_mask = (
                self.df["_kategori_norm"].str.contains(partial_pattern, regex=True, na=False) |
                self.df["_alt_kategori_norm"].str.contains(partial_pattern, regex=True, na=False) |
                self.df["_urun_grubu_norm"].str.contains(partial_pattern, regex=True, na=False)
        )
        broad_results = self.df[broad_mask]

        if not broad_results.empty:
            self.logger.debug(f"Geniş arama sonucu: {len(broad_results)} sonuç")
            return broad_results

        self.logger.debug("Hiçbir eşleşme bulunamadı")
        return pd.DataFrame(columns=self.df.columns)

    def get_best_match(self, results: pd.DataFrame) -> Optional[pd.Series]:
        """En iyi eşleşmeyi bulur"""
        if results.empty:
            return None

        grouped = (
            results.groupby(["Kategori", "Alt Kategori", "Ürün Grubu"], dropna=False)
            ["Komisyon_%_KDV_Dahil"]
            .max()
            .reset_index()
            .sort_values("Komisyon_%_KDV_Dahil", ascending=False)
        )

        return grouped.iloc[0] if not grouped.empty else None

    def get_alternative_matches(self, results: pd.DataFrame, exclude_best: pd.Series) -> pd.DataFrame:
        """Alternatif eşleşmeleri bulur"""
        if results.empty or exclude_best is None:
            return pd.DataFrame()

        alternatives = results[
            ~(
                    (results["Kategori"] == exclude_best["Kategori"]) &
                    (results["Alt Kategori"] == exclude_best["Alt Kategori"]) &
                    (results["Ürün Grubu"] == exclude_best["Ürün Grubu"])
            )
        ]

        if alternatives.empty:
            return pd.DataFrame()

        grouped_alternatives = (
            alternatives.groupby(["Kategori", "Alt Kategori", "Ürün Grubu"], dropna=False)
            ["Komisyon_%_KDV_Dahil"]
            .max()
            .reset_index()
            .sort_values("Komisyon_%_KDV_Dahil", ascending=False)
            .head(MAX_OTHER_RESULTS)
        )

        return grouped_alternatives

    def format_result_display(self, result: pd.Series, show_detailed: bool = True) -> str:
        """Sonuç görüntüleme formatı"""
        if result is None:
            return "Sonuç bulunamadı"

        commission_str = format_commission_display(
            result["Komisyon_%_KDV_Dahil"],
            SHOW_COMMISSION_AS_PERCENTAGE
        )

        if show_detailed:
            return f"""
📦 En İyi Eşleşme:
   🏷️  Kategori     : {result['Kategori']}
   📂  Alt Kategori : {result['Alt Kategori']}
   📋  Ürün Grubu   : {result['Ürün Grubu']}
   💰  Komisyon     : {commission_str}"""
        else:
            return f"{result['Kategori']} > {result['Alt Kategori']} > {result['Ürün Grubu']} | {commission_str}"

    def format_alternatives_display(self, alternatives: pd.DataFrame) -> str:
        """Alternatif sonuçların görüntüleme formatı"""
        if alternatives.empty:
            return ""

        lines = ["\n🔍 Diğer Olası Eşleşmeler:"]

        for _, row in alternatives.iterrows():
            commission_str = format_commission_display(
                row["Komisyon_%_KDV_Dahil"],
                SHOW_COMMISSION_AS_PERCENTAGE
            )
            lines.append(f"   • {row['Kategori']} > {row['Alt Kategori']} > {row['Ürün Grubu']} | {commission_str}")

        return "\n".join(lines)

    def search_and_display(self, query: str) -> bool:
        """Arama yapar ve sonuçları görüntüler"""
        if not query.strip():
            return False

        try:
            results = self.search_products(query.strip())

            if results.empty:
                print(f"\n❌ '{query}' için sonuç bulunamadı.")
                print("💡 Öneriler:")
                print("   • Daha genel bir terim deneyin (örn: 'ütü' yerine 'ev aletleri')")
                print("   • Yazım hatası olup olmadığını kontrol edin")
                print("   • Farklı kelimeler kullanmayı deneyin")
                return False

            best_match = self.get_best_match(results)

            if best_match is None:
                print(f"\n⚠️ '{query}' için uygun komisyon bulunamadı.")
                return False

            print(self.format_result_display(best_match, SHOW_DETAILED_RESULTS))

            if SHOW_DETAILED_RESULTS:
                alternatives = self.get_alternative_matches(results, best_match)
                alternatives_text = self.format_alternatives_display(alternatives)
                if alternatives_text:
                    print(alternatives_text)

            total_matches = len(results.groupby(["Kategori", "Alt Kategori", "Ürün Grubu"]).size())
            if total_matches > 1:
                print(f"\n📊 Toplam {total_matches} farklı ürün grubu eşleşmesi bulundu.")
            return True

        except Exception as e:
            self.logger.error(f"Arama hatası: {e}")
            print(f"\n💥 Arama sırasında hata: {e}")
            return False

    def get_search_suggestions(self, limit: int = 10) -> List[str]:
        """Popüler arama önerileri getirir"""
        try:
            all_products = ' '.join(self.df['Ürün Grubu'].astype(str).tolist())
            words = re.findall(r'\b\w{3,}\b', all_products.lower())
            word_freq = {}
            for word in words:
                if word not in ['için', 'ile', 'olan', 'her', 'tüm']:  # Stop words
                    word_freq[word] = word_freq.get(word, 0) + 1
            popular_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            return [word for word, freq in popular_words[:limit]]

        except Exception as e:
            self.logger.warning(f"Öneri oluşturulamadı: {e}")
            return ["telefon", "ayakkabı", "kitap", "elektronik", "giyim"]

    def show_statistics(self) -> None:
        """Sistem istatistiklerini gösterir"""
        if self.df is None:
            return

        print(f"""
📈 Sistem İstatistikleri:
   📁 Toplam kayıt      : {len(self.df):,}
   🏷️ Kategori sayısı    : {self.df['Kategori'].nunique():,}
   📂 Alt kategori sayısı: {self.df['Alt Kategori'].nunique():,}
   📋 Ürün grubu sayısı  : {self.df['Ürün Grubu'].nunique():,}
   💰 Ort. komisyon     : {self.df['Komisyon_%_KDV_Dahil'].mean():.2f}%
   📊 Min/Max komisyon  : {self.df['Komisyon_%_KDV_Dahil'].min():.2f}% / {self.df['Komisyon_%_KDV_Dahil'].max():.2f}%
   🗂️ CSV dosyası       : {CSV_PATH}""")

    def interactive_search(self) -> None:
        """Etkileşimli arama arayüzü"""
        print(f"""
🔍 Trendyol Komisyon Sorgulama Sistemi v2
{'=' * 50}
📋 Kullanım: Ürün adı girin (örn: 'telefon', 'ayakkabı', 'kitap')
💡 Komutlar: 
   • 'stats' - sistem istatistikleri
   • 'help' - yardım
   • 'clear' - ekranı temizle
   • Enter (boş) - çıkış
""")

        suggestions = self.get_search_suggestions(8)
        if suggestions:
            print(f"🎯 Popüler aramalar: {', '.join(suggestions)}")
        print("-" * 50)

        while True:
            try:
                query = input("\n🔍 Ürün adı: ").strip()

                if not query:
                    print("👋 Çıkılıyor...")
                    break

                if query.lower() == 'stats':
                    self.show_statistics()
                    continue
                elif query.lower() == 'help':
                    print("""
🆘 Yardım:
   • Genel terimler kullanın: 'telefon', 'ayakkabı'
   • Marka isimleri genelde kategori değil: 'samsung' yerine 'telefon'
   • Birden fazla kelime: 'spor ayakkabı', 'cep telefonu'
   • Türkçe karakter kullanabilirsiniz: 'çamaşır makinesi'
                    """)
                    continue
                elif query.lower() == 'clear':
                    import os
                    os.system('cls' if os.name == 'nt' else 'clear')
                    continue

                self.search_and_display(query)

            except KeyboardInterrupt:
                print("\n\n👋 Sistem kapatılıyor...")
                break
            except Exception as e:
                self.logger.error(f"Beklenmeyen hata: {e}")
                print(f"\n💥 Beklenmeyen hata: {e}")


def main():
    try:
        lookup_system = TrendyolCommissionLookup()
        lookup_system.interactive_search()

    except FileNotFoundError as e:
        print(f"\n❌ Dosya hatası: {e}")
        print("💡 Önce extract script'ini çalıştırarak CSV dosyasını oluşturun.")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Sistem hatası: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()