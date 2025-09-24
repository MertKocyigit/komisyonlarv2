
from flask import Blueprint, request, jsonify
from .kdv import add_vat, remove_vat, from_vat_amount

calc_bp = Blueprint("calc_bp", __name__, url_prefix="/api/calc")

def _to_camel_payload(res, direction, rounding):
    # Map dataclass fields (snake_case) -> camelCase
    data = {
        "direction": direction,
        "rounding": rounding,
        "priceExclVat": res.price_excl_vat,
        "vatAmount": res.vat_amount,
        "priceInclVat": res.price_incl_vat,
        "rate": res.rate,
        "withholdingRate": res.withholding_rate,
        "withholdingAmount": res.withholding_amount,
        "payableVat": res.payable_vat,
        "error": None,
        "params": {},
    }
    return data

@calc_bp.post("/kdv")
def api_calc_kdv():
    try:
        d = request.get_json(silent=True) or {}
        direction = str(d.get("direction", "add")).lower()
        rate = d.get("rate", 0.20)
        rounding = d.get("rounding", "even")  # "even" | "up"
        w = d.get("withholdingRate", d.get("withholding_rate"))

        if direction == "add":
            price = float(d["price"])
            res = add_vat(price, rate=rate, withholding_rate=w, rounding=rounding)
        elif direction == "remove":
            price = float(d["price"])
            res = remove_vat(price, rate=rate, withholding_rate=w, rounding=rounding)
        elif direction in ("from_vat", "from_kdv"):
            vat_amount = float(d["vatAmount"] if "vatAmount" in d else d["vat_amount"])
            res = from_vat_amount(vat_amount, rate=rate, withholding_rate=w, rounding=rounding)
            direction = "from_vat"
        else:
            return jsonify({"success": False, "error": "direction 'add' | 'remove' | 'from_vat' olmalı", "data": {}}), 400

        data = _to_camel_payload(res, direction, rounding)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "data": {}}), 500
