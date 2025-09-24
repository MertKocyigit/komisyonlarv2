<div align="center">

# Çoklu Pazar Yeri Komisyon Araç Takımı

Türkiye e-ticaret pazar yerleri için komisyon tablolarını **çıkaran**, **normalize eden** ve **sorgulayan** birleşik bir araç takımı.

- Üretim-hazır **Flask API** (`app.py`) ve sade bir web arayüzü (`_legacy/index.html`)
- **Güncelleme hattı** (`update/`): PDF → (Excel) → Standart CSV
- Pazar yeri bazlı **çıkarıcı betikler** (`scripts/`)
- İnce bir **domain/servis katmanı** (`core/`)

> Hazır akışlar: **Trendyol**, **Hepsiburada**, **N11**, **ÇiçekSepeti**, **PTTAVM**.  
> (Ayrıca **Amazon TR** için CSV okuma mevcut; istenirse aynı şablonla PDF/Excel akışına genişletilebilir.)

</div>

---

## İçindekiler

- [1) Hızlı Başlangıç](#1-hızlı-başlangıç)
  - [Gereksinimler](#gereksinimler)
  - [Kurulum](#kurulum)
  - [API’yi Çalıştırma](#apiyi-çalıştırma)
  - [Ortam Değişkenleri](#ortam-değişkenleri)
- [2) Veri Modeli & Normalizasyon](#2-veri-modeli--normalizasyon)
- [3) Proje Yapısı](#3-proje-yapısı)
- [4) API Uçları](#4-api-uçları)
- [5) Güncelleme Hatları (PDF→(Excel)→CSV)](#5-güncelleme-hatları-pdfexcelcsv)
  - [Ortak Bayraklar](#ortak-bayraklar)
  - [Varsayılan Çıktı Dosyaları](#varsayılan-çıktı-dosyaları)
  - [N11 – Kısa not](#n11--kısa-not)
  - [ÇiçekSepeti – Kısa not](#çiçeksepeti--kısa-not)
  - [PTTAVM – Kısa not](#pttavm--kısa-not)
- [6) Frontend (`_legacy/index.html`)](#6-frontend-_legacyindexhtml)
- [7) Yeni Pazar Yeri Ekleme](#7-yeni-pazar-yeri-ekleme)
- [8) Sık Karşılaşılan Sorunlar](#8-sık-karşılaşılan-sorunlar)
- [9) Geliştirme Notları](#9-geliştirme-notları)

---

## 1) Hızlı Başlangıç

### Gereksinimler
- Python **3.11+** (önerilen: 3.12)
- `pip` ve tercihen sanal ortam (venv)
- (İhtiyaca göre) PDF motorları:  
  - `pdfplumber` (varsayılan)  
  - `camelot-py` (Ghostscript gerekir)  
  - `tabula-py` (Java gerekir)

### Kurulum
```bash
python -m venv .venv
# Windows
.\venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

# Gereken paketler (ör.)
pip install flask flask-cors pandas openpyxl pdfplumber
# İhtiyaç olursa:
# pip install camelot-py tabula-py
```

### API’yi Çalıştırma
```bash
# CSV klasörü (opsiyonel – aksi halde <repo>/data kullanılır)
# Windows
set DATA_DIR=C:\full\path\to\data
# macOS/Linux
# export DATA_DIR="/full/path/to/data"

# (Ops.) özel index dosyası
# Windows
# set INDEX_HTML_PATH=C:\full\path\to\index.html
# macOS/Linux
# export INDEX_HTML_PATH="/full/path/to/index.html"

python app.py
# → http://127.0.0.1:5000
```

### Oram Değişkenleri
- `DATA_DIR` → normalize CSV klasörü (varsayılan: `<repo>/data`)
- `INDEX_HTML_PATH` → özel bir HTML dosyası servis etmek istersen
- `PORT` → varsayılan `5000`

---

## 2) Veri Modeli & Normalizasyon

Tüm pazar yerleri **4 kolon**a normalize edilir (UI ve API bu şemayı kullanır):

| Kategori | Alt Kategori | Ürün Grubu | Komisyon_%_KDV_Dahil |
|---|---|---|---|

**`data/` içindeki örnek CSV’ler**
- `commissions_flat.csv` (Trendyol)
- `hepsiburada_commissions.csv`
- `n11_commissions.csv`
- `ciceksepeti_commissions.csv`
- `pttavm_commissions.csv`
- (Ops.) `amazon_commissions.csv`

Geçici/yedek klasörleri:
- `data/tmp/` → geçici Excel/CSV çıktıları
- `data/backup/` → zaman damgalı CSV yedekleri

> Kolon adları dosyadan dosyaya değişebilir. `app.py` içindeki **eşleştirme (candidate) listeleri**, “Urun Grubu/Ürün Grubu” gibi farklı başlıkları otomatik eşler.

---

## 3) Proje Yapısı

```
proje_structured/
├── app.py                  # Flask API + arayüzü besleyen servis
├── _legacy/index.html      # Basit UI (arama + kârlılık hesaplama)
├── data/                   # Normalize CSV’ler + tmp/ + backup/
│   ├── hepsiburada_commissions.csv
│   ├── n11_commissions.csv
│   ├── commissions_flat.csv           # Trendyol
│   ├── amazon_commissions.csv         # Amazon TR (hazır CSV)
│   ├── ciceksepeti_commissions.csv
│   ├── pttavm_commissions.csv
│   ├── tmp/
│   └── backup/
├── scripts/                # PDF/Excel → CSV çıkarıcıları
│   ├── pdf_to_excel_helper.py
│   ├── trendyol_extract_commissions.py
│   ├── hepsiburada_extract_commissions.py
│   ├── n11_extract_commissions.py
│   ├── ciceksepeti_extract_commissions.py
│   └── pttavm_extract_commissions.py
└── update/                 # PDF→(Excel)→CSV tek komutluk akışlar
    ├── run_update.py       # Ortak CLI (site seçerek)
    ├── trendyol_update.py
    ├── hepsiburada_update.py
    ├── n11_update.py
    ├── ciceksepeti_update.py
    └── pttavm_update.py
```

**Önemli modüller**
- **core/** → veri modeli ve servis katmanı  
  `datasource.py` (CSV okuma/eşleme), `interfaces.py`, `models.py`, `registry.py`, `services.py`
- **scripts/** → pazar yeri özel extractor’lar
- **update/** → “tek komutla güncelle” sarmalayıcıları
- **app.py** → REST API ve UI servis katmanı

---

## 4) API Uçları

Temel URL: `http://127.0.0.1:5000`

**Pazar yerleri & Hot-reload**
```
GET  /api/marketplaces
POST /api/reload                 # CSV’leri yeniden yüklemeye zorlar (mtime izleme de var)
```

**Arama (UI listeleri için)**
```
GET /api/search?marketplace=<id>&q=<text>
```
- **N11 & Amazon**: yalnızca **Ürün Grubu** + (maks.) komisyon döner
- **Trendyol/Hepsiburada/ÇiçekSepeti/PTTAVM**: yol bilgisi (Kategori→Alt Kategori→Ürün Grubu) + komisyon

**Hiyerarşi sorguları**
```
GET /api/categories?marketplace=<id>
GET /api/sub-categories?marketplace=<id>&category=<cat>
GET /api/product-groups?marketplace=<id>&category=<cat>&subCategory=<sub>
```

**Komisyon sorgusu (tekil)**
```
GET /api/commission-rate?marketplace=<id>&category=<cat>&subCategory=<sub>&productGroup=<pg>
→ { data: <float>, found: true/false }
```

**Kârlılık hesaplama**
```
POST /api/calculate
Body (JSON):
{
  "marketplace": "trendyol",
  "salePrice": 1000.0,        # KDV dahil satış
  "buyPrice": 700.0,          # KDV dahil maliyet
  "commissionPercent": 12.5,  # KDV dahil komisyon %
  "servicePercent": 0.0,
  "exportPercent": 0.0,
  "cargoPrice": 0.0,
  "vatPercent": 20.0,
  "includeVatDeduction": true
}
→ { payout, netProfit, profitMargin, ... KDV kırılımları ... }
```

**Örnek `curl`**
```bash
curl "http://127.0.0.1:5000/api/search?marketplace=n11&q=telefon"
curl "http://127.0.0.1:5000/api/categories?marketplace=trendyol"
curl "http://127.0.0.1:5000/api/commission-rate?marketplace=hepsiburada&category=Elektronik&subCategory=Telefon&productGroup=Aksesuar"
```

---


## 5) Güncelleme Hatları (PDF→(Excel)→CSV)

Bu bölüm, her pazar yeri için **tek komutla** güncelleme örneklerini içerir.  
Varsayılan çıktı klasörü: `<repo>/data` • Geçici: `<repo>/data/tmp` • Yedekler: `<repo>/data/backup`

### Hızlı Özet

| Pazar yeri     | Komut (önerilen)                         | Girdi              | Varsayılan çıktı CSV                | Not |
|---|---|---|---|---|
| **N11**         | `python -m update.run_update --site n11 …`          | `--pdf` veya `--excel` | `data/n11_commissions.csv`          | PDF→Excel dener; gerekirse doğrudan PDF parse |
| **Hepsiburada** | `python -m update.run_update --site hepsiburada …`  | `--pdf` veya `--excel` | `data/hepsiburada_commissions.csv`  | Excel’de `Processed_Data` sayfası beklenir |
| **Trendyol**    | `python -m update.run_update --site trendyol …`     | `--pdf` veya `--excel` | `data/commissions_flat.csv`         | Excel’de `Processed_Data` sayfası beklenir |
| **ÇiçekSepeti** | `python -m update.ciceksepeti_update …`             | **`--pdf`**            | `data/ciceksepeti_commissions.csv`  | Extractor yolu esnek (parametre/ENV/fallback) |
| **PTTAVM**      | `python -m update.pttavm_update …`                  | **`--pdf`**            | `data/pttavm_commissions.csv`       | Extractor script yolu verilmeli |

> `--backup` yedeği `data/backup/` altına zaman damgalı dosya olarak alır.  
> `--keep-temp` geçici dosyaları `data/tmp/` altında **silmeden** bırakır (debug).

---

### 5.1 Birleşik Koşucu (run_update) — *N11 / Hepsiburada / Trendyol*

> **Sadece bu üç siteyi** destekler: `--site n11|hepsiburada|trendyol`  
> Girdi **mutlaka** `--pdf` **veya** `--excel` olmalı (ikisi birden değil).

**Genel kullanım (PDF’ten başlat)**  
```bash
python -m update.run_update --site n11 \
  --pdf "C:\path\N11_Komisyon_Oranlari-2025.pdf" \
  --prefer auto --page-range "1-99" --backup --keep-temp --log INFO
```

**Excel hazırsa (PDF→Excel’i önceden ürettin)**  
```bash
python -m update.run_update --site hepsiburada \
  --excel "C:\path\hepsiburada_from_pdf.xlsx" \
  --backup --log INFO
```

**Trendyol (PDF örneği)**  
```bash
python -m update.run_update --site trendyol \
  --pdf "C:\path\Trendyol_Komisyon.pdf" \
  --prefer pdfplumber --backup --log INFO
```

**Notlar**
- PDF girdi verildiğinde `run_update`, mümkünse otomatik olarak **PDF→Excel (Processed_Data)** üretir ve ardından normalize eder.
- Hepsiburada/Trendyol’da Excel yolu verdiğinde **`Processed_Data`** sayfası beklenir (helper çıktısıyla uyumlu).
- Çalışma sonunda **JSON özet** STDOUT’a yazılır (site, `csv_path`, kullanılan `excel_path`, vb.).

---

### 5.2 N11 — ek örnekler

**PDF ile (otomatik PDF→Excel denemeli, gerekirse direkt PDF parse fallback)**  
```bash
python -m update.run_update --site n11 \
  --pdf "C:\path\N11_Komisyon_Oranlari-2025.pdf" \
  --prefer auto --backup --log INFO
```

**Excel ile (Processed_Data sayfası)**  
```bash
python -m update.run_update --site n11 \
  --excel "C:\path\n11_from_pdf.xlsx" \
  --backup --keep-temp --log DEBUG
```

---

### 5.3 Hepsiburada — ek örnek

```bash
python -m update.run_update --site hepsiburada \
  --pdf "C:\path\HB_Komisyon_Listesi.pdf" \
  --prefer auto --page-range "1,3,5-9" --backup --log INFO
```

---

### 5.4 Trendyol — ek örnek

```bash
python -m update.run_update --site trendyol \
  --excel "C:\path\trendyol_from_pdf.xlsx" \
  --backup --log INFO
```

---

### 5.5 ÇiçekSepeti (özel sarmalayıcı)

`update.run_update` kapsamı **dışındadır**. `update.ciceksepeti_update` kullan.

**Hızlı başlat (extractor yolu otomatik bulunmaya çalışılır)**  
```bash
python -m update.ciceksepeti_update \
  --pdf "C:\path\Ciceksepeti_Komisyon.pdf" \
  --backup --log INFO
```

**Extractor yolunu elle belirtme**  
```bash
python -m update.ciceksepeti_update \
  --pdf "C:\path\Ciceksepeti_Komisyon.pdf" \
  --extractor ".\scripts\ciceksepeti_extract_commissions.py" \
  --backup --log DEBUG
```

**ENV ile extractor belirtme (Windows ör.)**  
```bat
set CICEKSEPETI_EXTRACTOR=.\scripts\ciceksepeti_extract_commissions.py
python -m update.ciceksepeti_update --pdf "C:\path\Ciceksepeti_Komisyon.pdf" --backup
```

---

### 5.6 PTTAVM (özel sarmalayıcı)

`update.run_update` kapsamı **dışındadır**. `update.pttavm_update` kullan.

**Örnek kullanım**  
```bash
python -m update.pttavm_update \
  --pdf "C:\path\PTTAVM_Komisyon.pdf" \
  --extractor ".\scripts\pttavm_extract_commissions.py" \
  --out-csv ".\data\pttavm_commissions.csv" \
  --backup
```

---

### 5.7 Doğrudan extractor çalıştırmak (opsiyonel)

Bazen ayarları ince ayar yapmak isteyebilirsin. Extractor’lar doğrudan da çağrılabilir:

**N11 (PDF → CSV)**  
```bash
python .\scripts\n11_extract_commissions.py \
  --pdf "C:\path\N11_Komisyon_Oranlari-2025.pdf" \
  --out-csv ".\data\n11_commissions.csv" --log INFO
```

**Hepsiburada (Excel→CSV)**  
```bash
python .\scripts\hepsiburada_extract_commissions.py \
  --excel "C:\path\hepsiburada_from_pdf.xlsx" --sheet "Processed_Data" \
  --out-csv ".\data\hepsiburada_commissions.csv" --log INFO
```

**Trendyol (PDF→CSV)**  
```bash
python .\scripts\trendyol_extract_commissions.py \
  --pdf "C:\path\Trendyol_Komisyon.pdf" \
  --out-csv ".\data\commissions_flat.csv"
```

**ÇiçekSepeti (PDF→CSV)**  
```bash
python .\scripts\ciceksepeti_extract_commissions.py \
  --pdf "C:\path\Ciceksepeti_Komisyon.pdf" \
  --out-app-csv ".\data\ciceksepeti_commissions.csv" --backup
```

**PTTAVM (PDF→CSV)**  
```bash
python .\scripts\pttavm_extract_commissions.py \
  --pdf "C:\path\PTTAVM_Komisyon.pdf" \
  --out-app-csv ".\data\pttavm_commissions.csv" --backup
```

---

### 5.8 İpuçları

- **Sayfa filtresi**: `--page-range "1-3,7,10-12"` biçimi geçerlidir.
- **Motor seçimi**: `--prefer pdfplumber|camelot|tabula|auto`  
  - `camelot` için **Ghostscript**, `tabula` için **Java** gerekir.
- **Log seviyesi**: `--log DEBUG` ile ayrıntılı akış görülebilir.
- **Geçici dosyalar**: `--keep-temp` ile `data/tmp/` korunur; PDF→Excel ara çıktıları ve ham satırlar burada kalır.



## 6) Frontend (`_legacy/index.html`)

Tailwind tabanlı basit bir arayüz:
- Pazar yeri seçimi + **ürün/komisyon arama**
- Fiyat/masraf girişleri
- **Ödeme, net kâr, marj** ve KDV kırılımı
- Grafiksel özet

> `INDEX_HTML_PATH` ayarlanmadıysa `app.py`, `_legacy/index.html` dosyasını `/` adresinden servis eder.

---

## 7) Yeni Pazar Yeri Ekleme

1. Extractor yaz (PDF/Excel → 4 kolonlu CSV) ve `scripts/` altına ekle.  
2. Güncelleme sarmalayıcısı oluştur (`update/<site>_update.py`).  
3. `app.py` içindeki pazar yeri kaydına **CSV yolu** ve **kolon adayları** ekle.  
4. CSV’yi `data/` altına koy, `POST /api/reload` ile yeniden yükle.

---

## 8) Sık Karşılaşılan Sorunlar

- **“Ürün Grubu kolonu bulunamadı”** → CSV başlıkları beklenen isimlerle eşleşmiyor olabilir. İlgili pazar yerinin **candidate** listesini güncelle veya başlıkları düzelt.  
- **Ondalık/yüzde karmaşası** → Virgül/nokta ayracı normalize edilir; yine de komisyon değerlerinin yüzde türünde olduğundan emin ol.  
- **PDF’ten tablo çıkmıyor** → `--prefer camelot` veya `--prefer tabula` ile deneyin (sistem bağımlılıklarını kurduğunuzdan emin olun).  
- **Hot-reload görmüyor** → `POST /api/reload` çağırın veya API’yi yeniden başlatın (mtime takibi de var).  
- **Windows yol biçimi** → Ters bölü işaretlerini kaçırın veya raw string kullanın.

---

## 9) Geliştirme Notları

- ETL: **pandas**, Excel I/O: **openpyxl**.  
- Veritabanı yok; **CSV** tabanlı yapı yedekleme/diff için pratik.  
- `core/` ince tutuldu; genişletme kolay.  
- UI/REST ayrımı net: UI yalnızca API’yi tüketir.

---

