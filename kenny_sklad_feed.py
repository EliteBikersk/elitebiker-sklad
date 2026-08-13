# -*- coding: utf-8 -*-
"""
kenny_sklad_feed.py — SK Profibike dostupnost.xml → Shoptet aktualizačný feed
Aktualizuje: sklad (AMOUNT) + dostupnosti. Páruje podľa CODE (kód varianty = <kod>).
Použitie:  python3 kenny_sklad_feed.py vstup.xml vystup.xml
           KENNY_XML_URL=https://... python3 kenny_sklad_feed.py - vystup.xml
"""
import sys, os
from lxml import etree

IN_TEXT = 'Skladom u dodávateľa'
OUT_TEXT = 'Na otázku'

# server odmieta neznáme User-Agenty, preto sa hlásime ako bežný prehliadač
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def load(src):
    if src == '-':
        import urllib.request
        url = os.environ['KENNY_XML_URL']
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=180) as r:
            return etree.parse(r)
    return etree.parse(src)


def main(src, dst):
    t = load(src)
    best = {}
    for op in t.iter('option'):
        code = (op.findtext('kod') or '').strip()
        if not code:
            continue
        try:
            qty = max(int(float(op.findtext('sklad') or 0)), 0)
        except ValueError:
            qty = 0
        # ten istý kód sa môže opakovať – berieme vyšší sklad
        if code not in best or qty > best[code]:
            best[code] = qty

    shop = etree.Element('SHOP')
    for code, qty in best.items():
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = code
        st = etree.SubElement(si, 'STOCK')
        etree.SubElement(st, 'AMOUNT').text = str(qty)
        etree.SubElement(si, 'AVAILABILITY_IN_STOCK').text = IN_TEXT
        etree.SubElement(si, 'AVAILABILITY_OUT_OF_STOCK').text = OUT_TEXT

    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    print(f'OK: {len(best)} položiek → {dst}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '-',
         sys.argv[2] if len(sys.argv) > 2 else 'kenny_sklad_shoptet.xml')
