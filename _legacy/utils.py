#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trendyol Komisyon Sistemi - Yardımcı Fonksiyonlar
"""

import re
import logging
from typing import Optional, List, Dict, Any
from functools import lru_cache
import pandas as pd


# Logging yapılandırması
def setup_logging(log_path: str = None, log_level: str = "INFO") -> logging.Logger:
    """Logging sistemini yapılandırır"""
    logger = logging.getLogger("TrendyolCommission")

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, log_level.upper()))

    # Format
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (opsiyonel)
    if log_path:
        try:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Log dosyası oluşturulamadı: {e}")

    return logger


@lru_cache(maxsize=1000)
def normalize_text(text: Any) -> str:
    """
    Metni normalize eder (Türkçe karakter dönüşümü, boşluk temizleme)
    Cache ile performans optimizasyonu
    Mixed type hatalarını önlemek için Any tipini kabul eder
    """
    if text is None or pd.isna(text):
        return ""

    # CRITICAL FIX: Handle any type by converting to string first
    text = str(text).strip().lower()

    if text in ['nan', 'none', '']:
        return ""

    # Türkçe karakter dönüşümü
    turkish_map = str.maketrans("ığüşöçİĞÜŞÖÇ", "igusocIGUSOC")
    text = text.translate(turkish_map)

    # Çoklu boşlukları tek boşluk yap
    text = re.sub(r"\s+", " ", text)

    return text


def parse_commission_to_float(value: Any) -> Optional[float]:
    """
    Komisyon değerini float'a dönüştürür
    Mixed type hatalarını önlemek için güvenli parsing yapar
    """
    if value is None or pd.isna(value):
        return None

    # Convert to string first to handle any type (int, float, str)
    value_str = str(value).strip()
    if not value_str or value_str.lower() in ['nan', 'none', '']:
        return None

    # Sayısal değerleri çıkar
    numbers = re.findall(r"[\d\.,]+", value_str)
    if not numbers:
        return None

    raw_number = numbers[0]

    # Virgül ve nokta işleme
    if "," in raw_number and "." in raw_number:
        # Örnek: 1.234,56 -> 1234.56
        raw_number = raw_number.replace(".", "").replace(",", ".")
    elif "," in raw_number:
        # Örnek: 1234,56 -> 1234.56
        raw_number = raw_number.replace(",", ".")

    try:
        result = float(raw_number)

        # Eğer değer 0-1 arasında ise (decimal format), yüzde yapmak için 100 ile çarp
        if 0 < result <= 1:
            result = result * 100

        # Komisyon değeri makul aralıkta mı kontrol et
        if 0 <= result <= 100:
            return result
        else:
            logging.getLogger("TrendyolCommission").warning(
                f"Anormal komisyon değeri: {result}% (orijinal: {value})"
            )
            return result
    except ValueError:
        logging.getLogger("TrendyolCommission").error(
            f"Komisyon değeri parse edilemedi: {value}"
        )
        return None


def find_column_by_aliases(df: pd.DataFrame, aliases: List[str]) -> Optional[str]:
    """
    DataFrame'de belirtilen alias'lara göre sütun arar
    Mixed type hatalarını önlemek için güvenli işlemler yapar
    """
    # Convert column names to strings to handle mixed types
    df_columns_normalized = {normalize_text(str(col)): str(col) for col in df.columns}

    for alias in aliases:
        alias_normalized = normalize_text(alias)

        # Tam eşleşme
        if alias_normalized in df_columns_normalized:
            return df_columns_normalized[alias_normalized]

        # Kısmi eşleşme
        for norm_col, orig_col in df_columns_normalized.items():
            if alias_normalized in norm_col or norm_col in alias_normalized:
                return orig_col

    return None


def validate_dataframe_columns(df: pd.DataFrame, required_columns: Dict[str, List[str]]) -> Dict[str, str]:
    """
    DataFrame'de gerekli sütunları bulur ve eşler
    Mixed type hatalarını önlemek için güvenli sütun işlemleri yapar
    """
    # Convert column names to strings to handle any mixed types
    df.columns = [str(col).strip() if col is not None else '' for col in df.columns]

    column_mapping = {}
    missing_columns = []

    for required_name, aliases in required_columns.items():
        found_column = find_column_by_aliases(df, aliases)
        if found_column:
            column_mapping[required_name] = found_column
        else:
            missing_columns.append(required_name)

    if missing_columns:
        available_cols = ", ".join(df.columns.tolist())
        raise ValueError(
            f"Gerekli sütunlar bulunamadı: {', '.join(missing_columns)}. "
            f"Mevcut sütunlar: {available_cols}"
        )

    return column_mapping


def clean_dataframe_text_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """
    DataFrame'deki metin sütunlarını temizler
    Mixed type hatalarını önlemek için güvenli string işlemleri yapar
    """
    df = df.copy()

    for col in columns:
        if col in df.columns:
            # CRITICAL FIX: Convert to string first to handle mixed types
            df[col] = df[col].astype(str)

            # Clean whitespace and normalize
            df[col] = df[col].str.replace(r"\s+", " ", regex=True).str.strip()

            # NaN benzeri değerleri temizle
            df[col] = df[col].replace({
                "nan": "", "NaN": "", "None": "", "null": "", "NULL": ""
            })

    return df


def format_commission_display(commission: float, as_percentage: bool = True) -> str:
    """Komisyon değerini görüntü için formatlar"""
    if commission is None:
        return "N/A"

    if as_percentage:
        return f"{commission:.2f}%"
    else:
        return f"{commission:.4f}"


def create_search_pattern(query: str, exact_word: bool = False) -> str:
    """Arama için regex pattern oluşturur"""
    escaped_query = re.escape(normalize_text(query))

    if exact_word:
        return f"\\b{escaped_query}\\b"
    else:
        return escaped_query


def get_unique_values_from_column(df: pd.DataFrame, column: str, min_length: int = 2) -> List[str]:
    """
    Sütundan benzersiz ve temiz değerleri çıkarır
    Mixed type hatalarını önlemek için güvenli işlemler yapar
    """
    if column not in df.columns:
        return []

    # CRITICAL FIX: Convert to string first before processing
    values = df[column].dropna().astype(str).unique().tolist()

    # Minimum uzunluk kontrolü ve boş değerleri filtrele
    clean_values = [
        val for val in values
        if val and len(val.strip()) >= min_length and val.strip().lower() not in ["nan", "none", "null", ""]
    ]

    return sorted(clean_values)