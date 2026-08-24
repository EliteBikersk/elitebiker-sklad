# -*- coding: utf-8 -*-
"""
sloger_sklad_feed.py — Sloger → Shoptet aktualizačný feed
v3: číta OBA feedy.
    - katalóg (SLOGER_CATALOG_URL)      = zoznam všetkých kódov, ktoré Sloger vedie
    - dostupnosti (SLOGER_XML_URL)      = skutočné sklady
    Kód, ktorý je v katalógu ale NIE je v dostupnostiach → 0 ks + MISSING_TEXT.
Použitie: python3 sloger_sklad_feed.py - docs/sloger_sklad_shoptet.xml
"""
import sys, os, time, io
from lxml import etree

IN_TEXT = 'Skladom u dodávateľa'
OUT_TEXT = 'Na otázku'
MISSING_TEXT = 'Momentálne nedostupné'   # pre kódy chýbajúce v dostupnostiach

# stock_availability_days -> text, keď je stock_amount 0
DAYS_TEXT = {0: OUT_TEXT, 2: 'Do 2 dní', 3: 'Do 3 dní', 5: 'Do 5 dní',
             31: 'Do mesiaca', 999: OUT_TEXT}

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
ATTEMPTS, WAIT, TIMEOUT, MIN_ITEMS = 5, 60, 180, 100


def fetch(url):
    import urllib.request
    last = None
    for n in range(1, ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read()
            print(f'  pokus {n}: OK, {len(data)} bajtov')
            return data
        except Exception as e:
            last = e
            print(f'  pokus {n}/{ATTEMPTS} zlyhal: {e}')
            if n < ATTEMPTS:
                time.sleep(WAIT)
    raise SystemExit(f'CHYBA: server neodpovedal po {ATTEMPTS} pokusoch ({last})')


def main(dst):
    # 1) dostupnosti = sklady
    print('Sťahujem dostupnostný feed...')
    t = etree.parse(io.BytesIO(fetch(os.environ['SLOGER_XML_URL'])))
    stock = {}
    for av in t.iter('availability'):
        code = (av.findtext('code') or '').strip()
        if not code:
            continue
        try:
            qty = max(int(av.findtext('stock_amount') or 0), 0)
        except ValueError:
            qty = 0
        try:
            days = int(av.findtext('stock_availability_days') or 999)
        except ValueError:
            days = 999
        if code not in stock or qty > stock[code][0]:
            stock[code] = (qty, days)
    print(f'  dostupnosti: {len(stock)} kódov')

    if len(stock) < MIN_ITEMS:
        raise SystemExit(f'CHYBA: dostupnosti maju len {len(stock)} poloziek, nezapisujem')

    # 2) katalóg = všetky kódy, ktoré Sloger vôbec vedie
    katalog = set()
    url = os.environ.get('SLOGER_CATALOG_URL', '').strip()
    if url:
        print('Sťahujem katalógový feed...')
        try:
            k = etree.parse(io.BytesIO(fetch(url)))
            for el in k.iter('code'):
                c = (el.text or '').strip()
                if c:
                    katalog.add(c)
            print(f'  katalóg: {len(katalog)} kódov')
        except SystemExit as e:
            print(f'VAROVANIE: katalóg sa nepodarilo stiahnuť ({e}) – nulovanie preskočené')
    else:
        print('VAROVANIE: SLOGER_CATALOG_URL nie je nastavené – nulovanie preskočené')

    chybajuce = katalog - set(stock)

    # 3) výstup
    shop = etree.Element('SHOP')

    def polozka(code, qty, text_out):
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = code
        st = etree.SubElement(si, 'STOCK')
        etree.SubElement(st, 'AMOUNT').text = str(qty)
        etree.SubElement(si, 'AVAILABILITY_IN_STOCK').text = IN_TEXT
        etree.SubElement(si, 'AVAILABILITY_OUT_OF_STOCK').text = text_out

    for code, (qty, days) in stock.items():
        polozka(code, qty, DAYS_TEXT.get(days, OUT_TEXT))
    for code in sorted(chybajuce):
        polozka(code, 0, MISSING_TEXT)

    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    print(f'OK: {len(stock)} z dostupností + {len(chybajuce)} vynulovaných = '
          f'{len(stock) + len(chybajuce)} položiek → {dst}')


if __name__ == '__main__':
    main(sys.argv[2] if len(sys.argv) > 2 else 'sloger_sklad_shoptet.xml')
