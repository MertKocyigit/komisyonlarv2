from pathlib import Path
from abc import ABC, abstractmethod
from typing import Dict, Optional
import logging

# Local imports
from scripts.pdf_to_excel_helper import pdf_to_excel
from .utils import run_subprocess, atomic_replace, backup_file, timestamp
from .config import TMP_DIR, BACKUP_DIR

logger = logging.getLogger(__name__)

class BaseUpdate(ABC):
    """Tüm site updater'lar için base interface"""

    name: str

    @abstractmethod
    def target_csv_path(self) -> Path:
        """Hedef CSV dosya yolu"""
        pass

    @abstractmethod
    def extract_script_cmd(self, excel_path: Path, out_csv_path: Path) -> list:
        """Site-specific script komut satırı"""
        pass

    def run(self,
            input_path: Path,
            prefer: str = "auto",
            page_range: Optional[str] = None,
            ocr: bool = False,
            backup: bool = False,
            dry_run: bool = False,
            keep_temp: bool = False) -> Dict:
        """Ana update akışı"""

        input_path = Path(input_path)

        if not input_path.exists():
            raise FileNotFoundError(f"Girdi dosyası bulunamadı: {input_path}")

        # Temp klasörü oluştur
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        # Excel dosyası belirleme
        excel_rows = None
        engine_used = "excel-input"
        created_temp_excel = False

        if input_path.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
            # Excel girdi - direkt kullan
            excel_path = input_path
            logger.info(f"Excel girdi kullanılıyor: {excel_path}")
        else:
            # PDF girdi - önce Excel'e dönüştür
            excel_path = TMP_DIR / f"{self.name}_{timestamp()}_from_pdf.xlsx"
            created_temp_excel = True
            logger.info(f"PDF→Excel dönüşümü: {input_path} → {excel_path}")

            if dry_run:
                engine_used = "dry-run-pdf"
                excel_rows = 0
            else:
                pdf_result = pdf_to_excel(
                    str(input_path),
                    str(excel_path),
                    page_range=page_range,
                    prefer=prefer,
                    ocr=ocr
                )
                engine_used = pdf_result.get("engine_used", "unknown")
                excel_rows = pdf_result.get("rows_total", 0)
                logger.info(f"PDF işlemi tamamlandı - Motor: {engine_used}, Satırlar: {excel_rows}")

        # Temp CSV yolu (benzersiz)
        tmp_csv = TMP_DIR / f"{self.name}_{timestamp()}_new.csv"

        # Site script komutunu hazırla
        cmd = self.extract_script_cmd(excel_path, tmp_csv)

        if dry_run:
            return {
                "site": self.name,
                "dry_run": True,
                "engine_used": engine_used,
                "excel_rows": excel_rows,
                "cmd": " ".join(map(str, cmd)),
                "target_csv": str(self.target_csv_path()),
                "excel_path": str(excel_path),
                "tmp_csv": str(tmp_csv)
            }

        # Site script'ini çalıştır
        logger.info(f"Site script çalıştırılıyor: {self.name}")
        run_subprocess(list(map(str, cmd)))

        if not tmp_csv.exists():
            raise RuntimeError(f"Script CSV üretmedi: {tmp_csv}")

        # CSV boş mu kontrol et
        if tmp_csv.stat().st_size == 0:
            raise RuntimeError(f"Oluşan CSV boş görünüyor: {tmp_csv}")

        # Hedef CSV yolu
        target_csv = self.target_csv_path()

        # Backup (opsiyonel)
        backup_path = None
        if backup and target_csv.exists():
            backup_path = backup_file(target_csv, BACKUP_DIR)

        # Atomik değiştirme
        logger.info(f"CSV güncelleniyor: {tmp_csv} → {target_csv}")
        atomic_replace(tmp_csv, target_csv)

        # Temp Excel'i temizle (PDF'ten üretildiyse)
        if created_temp_excel and not keep_temp:
            try:
                excel_path.unlink(missing_ok=True)
                logger.debug(f"Temp Excel silindi: {excel_path}")
            except Exception:
                logger.warning(f"Temp Excel silinemedi: {excel_path}")

        return {
            "site": self.name,
            "engine_used": engine_used,
            "excel_rows": excel_rows,
            "csv_path": str(target_csv),
            "backup_path": str(backup_path) if backup_path else None,
            "excel_path": str(excel_path)
        }
