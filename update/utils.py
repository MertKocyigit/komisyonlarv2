from pathlib import Path
import os
import shutil
import subprocess
import datetime
import logging

logger = logging.getLogger(__name__)

def run_subprocess(cmd: list) -> None:
    """Subprocess çalıştır ve hata durumunda exception at"""
    logger.info(f"Komut çalıştırılıyor: {' '.join(map(str, cmd))}")

    env = os.environ.copy()
    # Çocuk süreçleri UTF-8 moda zorla
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    result = subprocess.run(
        list(map(str, cmd)),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        encoding="utf-8",
        errors="replace",  # cp1254 gibi konsollarda çökmesin
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Komut başarısız (exit code: {})\nKomut: {}\nSTDOUT:\n{}\nSTDERR:\n{}".format(
                result.returncode, " ".join(map(str, cmd)), result.stdout, result.stderr
            )
        )

def atomic_replace(src: Path, dst: Path) -> None:
    """Atomik dosya değiştirme (mümkünse os.replace, değilse fallback)"""
    src = Path(src)
    dst = Path(dst)

    # Hedef klasörü oluştur
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Aynı file system'de atomik
        os.replace(src, dst)
        logger.info(f"Atomik replace: {src} → {dst}")
    except OSError:
        # Farklı file system fallback
        logger.warning("Farklı disk, fallback kullanılıyor")
        if dst.exists():
            dst.unlink()
        shutil.move(str(src), str(dst))
        logger.info(f"Fallback move: {src} → {dst}")

def timestamp() -> str:
    """Timestamp formatı: 2025-08-27_142501"""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")

def backup_file(file_path: Path, backup_dir: Path) -> Path:
    """Dosyayı backup klasörüne tarih damgasıyla kopyala"""
    if not file_path.exists():
        raise FileNotFoundError(f"Yedeklenecek dosya bulunamadı: {file_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{file_path.stem}_{timestamp()}{file_path.suffix}"

    shutil.copy2(file_path, backup_path)
    logger.info(f"Backup oluşturuldu: {backup_path}")

    return backup_path
