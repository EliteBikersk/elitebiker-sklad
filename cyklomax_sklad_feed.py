# -*- coding: utf-8 -*-
"""
cyklomax_sklad_feed.py — Cyklomax dostupnostni.xml → Shoptet aktualizačný feed
Aktualizuje: sklad (AMOUNT) + dostupnosti. Páruje podľa CODE (= <ID> z feedu).
"""
import sys, os, time, io
from lxml import etree

IN_TEXT = 'Skladom u dodávateľa'
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
    best = {}
    for p in t.iter('PRODUCT'):
        code = (p.findtext('ID') or '').strip()
        if not code:
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

    shop = etree.Element('SHOP')
    for code, qty in best.items():
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = code
        st = etree.SubElement(si, 'STOCK')
        etree.SubElement(st, 'AMOUNT').text = str(qty)
        etree.SubElement(si, 'AVAILABILITY_IN_STOCK').text = IN_TEXT
        etree.SubElement(si, 'AVAILABILITY_OUT_OF_STOCK').text = OUT_TEXT

    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    skladom = sum(1 for q in best.values() if q > 0)
    print(f'OK: {len(best)} položiek ({skladom} skladom) → {dst}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '-',
         sys.argv[2] if len(sys.argv) > 2 else 'cyklomax_sklad_shoptet.xml')
