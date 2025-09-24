Proje Yapısı ve Veri Akışı (Genel Bakış)
proje_structured/
├── app.py                  # Flask API + arayüzü besleyen servis
├── _legacy/index.html      # Hazır UI (komisyon/kar hesaplama + arama)
├── data/
│   ├── hepsiburada_commissions.csv
│   ├── n11_commissions.csv
│   ├── commissions_flat.csv           # Trendyol çıktısı
│   ├── amazon_commissions.csv         # Amazon TR (hazır CSV)
│   ├── ciceksepeti_commissions.csv
│   ├── pttavm_commissions.csv
│   ├── tmp/                           # PDF→Excel ara dosyalar
│   └── backup/                        # Otomatik yedekler (timestamp’li)
├── scripts/                            # Kaynaktan çıkarıcılar (extractor)
│   ├── pdf_to_excel_helper.py          # PDF→Excel yardımcı
│   ├── trendyol_extract_commissions.py
│   ├── hepsiburada_extract_commissions.py
│   ├── n11_extract_commissions.py
│   ├── ciceksepeti_extract_commissions.py
│   └── pttavm_extract_commissions.py
└── update/                             # “Tek komutla güncelle” sarmalayıcılar
    ├── run_update.py                   # Ortak CLI (site seçerek)
    ├── trendyol_update.py
    ├── hepsiburada_update.py
    ├── n11_update.py
    ├── ciceksepeti_update.py
    └── pttavm_update.py


Sistemin ana yürütücüsü app.py dosyasıdır. Arayüz (_legacy/index.html) ve REST uçları bu bileşen üzerinden sunulur. Veriler data/ dizini altındaki CSV dosyalarından okunur. scripts/ dizini, ham kaynakları (PDF/Excel) dört sütunlu standart CSV formatına dönüştürür. update/ dizini ise bu adımları tek komutla çalıştıran orkestrasyon dosyalarını içerir.

Arayüzün ve API’nin beklediği standart CSV şeması aşağıdaki gibidir:

Kategori | Alt Kategori | Ürün Grubu | Komisyon_%_KDV_Dahil

Kolon adları dosyadan dosyaya küçük farklılıklar gösterebilir; app.py içerisinde tanımlı bir eşleştirme haritası (candidate isimler) bulunmaktadır. Bu sayede “Urun Grubu”/“Ürün Grubu” gibi başlık varyasyonlarında kodda değişiklik yapılmasına gerek kalmadan servis doğru alanları otomatik olarak eşler.

Arayüz ve API – Günlük Kullanım

Arayüz açıldığında; solda pazaryeri seçimi (Trendyol, Hepsiburada, N11, Amazon, ÇiçekSepeti, PTTAVM), ortada arama alanı ve altta komisyon/kâr hesaplama bileşenleri yer alır. Kullanım akışı basittir: arama kutusuna yazılır, listeden uygun satır seçilir ve komisyon alanları otomatik olarak doldurulur. Dileyen kullanıcılar aynı işlemleri doğrudan API üzerinden de gerçekleştirebilir.

Arama davranışı pazaryerine göre farklılık gösterir:

Hepsiburada: Kategori / Alt Kategori / Ürün Grubu / Komisyon sütunları ile sonuç verir.

N11 & Amazon: Arama alanında yalnızca Ürün Grubu görüntülenir; aynı ürüne birden fazla oran varsa maksimum komisyon döndürülür.

ÇiçekSepeti & PTTAVM: Yol bilgisi (“Kategori → Alt Kategori → Ürün Grubu”) gösterilir; birden fazla oran mevcutsa en yüksek oran esas alınır.

Trendyol: Sonuçlar düz satırlar halinde gelir ve komisyon doğrudan alınır.

CSV dosyalarında değişiklik gerçekleştiğinde servis bu durumu algılar ve hot-reload ile dosyaları yeniden yükler.

POST /api/reload


Sık kullanılan uç noktaların özeti aşağıdadır:

Pazaryerlerini listeleme: GET /api/marketplaces

Arama: GET /api/search?marketplace={id}&q={metin}

Kategori zinciri:
GET /api/categories?marketplace={id}
GET /api/sub-categories?marketplace={id}&category={adı}
GET /api/product-groups?marketplace={id}&category={adı}&subCategory={adı}

Doğrudan komisyon oranı:
GET /api/commission-rate?marketplace={id}&category={adı}&subCategory={adı}&productGroup={adı}

Kâr/komisyon hesaplama (POST JSON):
/api/calculate

Güncelleme (Update) Akışları – PDF’ten CSV’ye Tek Adımda

Güncelleme süreci temelde üç aşamadan oluşur ve çoğu durumda bu adımlar update/ altındaki komutlar tarafından otomatik olarak yürütülür:

PDF → Excel (gerekiyorsa)

Excel/PDF → CSV (4 sütun)

CSV’nin data/ dizinine yazılması ve önceki sürümün data/backup/ altına yedeklenmesi

Tüm siteler için ortak bir komut mevcuttur. Hedef site seçilerek aşağıdaki şekilde çalıştırılır:

python -m update.run_update \
  --site n11|hepsiburada|trendyol \
  --pdf "C:\…\kaynak.pdf" \
  --prefer auto \
  --backup --log INFO
# ya da hazır Excel varsa
python -m update.run_update --site hepsiburada --excel "C:\…\from_pdf.xlsx" --backup


Ek notlar: --prefer ile pdfplumber/camelot/tabula seçilebilir; --ocr karmaşık PDF’lerde yardımcı olur; --dry-run çıktıyı yazmadan deneme yapar; --keep-temp ara dosyaların korunmasını sağlar.

