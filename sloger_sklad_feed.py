# -*- coding: utf-8 -*-
"""
sloger_sklad_feed.py — Sloger availabilities XML → Shoptet aktualizačný feed
Aktualizuje: sklad (AMOUNT) + dostupnosti. Páruje podľa CODE (kód varianty).
Použitie:  python3 sloger_sklad_feed.py vstup.xml vystup.xml
           SLOGER_XML_URL=https://... python3 sloger_sklad_feed.py - vystup.xml
"""
import sys, os
from lxml import etree

IN_TEXT = 'Skladom u dodávateľa'
OUT_TEXT = 'Na otázku'

# stock_availability_days -> text dostupnosti, keď je stock_amount 0
DAYS_TEXT = {
    0: OUT_TEXT,
    2: 'Do 2 dní',
    3: 'Do 3 dní',
    5: 'Do 5 dní',
    31: 'Do mesiaca',
    999: OUT_TEXT,
}


def load(src):
    if src == '-':
        import urllib.request
        url = os.environ['SLOGER_XML_URL']
        req = urllib.request.Request(url, headers={'User-Agent': 'elitebiker-sklad-bot/1.0'})
        with urllib.request.urlopen(req, timeout=180) as r:
            return etree.parse(r)
    return etree.parse(src)


def main(src, dst):
    t = load(src)
    best = {}
    for av in t.iter('availability'):
        code = (av.findtext('code') or '').strip()
        if not code:
            continue
        try:
            qty = int(av.findtext('stock_amount') or 0)
        except ValueError:
            qty = 0
        try:
            days = int(av.findtext('stock_availability_days') or 0)
        except ValueError:
            days = 999
        qty = max(qty, 0)
        # ten istý kód sa vo feede môže opakovať – berieme vyšší sklad
        prev = best.get(code)
        if prev is None or qty > prev[0]:
            best[code] = (qty, days)

    shop = etree.Element('SHOP')
    for code, (qty, days) in best.items():
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = code
        st = etree.SubElement(si, 'STOCK')
        etree.SubElement(st, 'AMOUNT').text = str(qty)
        etree.SubElement(si, 'AVAILABILITY_IN_STOCK').text = IN_TEXT
        etree.SubElement(si, 'AVAILABILITY_OUT_OF_STOCK').text = DAYS_TEXT.get(days, OUT_TEXT)

    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    print(f'OK: {len(best)} položiek → {dst}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '-',
         sys.argv[2] if len(sys.argv) > 2 else 'sloger_sklad_shoptet.xml')
