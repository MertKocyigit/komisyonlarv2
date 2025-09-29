#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

# Desi hesaplama import'u
from calculators.desi import calculate_desi_api

# ==================== FLASK ====================
app = Flask(__name__)
CORS(app)

# ==================== PATH AYARLARI ====================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()

# index.html yolu ENV ile override edilebilir; yoksa _legacy/index.html denenir
INDEX_HTML_PATH = os.getenv("INDEX_HTML_PATH", str(BASE_DIR / "_legacy" / "index.html"))


def _find_index_html() -> Optional[str]:
    candidates = [
        INDEX_HTML_PATH,
        str(BASE_DIR / "index.html"),
        str(BASE_DIR / "_legacy" / "index.html"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


# ==================== Yardımcılar / Normalizasyon ====================
def _ascii_tr(s: str) -> str:
    if s is None:
        return ""
    repl = {'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S', 'ı': 'i', 'İ': 'I', 'ö': 'o', 'Ö': 'O',
            'ç': 'c', 'Ç': 'C'}
    for o, n in repl.items():
        s = s.replace(o, n)
    return s


def _to_camel_from_any(s: str) -> str:
    s = _ascii_tr(s)
    parts = re.split(r"[^A-Za-z0-9]+", s.strip())
    parts = [p for p in parts if p]
    if not parts:
        return s
    first = parts[0].lower()
    rest = [p.capitalize() for p in parts[1:]]
    return first + "".join(rest)


def _extract_num(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)) and pd.notna(val):
        return float(val)
    s = str(val).replace("%", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def normalize_api_item(item: dict) -> dict:
    """
    Türkçe anahtarları camelCase'e çevirir.
    Hepsiburada'daki 'Ana Kategori' + 'Kategori' durumunda 'Kategori' -> subCategory yapılır.
    Diğer durumlarda:
      - 'Kategori' -> category
      - 'Alt Kategori' -> subCategory
      - 'Ürün Grubu/Urun Grubu/Urun_Grubu' -> productGroup
      - Komisyon alanları -> commissionPercent/commissionText
      - displayProductGroup = Category → SubCategory → ProductGroup (boşlar atlanır)
    """
    has_ana_k = "Ana Kategori" in item
    has_k = "Kategori" in item
    has_alt = "Alt Kategori" in item

    out: Dict[str, Any] = {}

    for k, v in item.items():
        nk = None

        # Dinamik eşleme (Hepsiburada için)
        if k == "Kategori":
            if has_ana_k and not has_alt:
                nk = "subCategory"  # Hepsiburada case: Kategori aslında alt kategori
            else:
                nk = "category"
        elif k == "Ana Kategori":
            nk = "category"
        elif k == "Alt Kategori":
            nk = "subCategory"
        elif k in ("Ürün Grubu", "Urun Grubu", "Urun_Grubu"):
            nk = "productGroup"
        elif k in ("Komisyon_%_KDV_Dahil", "Uygulanan_Komisyon_%_KDV_Dahil"):
            nk = "commissionPercent"
        elif k == "komisyon":
            nk = "commissionText"
        elif re.match(r"^[a-zA-Z][a-zA-Z0-9]*$", k or ""):
            nk = k  # zaten camelCase
        else:
            nk = _to_camel_from_any(k or "")

        out[nk] = v

    # commissionPercent yoksa metinden yakala
    if out.get("commissionPercent") in (None, ""):
        maybe = _extract_num(out.get("commissionText"))
        if maybe is not None:
            out["commissionPercent"] = maybe

    # commissionText üret
    if not out.get("commissionText") and out.get("commissionPercent") is not None:
        try:
            out["commissionText"] = (f"{float(out['commissionPercent']):.2f}%").replace(".", ",")
        except Exception:
            pass

    # displayCommissionText
    if not out.get("displayCommissionText") and out.get("commissionText"):
        out["displayCommissionText"] = out["commissionText"]

    # displayProductGroup: Category → SubCategory → ProductGroup
    cat = (out.get("category") or "").strip()
    sub = (out.get("subCategory") or "").strip()
    pg = (out.get("productGroup") or "").strip()
    parts = [p for p in (cat, sub, pg) if p]
    if parts:
        out["displayProductGroup"] = " → ".join(parts)  # → işareti
    elif pg and not out.get("displayProductGroup"):
        out["displayProductGroup"] = pg  # son çare

    return out


# ==================== KDV HESAPLAMA FONKSİYONLARI ====================
def calculate_kdv_api(data: dict) -> dict:
    """
    KDV hesaplama API fonksiyonu

    Parameters:
    - direction: 'add' (KDV ekle) veya 'remove' (KDV çıkar)
    - price: Hesaplanacak tutar
    - rate: KDV oranı (1, 10, 18, 20 vb.)
    - withholdingRate: Tevkifat oranı (opsiyonel, örn: '7/10')
    - rounding: Yuvarlama türü (opsiyonel, 'even', 'up', 'down')
    """
    try:
        # Parametreleri al ve validate et
        direction = data.get('direction', 'add')
        price = float(data.get('price', 0))
        rate = float(data.get('rate', 20))
        withholding_rate = data.get('withholdingRate', None)
        rounding_method = data.get('rounding', 'even')

        if price <= 0:
            return {
                'success': False,
                'error': 'Fiyat 0\'dan büyük olmalıdır',
                'data': {}
            }

        if rate < 0 or rate > 100:
            return {
                'success': False,
                'error': 'KDV oranı 0-100 arasında olmalıdır',
                'data': {}
            }

        # KDV hesaplama
        if direction == 'add':
            # KDV hariç fiyata KDV ekle
            price_excl_vat = price
            vat_amount = price_excl_vat * (rate / 100)
            price_incl_vat = price_excl_vat + vat_amount
        else:  # remove
            # KDV dahil fiyattan KDV çıkar
            price_incl_vat = price
            price_excl_vat = price_incl_vat / (1 + rate / 100)
            vat_amount = price_incl_vat - price_excl_vat

        # Yuvarlama uygula
        def round_value(value, method='even'):
            if method == 'up':
                return round(value + 0.005, 2)
            elif method == 'down':
                return round(value - 0.005, 2)
            else:  # even (banker's rounding)
                return round(value, 2)

        price_excl_vat = round_value(price_excl_vat, rounding_method)
        vat_amount = round_value(vat_amount, rounding_method)
        price_incl_vat = round_value(price_incl_vat, rounding_method)

        result = {
            'priceExclVat': price_excl_vat,
            'vatAmount': vat_amount,
            'priceInclVat': price_incl_vat,
            'vatRate': rate,
            'direction': direction
        }

        # Tevkifat hesaplama
        if withholding_rate:
            try:
                if '/' in withholding_rate:
                    # Kesir formatı (örn: 7/10)
                    num, den = map(float, withholding_rate.split('/'))
                    withholding_ratio = num / den
                else:
                    # Yüzde formatı (örn: 0.7)
                    withholding_ratio = float(withholding_rate)

                withholding_amount = vat_amount * withholding_ratio
                payable_vat = vat_amount - withholding_amount

                result['withholdingRate'] = withholding_rate
                result['withholdingAmount'] = round_value(withholding_amount, rounding_method)
                result['payableVat'] = round_value(payable_vat, rounding_method)

            except (ValueError, ZeroDivisionError):
                return {
                    'success': False,
                    'error': 'Geçersiz tevkifat oranı formatı',
                    'data': {}
                }

        return {
            'success': True,
            'data': result
        }

    except ValueError as e:
        return {
            'success': False,
            'error': f'Geçersiz sayısal değer: {str(e)}',
            'data': {}
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Hesaplama hatası: {str(e)}',
            'data': {}
        }


# ==================== HEPSİJET KARGO HESAPLAMA FONKSİYONLARI ====================
def calculate_hepsijet_api(data: dict) -> dict:
    """
    HepsiJet kargo ücreti hesaplama API fonksiyonu (CSV tabanlı)

    Parameters:
    - desi: Desi değeri
    """
    try:
        # Desi değerini al
        desi_value = data.get('desi', 0)

        try:
            desi_value = float(desi_value) if desi_value not in (None, "") else 0
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': 'Geçersiz desi değeri',
                'data': {}
            }

        # Validation
        if desi_value <= 0:
            return {
                'success': False,
                'error': 'Desi değeri 0\'dan büyük olmalıdır',
                'data': {}
            }

        # CSV dosyasından fiyat bilgisini oku
        try:
            csv_path = DATA_DIR / "hepsijet_desi.csv"
            if not csv_path.exists():
                return {
                    'success': False,
                    'error': 'HepsiJet desi fiyat tablosu bulunamadı',
                    'data': {}
                }

            df = pd.read_csv(csv_path, encoding="utf-8-sig")

            # En yakın desi değerini bul
            df['desi_diff'] = abs(df['desi'] - desi_value)
            closest_row = df.loc[df['desi_diff'].idxmin()]

            closest_desi = closest_row['desi']
            price = closest_row['hepsijet_try']

        except Exception as e:
            return {
                'success': False,
                'error': f'CSV okuma hatası: {str(e)}',
                'data': {}
            }

        result = {
            'desiValue': desi_value,
            'closestDesi': int(closest_desi),
            'price': float(price),
            'priceFormatted': f"{float(price):.2f}".replace(".", ",") + " TL"
        }

        return {
            'success': True,
            'data': result
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Hesaplama hatası: {str(e)}',
            'data': {}
        }


# ==================== SERVİS ====================
class MultiMarketplaceCommissionService:
    """
    - CSV'leri DATA_DIR altında arar (sadece dosya adı verilir).
    - Her istekte dosyaların mtime'ına bakıp değiştiyse yeniden yükler.
    - Tüm marketplace'ler normalize edilerek 4 kolonla sunulur:
      ['Kategori', 'Alt Kategori', 'Ürün Grubu', 'Komisyon_%_KDV_Dahil']
    """

    def __init__(self) -> None:
        self.marketplaces: Dict[str, Dict[str, Any]] = {
            "trendyol": {
                "name": "Trendyol",
                "csv_file": "commissions_flat.csv",
                "columns_candidates": {
                    "category": ["Ana Kategori", "Kategori"],
                    "sub_category": ["Kategori", "Alt Kategori"],
                    "product_group": ["Ürün Grubu", "Urun Grubu", "Urun_Grubu"],
                    "commission": ["Komisyon_%_KDV_Dahil", "komisyon"],
                },
            },
            "hepsiburada": {
                "name": "Hepsiburada",
                "csv_file": "hepsiburada_commissions.csv",
                "columns_candidates": {
                    "category": ["Ana Kategori", "Kategori"],
                    "sub_category": ["Kategori", "Alt Kategori"],
                    "product_group": ["Ürün Grubu", "Urun Grubu", "Urun_Grubu"],
                    "commission": ["Komisyon_%_KDV_Dahil", "Uygulanan_Komisyon_%_KDV_Dahil", "komisyon"],
                },
            },
            "n11": {
                "name": "N11",
                "csv_file": "n11_commissions.csv",
                "columns_candidates": {
                    "category": ["Kategori", "Ana Kategori"],
                    "sub_category": ["Alt Kategori", "Kategori"],
                    "product_group": ["Ürün Grubu", "Urun Grubu", "Urun_Grubu"],
                    "commission": ["Komisyon_%_KDV_Dahil", "komisyon"],
                },
            },
            "amazon": {
                "name": "Amazon",
                "csv_file": "amazon_commissions.csv",
                "columns_candidates": {
                    "category": ["Kategori"],
                    "sub_category": ["Alt Kategori"],
                    "product_group": ["Ürün Grubu", "Kategori"],
                    "commission": ["Komisyon_%_KDV_Dahil", "Satış Komisyonu (+KDV)"],
                },
            },
            "ciceksepeti": {
                "name": "Çiçeksepeti",
                "csv_file": "ciceksepeti_commissions.csv",
                "columns_candidates": {
                    "category": ["Kategori", "Ana Kategori"],
                    "sub_category": ["Alt Kategori", "Kategori"],
                    "product_group": ["Ürün Grubu", "Kategori"],
                    "commission": ["Komisyon_%_KDV_Dahil", "Komisyon Oranı", "Revize Komisyon Oranı"],
                },
            },
            "pttavm": {
                "name": "PTTAVM",
                "csv_file": "pttavm_commissions.csv",
                "columns_candidates": {
                    "category": ["Kategori", "Ana Kategori"],
                    "sub_category": ["Alt Kategori"],
                    "product_group": ["Ürün Grubu", "Alt Kategori", "Kategori"],
                    "commission": ["Komisyon_%_KDV_Dahil", "Komisyon", "Komisyon Oranları"],
                },
            },
        }

        self._files: Dict[str, Path] = {}
        self._mtimes: Dict[str, float] = {}
        self._data: Dict[str, List[Dict[str, Any]]] = {}

        self._init_file_registry()
        self.refresh_if_changed(force=True)

    # ---------- PATH ----------
    def _resolve_csv_path(self, filename: str) -> Path:
        fn = Path(filename)
        if fn.is_absolute():
            return fn
        candidates = [
            DATA_DIR / filename,
            BASE_DIR / "data" / filename,
            BASE_DIR / filename,
        ]
        for p in candidates:
            if p.exists():
                return p
        return DATA_DIR / filename

    def _init_file_registry(self) -> None:
        for key, mp in self.marketplaces.items():
            p = self._resolve_csv_path(mp["csv_file"])
            self._files[key] = p
            self._mtimes[key] = -1.0

    # ---------- IO / DÖNÜŞÜMLER ----------
    @staticmethod
    def _read_csv_with_fallbacks(path: Path) -> pd.DataFrame:
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            return pd.read_csv(path, encoding="cp1254")

    @staticmethod
    def _extract_number(x: Any) -> Optional[float]:
        if x is None:
            return None
        s = str(x).strip().replace(",", ".")
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        return float(m.group(1)) if m else None

    @staticmethod
    def _fix_scale(series: pd.Series) -> pd.Series:
        ser = pd.to_numeric(series, errors="coerce")
        if ser.notna().sum() > 0 and float(ser.quantile(0.95)) <= 1.0:
            ser = ser * 100.0
        return ser

    def _pick_first_present(self, df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        for c in candidates:
            if c in df.columns:
                return c
        return None

    def _normalize_to_flat4(self, df: pd.DataFrame, candidates: Dict[str, List[str]]) -> pd.DataFrame:
        cat_col = self._pick_first_present(df, candidates["category"]) or ""
        sub_col = self._pick_first_present(df, candidates["sub_category"]) or ""
        grp_col = self._pick_first_present(df, candidates["product_group"]) or ""
        com_col = self._pick_first_present(df, candidates["commission"]) or ""

        if not grp_col:
            raise ValueError("Ürün Grubu kolonu bulunamadı (candidates=%s)" % candidates["product_group"])
        if not (cat_col or sub_col):
            raise ValueError("Kategori/Alt Kategori kolonları bulunamadı.")

        out = pd.DataFrame()

        if cat_col and sub_col and cat_col != sub_col:
            out["Kategori"] = df[cat_col].astype(str).str.strip()
            out["Alt Kategori"] = df[sub_col].astype(str).str.strip()
        else:
            use_col = cat_col or sub_col
            out["Kategori"] = df[use_col].astype(str).str.strip()
            out["Alt Kategori"] = ""

        out["Ürün Grubu"] = df[grp_col].astype(str).str.strip()

        if com_col:
            vals = df[com_col].astype(str).map(self._extract_number)
            vals = self._fix_scale(vals)
        else:
            vals = pd.Series([None] * len(df))

        out["Komisyon_%_KDV_Dahil"] = pd.to_numeric(vals, errors="coerce")

        out = out[(out["Kategori"] != "") | (out["Alt Kategori"] != "") | (out["Ürün Grubu"] != "")]
        out = out.drop_duplicates().reset_index(drop=True)
        return out

    def _load_csv_normalized(self, path: Path, mp_key: str) -> List[Dict[str, Any]]:
        df = self._read_csv_with_fallbacks(path)

        wanted = ["Kategori", "Alt Kategori", "Ürün Grubu", "Komisyon_%_KDV_Dahil"]
        if all(c in df.columns for c in wanted):
            out = df[wanted].copy()
            out["Komisyon_%_KDV_Dahil"] = self._fix_scale(out["Komisyon_%_KDV_Dahil"])
            out = out.fillna("")
            out["Komisyon_%_KDV_Dahil"] = pd.to_numeric(out["Komisyon_%_KDV_Dahil"], errors="coerce")
            return out.to_dict(orient="records")

        cands = self.marketplaces[mp_key]["columns_candidates"]
        out = self._normalize_to_flat4(df, cands).fillna("")
        return out.to_dict(orient="records")

    # ---------- HOT RELOAD ----------
    def refresh_if_changed(self, force: bool = False) -> bool:
        changed = False
        for key, path in self._files.items():
            if not path.exists():
                self._data[key] = []
                continue
            m = path.stat().st_mtime
            if force or m != self._mtimes.get(key, -1):
                try:
                    self._data[key] = self._load_csv_normalized(path, key)
                    self._mtimes[key] = m
                    changed = True
                except Exception as e:
                    app.logger.warning(f"{key} yüklenemedi: {e}")
        return changed

    # ---------- PUBLIC QUERIES ----------
    def get_available_marketplaces(self) -> List[Dict[str, Any]]:
        res = []
        for mid, info in self.marketplaces.items():
            p = self._files.get(mid)
            rows = self._data.get(mid, [])
            # benzersiz Ürün Grubu sayımı
            if mid in ("n11", "amazon", "ciceksepeti", "pttavm"):
                count = len({r.get("Ürün Grubu", "") for r in rows if r.get("Ürün Grubu", "")})
            else:
                count = len(rows)
            res.append({
                "id": mid,
                "name": info["name"],
                "productCount": count,  # camelCase
                "csv": str(p) if p else None,
                "exists": (p.exists() if p else False),
                "rowCount": count,  # camelCase
            })
        return res

    @staticmethod
    def _normalize_turkish(text: str) -> str:
        if text is None:
            return ""
        repl = {'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S', 'ı': 'i', 'İ': 'I', 'ö': 'o', 'Ö': 'O',
                'ç': 'c', 'Ç': 'C'}
        for o, n in repl.items():
            text = text.replace(o, n)
        return text

    def search_products(self, marketplace_id: str, query: str) -> List[Dict[str, Any]]:
        """
        Arama önceliği:
          1) 'Kategori' içinde geçenler
          2) 'Alt Kategori' içinde geçenler
          3) 'Ürün Grubu' içinde geçenler
        Sonuçlar bu önceliğe göre sıralanır; aynı önceliktekiler yol metnine göre alfabetiktir.
        """
        rows = self._data.get(marketplace_id, [])
        q = self._normalize_turkish(str(query or "").lower()).strip()

        if not q:
            return rows

        ranked = []
        for r in rows:
            cat = self._normalize_turkish(str(r.get("Kategori", "")).lower())
            sub = self._normalize_turkish(str(r.get("Alt Kategori", "")).lower())
            grp = self._normalize_turkish(str(r.get("Ürün Grubu", "")).lower())

            in_cat = q in cat
            in_sub = q in sub
            in_grp = q in grp

            if not (in_cat or in_sub or in_grp):
                continue

            priority = 0 if in_cat else (1 if in_sub else 2)
            path_for_sort = f"{r.get('Kategori', '')} → {r.get('Alt Kategori', '')} → {r.get('Ürün Grubu', '')}".lower()

            ranked.append((priority, path_for_sort, r))

        ranked.sort(key=lambda x: (x[0], x[1]))
        return [item[2] for item in ranked]

    def list_categories(self, site_key: str) -> List[str]:
        rows = self._data.get(site_key, [])
        return sorted({r.get("Kategori", "") for r in rows if r.get("Kategori", "")})

    def list_subcategories(self, site_key: str, category: str) -> List[str]:
        rows = [r for r in self._data.get(site_key, []) if r.get("Kategori", "") == (category or "")]
        return sorted({r.get("Alt Kategori", "") for r in rows if r.get("Alt Kategori", "")})

    def list_product_groups(self, site_key: str, category: str, sub: str) -> List[str]:
        rows = [r for r in self._data.get(site_key, [])
                if r.get("Kategori", "") == (category or "") and r.get("Alt Kategori", "") == (sub or "")]
        return sorted({r.get("Ürün Grubu", "") for r in rows if r.get("Ürün Grubu", "")})

    def find_commission(self, site_key: str, category: str, sub: str, group: str) -> Optional[float]:
        for r in self._data.get(site_key, []):
            if r.get("Kategori", "") == (category or "") and \
                    r.get("Alt Kategori", "") == (sub or "") and \
                    r.get("Ürün Grubu", "") == (group or ""):
                val = r.get("Komisyon_%_KDV_Dahil", None)
                try:
                    return float(val) if val is not None else None
                except Exception:
                    return None
        return None

    # ---------- Ürün Grubu + Komisyon listesi (duplicate → MAX) ----------
    def list_pg_commissions(self, site_key: str, q: str = "") -> List[Dict[str, Any]]:
        rows = self._data.get(site_key, [])
        norm_q = self._normalize_turkish(q.lower()) if q else ""
        seen: Dict[str, Dict[str, Any]] = {}

        def fmt(val: Optional[float]) -> str:
            if val is None:
                return ""
            try:
                return (f"{float(val):.2f}%").replace(".", ",")
            except Exception:
                return ""

        for r in rows:
            pg = str(r.get("Ürün Grubu", "") or "").strip()
            if not pg:
                continue
            if norm_q and norm_q not in self._normalize_turkish(pg.lower()):
                continue

            val = r.get("Komisyon_%_KDV_Dahil", None)
            if isinstance(val, str) and val.strip() == "":
                val = None
            else:
                try:
                    val = float(val)
                except Exception:
                    val = None

            current = seen.get(pg, None)
            if current is None or ((val or 0.0) > ((current.get("commissionPercent") or 0.0))):
                seen[pg] = {
                    "productGroup": pg,
                    "commissionPercent": val,
                    "commissionText": fmt(val),
                }

        return sorted(seen.values(), key=lambda x: x["productGroup"].lower())

    # ---------- HESAPLAMA ----------
    def calculate_commission(self, marketplace_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tüm marketplace'ler için komisyon hesaplama
        Hepsiburada formülü: Satış Fiyatı - Komisyon - Hizmet Bedeli - İşlem Bedeli - Kargo = Ödenen Tutar
        Net Kar: Ödenen Tutar - Alış Fiyatı
        """
        # Parametreleri al
        sale_price = float(params.get('salePrice', 0) or 0)
        buy_price = float(params.get('buyPrice', 0) or 0)
        cargo_price = float(params.get('cargoPrice', 0) or 0)
        vat_percent = float(params.get('vatPercent', 0) or 0)
        commission_percent = float(params.get('commissionPercent', 0) or 0)
        service_percent = float(params.get('servicePercent', 0) or 0)
        export_percent = float(params.get('exportPercent', 0) or 0)
        include_vat_deduction = bool(params.get('includeVatDeduction', False))

        if sale_price <= 0:
            return self._empty_calc_result(marketplace_id, "Satış fiyatı 0'dan büyük olmalıdır")

        # GİDER HESAPLAMALARI
        # 1. Komisyon (Satış fiyatı üzerinden)
        commission_amount = sale_price * commission_percent / 100.0

        # 2. Hizmet Bedeli (Satış fiyatı üzerinden)
        service_amount = sale_price * service_percent / 100.0

        # 3. İşlem/Export Bedeli (Satış fiyatı üzerinden)
        export_amount = sale_price * export_percent / 100.0

        # 4. Kargo Kesintisi (Direkt tutar)
        cargo_deduction = cargo_price

        # ANA HESAPLAMA
        # Satıcıya Ödenen Tutar = Satış Fiyatı - Tüm Giderler
        payout = sale_price - (commission_amount + service_amount + export_amount + cargo_deduction)

        # Net Kar = Ödenen Tutar - Alış Fiyatı
        net_profit = payout - buy_price

        # Kar Marjı = (Net Kar / Satış Fiyatı) * 100
        profit_margin = (net_profit / sale_price * 100.0) if sale_price > 0 else 0.0

        # KDV HESAPLAMALARI (Muhasebe için)
        sale_vat = self._extract_vat_share(sale_price, vat_percent)
        buy_vat = self._extract_vat_share(buy_price, vat_percent)
        comm_vat = self._extract_vat_share(commission_amount, vat_percent)
        serv_vat = self._extract_vat_share(service_amount, vat_percent)
        exp_vat = self._extract_vat_share(export_amount, vat_percent)

        # İndirilecek KDV
        input_vat = buy_vat
        if include_vat_deduction:
            # Platform kesintilerindeki KDV'ler indirilabilir
            input_vat += comm_vat + serv_vat + exp_vat

        # Ödenecek KDV
        vat_payable = max(sale_vat - input_vat, 0.0)

        return {
            'marketplace': marketplace_id,
            'payout': round(payout, 2),  # Satıcıya ödenen tutar
            'netProfit': round(net_profit, 2),  # Net kar
            'profitMargin': round(profit_margin, 2),  # Kar marjı %
            'netMargin': round(profit_margin, 2),  # Kar marjı % (alias)
            'detailedProfitNet': round(net_profit, 2),  # Net kar (alias)

            # Gider Detayları
            'commissionAmount': round(commission_amount, 2),  # Komisyon tutarı
            'serviceAmount': round(service_amount, 2),  # Hizmet bedeli
            'exportAmount': round(export_amount, 2),  # İşlem/Export bedeli
            'cargoDeduction': round(cargo_deduction, 2),  # Kargo kesintisi

            # KDV Detayları
            'saleVat': round(sale_vat, 2),  # Satış KDV'si
            'buyVat': round(buy_vat, 2),  # Alış KDV'si
            'commVat': round(comm_vat, 2),  # Komisyon KDV'si
            'servVat': round(serv_vat, 2),  # Hizmet bedeli KDV'si
            'expVat': round(exp_vat, 2),  # Export bedeli KDV'si
            'inputVat': round(input_vat, 2),  # İndirilecek KDV toplam
            'vatPayable': round(vat_payable, 2),  # Ödenecek KDV

            'params': params
        }

    def _extract_vat_share(self, gross: float, vat_percent: float) -> float:
        """
        Brüt tutardan KDV payını çıkarır
        Örnek: 100 TL (KDV dahil) ve %18 KDV → KDV = 100 * (18/118) = 15.25 TL
        """
        return (gross * (vat_percent / (100.0 + vat_percent))) if vat_percent > 0 else 0.0

    def _empty_calc_result(self, marketplace_id: str, error_msg: str) -> Dict[str, Any]:
        """Hata durumunda boş sonuç döndürür"""
        return {
            'marketplace': marketplace_id,
            'payout': 0.0,
            'netProfit': 0.0,
            'profitMargin': 0.0,
            'netMargin': 0.0,
            'detailedProfitNet': 0.0,
            'commissionAmount': 0.0,
            'serviceAmount': 0.0,
            'exportAmount': 0.0,
            'cargoDeduction': 0.0,
            'saleVat': 0.0,
            'buyVat': 0.0,
            'commVat': 0.0,
            'servVat': 0.0,
            'expVat': 0.0,
            'inputVat': 0.0,
            'vatPayable': 0.0,
            'error': error_msg,
            'params': {}
        }


commission_service = MultiMarketplaceCommissionService()


# ==================== HOT-RELOAD TETİKLEYİCİ ====================
@app.before_request
def _auto_refresh():
    try:
        commission_service.refresh_if_changed()
    except Exception as e:
        app.logger.warning(f"CSV auto-reload başarısız: {e}")


# ==================== ÖNEMLİ: DESI ENDPOINT'İ app.run() ÖNCESİNDE ====================
@app.post("/api/calc/desi")
def api_calc_desi():
    """
    Desi hesaplama API endpoint'i

    POST /api/calc/desi
    {
        "width": 30,      # En (cm)
        "height": 20,     # Boy (cm)
        "length": 15,     # Yükseklik (cm)
        "desi_factor": 3000  # Opsiyonel, varsayılan 3000
    }
    """
    try:
        # Content-Type kontrolü
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Content-Type application/json gerekli',
                'data': {}
            }), 400

        # JSON verisi al
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({
                'success': False,
                'error': 'Geçersiz JSON verisi',
                'data': {}
            }), 400

        # Debug log
        app.logger.info(f"Desi calculation request: {data}")

        # Hesaplama yap
        result = calculate_desi_api(data)

        # Debug log
        app.logger.info(f"Desi calculation result: {result}")

        # HTTP status code belirle
        status_code = 200 if result['success'] else 400

        # UTF-8 encoding ile JSON döndür
        response = jsonify(result)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'

        return response, status_code

    except Exception as e:
        app.logger.error(f"Desi calculation error: {str(e)}")
        error_response = {
            'success': False,
            'error': f'Sunucu hatası: {str(e)}',
            'data': {}
        }
        response = jsonify(error_response)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500


# Test endpoint'i
@app.get("/api/calc/desi/test")
def test_desi_endpoint():
    """Test için basit desi hesaplama"""
    test_data = {
        'width': 30,
        'height': 20,
        'length': 15,
        'desi_factor': 3000
    }

    result = calculate_desi_api(test_data)
    response = jsonify(result)
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response


# ==================== KDV HESAPLAMA ENDPOINT'İ ====================
@app.post("/api/calc/kdv")
def api_calc_kdv():
    """
    KDV hesaplama API endpoint'i

    POST /api/calc/kdv
    {
        "direction": "add",     # "add" veya "remove"
        "price": 100,          # Hesaplanacak tutar
        "rate": 20,            # KDV oranı
        "withholdingRate": "7/10",  # Opsiyonel tevkifat oranı
        "rounding": "even"     # Opsiyonel yuvarlama türü
    }
    """
    try:
        # Content-Type kontrolü
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Content-Type application/json gerekli',
                'data': {}
            }), 400

        # JSON verisi al
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({
                'success': False,
                'error': 'Geçersiz JSON verisi',
                'data': {}
            }), 400

        # Debug log
        app.logger.info(f"KDV calculation request: {data}")

        # Hesaplama yap
        result = calculate_kdv_api(data)

        # Debug log
        app.logger.info(f"KDV calculation result: {result}")

        # HTTP status code belirle
        status_code = 200 if result['success'] else 400

        # UTF-8 encoding ile JSON döndür
        response = jsonify(result)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'

        return response, status_code

    except Exception as e:
        app.logger.error(f"KDV calculation error: {str(e)}")
        error_response = {
            'success': False,
            'error': f'Sunucu hatası: {str(e)}',
            'data': {}
        }
        response = jsonify(error_response)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500


# ==================== HEPSİJET KARGO HESAPLAMA ENDPOINT'İ ====================
@app.post("/api/calc/hepsijet")
def api_calc_hepsijet():
    """
    HepsiJet kargo ücreti hesaplama API endpoint'i

    POST /api/calc/hepsijet
    {
        "desi": 5.5    # Desi değeri
    }
    """
    try:
        # Content-Type kontrolü
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Content-Type application/json gerekli',
                'data': {}
            }), 400

        # JSON verisi al
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({
                'success': False,
                'error': 'Geçersiz JSON verisi',
                'data': {}
            }), 400

        # Debug log
        app.logger.info(f"HepsiJet calculation request: {data}")

        # Hesaplama yap
        result = calculate_hepsijet_api(data)

        # Debug log
        app.logger.info(f"HepsiJet calculation result: {result}")

        # HTTP status code belirle
        status_code = 200 if result['success'] else 400

        # UTF-8 encoding ile JSON döndür
        response = jsonify(result)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'

        return response, status_code

    except Exception as e:
        app.logger.error(f"HepsiJet calculation error: {str(e)}")
        error_response = {
            'success': False,
            'error': f'Sunucu hatası: {str(e)}',
            'data': {}
        }
        response = jsonify(error_response)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500


# ==================== ROUTES ====================
@app.route("/")
def index():
    index_path = _find_index_html()
    if index_path:
        return send_file(index_path, mimetype="text/html; charset=utf-8")
    return (
        "<h1>index.html bulunamadı</h1>"
        f"<p>Aranan yol: {INDEX_HTML_PATH}</p>"
        "<p>INDEX_HTML_PATH ortam değişkeniyle yol belirleyebilirsin.</p>"
    )


# ---- Marketplace path routing (/trendyol, /n11, /amazon, /ciceksepeti, /pttavm, /hepsiburada) ----
@app.route("/<marketplace_id>")
def index_marketplace(marketplace_id):
    if marketplace_id in commission_service.marketplaces:
        index_path = _find_index_html()
        if index_path:
            return send_file(index_path, mimetype="text/html; charset=utf-8")
    return index()


# İstersen local ön-ekli path için de aynı davranış:
@app.route("/local/<marketplace_id>")
def index_marketplace_local(marketplace_id):
    if marketplace_id in commission_service.marketplaces:
        index_path = _find_index_html()
        if index_path:
            return send_file(index_path, mimetype="text/html; charset=utf-8")
    return index()


# ---- Health & Admin ----
@app.get("/api/health")
def health_check():
    try:
        # Test desi calculation
        test_result = calculate_desi_api({
            'width': 10, 'height': 10, 'length': 10, 'desi_factor': 3000
        })
        desi_working = test_result.get('success', False)

        # Test KDV calculation
        kdv_test_result = calculate_kdv_api({
            'direction': 'add', 'price': 100, 'rate': 20
        })
        kdv_working = kdv_test_result.get('success', False)

        # Test HepsiJet calculation
        hepsijet_test_result = calculate_hepsijet_api({
            'desi': 5
        })
        hepsijet_working = hepsijet_test_result.get('success', False)

        return jsonify({
            "success": True,
            "message": "API OK",
            "features": {
                "commission": True,
                "kdv": kdv_working,
                "desi": desi_working,
                "hepsijet": hepsijet_working
            },
            "marketplaces": commission_service.get_available_marketplaces()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"API Error: {str(e)}",
            "features": {
                "commission": True,
                "kdv": False,
                "desi": False,
                "hepsijet": False
            }
        }), 500


@app.get("/api/marketplaces")
def get_marketplaces():
    try:
        return jsonify({'success': True, 'data': commission_service.get_available_marketplaces()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.post("/api/reload")
def manual_reload():
    changed = commission_service.refresh_if_changed(force=True)
    return jsonify({"success": True, "reloaded": changed})


# ---- Generic endpoints ----
@app.get("/api/search")
def search_products():
    try:
        marketplace_id = request.args.get('marketplace', 'trendyol')
        query = request.args.get('q', '')
        if marketplace_id not in commission_service.marketplaces:
            return jsonify({'success': False, 'error': 'Geçersiz marketplace'}), 400

        # HEPSIBURADA: yalnız ilk 4 sütunu döndür → sonra normalize
        if marketplace_id == "hepsiburada":
            rows = commission_service.search_products(marketplace_id, query)
            data = []
            for r in rows:
                val = r.get("Komisyon_%_KDV_Dahil", None)
                if isinstance(val, float) and pd.isna(val):
                    val = None
                data.append({
                    "Ana Kategori": r.get("Kategori", ""),  # normalize → category
                    "Kategori": r.get("Alt Kategori", ""),  # normalize → subCategory (dinamik kural)
                    "Ürün Grubu": r.get("Ürün Grubu", ""),
                    "Uygulanan_Komisyon_%_KDV_Dahil": val
                })
            data = [normalize_api_item(d) for d in data]
            return jsonify({'success': True, 'data': data, 'count': len(data), 'marketplace': marketplace_id})

        # N11 / Amazon: sadece ürün grubu + max komisyon → yine camelCase'e çevir
        if marketplace_id in ("n11", "amazon"):
            items = commission_service.list_pg_commissions(marketplace_id, query)
            data = []
            for it in items:
                data.append({
                    "Kategori": "",
                    "Alt Kategori": "",
                    "Ürün Grubu": it["productGroup"],
                    "Komisyon_%_KDV_Dahil": it["commissionPercent"],
                    "komisyon": it["commissionText"],
                })
            data = [normalize_api_item(d) for d in data]
            return jsonify({'success': True, 'data': data, 'count': len(data), 'marketplace': marketplace_id})

        # Çiçeksepeti & PTTAVM: kategori yolu görünsün (Kategori → Alt Kategori → Ürün Grubu)
        if marketplace_id in ("ciceksepeti", "pttavm"):
            filtered = commission_service.search_products(marketplace_id, query)
            best_by_pg: Dict[str, Dict[str, Any]] = {}

            def _fmt(val: Optional[float]) -> str:
                if val is None:
                    return ""
                try:
                    return (f"{float(val):.2f}%").replace(".", ",")
                except Exception:
                    return ""

            for r in filtered:
                pg = (r.get("Ürün Grubu", "") or "").strip()
                if not pg:
                    continue
                val = r.get("Komisyon_%_KDV_Dahil", None)
                try:
                    val_num = float(val) if val not in (None, "") else None
                except Exception:
                    val_num = None

                current = best_by_pg.get(pg)
                if current is None or ((val_num or 0.0) > (current.get("_val") or 0.0)):
                    best = dict(r)
                    best["_val"] = val_num
                    best_by_pg[pg] = best

            data = []
            for pg, r in sorted(best_by_pg.items(), key=lambda kv: kv[0].lower()):
                cat = r.get("Kategori", "") or ""
                sub = r.get("Alt Kategori", "") or ""
                val = r.get("_val", None)
                data.append({
                    "Kategori": cat,
                    "Alt Kategori": sub,
                    "Ürün Grubu": pg,
                    "Komisyon_%_KDV_Dahil": val,
                    "komisyon": _fmt(val),
                })
            data = [normalize_api_item(d) for d in data]
            return jsonify({'success': True, 'data': data, 'count': len(data), 'marketplace': marketplace_id})

        # Diğer pazar yerleri: standart davranış
        results = commission_service.search_products(marketplace_id, query)
        safe = []
        for r in results:
            rr = {}
            for k, v in r.items():
                if isinstance(v, float) and pd.isna(v):
                    rr[k] = None
                else:
                    rr[k] = v
            safe.append(rr)

        data = [normalize_api_item(rr) for rr in safe]
        return jsonify({'success': True, 'data': data, 'count': len(data), 'marketplace': marketplace_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.get("/api/categories")
def get_categories():
    try:
        marketplace_id = request.args.get('marketplace', 'trendyol')
        cats = commission_service.list_categories(marketplace_id)
        return jsonify({'success': True, 'data': cats, 'marketplace': marketplace_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.get("/api/sub-categories")
def get_sub_categories():
    try:
        marketplace_id = request.args.get('marketplace', 'trendyol')
        category = request.args.get('category')
        if not category:
            return jsonify({'success': False, 'error': 'Kategori parametresi gerekli'}), 400
        subs = commission_service.list_subcategories(marketplace_id, category)
        return jsonify({'success': True, 'data': subs, 'marketplace': marketplace_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.get("/api/product-groups")
def get_product_groups():
    try:
        marketplace_id = request.args.get('marketplace', 'trendyol')
        category = request.args.get('category')
        sub_category = request.args.get('subCategory')
        if not category or not sub_category:
            return jsonify({'success': False, 'error': 'Kategori ve alt kategori gerekli'}), 400
        grps = commission_service.list_product_groups(marketplace_id, category, sub_category)
        return jsonify({'success': True, 'data': grps, 'marketplace': marketplace_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.get("/api/commission-rate")
def get_commission_rate():
    try:
        marketplace_id = request.args.get('marketplace', 'trendyol')
        category = request.args.get('category')
        sub_category = request.args.get('subCategory')
        product_group = request.args.get('productGroup')
        if not all([category, sub_category, product_group]):
            return jsonify({'success': False, 'error': 'Tüm parametreler gerekli'}), 400
        value = commission_service.find_commission(marketplace_id, category, sub_category, product_group)
        found = (value is not None) and (not pd.isna(value))
        return jsonify({'success': True,
                        'data': float(value) if found else 0.0,
                        'found': bool(found),
                        'marketplace': marketplace_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.post("/api/calculate")
def calculate_commission():
    try:
        params = request.get_json(silent=True) or {}
        marketplace_id = params.get('marketplace', 'trendyol')
        result = commission_service.calculate_commission(marketplace_id, params)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        fallback = commission_service._empty_calc_result("unknown", str(e))
        return jsonify({'success': False, 'error': str(e), 'data': fallback}), 500


# ---- Site-spesifik kısa yol endpoint'leri ----
@app.get("/api/<site>/categories")
def categories_site(site):
    return jsonify(commission_service.list_categories(site))


@app.get("/api/<site>/subcategories")
def subcategories_site(site):
    category = request.args.get("category", "")
    return jsonify(commission_service.list_subcategories(site, category))


@app.get("/api/<site>/groups")
def groups_site(site):
    category = request.args.get("category", "")
    sub = request.args.get("sub", "")
    return jsonify(commission_service.list_product_groups(site, category, sub))


@app.get("/api/<site>/commission")
def commission_site(site):
    category = request.args.get("category", "")
    sub = request.args.get("sub", "")
    group = request.args.get("group", "")
    value = commission_service.find_commission(site, category, sub, group)
    found = (value is not None) and (not pd.isna(value))
    return jsonify({"commission": float(value) if found else 0.0, "found": bool(found)})


# ---- N11'e özel sade endpoint (opsiyonel) ----
@app.get("/api/n11/product-groups")
def n11_product_groups():
    try:
        q = request.args.get("q", "")
        data = commission_service.list_pg_commissions("n11", q)
        data = [normalize_api_item(d) for d in data]
        return jsonify({"success": True, "marketplace": "n11", "count": len(data), "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ---- KDV UI (serves static tester page) ----
@app.get("/kdv")
def kdv_ui():
    try:
        html_path = BASE_DIR / "_legacy" / "kdv.html"
    except Exception:
        html_path = Path(__file__).parent / "_legacy" / "kdv.html"
    return send_file(html_path)


# ==================== MAIN ====================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=False, host="127.0.0.1", port=port)