Gerekirse pazaryerine özel komutlar da kullanılabilir:

Trendyol

python -m update.trendyol_update --pdf "…Trendyol.pdf" --backup
# ya da
python -m update.trendyol_update --excel "…trendyol_from_pdf.xlsx" --backup


Çıktı: data/commissions_flat.csv

Hepsiburada

python -m update.hepsiburada_update --pdf "…Hepsiburada.pdf" --backup
# veya
python -m update.hepsiburada_update --excel "…hepsiburada_from_pdf.xlsx" --backup


Çıktı: data/hepsiburada_commissions.csv

N11

python -m update.n11_update --pdf "…n11.pdf" --backup
# veya
python -m update.n11_update --excel "…n11_from_pdf.xlsx" --backup


Çıktı: data/n11_commissions.csv
Not: N11 aramasının arayüzde yalnızca Ürün Grubu göstermesi, karmaşıklığı azaltmak ve en yüksek oranı öne çıkarmak amacıyla tercih edilmiştir.

ÇiçekSepeti

python -m update.ciceksepeti_update --pdf "…ciceksepeti.pdf" --backup


İç süreçte metin tabanlı ayrıştırma uygulanır; aynı Ürün Grubu birden fazla kez geçiyorsa maksimum komisyon dikkate alınır.
Çıktı: data/ciceksepeti_commissions.csv

PTTAVM

python -m update.pttavm_update --pdf "…pttavm.pdf" --out-csv "data/pttavm_commissions.csv" --backup


pdfplumber ile tablo yakalanır, temizlenir ve standart dört sütunlu formata dönüştürülür.
Çıktı: data/pttavm_commissions.csv

Amazon TR
Şimdilik hazır CSV üzerinden çalışmaktadır (data/amazon_commissions.csv). İleride PDF/Excel akışına geçirilmek istendiğinde scripts/ altına bir extractor ve update/ altına bir sarmalayıcı eklenerek aynı desen izlenebilir.

Ürün ve Komisyon Bulma – Arka Plan

Arama işlemi önce kategori, ardından alt kategori ve son olarak ürün grubu eşleşmelerine bakar. Türkçe karakterler normalize edildiğinden “kulaklık” ile “kulaklik” aynı şekilde değerlendirilir.

{
  category, subCategory, productGroup,
  commissionPercent, commissionText,
  displayProductGroup  # "Kategori → Alt Kategori → Ürün Grubu"
}


Pazaryerine bağlı nüanslar bulunmaktadır; örneğin N11/Amazon yalnızca ürün grubunu verir.

Diğer Python Betikleri – Sorumluluklar

scripts/pdf_to_excel_helper.py
PDF tabanlı tabloları çıkararak Processed_Data sayfasına sahip bir Excel üretir. Varsayılan motor pdfplumber olup, gerekirse camelot/tabula tercih edilebilir.

scripts/trendyol_extract_commissions.py
Kaynak veriyi aşağıdaki dört sütunlu standarda dönüştürür: Kategori | Alt Kategori | Ürün Grubu | Komisyon_%_KDV_Dahil.

scripts/hepsiburada_extract_commissions.py
Processed_Data üzerinden aynı dört sütunlu CSV’yi hazırlar.

scripts/n11_extract_commissions.py
N11’e özgü metin yapısı için kural tabanlı ayrıştırma yapar. Komisyon değerini + işaretini izleyen ilk sayısal ifadeden alır; ürün grubunu ilgili metin parçasından türetir.

scripts/ciceksepeti_extract_commissions.py
Metin tabanlı ayrıştırma, eşleme listeleri ve düzenli ifadelerle veriyi dört sütunlu forma indirger.

scripts/pttavm_extract_commissions.py
Tablolar pdfplumber ile çekilir, başlıklar/gürültü temizlenir.

update/*_update.py
Her pazaryeri için “PDF→(Excel)→CSV→yedek” adımlarını sıralı biçimde çalıştırır.

update/run_update.py
Ortak giriş noktasıdır; --site parametresiyle hedef belirlenerek işlemler yürütülür.

core/*
Veri modeli ve servis katmanı burada bulunur: datasource CSV okuma/normalize işlemlerini üstlenir; services kategori–ürün grubu–komisyon sorgularını koordine eder; registry pazaryeri çözümlemelerini gerçekleştirir.

Örnek İstekler (cURL)
# Arama (N11 – yalnız Ürün Grubu + maksimum komisyon)
curl "http://127.0.0.1:5000/api/search?marketplace=n11&q=kulaklik"

# Kategori zinciri
curl "http://127.0.0.1:5000/api/categories?marketplace=hepsiburada"
curl "http://127.0.0.1:5000/api/sub-categories?marketplace=hepsiburada&category=Elektronik"
curl "http://127.0.0.1:5000/api/product-groups?marketplace=hepsiburada&category=Elektronik&subCategory=Kulaklik"

# Komisyon oranı
curl "http://127.0.0.1:5000/api/commission-rate?marketplace=trendyol&category=Elektronik&subCategory=Kulaklik&productGroup=TrueWireless"

# Hesaplama
curl -X POST "http://127.0.0.1:5000/api/calculate" \
  -H "Content-Type: application/json" \
  -d '{
    "marketplace":"trendyol",
    "salePrice": 1000,
    "buyPrice": 600,
    "cargoPrice": 30,
    "vatPercent": 20,
    "commissionPercent": 12.5,
    "servicePercent": 0,
    "exportPercent": 0,
    "includeVatDeduction": true
  }'