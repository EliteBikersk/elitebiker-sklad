# -*- coding: utf-8 -*-
"""
krabcycles_sklad_feed.py — KrabCycles partner feed → Shoptet aktualizačný feed
Aktualizuje: sklad (AMOUNT) + dostupnosti + dodávateľ. Páruje podľa CODE (= <code>, napr. P811).

Env:
  KRABCYCLES_XML_URL – partnerský feed (odporúčam verziu ?samostatne_varianty)
"""
import sys, os, time, io
from lxml import etree

PAMAT_SUBOR = 'krabcycles_pamat_kodov.txt'

MISSING_TEXT = 'Momentálne nedostupné'   # pre kódy, ktoré dodávateľ vyradil z feedu


def s_pamatou(best, dst, cudzie=frozenset()):
    """Pamätá si všetky kódy, ktoré kedy boli vo feede (docs/<dod>_pamat_kodov.txt).
    Kód, ktorý dnes vo feede nie je, dostane 0 ks + MISSING_TEXT. Nič sa neskrýva."""
    cesta = os.path.join(os.path.dirname(os.path.abspath(dst)), PAMAT_SUBOR)
    pamat = set()
    if os.path.exists(cesta):
        for line in open(cesta, encoding='utf-8'):
            line = line.strip()
            if line and not line.startswith('#'):
                pamat.add(line)
    vyradene = (pamat - set(best)) - set(cudzie)
    nove = set(best) - pamat
    pamat |= set(best)
    with open(cesta, 'w', encoding='utf-8') as fh:
        fh.write('# kódy, ktoré boli niekedy vo feede dodávateľa\n')
        for c in sorted(pamat):
            fh.write(c + '\n')
    print(f'pamäť: {len(pamat)} kódov (+{len(nove)} nových) | vyradených dodávateľom: {len(vyradene)} → {MISSING_TEXT}')
    return vyradene

IN_TEXT = 'Skladom u dodávateľa'
OUT_TEXT = 'Na otázku'
SUPPLIER = 'KrabCycles'

# nákupná cena: feed je v CZK bez DPH. Prepočet zapneš CENY = True.
CENY = False
KURZ_CZK = 24.5        # CZK za 1 EUR
PRIRAZKA = 0.0         # násobok, napr. 0.30 = +30 %

# delivery_date (dni) -> text dostupnosti, keď je sklad 0
def text_pre(days):
    if days <= 0:   return OUT_TEXT   # 0 dní a pritom nula kusov = nevie sa
    if days <= 5:   return 'Do 5 dní'
    if days <= 31:  return 'Do mesiaca'
    return OUT_TEXT           # 51440 = "na dotaz"

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
ATTEMPTS, WAIT, TIMEOUT, MIN_ITEMS = 5, 60, 180, 100


def cudzie_kody(moj):
    cesta = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vlastnik_kodov.txt')
    s = set()
    if not os.path.exists(cesta):
        return s
    for line in open(cesta, encoding='utf-8'):
        line = line.split('#', 1)[0].strip()
        if ';' in line:
            code, dod = [x.strip() for x in line.split(';', 1)]
            if dod.lower() != moj.lower():
                s.add(code)
    return s


def fetch(url):
    import urllib.request
    last = None
    for n in range(1, ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read()
            print(f'pokus {n}: OK, {len(data)} bajtov')
            return data
        except Exception as e:
            last = e
            print(f'pokus {n}/{ATTEMPTS} zlyhal: {e}')
            if n < ATTEMPTS:
                time.sleep(WAIT)
    raise SystemExit(f'CHYBA: server neodpovedal po {ATTEMPTS} pokusoch ({last})')


def load(src):
    if src == '-':
        return etree.parse(io.BytesIO(fetch(os.environ['KRABCYCLES_XML_URL'])))
    return etree.parse(src)


def cislo(x, default=0):
    try:
        return float((x or '').replace(',', '.'))
    except ValueError:
        return default


def main(src, dst):
    cudzie = cudzie_kody(SUPPLIER)
    t = load(src)
    best = {}
    # produkty aj vnorené <alternate> – zvládne obe verzie feedu
    for el in list(t.iter('product')) + list(t.iter('alternate')):
        code = (el.findtext('code') or '').strip()
        if not code or code in cudzie:
            continue
        # produkt, ktorý má <alternates> s obsahom, je len obal – jeho sklad je súčet variantov
        alts = el.find('alternates')
        if alts is not None and len(alts):
            continue
        qty = max(int(cislo(el.findtext('avaibility_q'))), 0)
        days = int(cislo(el.findtext('delivery_date'), 99999))
        vo = cislo(el.findtext('price_vo'))
        if code not in best or qty > best[code][0]:
            best[code] = (qty, days, vo)

    if len(best) < MIN_ITEMS:
        raise SystemExit(f'CHYBA: feed ma len {len(best)} poloziek, nezapisujem')

    vyradene = s_pamatou(best, dst, cudzie)
    for code in vyradene:
        best[code] = (0, 99999, 0)

    shop = etree.Element('SHOP')
    for code, (qty, days, vo) in best.items():
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = code
        etree.SubElement(si, 'SUPPLIER').text = SUPPLIER
        if CENY and vo > 0:
            eur = vo / KURZ_CZK * (1 + PRIRAZKA)
            etree.SubElement(si, 'PURCHASE_PRICE').text = f'{eur:.2f}'
        st = etree.SubElement(si, 'STOCK')
        etree.SubElement(st, 'AMOUNT').text = str(qty)
        etree.SubElement(si, 'AVAILABILITY_IN_STOCK').text = IN_TEXT
        etree.SubElement(si, 'AVAILABILITY_OUT_OF_STOCK').text = MISSING_TEXT if code in vyradene else text_pre(days)

    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    skladom = sum(1 for q, _, _ in best.values() if q > 0)
    print(f'OK: {len(best)} položiek ({skladom} skladom) → {dst}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '-',
         sys.argv[2] if len(sys.argv) > 2 else 'krabcycles_sklad_shoptet.xml')
