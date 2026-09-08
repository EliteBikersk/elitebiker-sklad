# -*- coding: utf-8 -*-
"""
sloger_sklad_feed.py — Sloger → Shoptet aktualizačný feed  (v6)

Logika:
  ZNAČKOVÉ feedy  = všetko, čo si kedy importoval do e-shopu
  KATALÓG + DOSTUPNOSTI = čo Sloger vedie DNES

  kód v dostupnostiach            → skutočný sklad + dostupnosť
  variant, ktorý dnes chýba       → 0 ks + 'Momentálne nedostupné'
  produkt (bez variantov), chýba  → 0 ks + skrytý (VISIBILITY)

Env:
  SLOGER_XML_URL       – dostupnostný feed        [povinné]
  SLOGER_CATALOG_URL   – hlavný katalóg           [povinné pre skrývanie]
  SLOGER_BRAND_FEEDS   – značkové feedy, 1/riadok [povinné pre skrývanie]
"""
import sys, os, time, io
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

IN_TEXT = 'Skladom u dodávateľa'
OUT_TEXT = 'Na otázku'
MISSING_TEXT = 'Momentálne nedostupné'
SUPPLIER = 'Sloger'
DOPRAVA = 0.0          # € k nákupnej cene (0 = nepripočítavať)

SKRYVAT = True         # skrývať produkty, ktoré Sloger už nevedie
VIS_ON = 'visible'
VIS_OFF = 'hidden'     # ak validátor odmietne, skús 'detailOnly'

DAYS_TEXT = {0: OUT_TEXT, 2: 'Do 2 dní', 3: 'Do 3 dní', 5: 'Do 5 dní',
             31: 'Do mesiaca', 999: OUT_TEXT}

KOD_TAGY = {'code', 'kod', 'sku', 'product_code', 'item_code', 'productno'}
CENA_TAGY = {'price_no_vat', 'price_novat', 'voc', 'purchase_price'}

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
ATTEMPTS, WAIT, TIMEOUT, MIN_ITEMS = 3, 30, 240, 100


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
    raise RuntimeError(str(last))


def _text(el, tagy):
    for ch in el:
        if isinstance(ch.tag, str) and ch.tag.lower() in tagy:
            t = (ch.text or '').strip()
            if t:
                return t
    return None


def precitaj(data):
    """→ (kody, varianty, ceny, rodic). Variant = kód vnútri <options>.
    rodic = {kód produktu: {kódy jeho variantov}}"""
    kody, varianty, ceny, rodic = set(), set(), {}, {}
    t = etree.parse(io.BytesIO(data))
    for el in t.iter():
        if not isinstance(el.tag, str):
            continue
        code = _text(el, KOD_TAGY)
        if not code:
            continue
        kody.add(code)
        # je to variant? (niektorý predok je <options>/<variants>)
        p, je_variant = el.getparent(), False
        while p is not None:
            if isinstance(p.tag, str) and p.tag.lower() in ('options', 'variants'):
                varianty.add(code)
                je_variant = True
                break
            p = p.getparent()
        # priradenie variantu k nadradenému produktu
        if je_variant:
            q = el.getparent()
            while q is not None:
                rc = _text(q, KOD_TAGY)
                if rc and rc != code:
                    rodic.setdefault(rc, set()).add(code)
                    break
                q = q.getparent()
        # cena – vlastná alebo zdedená
        cena = _text(el, CENA_TAGY)
        if cena is None:
            p = el.getparent()
            while p is not None and cena is None:
                cena = _text(p, CENA_TAGY)
                p = p.getparent()
        try:
            v = float((cena or '').replace(',', '.'))
            if v > 0:
                ceny[code] = v
        except ValueError:
            pass
    return kody, varianty, ceny, rodic


