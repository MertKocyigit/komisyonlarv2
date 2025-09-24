#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

EXCEL_PATH = BASE_DIR / "hepsiburada_komisyon_oranlari_v10_29-08-2024.xlsx"
CSV_PATH   = BASE_DIR / "hepsiburada_commissions_flat.csv"
XLSX_PATH  = BASE_DIR / "hepsiburada_commissions_full.xlsx"
LOG_PATH   = BASE_DIR / "hepsiburada_commission_system.log"

# Excel ayarları
EXCEL_SHEET_INDEX = 0  # İlk sheet'i kullan (index 0)
EXCEL_SHEET_NAME  = None  # None ise index kullanılır
ENCODING_OUTPUT   = "utf-8-sig"

# Header/kolon tanımlama için aliases
HEADER_ALIASES = {
    "ana_kategori": [
        "ana kategori", "main category", "category",
        "ana-kategori", "anakategori", "kategori ana"
    ],
    "kategori": [
        "kategori", "alt ana kategori", "sub main category",
        "katagori", "alt kategori ana", "category"
    ],
    "alt_kategori": [
        "alt kategori", "altkategori", "sub category",
        "subcategory", "alt-kategori", "kategori alt"
    ],
    "urun_grubu": [
        "ürün grubu", "urun grubu", "ürün grubu detayı",
        "urun grubu detayi", "product group", "urun-grubu",
        "grup", "ürün", "urun", "product"
    ],
    "komisyon": [
        "komisyon", "komisyon (+kdv)", "komisyon (kdv dahil)",
        "komisyon % (kdv dahil)", "komisyon oranı",
        "commission", "commission rate", "rate"
    ],
    "marka_komisyon": [
        "marka kategori komisyon", "marka komisyon",
        "marka kategori komisyon (+kdv)",
        "marka komisyon (+kdv)", "brand commission",
        "marka-komisyon", "markakomisyon"
    ],
    "vade": [
        "vade", "payment term", "term", "ödeme vadesi"
    ],
    "marka": [
        "marka", "brand", "marka adı", "brand name"
    ]
}

# Logging ayarları
LOG_LEVEL      = "INFO"
LOG_FORMAT     = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT= "%Y-%m-%d %H:%M:%S"

# Processing ayarları
MIN_SIMILARITY_THRESHOLD = 0.6
MAX_FUZZY_RESULTS        = 10
CACHE_ENABLED            = True
CACHE_SIZE               = 1000

# Veri temizleme ayarları
PRODUCT_GROUP_SEPARATORS  = r"[;,|\n\r]+"  # Ürün grubu ayırıcıları
NORMALIZE_WHITESPACE      = True
FORWARD_FILL_CATEGORIES   = True  # Kategorileri aşağı doğru kopyala

# Validation ayarları
REQUIRE_COMMISSION_VALUE  = True  # Komisyon değeri zorunlu mu?
MIN_COMMISSION_VALUE      = 0.0
MAX_COMMISSION_VALUE      = 50.0

# Output ayarları
INCLUDE_RAW_DATA_IN_XLSX  = True  # XLSX'e ham veri sayfası ekle
SORT_OUTPUT_BY_CATEGORY   = True
DEDUPLICATE_RECORDS       = True  # Aynı kayıtları birleştir

# UI/Display ayarları
UI_LANGUAGE               = "tr"
SHOW_DETAILED_RESULTS     = True
SHOW_COMMISSION_AS_PERCENTAGE = True
DECIMAL_PLACES            = 2

# Debug ayarları
DEBUG_MODE                = False
SAVE_INTERMEDIATE_FILES   = DEBUG_MODE  # Debug modunda ara dosyaları kaydet
VERBOSE_LOGGING           = DEBUG_MODE

# Performance ayarları
CHUNK_SIZE                = 1000  # Büyük dosyalar için chunk boyutu
MAX_MEMORY_USAGE_MB       = 512   # Maksimum bellek kullanımı

# Error handling
CONTINUE_ON_ERRORS        = True  # Hata durumunda devam et
MAX_ERROR_COUNT           = 10    # Maksimum hata sayısı

# Validation rules
VALIDATION_RULES = {
    "kategori_required": True,
    "alt_kategori_required": True,
    "urun_grubu_required": True,
    "komisyon_required": True,
    "min_product_group_length": 2,   # Minimum ürün grubu karakter sayısı
    "max_product_group_length": 200  # Maksimum ürün grubu karakter sayısı
}

# Commission parsing patterns
COMMISSION_PATTERNS = {
    "percentage_with_symbol": r"(\d+(?:[,.]\d+)?)\s*%",
    "percentage_without_symbol": r"(\d+(?:[,.]\d+)?)",
    "decimal_separator": ",",  # Türkçe format (18,5%)
    "thousand_separator": "."
}

# Text normalization settings
TEXT_NORMALIZATION = {
    "remove_extra_spaces": True,
    "convert_to_ascii": False,   # Türkçe karakterleri koru
    "lowercase": False,          # Case'i koru
    "remove_special_chars": False,
    "normalize_unicode": True
}

# Export settings
EXPORT_SETTINGS = {
    "csv_separator": ",",
    "csv_encoding": "utf-8-sig",
    "xlsx_engine": "xlsxwriter",
    "include_index": False,
    "date_format": "%Y-%m-%d",
    "float_format": "%.2f"
}

# Column names for output
OUTPUT_COLUMNS = {
    "ana_kategori": "Ana Kategori",
    "kategori": "Kategori",
    "alt_kategori": "Alt Kategori",
    "urun_grubu": "Ürün Grubu",
    "komisyon": "Komisyon_%_KDV_Dahil",
    "marka_komisyon": "Marka_Kategori_Komisyon_%_KDV_Dahil",
    "uygulanan_komisyon": "Uygulanan_Komisyon_%_KDV_Dahil"
}


