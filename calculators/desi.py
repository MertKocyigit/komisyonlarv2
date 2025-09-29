#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desi hesaplama modülü
Kargo desi değeri ve hacimsel ağırlık hesaplamaları
"""

from dataclasses import dataclass
from typing import Union, Dict, Any
import json


@dataclass
class DesiResult:
    """Desi hesaplama sonuç sınıfı"""
    width: float  # En (cm)
    height: float  # Boy (cm)
    length: float  # Yükseklik (cm)
    volume_cm3: float  # Hacim (cm³)
    volume_m3: float  # Hacim (m³)
    desi: float  # Desi değeri
    volumetric_weight: float  # Hacimsel ağırlık (kg)
    desi_factor: float  # Kullanılan desi faktörü

    def to_dict(self):
        """Sonucu dictionary'e çevir - camelCase format"""
        return {
            'width': self.width,
            'height': self.height,
            'length': self.length,
            'volumeCm3': self.volume_cm3,
            'volumeM3': self.volume_m3,
            'desi': self.desi,
            'volumetricWeight': self.volumetric_weight,
            'desiFactor': self.desi_factor
        }


def calculate_desi(width: Union[float, int],
                   height: Union[float, int],
                   length: Union[float, int],
                   desi_factor: Union[float, int] = 3000) -> DesiResult:
    """
    Desi hesaplama fonksiyonu

    Args:
        width: En (cm)
        height: Boy (cm)
        length: Yükseklik (cm)
        desi_factor: Desi faktörü (varsayılan 3000)

    Returns:
        DesiResult: Hesaplama sonuçları

    Raises:
        ValueError: Geçersiz değerler için
    """
    # Tip kontrolü ve dönüşüm
    try:
        w = float(width)
        h = float(height)
        l = float(length)
        factor = float(desi_factor)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Geçersiz sayısal değer: {e}")

    # Değer kontrolü
    if w <= 0 or h <= 0 or l <= 0:
        raise ValueError("En, boy ve yükseklik değerleri 0'dan büyük olmalıdır")

    if factor <= 0:
        raise ValueError("Desi faktörü 0'dan büyük olmalıdır")

    # Hacim hesaplama (cm³)
    volume_cm3 = w * h * l

    # Hacim m³'e çevirme
    volume_m3 = volume_cm3 / 1_000_000

    # Desi hesaplama (hacim / faktör)
    desi = volume_cm3 / factor

    # Hacimsel ağırlık (kg) - desi ile aynı değer
    volumetric_weight = desi

    return DesiResult(
        width=w,
        height=h,
        length=l,
        volume_cm3=volume_cm3,
        volume_m3=volume_m3,
        desi=desi,
        volumetric_weight=volumetric_weight,
        desi_factor=factor
    )


