# -*- coding: utf-8 -*-
"""
cyklomax_sklad_feed.py — Cyklomax dostupnostni.xml → Shoptet aktualizačný feed
Aktualizuje: sklad (AMOUNT) + dostupnosti. Páruje podľa CODE (= <ID> z feedu).
"""
import sys, os, time, io
from lxml import etree

PAMAT_SUBOR = 'cyklomax_pamat_kodov.txt'

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


def cudzie_kody(moj):
    """Kódy, ktoré podľa vlastnik_kodov.txt patria INÉMU dodávateľovi – tie preskočíme."""
    cesta = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vlastnik_kodov.txt')
    s = set()
    if not os.path.exists(cesta):
        return s
    for line in open(cesta, encoding='utf-8'):
        line = line.split('#', 1)[0].strip()
        if not line or ';' not in line:
            continue
        code, dod = [x.strip() for x in line.split(';', 1)]
        if dod.lower() != moj.lower():
            s.add(code)
    return s

IN_TEXT = 'Skladom u dodávateľa'
SUPPLIER = 'Cyklomax'   # doplní sa ku každému kódu; '' = nedopĺňať
OUT_TEXT = 'Na otázku'

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

ATTEMPTS = 5      # počet pokusov
WAIT = 60         # sekúnd medzi pokusmi
TIMEOUT = 120     # timeout jedného pokusu
MIN_ITEMS = 100   # poistka proti orezanému feedu


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
        return etree.parse(io.BytesIO(fetch(os.environ['CYKLOMAX_XML_URL'])))
    return etree.parse(src)


def main(src, dst):
    t = load(src)
    cudzie = cudzie_kody(SUPPLIER)
    if cudzie:
        print(f'  preskakujem {len(cudzie)} kódov patriacich iným dodávateľom')
    best = {}
    for p in t.iter('PRODUCT'):
        code = (p.findtext('ID') or '').strip()
        if not code or code in cudzie:
            continue
        try:
            qty = max(int(float(p.findtext('STOCK') or 0)), 0)
        except ValueError:
            qty = 0
        # ten istý kód sa môže opakovať – berieme vyšší sklad
        if code not in best or qty > best[code]:
            best[code] = qty

    if len(best) < MIN_ITEMS:
        raise SystemExit(f'CHYBA: feed ma len {len(best)} poloziek, nezapisujem')

    vyradene = s_pamatou(best, dst, cudzie)
    for code in vyradene:
        best[code] = 0

    shop = etree.Element('SHOP')
    for code, qty in best.items():
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = code
        if SUPPLIER:
            etree.SubElement(si, 'SUPPLIER').text = SUPPLIER
        st = etree.SubElement(si, 'STOCK')
        etree.SubElement(st, 'AMOUNT').text = str(qty)
        etree.SubElement(si, 'AVAILABILITY_IN_STOCK').text = IN_TEXT
        etree.SubElement(si, 'AVAILABILITY_OUT_OF_STOCK').text = MISSING_TEXT if code in vyradene else OUT_TEXT

    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    skladom = sum(1 for q in best.values() if q > 0)
    print(f'OK: {len(best)} položiek ({skladom} skladom) → {dst}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '-',
         sys.argv[2] if len(sys.argv) > 2 else 'cyklomax_sklad_shoptet.xml')