def get_env_or_default(env_var: str, default_value):
    """Environment variable'dan değer al, yoksa default kullan."""
    env_value = os.getenv(env_var)
    if env_value is None:
        return default_value

    # Boolean conversion
    if isinstance(default_value, bool):
        return env_value.lower() in ('true', '1', 'yes', 'on')

    # Numeric conversion
    if isinstance(default_value, (int, float)):
        try:
            return type(default_value)(env_value)
        except ValueError:
            return default_value

    return env_value


LOG_LEVEL          = get_env_or_default("HEPSIBURADA_LOG_LEVEL", LOG_LEVEL)
DEBUG_MODE         = get_env_or_default("HEPSIBURADA_DEBUG", DEBUG_MODE)
CONTINUE_ON_ERRORS = get_env_or_default("HEPSIBURADA_CONTINUE_ON_ERRORS", CONTINUE_ON_ERRORS)

CUSTOM_EXCEL_PATH  = os.getenv("HEPSIBURADA_EXCEL_PATH")
if CUSTOM_EXCEL_PATH:
    EXCEL_PATH = Path(CUSTOM_EXCEL_PATH)

CUSTOM_CSV_PATH    = os.getenv("HEPSIBURADA_CSV_PATH")
if CUSTOM_CSV_PATH:
    CSV_PATH = Path(CUSTOM_CSV_PATH)

CUSTOM_XLSX_PATH   = os.getenv("HEPSIBURADA_XLSX_PATH")
if CUSTOM_XLSX_PATH:
    XLSX_PATH = Path(CUSTOM_XLSX_PATH)


N11_EXCEL_PATH = BASE_DIR / "data" / "raw" / "n11" / "n11_komisyon_oranlari_2025_kod_icin.xlsx"
N11_CSV_PATH   = BASE_DIR / "data" / "n11_commissions.csv"  # kanonik CSV (runtime)
N11_XLSX_PATH  = BASE_DIR / "data" / "raw" / "n11" / "n11_commissions_full.xlsx"
N11_LOG_PATH   = BASE_DIR / "n11_commission_system.log"

# N11 Excel sheet ayarları
N11_EXCEL_SHEET_INDEX = 0
N11_EXCEL_SHEET_NAME  = "Komisyon_Oranlari"
N11_ENCODING_OUTPUT   = "utf-8-sig"

# ENV overrides (Windows/CI vs.)
N11_EXCEL_PATH       = Path(get_env_or_default("N11_EXCEL_PATH", N11_EXCEL_PATH))
N11_CSV_PATH         = Path(get_env_or_default("N11_CSV_PATH",   N11_CSV_PATH))
N11_XLSX_PATH        = Path(get_env_or_default("N11_XLSX_PATH",  N11_XLSX_PATH))
N11_LOG_PATH         = Path(get_env_or_default("N11_LOG_PATH",   N11_LOG_PATH))
N11_EXCEL_SHEET_NAME = get_env_or_default("N11_SHEET_NAME",      N11_EXCEL_SHEET_NAME)

# ===========================================================================
# TRENDYOL – yeni
# ===========================================================================
TRENDYOL_EXCEL_PATH = BASE_DIR / "data" / "raw" / "trendyol" / "trendyol_komisyon_oranlari.xlsx"
TRENDYOL_CSV_PATH   = BASE_DIR / "data" / "trendyol_commissions.csv"
TRENDYOL_XLSX_PATH  = BASE_DIR / "data" / "raw" / "trendyol" / "trendyol_commissions_full.xlsx"
TRENDYOL_LOG_PATH   = BASE_DIR / "trendyol_commission_system.log"

TRENDYOL_EXCEL_SHEET_INDEX = 0
TRENDYOL_EXCEL_SHEET_NAME  = None
TRENDYOL_ENCODING_OUTPUT   = "utf-8-sig"

TRENDYOL_EXCEL_PATH       = Path(get_env_or_default("TRENDYOL_EXCEL_PATH", TRENDYOL_EXCEL_PATH))
TRENDYOL_CSV_PATH         = Path(get_env_or_default("TRENDYOL_CSV_PATH",   TRENDYOL_CSV_PATH))
TRENDYOL_XLSX_PATH        = Path(get_env_or_default("TRENDYOL_XLSX_PATH",  TRENDYOL_XLSX_PATH))
TRENDYOL_LOG_PATH         = Path(get_env_or_default("TRENDYOL_LOG_PATH",   TRENDYOL_LOG_PATH))
TRENDYOL_EXCEL_SHEET_NAME = get_env_or_default("TRENDYOL_SHEET_NAME",      TRENDYOL_EXCEL_SHEET_NAME)

# ===========================================================================
# Pazaryeri kaynakları – app.py için tek noktadan CSV/log erişimi
# ===========================================================================
MARKETPLACE_SOURCES = {
    "hepsiburada": {
        "csv_path": CSV_PATH,
        "excel_path": EXCEL_PATH,
        "log_path": LOG_PATH,
    },
    "n11": {
        "csv_path": N11_CSV_PATH,
        "excel_path": N11_EXCEL_PATH,
        "log_path": N11_LOG_PATH,
    },
    "trendyol": {
        "csv_path": TRENDYOL_CSV_PATH,
        "excel_path": TRENDYOL_EXCEL_PATH,
        "log_path": TRENDYOL_LOG_PATH,
    },
}

# ---------------------------------------------------------------------------
# (Opsiyonel) ortak sabitler – app/services tarafında gerekirse kullanılabilir
# ---------------------------------------------------------------------------
DEFAULT_CSV_ENCODING = "utf-8-sig"
DEFAULT_XLSX_ENGINE  = "openpyxl"
