#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hepsiburada/HepsiJet kargo hesaplama modülü
Ağırlık, desi, mesafe ve hizmet türüne göre kargo ücreti hesaplama
"""

from dataclasses import dataclass
from typing import Union, Dict, Any, List, Optional
from enum import Enum


class ServiceType(Enum):
    """Kargo hizmet türleri"""
    STANDARD = "standard"
    FAST = "fast"
    SAME_DAY = "same_day"
    NEXT_DAY = "next_day"


class RegionType(Enum):
    """Bölge türleri"""
    SAME_CITY = "same_city"  # Aynı şehir
    NEARBY_CITY = "nearby_city"  # Yakın şehir
    FAR_CITY = "far_city"  # Uzak şehir
    REMOTE_AREA = "remote_area"  # Uzak bölge


@dataclass
class CargoCalculationResult:
    """Kargo hesaplama sonuç sınıfı"""
    # Girdi parametreleri
    actual_weight: float  # Gerçek ağırlık (kg)
    width: float  # En (cm)
    height: float  # Boy (cm)
    length: float  # Yükseklik (cm)
    desi_factor: float  # Desi faktörü
    service_type: str  # Hizmet türü
    region_type: str  # Bölge türü

    # Hesaplanan değerler
    volume_cm3: float  # Hacim (cm³)
    volume_m3: float  # Hacim (m³)
    desi_weight: float  # Desi ağırlığı (kg)
    billable_weight: float  # Faturalandırılan ağırlık (kg)
    base_price: float  # Temel fiyat (TL)
    service_multiplier: float  # Hizmet çarpanı
    region_multiplier: float  # Bölge çarpanı
    total_price: float  # Toplam kargo ücreti (TL)

    # Ek bilgiler
    used_weight_type: str  # "actual" veya "desi"
    price_breakdown: Dict[str, float]  # Fiyat detayları


# Sabit fiyat tabloları (örnek değerler - gerçek tarife ile güncellenmelidir)
BASE_PRICES = {
    # Ağırlık aralığı (kg): Temel fiyat (TL)
    0.5: 15.00,
    1.0: 20.00,
    2.0: 25.00,
    3.0: 30.00,
    5.0: 40.00,
    10.0: 60.00,
    20.0: 100.00,
    30.0: 140.00,
    50.0: 200.00,
}

SERVICE_MULTIPLIERS = {
    ServiceType.STANDARD: 1.0,
    ServiceType.FAST: 1.3,
    ServiceType.NEXT_DAY: 1.5,
    ServiceType.SAME_DAY: 2.0,
}

REGION_MULTIPLIERS = {
    RegionType.SAME_CITY: 1.0,
    RegionType.NEARBY_CITY: 1.2,
    RegionType.FAR_CITY: 1.5,
    RegionType.REMOTE_AREA: 2.0,
}


def calculate_desi_weight(width: float, height: float, length: float,
                          desi_factor: float = 3000) -> tuple[float, float, float]:
    """
    Desi ağırlığı hesaplama

    Returns:
        tuple: (volume_cm3, volume_m3, desi_weight)
    """
    volume_cm3 = width * height * length
    volume_m3 = volume_cm3 / 1_000_000
    desi_weight = volume_cm3 / desi_factor

    return volume_cm3, volume_m3, desi_weight


def get_base_price(weight: float) -> float:
    """Ağırlığa göre temel fiyat hesaplama"""
    for weight_limit, price in sorted(BASE_PRICES.items()):
        if weight <= weight_limit:
            return price

    # En yüksek ağırlık aşılırsa, son fiyat + fazla ağırlık hesabı
    max_weight = max(BASE_PRICES.keys())
    max_price = BASE_PRICES[max_weight]
    extra_weight = weight - max_weight
    extra_price = extra_weight * 3.0  # kg başına 3 TL (örnek)

    return max_price + extra_price


def calculate_hepsiburada_cargo(
        actual_weight: float,
        width: float,
        height: float,
        length: float,
        service_type: Union[str, ServiceType] = ServiceType.STANDARD,
        region_type: Union[str, RegionType] = RegionType.SAME_CITY,
        desi_factor: float = 3000
) -> CargoCalculationResult:
    """
    HepsiJet kargo ücreti hesaplama

    Args:
        actual_weight: Gerçek ağırlık (kg)
        width: En (cm)
        height: Boy (cm)
        length: Yükseklik (cm)
        service_type: Hizmet türü
        region_type: Bölge türü
        desi_factor: Desi faktörü (varsayılan 3000)

    Returns:
        CargoCalculationResult: Hesaplama sonuçları
    """
    # Tip dönüşümleri
    if isinstance(service_type, str):
        service_type = ServiceType(service_type)
    if isinstance(region_type, str):
        region_type = RegionType(region_type)

    # Desi hesaplama
    volume_cm3, volume_m3, desi_weight = calculate_desi_weight(
        width, height, length, desi_factor
    )

    # Faturalandırılan ağırlık (hangisi büyükse)
    if actual_weight >= desi_weight:
        billable_weight = actual_weight
        used_weight_type = "actual"
    else:
        billable_weight = desi_weight
        used_weight_type = "desi"

    # Minimum ağırlık kontrolü (0.5 kg)
    billable_weight = max(billable_weight, 0.5)

    # Temel fiyat
    base_price = get_base_price(billable_weight)

    # Çarpanlar
    service_multiplier = SERVICE_MULTIPLIERS[service_type]
    region_multiplier = REGION_MULTIPLIERS[region_type]

    # Toplam fiyat hesaplama
    total_price = base_price * service_multiplier * region_multiplier

    # Fiyat detayları
    price_breakdown = {
        "base_price": base_price,
        "service_fee": base_price * (service_multiplier - 1),
        "region_fee": base_price * service_multiplier * (region_multiplier - 1),
        "total": total_price
    }

    return CargoCalculationResult(
        actual_weight=actual_weight,
        width=width,
        height=height,
        length=length,
        desi_factor=desi_factor,
        service_type=service_type.value,
        region_type=region_type.value,
        volume_cm3=volume_cm3,
        volume_m3=volume_m3,
        desi_weight=desi_weight,
        billable_weight=billable_weight,
        base_price=base_price,
        service_multiplier=service_multiplier,
        region_multiplier=region_multiplier,
        total_price=total_price,
        used_weight_type=used_weight_type,
        price_breakdown=price_breakdown
    )


def calculate_hepsiburada_cargo_api(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    API için HepsiJet kargo hesaplama

    Args:
        data: {
            "actual_weight": float,    # Gerçek ağırlık (kg)
            "width": float,           # En (cm)
            "height": float,          # Boy (cm)
            "length": float,          # Yükseklik (cm)
            "service_type": str,      # "standard", "fast", "next_day", "same_day"
            "region_type": str,       # "same_city", "nearby_city", "far_city", "remote_area"
            "desi_factor": float      # Opsiyonel, varsayılan 3000
        }

    Returns:
        dict: API response
    """
    try:
        # Parametreleri al
        actual_weight = data.get('actual_weight', 0)
        width = data.get('width', 0)
        height = data.get('height', 0)
        length = data.get('length', 0)
        service_type = data.get('service_type', 'standard')
        region_type = data.get('region_type', 'same_city')
        desi_factor = data.get('desi_factor', 3000)

        # Tip kontrolü ve dönüşüm
        try:
            actual_weight = float(actual_weight) if actual_weight not in (None, "") else 0
            width = float(width) if width not in (None, "") else 0
            height = float(height) if height not in (None, "") else 0
            length = float(length) if length not in (None, "") else 0
            desi_factor = float(desi_factor) if desi_factor not in (None, "") else 3000
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': 'Geçersiz sayısal değer girişi',
                'data': {}
            }

        # Validasyon
        if actual_weight <= 0:
            return {
                'success': False,
                'error': 'Gerçek ağırlık 0\'dan büyük olmalıdır',
                'data': {}
            }

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

        # Geçerli değer kontrolü
        valid_services = [s.value for s in ServiceType]
        valid_regions = [r.value for r in RegionType]

        if service_type not in valid_services:
            return {
                'success': False,
                'error': f'Geçersiz hizmet türü. Geçerli değerler: {valid_services}',
                'data': {}
            }

        if region_type not in valid_regions:
            return {
                'success': False,
                'error': f'Geçersiz bölge türü. Geçerli değerler: {valid_regions}',
                'data': {}
            }

        # Hesaplama
        result = calculate_hepsiburada_cargo(
            actual_weight=actual_weight,
            width=width,
            height=height,
            length=length,
            service_type=service_type,
            region_type=region_type,
            desi_factor=desi_factor
        )

        # API Response formatı
        return {
            'success': True,
            'data': {
                # Girdi parametreleri
                'actualWeight': result.actual_weight,
                'width': result.width,
                'height': result.height,
                'length': result.length,
                'desiFactor': result.desi_factor,
                'serviceType': result.service_type,
                'regionType': result.region_type,

                # Hesaplanan değerler
                'volumeCm3': result.volume_cm3,
                'volumeM3': result.volume_m3,
                'desiWeight': result.desi_weight,
                'billableWeight': result.billable_weight,
                'basePrice': result.base_price,
                'serviceMultiplier': result.service_multiplier,
                'regionMultiplier': result.region_multiplier,
                'totalPrice': result.total_price,

                # Ek bilgiler
                'usedWeightType': result.used_weight_type,
                'priceBreakdown': result.price_breakdown
            },
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


def get_service_types() -> List[Dict[str, str]]:
    """Mevcut hizmet türlerini listele"""
    return [
        {"value": "standard", "label": "Standart Kargo"},
        {"value": "fast", "label": "Hızlı Kargo"},
        {"value": "next_day", "label": "Ertesi Gün"},
        {"value": "same_day", "label": "Aynı Gün"}
    ]


def get_region_types() -> List[Dict[str, str]]:
    """Mevcut bölge türlerini listele"""
    return [
        {"value": "same_city", "label": "Aynı Şehir"},
        {"value": "nearby_city", "label": "Yakın Şehir"},
        {"value": "far_city", "label": "Uzak Şehir"},
        {"value": "remote_area", "label": "Uzak Bölge"}
    ]


# Test fonksiyonu
def test_hepsiburada_cargo():
    """HepsiJet kargo hesaplama test fonksiyonu"""
    print("HepsiJet Kargo Hesaplama Test")
    print("-" * 50)

    test_cases = [
        {
            "actual_weight": 2.5,
            "width": 30, "height": 20, "length": 15,
            "service_type": "standard",
            "region_type": "same_city"
        },
        {
            "actual_weight": 1.0,
            "width": 50, "height": 30, "length": 50,
            "service_type": "fast",
            "region_type": "far_city"
        }
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\nTest {i}:")
        print(f"Ağırlık: {case['actual_weight']} kg")
        print(f"Ölçüler: {case['width']}x{case['height']}x{case['length']} cm")
        print(f"Hizmet: {case['service_type']}, Bölge: {case['region_type']}")

        result = calculate_hepsiburada_cargo(**case)

        print(f"Desi Ağırlığı: {result.desi_weight:.2f} kg")
        print(f"Faturalandırılan: {result.billable_weight:.2f} kg ({result.used_weight_type})")
        print(f"Kargo Ücreti: {result.total_price:.2f} TL")


if __name__ == "__main__":
    test_hepsiburada_cargo()