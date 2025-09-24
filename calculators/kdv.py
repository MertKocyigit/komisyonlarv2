
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP, getcontext
from typing import Literal, Optional, Union

getcontext().prec = 28
TWOP = Decimal("0.01")
RoundingMode = Literal["even","half_even","up","half_up"]

def _q2(x: Decimal, mode: RoundingMode) -> Decimal:
    r = ROUND_HALF_EVEN if mode in ("even", "half_even") else ROUND_HALF_UP
    return x.quantize(TWOP, rounding=r)

def _norm_rate(rate_input: Union[float,int,str]) -> Decimal:
    r = Decimal(str(rate_input))
    return r/Decimal(100) if r >= 1 else r

def _parse_withholding(w: Optional[Union[str,float,int]]) -> Decimal:
    if w is None:
        return Decimal("0")
    s = str(w).strip().replace(" ","")
    if "/" in s:
        a,b = s.split("/",1)
        if b == "0": return Decimal("0")
        return (Decimal(a)/Decimal(b)).max(Decimal("0")).min(Decimal("1"))
    val = Decimal(s)
    if val > 1: val = val/Decimal(100)
    if val < 0: val = Decimal("0")
    if val > 1: val = Decimal("1")
    return val

@dataclass
class KDVResult:
    price_excl_vat: float   # net
    vat_amount: float       # kdv
    price_incl_vat: float   # brut
    rate: float
    withholding_rate: float
    withholding_amount: float
    payable_vat: float

def add_vat(price_excl_vat: float, rate: Union[float,int,str] = 0.20,
            withholding_rate: Optional[Union[str,float,int]] = None,
            rounding: RoundingMode = "even", ndigits: int = 2) -> KDVResult:
    net = Decimal(str(price_excl_vat))
    oran = _norm_rate(rate)
    kdv = _q2(net * oran, rounding)
    brut = _q2(net + kdv, rounding)
    tw = _parse_withholding(withholding_rate)
    tevkifat = _q2(kdv * tw, rounding)
    payable = _q2(kdv - tevkifat, rounding)
    return KDVResult(float(_q2(net, rounding)), float(kdv), float(brut), float(oran),
                     float(tw), float(tevkifat), float(payable))

def remove_vat(price_incl_vat: float, rate: Union[float,int,str] = 0.20,
               withholding_rate: Optional[Union[str,float,int]] = None,
               rounding: RoundingMode = "even", ndigits: int = 2) -> KDVResult:
    brut = Decimal(str(price_incl_vat))
    oran = _norm_rate(rate)
    net = _q2(brut / (Decimal(1) + oran), rounding)
    kdv = _q2(brut - net, rounding)
    brut = _q2(brut, rounding)
    tw = _parse_withholding(withholding_rate)
    tevkifat = _q2(kdv * tw, rounding)
    payable = _q2(kdv - tevkifat, rounding)
    return KDVResult(float(net), float(kdv), float(brut), float(oran),
                     float(tw), float(tevkifat), float(payable))

def from_vat_amount(vat_amount: float, rate: Union[float,int,str] = 0.20,
                    withholding_rate: Optional[Union[str,float,int]] = None,
                    rounding: RoundingMode = "even", ndigits: int = 2) -> KDVResult:
    kdv = _q2(Decimal(str(vat_amount)), rounding)
    oran = _norm_rate(rate)
    net = _q2(kdv / oran, rounding)
    brut = _q2(net + kdv, rounding)
    tw = _parse_withholding(withholding_rate)
    tevkifat = _q2(kdv * tw, rounding)
    payable = _q2(kdv - tevkifat, rounding)
    return KDVResult(float(net), float(kdv), float(brut), float(oran),
                     float(tw), float(tevkifat), float(payable))
