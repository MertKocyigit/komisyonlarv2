from pathlib import Path

# Proje kökü
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Ana klasörler
DATA_DIR = PROJECT_ROOT / "data"
TMP_DIR = DATA_DIR / "tmp"
BACKUP_DIR = DATA_DIR / "backup"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Hedef CSV dosyaları
N11_CSV_PATH = DATA_DIR / "n11_commissions.csv"
HEPSIBURADA_CSV_PATH = DATA_DIR / "hepsiburada_commissions.csv"
TRENDYOL_CSV_PATH = DATA_DIR / "commissions_flat.csv"  # Mevcut trendyol dosya adı
