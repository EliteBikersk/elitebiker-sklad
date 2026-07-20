# -*- coding: utf-8 -*-
"""
benefit_sklad_feed.py — Benefit ZjednodusenyKatalog (Katalog__1X.xml) → Shoptet aktualizačný feed
Aktualizuje: sklad (AMOUNT) + dostupnosti. Páruje podľa CODE (kód varianty).
Použitie:  python3 benefit_sklad_feed.py vstup.xml vystup.xml
           BENEFIT_XML_URL=https://... python3 benefit_sklad_feed.py - vystup.xml
"""
import sys, os
from lxml import etree

NS = '{http://www.benefitcz.cz/ws/}'
IN_TEXT = 'Skladom u dodávateľa'
OUT_TEXT = 'Na otázku'
WAREHOUSE = 'Sklad u dodávateľa'

def load(src):
    if src == '-':
        import urllib.request
        url = os.environ['BENEFIT_XML_URL']
        req = urllib.request.Request(url, headers={'User-Agent': 'elitebiker-sklad-bot/1.0'})
        with urllib.request.urlopen(req, timeout=180) as r:
            return etree.parse(r)
    return etree.parse(src)

def main(src, dst):
    t = load(src)
    shop = etree.Element('SHOP')
    n = 0
    for it in t.iter(NS + 'SimpleExportKatalogPolozka'):
        kar = (it.findtext(NS + 'KarCislo') or '').strip()
        if not kar:
            continue
        qty = int(it.findtext(NS + 'Mnozstvi') or 0)
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = kar
        st = etree.SubElement(si, 'STOCK')
        etree.SubElement(st, 'AMOUNT').text = str(max(qty, 0))
        etree.SubElement(si, 'AVAILABILITY_IN_STOCK').text = IN_TEXT
        etree.SubElement(si, 'AVAILABILITY_OUT_OF_STOCK').text = OUT_TEXT
        n += 1
    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    print(f'OK: {n} položiek → {dst}')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '-',
         sys.argv[2] if len(sys.argv) > 2 else 'benefit_sklad_shoptet.xml')
