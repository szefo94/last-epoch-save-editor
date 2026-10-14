"""Imports the gear sets of a Maxroll Last Epoch build guide into data/guides/<slug>.json.

Usage: python import_maxroll.py https://maxroll.gg/last-epoch/build-guides/<guide-slug>
       python import_maxroll.py https://maxroll.gg/last-epoch/planner/<id>

Maxroll pages embed their planner data (one profile per leveling stage, each with the
recommended item per slot). Item type / sub type ids and affix ids are the game's own, so
they map straight onto data/bases.json and data/affixes.json. Planner tiers are 1-based;
the guide files store them 0-based like the rest of this tool.
"""
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GUIDE_FOLDER = os.path.join(HERE, 'data', 'guides')
PLANNER_RE = re.compile(r'\{"id":"[a-z0-9]{6,12}","date":"[^"]*","name":"[^"]*","class":"[^"]*","data":\{')
UNIQUE_RE = re.compile(r'"embedType":"le-item","id":"(\d+):(\d+):(\d+)"')
UNIQUE_ATTR_RE = re.compile(r'"unique":"(\d+)"')
LEVELS_RE = re.compile(r'(?:lvl|level)s?\.?\s*(\d+)\s*(?:-|to)\s*(\d+)', re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


def extract_planner(html):
    m = PLANNER_RE.search(html)
    if not m:
        raise ValueError('no planner data found on the page')
    return json.JSONDecoder().raw_decode(html[m.start():])[0]


def item_spec(it, slot):
    """One planner item as a guide spec. Uniques keep their id (with affixes they are legendaries).
    Sealed and corrupted affixes are left out: the save format of those is not known."""
    spec = {'slot': slot, 'base': it['itemType'], 'sub': it['subType'],
            'affixes': [[a['id'], max(0, a['tier'] - 1)] for a in it.get('affixes', [])]}
    unique = it.get('uniqueID', it.get('uniqueId'))
    if unique is not None:
        spec['unique'] = unique
    return spec


PLANNER_API = 'https://planners.maxroll.gg/profiles/le/%s'
PLANNER_URL_RE = re.compile(r'maxroll\.gg/last-epoch/planner/([a-z0-9]+)', re.I)


def load_build(url):
    """Guide dict for a Maxroll build guide page or a Maxroll planner link."""
    m = PLANNER_URL_RE.search(url)
    if m:
        planner = json.loads(fetch(PLANNER_API % m.group(1)))
        if isinstance(planner.get('data'), str):
            planner['data'] = json.loads(planner['data'])
        return convert(url, '', planner)
    return convert(url, fetch(url))


def convert(url, html, planner=None):
    planner = planner or extract_planner(html)
    data = planner['data']
    items = data['items']
    stages = []
    for p in data['profiles']:
        m = LEVELS_RE.search(p['name'])
        levels = [int(m.group(1)), int(m.group(2))] if m else [1, p.get('level', 100)]
        stage = {'name': p['name'], 'levels': levels, 'level': p.get('level'), 'items': [], 'idols': [],
                 'class': p.get('class'), 'mastery': p.get('mastery'),
                 'passives': (p.get('passives') or {}).get('history', []),
                 'weaver': (p.get('weaver') or {}).get('history', []),
                 'skillTrees': {k: v.get('history', []) for k, v in (p.get('skillTrees') or {}).items()},
                 'activeSkills': p.get('activeSkills') or [], 'specializedSkills': p.get('specializedSkills') or [],
                 'blessings': [{'sub': b['subType'], 'roll': (b.get('implicits') or [1])[0]} if b else None
                               for b in (p.get('blessings') or [])],
                 'quests': p.get('quests') or []}
        for slot, item_id in p['items'].items():
            if item_id is None:
                continue
            spec = item_spec(item_id if isinstance(item_id, dict) else items[str(item_id)], slot)   # some planners embed items inline
            if spec['base'] == 41:          # idol altar (base type 41) sits in its own slot
                stage['altar'] = spec
            else:
                stage['items'].append(spec)
        for item_id in p.get('idols') or []:
            spec = item_spec(item_id if isinstance(item_id, dict) else items[str(item_id)], 'idol') if item_id is not None else None
            if spec:
                stage['idols'].append(spec)
        stages.append(stage)
    uniques = []
    for _, _, uid in UNIQUE_RE.findall(html):
        if int(uid) not in uniques:
            uniques.append(int(uid))
    for uid in UNIQUE_ATTR_RE.findall(html):
        if int(uid) not in uniques:
            uniques.append(int(uid))
    title = re.search(r'<title>([^<]*)</title>', html)
    return {'name': planner.get('name'), 'title': title.group(1).split('|')[0].strip() if title else planner.get('name'),
            'source': url, 'planner': planner.get('id'), 'date': planner.get('date'),
            'class': data['profiles'][0]['class'] if data['profiles'] else None,
            'stages': stages, 'uniques': uniques}


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    url = argv[1]
    guide = load_build(url)
    slug = url.rstrip('/').rsplit('/', 1)[-1]
    os.makedirs(GUIDE_FOLDER, exist_ok=True)
    out = os.path.join(GUIDE_FOLDER, slug + '.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(guide, f, indent=1)
    print('Wrote %s: %s, %d uniques' % (out, guide['name'], len(guide['uniques'])))
    for st in guide['stages']:
        print('  %s: %d items, %d idols' % (st['name'], len(st['items']), len(st['idols'])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