def calculate_desi_api(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    API için desi hesaplama fonksiyonu

    Args:
        data: Request verisi
        {
            "width": float,      # En (cm)
            "height": float,     # Boy (cm)
            "length": float,     # Yükseklik (cm)
            "desi_factor": float # Opsiyonel, varsayılan 3000
        }

    Returns:
        dict: API response
        {
            "success": bool,
            "data": {
                "width": float,
                "height": float,
                "length": float,
                "volumeCm3": float,
                "volumeM3": float,
                "desi": float,
                "volumetricWeight": float,
                "desiFactor": float
            },
            "error": str|None
        }
    """
    try:
        # Parametreleri al ve validate et
        if not isinstance(data, dict):
            return {
                'success': False,
                'error': 'Veri dictionary formatında olmalıdır',
                'data': {}
            }

        # Parametreleri al
        width = data.get('width')
        height = data.get('height')
        length = data.get('length')
        desi_factor = data.get('desi_factor', 3000)

        # None kontrolü
        if width is None:
            return {
                'success': False,
                'error': 'Uzunluk (width) parametresi gerekli',
                'data': {}
            }

        if height is None:
            return {
                'success': False,
                'error': 'Genişlik (height) parametresi gerekli',
                'data': {}
            }

        if length is None:
            return {
                'success': False,
                'error': 'Yükseklik (length) parametresi gerekli',
                'data': {}
            }

        # Tip kontrolü ve dönüşüm
        try:
            width = float(width) if width not in (None, "", "null") else 0
            height = float(height) if height not in (None, "", "null") else 0
            length = float(length) if length not in (None, "", "null") else 0
            desi_factor = float(desi_factor) if desi_factor not in (None, "", "null") else 3000
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': 'Geçersiz sayısal değer girişi',
                'data': {}
            }

        # Validasyon
        if width <= 0 or height <= 0 or length <= 0:
            return {
                'success': False,
                'error': 'En, boy ve yükseklik değerleri 0\'dan büyük olmalıdır',
                'data': {}
            }

        if desi_factor <= 0:
            return {
                'success': False,
                'error': 'Desi faktörü 0\'dan büyük olmalıdır',
                'data': {}
            }

        # Hesaplama
        result = calculate_desi(width, height, length, desi_factor)

        # API Response formatı - camelCase
        return {
            'success': True,
            'data': result.to_dict(),
            'error': None
        }

    except ValueError as e:
        return {
            'success': False,
            'error': str(e),
            'data': {}
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Beklenmeyen hata: {str(e)}',
            'data': {}
        }


def get_common_desi_factors() -> Dict[str, int]:
    """
    Yaygın kullanılan desi faktörleri

    Returns:
        dict: Kargo şirketi -> desi faktörü eşlemesi
    """
    return {
        "yurtici_kargo": 3000,
        "mng_kargo": 3000,
        "aras_kargo": 3000,
        "ptt_kargo": 3000,
        "ups": 5000,
        "fedex": 5000,
        "dhl": 5000,
        "tnt": 5000,
        "standard": 3000  # Varsayılan
    }


def calculate_shipping_cost_estimate(desi: float,
                                     rate_per_desi: float = 5.0) -> float:
    """
    Tahmini kargo ücreti hesaplama

    Args:
        desi: Hesaplanan desi değeri
        rate_per_desi: Desi başına ücret (TL)

    Returns:
        float: Tahmini kargo ücreti
    """
    if desi <= 0 or rate_per_desi <= 0:
        return 0.0
    return round(desi * rate_per_desi, 2)


def format_desi_result(result: DesiResult, include_cost: bool = False, rate_per_desi: float = 5.0) -> str:
    """
    Desi sonucunu formatlanmış string olarak döndür

    Args:
        result: DesiResult objesi
        include_cost: Maliyet tahmini dahil edilsin mi
        rate_per_desi: Desi başına ücret (TL)

    Returns:
        str: Formatlanmış sonuç
    """
    output = []
    output.append(f"Ölçüler: {result.width} x {result.height} x {result.length} cm")
    output.append(f"Hacim: {result.volume_cm3:,.0f} cm³ ({result.volume_m3:.6f} m³)")
    output.append(f"Desi Faktörü: {result.desi_factor:,.0f}")
    output.append(f"Desi Değeri: {result.desi:.2f}")
    output.append(f"Hacimsel Ağırlık: {result.volumetric_weight:.2f} kg")

    if include_cost:
        cost = calculate_shipping_cost_estimate(result.desi, rate_per_desi)
        output.append(f"Tahmini Kargo Ücreti: {cost:.2f} TL")

    return "\n".join(output)


def validate_desi_input(width: Any, height: Any, length: Any, desi_factor: Any = 3000) -> Dict[str, Any]:
    """
    Desi giriş verilerini validate et

    Args:
        width: En değeri
        height: Boy değeri
        length: Yükseklik değeri
        desi_factor: Desi faktörü

    Returns:
        dict: Validation sonucu
    """
    try:
        w = float(width) if width not in (None, "", "null") else 0
        h = float(height) if height not in (None, "", "null") else 0
        l = float(length) if length not in (None, "", "null") else 0
        f = float(desi_factor) if desi_factor not in (None, "", "null") else 3000

        errors = []

        if w <= 0:
            errors.append("Uzunluk 0'dan büyük olmalı")
        if h <= 0:
            errors.append("Genişlik 0'dan büyük olmalı")
        if l <= 0:
            errors.append("Yükseklik 0'dan büyük olmalı")
        if f <= 0:
            errors.append("Desi faktörü 0'dan büyük olmalı")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'values': {'width': w, 'height': h, 'length': l, 'desi_factor': f}
        }

    except (ValueError, TypeError) as e:
        return {
            'valid': False,
            'errors': [f'Geçersiz sayısal değer: {str(e)}'],
            'values': {}
        }


# Test fonksiyonu
def test_desi_calculation():
    """Desi hesaplama test fonksiyonu"""
    print("Desi Hesaplama Test")
    print("-" * 40)

    test_cases = [
        {"width": 30, "height": 20, "length": 15, "factor": 3000},
        {"width": 50, "height": 30, "length": 50, "factor": 3000},
        {"width": 100, "height": 50, "length": 25, "factor": 3000},
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\nTest {i}:")
        print(f"Ölçüler: {case['width']}x{case['height']}x{case['length']} cm")

        result = calculate_desi(
            case['width'],
            case['height'],
            case['length'],
            case['factor']
        )

        print(f"Hacim: {result.volume_cm3:,.0f} cm³")
        print(f"Desi: {result.desi:.2f}")
        print(f"Hacimsel Ağırlık: {result.volumetric_weight:.2f} kg")


def test_api():
    """API test fonksiyonu"""
    print("\n" + "=" * 50)
    print("API Test")
    print("=" * 50)

    test_data = {
        "width": 50,
        "height": 30,
        "length": 50,
        "desi_factor": 3000
    }

    result = calculate_desi_api(test_data)
    print(f"API Sonuç: {json.dumps(result, indent=2, ensure_ascii=False)}")

    # Hatalı veri testi
    print("\nHatalı Veri Testi:")
    error_data = {
        "width": -10,
        "height": 30,
        "length": 50
    }

    error_result = calculate_desi_api(error_data)
    print(f"Hata Sonuç: {json.dumps(error_result, indent=2, ensure_ascii=False)}")


def test_validation():
    """Validation test fonksiyonu"""
    print("\n" + "=" * 50)
    print("Validation Test")
    print("=" * 50)

    test_cases = [
        {"width": 30, "height": 20, "length": 15},  # Geçerli
        {"width": -10, "height": 20, "length": 15},  # Negatif uzunluk
        {"width": "abc", "height": 20, "length": 15},  # Geçersiz tip
        {"width": None, "height": None, "length": None},  # None değerler
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\nValidation Test {i}: {case}")
        result = validate_desi_input(**case)
        print(f"Sonuç: {json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    # Testleri çalıştır
    test_desi_calculation()
    test_api()
    test_validation()

    # Örnek kullanım
    print("\n" + "=" * 50)
    print("Örnek Kullanım")
    print("=" * 50)

    try:
        # Normal hesaplama
        result = calculate_desi(40, 30, 25, 3000)
        print(format_desi_result(result, include_cost=True))

        # JSON çıktısı
        print(f"\nJSON Format:\n{json.dumps(result.to_dict(), indent=2, ensure_ascii=False)}")

    except ValueError as e:
        print(f"Hata: {e}")