def main(dst):
    cudzie = cudzie_kody(SUPPLIER)
    if cudzie:
        print(f'Preskakujem {len(cudzie)} kódov patriacich iným dodávateľom')
    print('Dostupnosti...')
    stock = {}
    for av in etree.parse(io.BytesIO(fetch(os.environ['SLOGER_XML_URL']))).iter('availability'):
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
    print(f'  {len(stock)} kódov')
    if len(stock) < MIN_ITEMS:
        raise SystemExit('CHYBA: dostupnosti su prazdne, nezapisujem')

    # čo Sloger vedie DNES = katalóg + dostupnosti
    dnes = set(stock)
    rodic = {}
    cat = os.environ.get('SLOGER_CATALOG_URL', '').strip()
    ceny = {}
    if cat:
        print('Katalóg...')
        k, _v, c, r = precitaj(fetch(cat))
        for a, b in r.items():
            rodic.setdefault(a, set()).update(b)
        dnes |= k
        ceny.update(c)
        print(f'  {len(k)} kódov, {len(c)} cien')

    # čo máš v e-shope = značkové feedy
    vsetko, varianty = set(), set()
    zdroje = [u.strip() for u in os.environ.get('SLOGER_BRAND_FEEDS', '').splitlines() if u.strip()]
    print(f'Značkové feedy ({len(zdroje)})...')
    ok = chyb = 0
    for u in zdroje:
        nazov = u.rsplit('/', 1)[-1]
        try:
            k, var, c, r = precitaj(fetch(u))
            for a, b in r.items():
                rodic.setdefault(a, set()).update(b)
            vsetko |= k
            varianty |= var
            ceny.update(c)
            ok += 1
            print(f'  {nazov}: {len(k)} kódov ({len(var)} variantov)')
        except Exception as e:
            chyb += 1
            print(f'  {nazov}: CHYBA – {e}')
    print(f'  spolu {len(vsetko)} kódov, {ok} ok / {chyb} chyba')

    chybajuce = (vsetko | dnes) - set(stock)
    # produkt sa NESKRÝVA, ak má aspoň jeden variant skladom
    na_skrytie = set()
    if SKRYVAT:
        for c in chybajuce:
            if c in varianty:
                continue
            if rodic.get(c, set()) & set(stock):
                continue
            na_skrytie.add(c)
    print(f'Chýba dnes: {len(chybajuce)}  (z toho na skrytie {len(na_skrytie)})')

    if vsetko and len(chybajuce) > 3 * len(stock):
        raise SystemExit('CHYBA: podozrivo vela na vynulovanie, nezapisujem')

    shop = etree.Element('SHOP')

    def polozka(code, qty, text_out, vis=None):
        if code in cudzie:
            return
        si = etree.SubElement(shop, 'SHOPITEM')
        etree.SubElement(si, 'CODE').text = code
        etree.SubElement(si, 'SUPPLIER').text = SUPPLIER
        if code in ceny:
            etree.SubElement(si, 'PURCHASE_PRICE').text = f'{ceny[code] + DOPRAVA:.2f}'
        if vis:
            etree.SubElement(si, 'VISIBILITY').text = vis
        st = etree.SubElement(si, 'STOCK')
        etree.SubElement(st, 'AMOUNT').text = str(qty)
        etree.SubElement(si, 'AVAILABILITY_IN_STOCK').text = IN_TEXT
        etree.SubElement(si, 'AVAILABILITY_OUT_OF_STOCK').text = text_out

    for code, (qty, days) in stock.items():
        polozka(code, qty, DAYS_TEXT.get(days, OUT_TEXT),
                VIS_ON if (SKRYVAT and code not in varianty) else None)
    for code in sorted(chybajuce):
        polozka(code, 0, MISSING_TEXT, VIS_OFF if code in na_skrytie else None)

    etree.ElementTree(shop).write(dst, encoding='UTF-8', xml_declaration=True, pretty_print=True)
    print(f'OK: {len(stock)} dostupných + {len(chybajuce)} nedostupných '
          f'= {len(shop)} položiek → {dst}')


if __name__ == '__main__':
    main(sys.argv[2] if len(sys.argv) > 2 else 'sloger_sklad_shoptet.xml')
