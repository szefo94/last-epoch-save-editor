#!/usr/bin/env python3
"""Downloads the item art used by the editor into data/icons/ and writes data/icons.json.

Source: the item database of lastepochtools.com, which serves every item picture in one sprite sheet
(a .webp plus a .css with the sprite rectangles) and a data bundle that names the sprite of every
base sub type and every unique. The art itself is Last Epoch's (Eleventh Hour Games).

Usage: python3 fetch_icons.py [--cache DIR] [--truecolor]   (needs Pillow; with Tk only, use --tk: bigger files)
"""
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://www.lastepochtools.com'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
OUT = os.path.join(HERE, 'data', 'icons')


def fetch(url, cache, name, binary=False):
    path = os.path.join(cache, name)
    if os.path.isfile(path):
        with open(path, 'rb') as f:
            data = f.read()
    else:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(path, 'wb') as f:
            f.write(data)
    return data if binary else data.decode('utf-8', 'replace')


def main(argv):
    cache = argv[argv.index('--cache') + 1] if '--cache' in argv else os.path.join(HERE, 'build', 'icons_cache')
    os.makedirs(cache, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    page = fetch(SITE + '/db/items', cache, 'db_items.html')
    bundles = re.findall(r'/data/(version\d+)/db/js/([0-9a-f]+)\.js', page)
    sheet = re.search(r'/data/(version\d+)/db/res/([0-9a-f]+)\.webp', page)
    if not bundles or not sheet:
        sys.exit('could not find the item database bundle on the page')
    version, sheet_id = sheet.groups()
    bases, uniques = {}, {}
    for ver, bid in bundles:
        js = fetch('%s/data/%s/db/js/%s.js' % (SITE, ver, bid), cache, bid + '.js')
        if 'uniqueList' not in js:
            continue
        ustart = js.index('uniqueList')
        starts = [(m.start(), int(m.group(1))) for m in re.finditer(r'baseTypeId:(\d+),maxAffixes', js[:ustart])]
        for m in re.finditer(r'sprite:"(I\d+)",\s*subTypeId:(\d+)', js[:ustart]):
            bt = max((b for p, b in starts if p < m.start()), default=None)
            bases['%d_%s' % (bt, m.group(2))] = m.group(1)
        for m in re.finditer(r'sprite:"(I\d+)",\s*uniqueId:(\d+)', js[ustart:]):
            uniques[m.group(2)] = m.group(1)
    css = fetch('%s/data/%s/db/res/%s.css' % (SITE, version, sheet_id), cache, 'sheet.css')
    px = r'(?:-?(\d+)px|(0))'
    rects = {}
    for m in re.finditer(r'\.itemdb-(I\d+)\{background-position:' + px + ' ' + px + r';width:(\d+)px;height:(\d+)px\}', css):
        rects[m.group(1)] = (int(m.group(2) or 0), int(m.group(4) or 0), int(m.group(6)), int(m.group(7)))
    webp = fetch('%s/data/%s/db/res/%s.webp' % (SITE, version, sheet_id), cache, 'sheet.webp', binary=True)
    need = sorted({s for s in list(bases.values()) + list(uniques.values()) if s in rects}, key=lambda n: int(n[1:]))
    print('%d base sub types, %d uniques, %d sprites to cut' % (len(bases), len(uniques), len(need)))

    if '--tk' in argv:
        import subprocess, tkinter as tk
        png = os.path.join(cache, 'sheet.png')
        subprocess.run(['dwebp', os.path.join(cache, 'sheet.webp'), '-o', png], check=True, capture_output=True)
        root = tk.Tk()
        root.withdraw()
        image = tk.PhotoImage(file=png)
        for name in need:
            x, y, w, h = rects[name]
            sub = tk.PhotoImage(width=w, height=h)
            root.tk.call(sub, 'copy', image, '-from', x, y, x + w, y + h, '-to', 0, 0)
            sub.write(os.path.join(OUT, name + '.png'), format='png')
    else:
        from io import BytesIO
        from PIL import Image
        image = Image.open(BytesIO(webp)).convert('RGBA')
        for name in need:
            x, y, w, h = rects[name]
            part = image.crop((x, y, x + w, y + h))
            if '--truecolor' not in argv:     # 256-colour palette with alpha: a quarter of the size, same look
                part = part.quantize(256, method=Image.Quantize.FASTOCTREE)
            part.save(os.path.join(OUT, name + '.png'), optimize=True)
    with open(os.path.join(HERE, 'data', 'icons.json'), 'w') as f:
        json.dump({'source': '%s item database sprite sheet (%s); game art by Eleventh Hour Games' % (SITE, version),
                   'bases': bases, 'uniques': uniques, 'sizes': {n: rects[n][2:] for n in need}}, f)
    total = sum(os.path.getsize(os.path.join(OUT, n)) for n in os.listdir(OUT)) // 1024
    print('wrote %d icons to %s (%d KB)' % (len(need), OUT, total))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
