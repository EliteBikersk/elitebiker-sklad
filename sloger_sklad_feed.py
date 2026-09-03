# -*- coding: utf-8 -*-
"""
sloger_sklad_feed.py — Sloger → Shoptet aktualizačný feed
v5: zdrojom zoznamu variantov sú ZNAČKOVÉ feedy, z ktorých boli produkty nahodené.

Vstupy (env):
  SLOGER_XML_URL      – dostupnostný feed (sklady)                [povinné]
  SLOGER_BRAND_FEEDS  – URL značkových feedov, jedna na riadok    [odporúčané]
  SLOGER_CATALOG_URL  – hlavný katalóg, doplnkový zdroj           [voliteľné]

Kód, ktorý je v značkových feedoch / katalógu, ale NIE je v dostupnostiach,
dostane 0 ks a dostupnosť MISSING_TEXT.
"""
import sys, os, time, io
from lxml import etree

IN_TEXT = 'Skladom u dodávateľa'
OUT_TEXT = 'Na otázku'
MISSING_TEXT = 'Momentálne nedostupné'

DAYS_TEXT = {0: OUT_TEXT, 2: 'Do 2 dní', 3: 'Do 3 dní', 5: 'Do 5 dní',
             31: 'Do mesiaca', 999: OUT_TEXT}

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
ATTEMPTS, WAIT, TIMEOUT, MIN_ITEMS = 3, 30, 180, 100

# Dopĺňanie chýbajúcich veľkostí podľa kódu:
#   kód varianty = kód modelu + jedna číslica (napr. 73243000|1, 102510512|0)
# Pre každý model doplníme číslice, ktoré Sloger nikde nehlási → 0 ks + nedostupné.
# Kód, ktorý v e-shope neexistuje, Shoptet pri "iba existujúce" ignoruje.
DOPLNIT_VARIANTY = True
MIN_DLZKA_KODU = 9        # len dlhé číselné kódy (krátke patria iným dodávateľom)


def fetch(url):
    import urllib.request
    last = None
    for n in range(1, ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except Exception as e:
            last = e
            if n < ATTEMPTS:
                time.sleep(WAIT)
    raise RuntimeError(f'{last}')


def kody_z_feedu(data):
    """Všetky <code> kdekoľvek v dokumente – produkty aj varianty v <options>."""
    k = set()
    for el in etree.parse(io.BytesIO(data)).iter('code'):
        c = (el.text or '').strip()
        if c:
            k.add(c)
    return k


def main(dst):
    # 1) dostupnosti
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

    # 2) zoznam všetkých variantov zo značkových feedov (+ katalóg)
    zdroje = [u.strip() for u in os.environ.get('SLOGER_BRAND_FEEDS', '').splitlines() if u.strip()]
    cat = os.environ.get('SLOGER_CATALOG_URL', '').strip()
    if cat:
        zdroje.append(cat)

    znama = set()
    ok = chyb = 0
    for u in zdroje:
        nazov = u.rsplit('/', 1)[-1]
        try:
            k = kody_z_feedu(fetch(u))
            znama |= k
            ok += 1
            print(f'  {nazov}: {len(k)} kódov')
        except Exception as e:
            chyb += 1
            print(f'  {nazov}: CHYBA – preskakujem ({e})')
    print(f'  spolu {len(znama)} kódov z {ok} feedov ({chyb} zlyhalo)')

    chybajuce = znama - set(stock)
    print(f'  chýba v dostupnostiach: {len(chybajuce)}')

    doplnene = set()
    if DOPLNIT_VARIANTY:
        from collections import defaultdict
        vsetky = set(stock) | znama
        pref = defaultdict(set)
        for c in vsetky:
            if c.isdigit() and len(c) >= MIN_DLZKA_KODU:
                pref[c[:-1]].add(c[-1])
        for p, cislice in pref.items():
            for x in '0123456789':
                if x not in cislice:
                    doplnene.add(p + x)
        doplnene -= vsetky
        print(f'  doplnené chýbajúce veľkosti: {len(doplnene)}')

    # poistka: keby sa zdroje nepodarilo stiahnuť, radšej nenuluj nič
    if znama and len(chybajuce) > 3 * len(stock):
        raise SystemExit('CHYBA: podozrivo vela kodov na vynulovanie, nezapisujem')

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
    for code in sorted(doplnene):
        polozka(code, 0, MISSING_TEXT)

    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    print(f'OK: {len(stock)} zo skladov + {len(chybajuce)} chýbajúcich '
          f'+ {len(doplnene)} doplnených veľkostí '
          f'= {len(stock) + len(chybajuce) + len(doplnene)} položiek → {dst}')


if __name__ == '__main__':
    main(sys.argv[2] if len(sys.argv) > 2 else 'sloger_sklad_shoptet.xml')
