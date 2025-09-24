#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, logging, importlib.util, sys
from pathlib import Path

log = logging.getLogger("pttavm_update")

def import_extractor(extractor_path: str):
    spec = importlib.util.spec_from_file_location("ptt_ext", extractor_path)
    if not spec or not spec.loader:
        raise RuntimeError("Extractor yüklenemedi")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    ap = argparse.ArgumentParser(description="PTTAVM komisyon PDF → CSV")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--extractor", required=False,
                    default=str(Path(__file__).resolve().parents[1] / "scripts" / "pttavm_extract_commissions.py"))
    ap.add_argument("--log", choices=["DEBUG","INFO","WARNING","ERROR"], default="INFO")
    ap.add_argument("--backup", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log))
    mod = import_extractor(args.extractor)

    out_csv = Path(args.out_csv)
    info = mod.run(
        args.pdf,
        out_lines_csv=out_csv.parent / "tmp" / "pttavm_lines.csv",
        out_raw_csv=out_csv.parent / "tmp" / "pttavm_raw.csv",
        out_app_csv=out_csv,
        backup=args.backup
    )
    log.info("Tamam: %s", info)

if __name__ == "__main__":
    sys.exit(main())
