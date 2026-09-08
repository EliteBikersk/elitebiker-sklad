# -*- coding: utf-8 -*-
"""
benefit_sklad_feed.py — Benefit ZjednodusenyKatalog (Katalog__1X.xml) → Shoptet aktualizačný feed
Aktualizuje: sklad (AMOUNT) + dostupnosti. Páruje podľa CODE (kód varianty).
Použitie:  python3 benefit_sklad_feed.py vstup.xml vystup.xml
           BENEFIT_XML_URL=https://... python3 benefit_sklad_feed.py - vystup.xml
"""
import sys, os
from lxml import etree


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

NS = '{http://www.benefitcz.cz/ws/}'
IN_TEXT = 'Skladom u dodávateľa'
SUPPLIER = 'Aspire'   # doplní sa ku každému kódu; '' = nedopĺňať
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
    cudzie = cudzie_kody(SUPPLIER)
    if cudzie:
        print(f'  preskakujem {len(cudzie)} kódov patriacich iným dodávateľom')
    shop = etree.Element('SHOP')
    n = 0
    for it in t.iter(NS + 'SimpleExportKatalogPolozka'):
        kar = (it.findtext(NS + 'KarCislo') or '').strip()
        if not kar or kar in cudzie:
            continue
        qty = int(it.findtext(NS + 'Mnozstvi') or 0)
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = kar
        if SUPPLIER:
            etree.SubElement(si, 'SUPPLIER').text = SUPPLIER
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
