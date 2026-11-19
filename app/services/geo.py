import re

# ISO 3166-1 alpha-2 + UK как алиас GB (Keitaro и рекламные кабинеты используют оба).
_ISO = (
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS "
    "BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE "
    "EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM "
    "HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC "
    "LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA "
    "NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW "
    "SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO "
    "TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW"
)
COUNTRIES = frozenset(_ISO.split())
_ALIASES = {"UK": "GB"}


def parse_geo(raw: str | list[str]) -> list[str]:
    """'mx, AU;ro' → ['MX', 'AU', 'RO']. Порядок сохраняется, дубли убираются."""
    parts = raw if isinstance(raw, list) else re.split(r"[\s,;]+", raw or "")
    result: list[str] = []
    unknown: list[str] = []
    for p in parts:
        code = p.strip().upper()
        if not code:
            continue
        code = _ALIASES.get(code, code)
        if code not in COUNTRIES:
            unknown.append(p.strip())
        elif code not in result:
            result.append(code)
    if unknown:
        raise ValueError(f"Неизвестные коды стран: {', '.join(unknown)}")
    if not result:
        raise ValueError("Укажи хотя бы одну страну (ISO-код, например AU)")
    return result
