#!/usr/bin/env python3
"""Core library for reading and editing Last Epoch offline saves.

Save files are the text "EPOCH" followed by one JSON document. Items live in
"savedItems"; each has a "data" byte array:

  old (data[0] == 2):  [2, base, sub, rarity, 0, imp1, imp2, imp3, ...]
  new (data[0] >= 3):  [6, id1, id2, id3, id4, base, sub, rarity, 0, imp1, imp2, imp3, ...]

  normal/magic/rare continue with:  forgingPotential, affixCount, then 3 bytes per affix
      (tier << 4 | affixId >> 8), affixId & 255, roll        (old format appends a 0)
  unique/set/legendary (rarity >= 7) continue with:  uniqueId (2 bytes), 8 roll bytes,
      legendaryAffixCount, then 3 bytes per affix

Item/affix names come from data/*.json (extracted game data from the open-source
LastEpochPlanner project).
"""
import argparse
import datetime
import json
import os
import random
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PREFIX = 'EPOCH'

# When the tool runs from a single-file .pyz archive (see build.py), HERE points inside the
# archive: data is then read through zipfile, and backups go next to the archive instead.
ARCHIVE = None
_p = HERE
while _p and _p != os.path.dirname(_p):
    if os.path.isfile(_p):
        ARCHIVE = _p
        break
    _p = os.path.dirname(_p)
APP_DIR = os.path.dirname(ARCHIVE) if ARCHIVE else HERE
if getattr(sys, 'frozen', False):      # PyInstaller binary: data is unpacked next to the modules,
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))   # backups go next to the binary


def read_text(*parts):
    """Text of a file that ships with the tool (data/...), from disk or from the .pyz archive."""
    if ARCHIVE:
        import zipfile
        inner = os.path.relpath(os.path.join(HERE, *parts), ARCHIVE).replace(os.sep, '/')
        with zipfile.ZipFile(ARCHIVE) as z:
            return z.read(inner).decode('utf-8')
    with open(os.path.join(HERE, *parts), encoding='utf-8') as f:
        return f.read()


def read_bytes(*parts):
    """Bytes of a file that ships with the tool, from disk or from the .pyz archive; None if absent."""
    try:
        if ARCHIVE:
            import zipfile
            inner = os.path.relpath(os.path.join(HERE, *parts), ARCHIVE).replace(os.sep, '/')
            with zipfile.ZipFile(ARCHIVE) as z:
                return z.read(inner)
        with open(os.path.join(HERE, *parts), 'rb') as f:
            return f.read()
    except (OSError, KeyError):
        return None


def list_files(*parts):
    """Names of the files in a folder that ships with the tool, from disk or from the archive."""
    if ARCHIVE:
        import zipfile
        inner = os.path.relpath(os.path.join(HERE, *parts), ARCHIVE).replace(os.sep, '/') + '/'
        with zipfile.ZipFile(ARCHIVE) as z:
            return sorted(n[len(inner):] for n in z.namelist() if n.startswith(inner) and '/' not in n[len(inner):])
    folder = os.path.join(HERE, *parts)
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

CLASSES = {0: 'Primalist', 1: 'Mage', 2: 'Sentinel', 3: 'Acolyte', 4: 'Rogue'}
CONTAINERS = {1: 'Inventory', 2: 'Helmet', 3: 'Body', 4: 'Weapon', 5: 'Off-hand', 6: 'Gloves',
              7: 'Belt', 8: 'Boots', 9: 'Ring 1', 10: 'Ring 2', 11: 'Amulet', 12: 'Relic', 29: 'Idols'}
# The rarity byte of normal gear only counts affixes (the game's own files use 1-4); "Exalted" is what the
# game calls any such item with a tier 6+ affix, and a unique with extra affixes is a legendary.
RARITY = {0: 'Normal', 1: 'Magic', 2: 'Magic', 3: 'Rare', 4: 'Rare', 5: 'Exalted', 6: 'Exalted',
          7: 'Unique', 8: 'Set', 9: 'Legendary'}
INVENTORY_ID = 1
INVENTORY_SIZE = (12, 8)
STASH_TAB_SIZE = (12, 17)

# Inventory footprint (width, height) per base type. Where unsure the larger size is
# used, so a wrong guess only wastes a little space instead of overlapping items.
SIZES = {0: (2, 2), 1: (2, 3), 2: (2, 1), 3: (2, 2), 4: (2, 2), 5: (1, 3), 6: (1, 3), 7: (1, 3),
         8: (1, 3), 9: (1, 3), 10: (1, 3), 12: (2, 4), 13: (2, 4), 14: (2, 4), 15: (2, 4),
         16: (2, 4), 17: (2, 3), 18: (2, 3), 19: (2, 3), 20: (1, 1), 21: (1, 1), 22: (2, 3),
         23: (2, 4)}

# Level requirement added by affixes: sum of tier values + 2 * highest - 10.
TIER_REQ = [1, 3, 6, 10, 14, 15, 16]
MAX_KIT_TIER = 4  # T5, the highest craftable tier


class Database:
    def __init__(self, folder='data'):
        def load(name):
            return json.loads(read_text(folder, name))
        self.bases = {}
        self.type_names = {}
        for name, b in load('bases.json').items():
            b['name'] = name
            self.bases[(b['baseTypeID'], b['subTypeID'])] = b
            self.type_names.setdefault(b['baseTypeID'], b['type'])
        self.affixes = {}
        for key, m in load('affixes.json').items():
            affix_id, tier = map(int, key.split('_'))
            self.affixes[(affix_id, tier)] = m
        self.uniques = {int(k): u for k, u in load('uniques.json').items()}

    def base(self, base_type, sub_type):
        return self.bases.get((base_type, sub_type))

    def base_name(self, base_type, sub_type):
        b = self.base(base_type, sub_type)
        return b['name'] if b else 'Unknown item %d/%d' % (base_type, sub_type)

    def subtypes(self, base_type):
        return sorted((b for b in self.bases.values() if b['baseTypeID'] == base_type),
                      key=lambda b: b['subTypeID'])

    def affix_text(self, affix_id, tier):
        m = self.affixes.get((affix_id, tier))
        if not m:
            return 'Unknown affix #%d' % affix_id
        return clean(' / '.join(m[k] for k in ('1', '2') if m.get(k)))

    def affix_label(self, affix_id):
        m = self.affixes[(affix_id, 0)]
        return '%d: %s %s' % (affix_id, m['type'], self.affix_text(affix_id, 0))

    def size(self, base_type, sub_type):
        b = self.base(base_type, sub_type) or {}
        if b.get('width') and b.get('height'):
            return b['width'], b['height']
        return SIZES.get(base_type, (1, 1))

    def unique_req(self, unique_id):
        u = self.uniques[unique_id]
        if u['req']['level']:
            return u['req']['level']
        b = self.base(u['baseTypeID'], u['subTypeID'])
        return b['req']['level'] if b else 0


def clean(text):
    return re.sub(r'\{[^}]*\}', '', text)


def affix_req(tiers):
    if not tiers:
        return 0
    values = [TIER_REQ[min(t, 6)] for t in tiers]
    return max(0, sum(values) + 2 * max(values) - 10)


# ---------------------------------------------------------------- item encoding

def _read_affixes(d, pos, count):
    affixes = []
    for _ in range(count):
        a, b, roll = d[pos:pos + 3]
        affixes.append((((a & 15) << 8) | b, a >> 4, roll))
        pos += 3
    return affixes, pos


class Icons:
    """Item pictures: data/icons/<sprite>.png per base sub type and per unique (see data/icons.json)."""

    def __init__(self):
        try:
            m = json.loads(read_text('data', 'icons.json'))
        except (OSError, KeyError, ValueError):
            m = {'bases': {}, 'uniques': {}, 'sizes': {}}
        self.bases, self.uniques, self.sizes = m['bases'], m['uniques'], m.get('sizes', {})

    def sprite(self, item):
        """Sprite name for an item (unique art first, else the base's), or None."""
        if not item:
            return None
        if item.get('unique') is not None and str(item['unique']) in self.uniques:
            return self.uniques[str(item['unique'])]
        return self.bases.get('%d_%d' % (item['base'], item['sub']))

    def png(self, sprite):
        return read_bytes('data', 'icons', sprite + '.png') if sprite else None


EXALTED_TIER = 5   # tier index of T6, the first exalted tier


NO_EXALTED_TYPES = set(range(25, 34)) | {34, 41}   # idols and idol altars: their high-tier affixes do not make them exalted


def rarity_name(item):
    """Rarity as the game shows it: Legendary for a unique with affixes, Set, Unique, Exalted for a tier 6+
    affix on gear, else Magic (1-2 affixes), Rare (3-4) or Normal."""
    if item is None:
        return ''
    if item.get('unique') is not None:
        if item['affixes']:
            return 'Legendary'
        return 'Set' if item['rarity'] == 8 else 'Unique'
    if item['base'] not in NO_EXALTED_TYPES and any(t >= EXALTED_TIER for _, t, _ in item['affixes']):
        return 'Exalted'
    n = len(item['affixes'])
    return 'Rare' if n >= 3 else 'Magic' if n else 'Normal'


def rarity_byte(item):
    """The rarity byte to store for an item's current affixes, following the game's own files."""
    if item.get('unique') is not None:
        if item['affixes']:
            return 9
        return 8 if item.get('rarity') == 8 else 7
    return min(len(item['affixes']), 4)


def decode(data):
    """Decodes an item byte array, or returns None if it is not an equipment item."""
    try:
        o = 1 if data[0] <= 2 else 5
        if len(data) < o + 9:
            return None
        item = {'version': data[0], 'uid': list(data[1:o]), 'base': data[o], 'sub': data[o + 1],
                'rarity': data[o + 2], 'flag': data[o + 3], 'implicits': list(data[o + 4:o + 7]),
                'fp': 0, 'affixes': [], 'unique': None, 'rolls': []}
        if item['rarity'] >= 7:
            item['unique'] = data[o + 7] * 256 + data[o + 8]
            item['rolls'] = list(data[o + 9:o + 17])
            if len(data) > o + 17:
                item['affixes'], _ = _read_affixes(data, o + 18, data[o + 17])
        else:
            item['fp'] = data[o + 7]
            item['affixes'], _ = _read_affixes(data, o + 9, data[o + 8])
        return item
    except (IndexError, ValueError):
        return None


def encode(item):
    version = item.get('version', 6)
    out = [version]
    if version > 2:
        out += item.get('uid') or [random.randrange(128)] + [random.randrange(256) for _ in range(3)]
    out += [item['base'], item['sub'], item['rarity'], item.get('flag', 0)] + list(item['implicits'])
    affix_bytes = []
    for affix_id, tier, roll in item.get('affixes', []):
        affix_bytes += [(tier << 4) | (affix_id >> 8), affix_id & 255, roll]
    if item.get('unique') is not None:
        out += [item['unique'] >> 8, item['unique'] & 255] + list(item['rolls'])
        out += [len(item.get('affixes', []))] + affix_bytes
    else:
        out += [item.get('fp', 0), len(item.get('affixes', []))] + affix_bytes
        if version <= 2:
            out.append(0)
    return out


def item_req(db, item):
    if item['unique'] is not None and item['unique'] in db.uniques:
        return db.unique_req(item['unique'])
    b = db.base(item['base'], item['sub'])
    req = b['req']['level'] if b else 0
    levels = [db.affixes[(a, 0)]['level'] for a, _, _ in item['affixes'] if (a, 0) in db.affixes]
    return max([req, affix_req([t for _, t, _ in item['affixes']])] + levels)


def item_title(db, item):
    if item is None:
        return 'Other (material / special item)'
    if item['unique'] is not None:
        u = db.uniques.get(item['unique'])
        return u['name'] if u else 'Unknown unique #%d' % item['unique']
    return db.base_name(item['base'], item['sub'])


def describe(db, item):
    """Multi-line description of an item."""
    if item is None:
        return 'Not an equipment item (material, key or other special entry).'
    b = db.base(item['base'], item['sub']) or {}
    lines = ['%s  [%s]' % (item_title(db, item), rarity_name(item)),
             '%s - %s, requires level %d' % (b.get('type', '?'), db.base_name(item['base'], item['sub']),
                                             item_req(db, item))]
    lines += ['  ' + clean(i) for i in b.get('implicits', [])]
    if item['unique'] is not None:
        u = db.uniques.get(item['unique'], {})
        lines += ['  * ' + clean(m) for m in u.get('mods', [])]
    else:
        lines.append('Forging potential: %d' % item['fp'])
    for affix_id, tier, roll in item['affixes']:
        lines.append('  T%d %s  (roll %d%%)' % (tier + 1, db.affix_text(affix_id, tier), round(roll / 2.55)))
    return '\n'.join(lines)


# ---------------------------------------------------------------- save files

BACKUP_ROOT = os.path.join(APP_DIR, 'backups')
GAME_SUBPATH = os.path.join('Eleventh Hour Games', 'Last Epoch', 'Saves')
# Candidate locations of the game's own save folder (Steam Deck / Linux Proton first, then Windows).
GAME_FOLDER_CANDIDATES = [
    os.path.expanduser('~/.local/share/Steam/steamapps/compatdata/899770/pfx/drive_c/users/steamuser/'
                       'AppData/LocalLow/' + GAME_SUBPATH),
    os.path.expanduser('~/.steam/steam/steamapps/compatdata/899770/pfx/drive_c/users/steamuser/'
                       'AppData/LocalLow/' + GAME_SUBPATH),
    os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'LocalLow', GAME_SUBPATH),
]


def game_running():
    """True when a Last Epoch process is running (its save files must not be written then)."""
    import subprocess
    try:
        return subprocess.run(['pgrep', '-f', '-i', 'last ?epoch'], capture_output=True).returncode == 0
    except OSError:
        return False


def find_game_folder():
    """Returns the game's live Saves folder if one of the known locations exists, else None."""
    for folder in GAME_FOLDER_CANDIDATES:
        if os.path.isdir(folder):
            return folder
    return None


def backup_files(paths, label='', backup_root=BACKUP_ROOT):
    """Copies the given files into backups/<timestamp>[_label]/ and returns that folder.

    Every write the tool makes goes through here first, so an original can always be restored.
    """
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(backup_root, stamp + ('_' + label if label else ''))
    os.makedirs(backup_dir, exist_ok=True)
    for path in paths:
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
    return backup_dir


def backup_folder(folder, label='full', backup_root=BACKUP_ROOT):
    """Backs up every save file in a folder (characters, stashes, tabs, global data)."""
    paths = [os.path.join(folder, n) for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n))]
    return backup_files(paths, label, backup_root)


def deploy(src_folder, names, dest_folder, backup_root=BACKUP_ROOT):
    """Copies the named save files from src_folder into dest_folder (normally the game's folder).

    The files about to be overwritten in dest_folder are backed up first. Returns the backup folder.
    """
    if os.path.realpath(src_folder) == os.path.realpath(dest_folder):
        raise ValueError('Source and destination are the same folder')
    backup_dir = backup_files([os.path.join(dest_folder, n) for n in names], 'game', backup_root)
    for name in names:
        shutil.copy2(os.path.join(src_folder, name), os.path.join(dest_folder, name))
    return backup_dir


class SaveFile:
    def __init__(self, path):
        self.path = path
        with open(path, encoding='utf-8') as f:
            text = f.read()
        if not text.startswith(PREFIX):
            raise ValueError('%s is not a Last Epoch save file' % path)
        self.json = json.loads(text[len(PREFIX):])

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def is_character(self):
        return 'characterName' in self.json

    @property
    def items(self):
        return self.json.setdefault('savedItems', [])

    def item_version(self):
        versions = [e['data'][0] for e in self.items if decode(e['data'])]
        if versions:
            return max(versions)
        return 6 if 'cycle' in self.json or not self.is_character else 2

    def save(self, backup_root=BACKUP_ROOT):
        backup_dir = backup_files([self.path], 'edit', backup_root)
        with open(self.path, 'w', encoding='utf-8', newline='') as f:
            f.write(PREFIX + json.dumps(self.json, separators=(',', ':'), ensure_ascii=False))
        return backup_dir


def list_saves(folder):
    """Returns (characters, stashes, tabs) save file names found in a folder."""
    chars, stashes, tabs = [], [], []
    for name in sorted(os.listdir(folder)):
        if '.' in name or not os.path.isfile(os.path.join(folder, name)):
            continue
        if 'CHARACTERSLOT' in name:
            chars.append(name)
        elif name.startswith('STASH') and '_TAB_' in name:
            tabs.append(name)
        elif name.startswith('STASH'):
            stashes.append(name)
    return chars, stashes, tabs


def occupied_cells(db, save, container):
    cells = set()
    for e in save.items:
        if save.is_character and e.get('containerID') != container:
            continue
        item = decode(e['data'])
        w, h = db.size(item['base'], item['sub']) if item else (1, 1)
        x0, y0 = e['inventoryPosition']['x'], e['inventoryPosition']['y']
        cells |= {(x0 + x, y0 + y) for x in range(w) for y in range(h)}
    return cells


def add_items(db, save, items, container=INVENTORY_ID):
    """Places items into free grid space. Returns the items that did not fit."""
    grid_w, grid_h = INVENTORY_SIZE if save.is_character else STASH_TAB_SIZE
    cells = occupied_cells(db, save, container)
    version = save.item_version()
    left_over = []
    for item in items:
        w, h = db.size(item['base'], item['sub'])
        spot = next(((x, y) for y in range(grid_h - h + 1) for x in range(grid_w - w + 1)
                     if not any((x + i, y + j) in cells for i in range(w) for j in range(h))), None)
        if spot is None:
            left_over.append(item)
            continue
        cells |= {(spot[0] + i, spot[1] + j) for i in range(w) for j in range(h)}
        entry = {'itemData': None, 'data': encode(dict(item, version=version)),
                 'inventoryPosition': {'x': spot[0], 'y': spot[1]}, 'quantity': 1}
        if save.is_character:
            entry['containerID'] = container
        entry['formatVersion'] = 2
        save.items.append(entry)
    return left_over


def place_item(db, save, item, x, y, container=INVENTORY_ID):
    """Puts one item at a grid position; raises ValueError when it would overlap or leave the grid."""
    grid_w, grid_h = INVENTORY_SIZE if save.is_character else STASH_TAB_SIZE
    w, h = db.size(item['base'], item['sub'])
    if x < 0 or y < 0 or x + w > grid_w or y + h > grid_h:
        raise ValueError('a %dx%d item does not fit at %d,%d' % (w, h, x, y))
    cells = occupied_cells(db, save, container)
    if any((x + i, y + j) in cells for i in range(w) for j in range(h)):
        raise ValueError('cell %d,%d is occupied' % (x, y))
    entry = {'itemData': None, 'data': encode(dict(item, version=save.item_version())),
             'inventoryPosition': {'x': x, 'y': y}, 'quantity': 1}
    if save.is_character:
        entry['containerID'] = container
    entry['formatVersion'] = 2
    save.items.append(entry)
    return entry


def clear_container(save, container=INVENTORY_ID):
    if save.is_character:
        save.json['savedItems'] = [e for e in save.items if e.get('containerID') != container]
    else:
        save.json['savedItems'] = []


# ---------------------------------------------------------------- item creation

def make_item(db, base_type, sub_type, affixes=(), fp=30, roll=255):
    """affixes: list of (affixId, tier) with tier 0-based."""
    return {'base': base_type, 'sub': sub_type, 'rarity': min(len(affixes), 4), 'flag': 0,
            'implicits': [roll] * 3, 'fp': fp, 'affixes': [(a, t, roll) for a, t in affixes],
            'unique': None, 'rolls': []}


def make_unique(db, unique_id, roll=255):
    u = db.uniques[unique_id]
    return {'base': u['baseTypeID'], 'sub': u['subTypeID'], 'rarity': 7, 'flag': 0,
            'implicits': [roll] * 3, 'fp': 0, 'affixes': [], 'unique': unique_id, 'rolls': [roll] * 8}


# Weapon styles: base types to generate. 18 = shield, 19 = catalyst, 17 = quiver.
STYLES = {'2H Axe': [12], '2H Mace': [13], '2H Sword': [16], '2H Spear': [14], 'Staff': [15],
          '1H Sword + Shield': [9, 18], '1H Axe + Shield': [5, 18], '1H Mace + Shield': [7, 18],
          'Sceptre + Shield': [8, 18], 'Sceptre + Catalyst': [8, 19], 'Wand + Catalyst': [10, 19],
          'Dagger + Dagger': [6, 6], 'Bow + Quiver': [23, 17]}
CASTER_STYLES = {'Staff', 'Sceptre + Catalyst', 'Wand + Catalyst'}
CLASS_STYLE = {0: '2H Axe', 1: 'Staff', 2: '2H Sword', 3: 'Wand + Catalyst', 4: 'Bow + Quiver'}
CLASS_ATTRIBUTE = {0: 501, 1: 502, 2: 501, 3: 502, 4: 503}  # Strength / Intelligence / Dexterity

# Helmet and body armor subtypes are class-specific in blocks; 0-7 are usable by everyone.
CLASS_ARMOR = {0: {3: range(8, 16), 1: range(16, 24), 0: range(24, 32), 2: range(32, 40), 4: range(42, 50)},
               1: {3: range(8, 16), 1: range(16, 24), 0: range(24, 32), 2: range(32, 41), 4: range(43, 51)}}
# Plain, non-class-specific subtypes to pick from for the other slots.
KIT_SUBTYPES = {2: [0, 1, 2, 5, 8, 9], 3: range(0, 7), 4: [0, 1, 2, 5, 7], 18: [0, 1, 2, 4, 5, 9, 14],
                19: range(0, 13), 17: range(0, 9), 22: [3, 5, 10], 21: [3]}

RESISTANCES = [45, 13, 24, 17, 7, 19, 10]  # physical, fire, lightning, cold, void, poison, necrotic
VIT, HEALTH, ARMOR, REGEN = 505, 25, 31, 22
# (prefix candidates, suffix candidates) per base type; 'A' = class attribute, 'R' = a resistance.
ARMOR_AFFIXES = {0: (['A', VIT], [HEALTH, 'R', ARMOR]), 1: ([VIT, 'A'], [HEALTH, ARMOR, 'R']),
                 2: ([VIT, 'A'], [HEALTH, 'R', REGEN]), 3: ([28, VIT, 'A'], [HEALTH, 'R', ARMOR]),
                 4: (['S', 'A', VIT], [HEALTH, 'R', ARMOR]), 20: (['A', VIT], [HEALTH, 'R', REGEN]),
                 21: (['A', VIT], [HEALTH, 'R', REGEN]), 22: (['A', VIT], [HEALTH, 'R', REGEN]),
                 18: ([3, 81], [HEALTH, 74, 'R']), 19: ([38, 4, 34], [HEALTH, REGEN]),
                 17: ([30, 5], [HEALTH, 8])}
MELEE_AFFIXES = ([63, 89, 2], [44, 68, 91])
CASTER_AFFIXES = ([38, 4, 34], [20, REGEN])
BOW_AFFIXES = ([432, 30], [68, 20])


def default_style(save):
    """Style matching the equipped weapon, else the class default."""
    equipped = {e.get('containerID'): decode(e['data']) for e in save.items}
    weapon, offhand = equipped.get(4), equipped.get(5)
    if weapon:
        wanted = [weapon['base']] + ([offhand['base']] if offhand else [])
        for style, types in STYLES.items():
            if types == wanted or (len(wanted) == 1 and types[0] == wanted[0]):
                return style
    return CLASS_STYLE.get(save.json.get('characterClass'), '2H Sword')


def _pick_base(db, base_type, level, char_class, caster):
    if base_type == 20:  # amulet: attack/cast speed from level 4, health before that
        sub = (3 if caster else 1) if level >= 4 else 5
        return db.base(20, sub)
    pools = []
    if base_type in CLASS_ARMOR:
        pools = [CLASS_ARMOR[base_type].get(char_class, []), range(0, 8)]
    elif base_type in KIT_SUBTYPES:
        pools = [KIT_SUBTYPES[base_type]]
    else:  # weapons: every regular base
        pools = [[b['subTypeID'] for b in db.subtypes(base_type)
                  if 'Avenged' not in b['name'] and 'Upgrade' not in ' '.join(b['implicits'])]]
    for pool in pools:
        usable = [db.base(base_type, s) for s in pool
                  if db.base(base_type, s) and db.base(base_type, s)['req']['level'] <= level]
        if usable:
            return max(usable, key=lambda b: (b['req']['level'], b['subTypeID']))
    return None


def _pick_tiers(db, affix_ids, base_req, level):
    """Raises tiers evenly as far as the level requirement allows."""
    tiers = [0] * len(affix_ids)
    while True:
        for i in sorted(range(len(tiers)), key=lambda i: (tiers[i], i)):
            trial = tiers[:i] + [tiers[i] + 1] + tiers[i + 1:]
            if (tiers[i] < MAX_KIT_TIER and (affix_ids[i], tiers[i] + 1) in db.affixes
                    and max(base_req, affix_req(trial)) <= level):
                tiers = trial
                break
        else:
            return tiers


def leveling_kit(db, level, char_class, style):
    """One item per equipment slot, each wearable at the given level."""
    caster = style in CASTER_STYLES
    resistances = [r for r in RESISTANCES if db.affixes[(r, 0)]['level'] <= level]
    counter = [0]

    def resolve(candidates, taken):
        picked = []
        for c in candidates:
            if c == 'A':
                c = CLASS_ATTRIBUTE.get(char_class, VIT)
            elif c == 'S':
                c = 4 if caster else 5 if style == 'Bow + Quiver' else 2  # cast speed / crit / melee speed
            elif c == 'R':
                c = resistances[counter[0] % len(resistances)]
                counter[0] += 1
            if c not in picked and c not in taken and db.affixes[(c, 0)]['level'] <= level:
                picked.append(c)
            if len(picked) == 2:
                break
        return picked

    kit = []
    for base_type in [0, 1, 2, 3, 4, 21, 21, 20, 22] + STYLES[style]:
        base = _pick_base(db, base_type, level, char_class, caster)
        if not base:
            continue
        if base_type in ARMOR_AFFIXES:
            prefixes, suffixes = ARMOR_AFFIXES[base_type]
        else:
            prefixes, suffixes = BOW_AFFIXES if base_type == 23 else CASTER_AFFIXES if caster else MELEE_AFFIXES
        ids = resolve(prefixes, [])
        ids += resolve(suffixes, ids)
        tiers = _pick_tiers(db, ids, base['req']['level'], level)
        kit.append(make_item(db, base_type, base['subTypeID'], list(zip(ids, tiers))))
    return kit


# ---------------------------------------------------------------- "freaky" items

EQUIP_SLOTS = range(2, 13)   # helmet .. relic
MAX_TIER_NIBBLE = 15         # the tier is stored in 4 bits; the game data defines up to index 7 (T8)


def max_tier(db, affix_id):
    """Highest tier index the game data defines for an affix (usually 7 = T8)."""
    return max((t for (a, t) in db.affixes if a == affix_id), default=0)


def equipped_items(save):
    """Decoded items worn by a character, in slot order."""
    worn = {e.get('containerID'): decode(e['data']) for e in save.items if e.get('containerID') in EQUIP_SLOTS}
    return [worn[c] for c in EQUIP_SLOTS if worn.get(c)]


MAX_AFFIXES = 4  # the game turns a non-unique item with more affixes into a plain white item


def freaky_item(db, item, extras=(), tier=None, repeat=1, raise_existing=True, roll=255, limit=MAX_AFFIXES):
    """A boosted copy of an item: max rolls, affixes raised to `tier` (default: the highest the data
    defines for each affix), plus `extras` affix ids added `repeat` times each, on any slot.
    Tested in game: tiers above T7 and affixes on foreign slots work; more than four affixes makes
    the game strip the item to white, so the list is cut to `limit` (extras first, then the item's
    own affixes). Uniques with affixes become legendaries and keep the unique's level requirement,
    which is the only way to wear high-tier affixes at a low level: a non-unique item needs level
    sum(tier values) + 2 * highest - 10 (four T8 affixes = level 86)."""
    def pick_tier(affix_id):
        return max_tier(db, affix_id) if tier is None else min(tier, MAX_TIER_NIBBLE)
    affixes = []
    for affix_id in extras:
        affixes += [(affix_id, pick_tier(affix_id), roll)] * repeat
    for affix_id, t, _ in item['affixes']:
        affixes.append((affix_id, pick_tier(affix_id) if raise_existing else t, roll))
    if limit:
        affixes = affixes[:limit]
    new = dict(item, uid=None, implicits=[roll] * 3, affixes=affixes, rolls=[roll] * len(item['rolls']))
    if item['unique'] is not None:
        new['rarity'] = 9 if affixes else item['rarity']
    else:
        new['rarity'] = min(len(affixes), 4)
        new['fp'] = 0
    return new


# Curated affixes for freaky items: (group, affix id). All reach T8 in the game data, and all were
# found to work on legendaries on any slot. Grouped for the editor's pick list.
FREAKY_MODS = [
    ('Speed', 28), ('Speed', 2), ('Speed', 4), ('Speed', 87), ('Speed', 432), ('Speed', 27),
    ('Melee', 89), ('Melee', 63), ('Melee', 77), ('Melee', 62), ('Melee', 69), ('Melee', 68),
    ('Spell', 38), ('Spell', 49), ('Spell', 84), ('Spell', 34), ('Spell', 330), ('Spell', 382),
    ('Ranged', 431), ('Ranged', 88), ('Ranged', 30),
    ('Damage', 9), ('Damage', 12), ('Damage', 16), ('Damage', 23), ('Damage', 15), ('Damage', 18),
    ('Damage', 61), ('Damage', 72), ('Damage', 5), ('Damage', 6), ('Damage', 55), ('Damage', 101),
    ('Minion', 26), ('Minion', 70),
    ('Defense', 25), ('Defense', 36), ('Defense', 52), ('Defense', 22), ('Defense', 46), ('Defense', 45),
    ('Defense', 1), ('Defense', 31), ('Defense', 8), ('Defense', 59), ('Defense', 92), ('Defense', 425),
    ('Defense', 20), ('Defense', 29),
    ('Attributes', 50), ('Attributes', 501), ('Attributes', 502), ('Attributes', 503), ('Attributes', 504),
    ('Attributes', 505),
    ('Utility', 65), ('Utility', 82), ('Utility', 75), ('Utility', 11),
    # "proc on X": effects triggered on hit, kill, block, crit or potion use
    ('Proc', 44), ('Proc', 41), ('Proc', 20), ('Proc', 55), ('Proc', 68), ('Proc', 56), ('Proc', 57),
    ('Proc', 60), ('Proc', 86), ('Proc', 428), ('Proc', 957), ('Proc', 810), ('Proc', 399),
    ('Proc', 393), ('Proc', 396), ('Proc', 398), ('Proc', 960), ('Proc', 961), ('Proc', 787),
    ('Proc', 1081), ('Proc', 964), ('Proc', 983), ('Proc', 982), ('Proc', 981), ('Proc', 443),
    ('Proc', 454), ('Proc', 998), ('Proc', 821), ('Proc', 958), ('Proc', 1000),
]

# Ready-made four-affix combinations. Fewer than four entries get repeated to fill the item.
FREAKY_PRESETS = {
    'Speed demon (2x move, 2x melee speed)': [28, 28, 2, 2],
    'Max movement speed': [28],
    'Max melee attack speed': [2],
    'Max cast speed': [4],
    'Melee DPS': [2, 89, 63, 6],
    'Melee fire (Paladin)': [2, 89, 12, 55],
    'Caster DPS': [4, 38, 9, 6],
    'Bow DPS': [432, 431, 5, 6],
    'Throwing DPS': [87, 88, 30, 6],
    'Damage over time': [72, 12, 61, 18],
    'Minion master': [26, 70, 4, 27],
    'Tank': [36, 46, 1, 92],
    'Regen tank': [25, 22, 69, 45],
    'Cooldowns and utility': [27, 28, 50, 65],
    'All attributes and resistances': [50, 46, 36, 28],
    'Melee all-rounder (spread over set)': [2, 89, 5, 6, 36, 46, 28],
    'Proc: ailments on hit': [55, 68, 56, 57],
    'Proc: fire explosions (melee fire)': [960, 961, 393, 398],
    'Proc: sustain on hit/kill/block': [44, 20, 41, 1081],
    'Proc: more damage to debuffed': [983, 982, 981, 86],
    'Proc: potion power': [998, 821, 75, 958],
}


def fill_four(affix_ids, limit=MAX_AFFIXES):
    """Repeats the chosen affixes round-robin until the item has `limit` of them."""
    ids = list(affix_ids)
    if not ids:
        return []
    return [ids[i % len(ids)] for i in range(limit)]


def lowest_uniques(db, max_level=0):
    """The lowest-level unique (with mods) for every equipment slot, as {base_type: unique_id}."""
    best = {}
    for u, d in db.uniques.items():
        if not d.get('mods'):
            continue
        t, req = d['baseTypeID'], db.unique_req(u)
        if t not in best or (req, u) < (db.unique_req(best[t]), best[t]):
            best[t] = u
    return best


def best_uniques(db, max_level):
    """The highest-level unique (with mods) per slot that is wearable at `max_level`."""
    best = {}
    for u, d in db.uniques.items():
        req = db.unique_req(u)
        if not d.get('mods') or req > max_level:
            continue
        t = d['baseTypeID']
        if t not in best or (req, u) > (db.unique_req(best[t]), best[t]):
            best[t] = u
    return best


def spread_mods(mods, count, per_item=MAX_AFFIXES):
    """Distributes a list of mods over `count` items, rotating so every item gets `per_item`
    different ones and every mod appears about equally often."""
    mods = list(dict.fromkeys(mods)) or []
    if not mods:
        return [[] for _ in range(count)]
    return [[mods[(i * per_item + k) % len(mods)] for k in range(min(per_item, len(mods)))] for i in range(count)]


def legendary_set(db, extras, tier=None, weapon_types=(8, 18), max_level=None, spread=False):
    """One legendary per slot plus the given weapon types, each carrying `extras` at `tier`
    (default T8). Built on the lowest-level unique per slot, or with `max_level` on the best unique
    wearable at that level. With `spread`, a longer mod list is rotated over the items so each gets
    four different mods; otherwise the same (filled) four go on every item."""
    best = best_uniques(db, max_level) if max_level is not None else lowest_uniques(db)
    slots = [t for t in [0, 1, 2, 3, 4, 21, 21, 20, 22] + list(weapon_types) if t in best]
    mods = spread_mods(extras, len(slots)) if spread else [fill_four(extras)] * len(slots)
    return [freaky_item(db, make_unique(db, best[t]), m, tier) for t, m in zip(slots, mods)]


def upgrade_set(db, worn, level, weapon_types=()):
    """Upgrades for a character's worn (freaky / legendary) items: each item's own affixes, raised
    to their top tier, on the best unique of the same base type wearable at `level`. Items whose
    unique is already the best one at that level are skipped. Extra `weapon_types` get the worn
    weapon's affixes (or the first item's when no weapon is worn)."""
    best = best_uniques(db, level)
    out, mods = [], {}
    for item in worn:
        ids = [a for a, _, _ in item['affixes'] if (a, 0) in db.affixes]
        mods.setdefault(item['base'], ids)
        u = best.get(item['base'])
        if u is None or not ids:
            continue
        if item['unique'] is not None and db.unique_req(u) <= db.unique_req(item['unique']):
            continue
        out.append(freaky_item(db, make_unique(db, u), ids))
    weapon_mods = next((mods[t] for t in mods if t >= 5 and t <= 19), next(iter(mods.values()), []))
    for t in weapon_types:
        if t in best and t not in mods and weapon_mods:
            out.append(freaky_item(db, make_unique(db, best[t]), weapon_mods))
    return out


def guide_upgrade(db, guide, level, fill=(), stages=None):
    """Every gear item of a guide as a legendary wearable at `level`: the guide's own unique when
    its requirement fits, otherwise the best unique of the same base type at that level. Each
    carries the guide's affixes raised to their top tier, topped up to four with `fill` mods
    (a list, or {base type: list}). Duplicates across stages are dropped."""
    best = best_uniques(db, level)
    seen, out = set(), []
    for st in (stages if stages is not None else guide['stages']):
        for spec in st['items']:
            if spec['base'] >= 25:
                continue
            u = spec.get('unique')
            if u not in db.uniques or db.unique_req(u) > level:
                u = best.get(spec['base'])
            if u is None:
                continue
            ids = [a for a, _ in spec['affixes'] if (a, 0) in db.affixes]
            extra = fill.get(spec['base'], []) if isinstance(fill, dict) else fill
            ids = list(dict.fromkeys(ids + [m for m in extra if m not in ids]))[:MAX_AFFIXES]
            key = (u, tuple(ids))
            if key in seen or not ids:
                continue
            seen.add(key)
            out.append(freaky_item(db, make_unique(db, u), ids))
    return out


def guide_all_idols(db, guide):
    """The idols of every stage of a guide, without duplicates."""
    seen, out = set(), []
    for st in guide['stages']:
        for spec in st.get('idols', []):
            key = (spec['base'], spec['sub'], spec.get('unique'), tuple(map(tuple, spec['affixes'])))
            if key not in seen:
                seen.add(key)
                out.append(spec_item(db, spec))
    return out


# Idols: single-tier affixes, normally one prefix + one suffix per idol. (base, sub, [affix ids]).
# A Paladin-flavoured set covering every idol shape; the game's idol grid is 5 x 4 cells.
PALADIN_IDOLS = [
    (26, 0, [135, 105]), (26, 0, [307, 872]), (26, 0, [134, 430]), (26, 0, [305, 105]),   # Minor Lagonian 1x1
    (28, 0, [135, 872]), (28, 0, [107, 430]),                                               # Stout Lagonian 1x2
    (27, 0, [107, 105]), (27, 0, [108, 117]),                                               # Humble Eterran 2x1
    (29, 0, [107, 430]), (29, 0, [135, 105]),                                               # Grand Heorot 3x1
    (30, 2, [134, 872]), (30, 2, [107, 115]),                                               # Large Rahyeh 1x3
    (31, 2, [107, 105]), (32, 2, [107, 430]), (33, 2, [135, 105]),                          # Ornate / Huge / Adorned
]


def idol_set(db, specs=PALADIN_IDOLS, roll=255):
    return [make_item(db, b, s, [(a, 0) for a in affixes], fp=0, roll=roll) for b, s, affixes in specs]


def stash_categories(stash):
    """{category id: name} of a stash's tab categories (folders); 0 is the game's "General"."""
    return {c['categoryId']: c['displayName'] for c in stash.json.get('categories', [])} or {0: 'General'}


def add_stash_category(stash, name, color=0, icon=0):
    """Adds a stash tab category and returns its id. The stash file still has to be saved."""
    cats = stash.json.setdefault('categories', [])
    if not cats:
        cats.append({'categoryId': 0, 'iconId': 0, 'colorId': 0, 'displayName': 'General',
                     'displayOrder': 0, 'folderPriority': None, 'dirty': False})
    cat_id = 1 + max(c['categoryId'] for c in cats)
    cats.append({'categoryId': cat_id, 'iconId': icon, 'colorId': color, 'displayName': name,
                 'displayOrder': len(cats), 'folderPriority': None, 'dirty': False})
    return cat_id


def add_stash_tab(stash, folder, name=None, category_id=0):
    """Creates the next stash tab file for a stash and registers it in the stash's tab list,
    under the given category. The stash file itself still has to be saved. Returns the new
    tab's SaveFile."""
    tabs = stash.json.setdefault('tabsv2', [])
    tab_id = 1 + max([-1] + [int(t.rsplit('_', 1)[1]) for t in tabs if t.rsplit('_', 1)[1].isdigit()])
    tab_name = '%s_TAB_%d' % (stash.json.get('id', stash.name), tab_id)
    path = os.path.join(folder, tab_name)
    if os.path.exists(path):
        raise ValueError('%s already exists' % tab_name)
    tab = {'displayOrder': len(tabs), 'tabId': tab_id, 'categoryId': category_id, 'iconId': 0, 'colorId': 0,
           'displayName': name or 'Stash Tab %d' % (tab_id + 1), 'tabPriority': None,
           'ignoreFolderPriority': False, 'savedItems': [], 'id': tab_name,
           'partitionKey': stash.json.get('partitionKey'), 'seqNo': 0, '_etag': None, 'version': 0}
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(PREFIX + json.dumps(tab, separators=(',', ':')))
    tabs.append(tab_name)
    stash.json['stashTabsCreated'] = True
    return SaveFile(path)


# ---------------------------------------------------------------- build guide sets

GUIDE_FOLDER = os.path.join(HERE, 'data', 'guides')


def load_guide(slug):
    """One imported guide by file name (without .json)."""
    guide = json.loads(read_text('data', 'guides', slug + '.json'))
    guide['file'] = slug + '.json'
    return guide


def load_guides():
    """Gear sets imported from build guides (see import_maxroll.py), one JSON file per guide."""
    return [load_guide(name[:-5]) for name in list_files('data', 'guides') if name.endswith('.json')]


def fit_to_level(db, item, level, char_class=None):
    """Makes an item wearable at the given level.

    A base with a higher requirement is swapped for the best base of the same type usable at
    that level; then affix tiers are lowered, highest first, until the requirement fits.
    """
    b = db.base(item['base'], item['sub'])
    if b and b['req']['level'] > level:
        alt = _pick_base(db, item['base'], level, char_class, caster=False)
        if alt:
            item['base'], item['sub'] = alt['baseTypeID'], alt['subTypeID']
    while item_req(db, item) > level and any(t > 0 for _, t, _ in item['affixes']):
        i = max(range(len(item['affixes'])), key=lambda i: item['affixes'][i][1])
        affix_id, tier, roll = item['affixes'][i]
        item['affixes'][i] = (affix_id, tier - 1, roll)
    # Affixes with their own minimum level (e.g. +1 to a skill) cannot be lowered: drop them.
    item['affixes'] = [(a, t, r) for a, t, r in item['affixes']
                       if db.affixes.get((a, 0), {}).get('level', 0) <= level]
    item['rarity'] = min(len(item['affixes']), 4)
    return item


def spec_item(db, spec):
    """A guide item spec as an item: a rare, or a unique / legendary when it names a unique."""
    affixes = [tuple(a) for a in spec['affixes']]
    if spec.get('unique') is not None and spec['unique'] in db.uniques:
        item = make_unique(db, spec['unique'])
        item['affixes'] = [(a, t, 255) for a, t in affixes][:MAX_AFFIXES]
        if item['affixes']:
            item['rarity'] = 9
        return item
    return make_item(db, spec['base'], spec['sub'], affixes, fp=0 if spec['base'] >= 25 else 30)


def guide_set(db, stage, level=None, char_class=None):
    """The items of one guide stage with max rolls, optionally fitted to a character level
    (uniques and legendaries are never changed)."""
    items = []
    for spec in stage['items']:
        item = spec_item(db, spec)
        if level is not None and item['unique'] is None:
            fit_to_level(db, item, level, char_class)
        items.append(item)
    return items


def guide_idols(db, stage):
    """A stage's idols, plus its idol altar when the guide has one."""
    specs = list(stage.get('idols', [])) + ([stage['altar']] if stage.get('altar') else [])
    return [spec_item(db, spec) for spec in specs]


# ---------------------------------------------------------------- command line

def import_build_tabs(db, stash, folder, guide):
    """Writes every preset of an imported build into its own stash tab, under a category named
    'imported from "<build name>"'. Items are the planner's items with max rolls; idols and the idol
    altar go in the same tab; the uniques the page mentions get one more tab. The tab files are
    written; the stash file still has to be saved. Returns (category id, [tab SaveFiles])."""
    name = 'imported from "%s"' % (guide.get('name') or guide.get('title') or 'build')
    cat = add_stash_category(stash, name, color=4)
    tabs = []
    for stage in guide['stages']:
        items = guide_set(db, stage) + guide_idols(db, stage)
        tab = add_stash_tab(stash, folder, stage['name'][:40], cat)
        left = add_items(db, tab, items)
        if left:   # a preset with too much for one tab spills into a second one
            tab.save()
            tab = add_stash_tab(stash, folder, (stage['name'] + ' (2)')[:40], cat)
            add_items(db, tab, left)
        tab.save()
        tabs.append(tab)
    uniques = [make_unique(db, u) for u in guide.get('uniques', []) if u in db.uniques]
    if uniques:
        tab = add_stash_tab(stash, folder, 'Uniques on page', cat)
        add_items(db, tab, uniques)
        tab.save()
        tabs.append(tab)
    return cat, tabs


def save_guide(guide, slug):
    """Keeps an imported guide in data/guides for the Guide sets tab; silently skipped when the data
    folder is read-only (packaged build)."""
    try:
        os.makedirs(GUIDE_FOLDER, exist_ok=True)
        with open(os.path.join(GUIDE_FOLDER, slug + '.json'), 'w', encoding='utf-8') as f:
            json.dump(guide, f, indent=1)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- character stats

STAT_RE = re.compile(r'^\s*([+-]?)\s*\(?(-?\d+(?:\.\d+)?)(?:\s*(?:-|to)\s*(-?\d+(?:\.\d+)?))?\)?\s*(%?)\s*(.*?)\s*$')
ELEMENT_NAMES = ['fire', 'cold', 'lightning', 'void', 'necrotic', 'poison', 'physical']
RES_CAP = 75


def parse_stat(text, roll=255):
    """One mod line (a '/'-separated hybrid gives several) -> [(key, value)] with the roll applied.
    '+(190-240) Mana' -> ('mana', 240 at max roll); '(40-47)% increased Health' -> ('% increased health', 47).
    Lines without a leading number (e.g. 'Can Equip Swords in Offhand') come back as (text, None)."""
    out = []
    for part in clean(text).split(' / '):
        m = STAT_RE.match(part)
        if not m or not m.group(5):
            out.append((part.strip().lower(), None))
            continue
        sign, lo, hi, pct, rest = m.groups()
        lo = float(lo)
        value = lo + (float(hi) - lo) * roll / 255.0 if hi is not None else lo
        if sign == '-':
            value = -value
        rest = rest.lower()
        if pct and rest.startswith('to '):      # '+X% to All Resistances' -> '% all resistances'
            rest = rest[3:]
        key = ('% ' if pct else '') + rest
        out.append((key, value))
    return out


def item_stats(db, item):
    """[(source line, key, value)] for an item's implicits, unique mods and affixes at their rolls."""
    out = []
    if not item:
        return out
    b = db.base(item['base'], item['sub']) or {}
    for i, text in enumerate(b.get('implicits', [])):
        roll = item['implicits'][i] if i < len(item['implicits']) else 255
        out += [(clean(text), k, v) for k, v in parse_stat(text, roll)]
    if item['unique'] is not None and item['unique'] in db.uniques:
        u = db.uniques[item['unique']]
        for text, rid in zip(u['mods'], u.get('rollIds', [None] * len(u['mods']))):
            roll = item['rolls'][rid] if rid is not None and rid < len(item['rolls']) else 255
            out += [(clean(text), k, v) for k, v in parse_stat(text, roll)]
    for a, t, roll in item['affixes']:
        text = db.affix_text(a, t)
        out += [('T%d %s' % (t + 1, text), k, v) for k, v in parse_stat(text, roll)]
    return out


def character_stats(db, save, trees=None):
    """Totals of every numeric stat a character carries: worn gear, idols, blessings, passives (per-point
    stats and threshold bonuses) and the class base. Returns (stats, summary): stats is
    {key: {'total': v, 'sources': [(source, v)]}}, summary a list of (label, text) derived lines."""
    trees = trees or load_trees()
    j = save.json
    level, char_class = j.get('level', 1), j.get('characterClass', 0)
    tree = trees.get(char_class, {})
    stats = {}

    def add(source, key, value):
        if value is None:
            return
        e = stats.setdefault(key, {'total': 0.0, 'sources': []})
        e['total'] += value
        e['sources'].append((source, value))

    for e in save.items:
        cid = e.get('containerID')
        if cid in EQUIP_SLOTS or cid == 29 or cid >= BLESSING_CONTAINER and cid != ALTAR_CONTAINER and cid < 60:
            item = decode(e['data'])
            if not item:
                continue
            where = CONTAINERS.get(cid, 'Idol' if cid == 29 else 'Blessing')
            name = '%s: %s' % (where, item_title(db, item))
            for line, key, value in item_stats(db, item):
                add(name + ' - ' + line, key, value)
    ct = j.get('savedCharacterTree') or {}
    for nid, points in zip(ct.get('nodeIDs', []), ct.get('nodePoints', [])):
        node = tree.get('passives', {}).get(str(nid))
        if not node:
            continue
        name = 'Passive: %s (%d)' % (node[4], points)
        for text in node[5]:
            for key, value in parse_stat(text):
                add(name + ' - ' + text, key, value * points if value is not None else None)
        if node[6] and points >= (node[7] or 0):
            for text in node[6]:
                for key, value in parse_stat(text):
                    add(name + ' - ' + text, key, value)
    base = tree.get('base', {})
    if base:
        add('Class base', 'health', base.get('baseHealth', 0) + base.get('healthPerLevel', 0) * (level - 1))
        add('Class base', 'mana', base.get('baseMana', 0) + base.get('manaPerLevel', 0) * (level - 1))
        add('Class base', 'health regen', base.get('healthRegen', 0) + base.get('healthRegenPerLevel', 0) * (level - 1))
        add('Class base', 'mana regen', base.get('manaRegen', 0))
        for attr, key in (('baseStr', 'strength'), ('baseDex', 'dexterity'), ('baseInt', 'intelligence'),
                          ('baseAtt', 'attunement'), ('baseVit', 'vitality')):
            add('Class base', key, base.get(attr, 0))
        add('Class base', '% endurance', 100 * base.get('baseEndurance', 0))

    def total(*keys):
        return sum(stats[k]['total'] for k in keys if k in stats)

    summary = []
    for el in ELEMENT_NAMES:
        v = total('%% %s resistance' % el, '% all resistances') + (total('% elemental resistance') if el in ('fire', 'cold', 'lightning') else 0)
        summary.append(('%s resistance' % el.title(), '%d%%' % min(v, RES_CAP) + (' (%d over the cap)' % (v - RES_CAP) if v > RES_CAP else '')))
    attrs = {a: total(a, 'all attributes', 'to all attributes') for a in ('strength', 'vitality', 'dexterity', 'intelligence', 'attunement')}
    summary.append(('Attributes', ', '.join('%s %d' % (a.title(), v) for a, v in attrs.items() if v)))
    flat_hp, inc_hp = total('health'), total('% increased health')
    summary.append(('Health', '%d flat, %d%% increased, so about %d without the vitality bonus' % (flat_hp, inc_hp, flat_hp * (1 + inc_hp / 100))))
    flat_mana, inc_mana = total('mana'), total('% increased mana')
    summary.append(('Mana', '%d flat, %d%% increased, so about %d' % (flat_mana, inc_mana, flat_mana * (1 + inc_mana / 100))))
    summary.append(('Mana regen', '%d%% increased' % total('% increased mana regen')))
    summary.append(('Armor', '%d flat, %d%% increased' % (total('armor'), total('% increased armor'))))
    summary.append(('Endurance', '%d%%, threshold +%d' % (total('% endurance'), total('endurance threshold'))))
    crit_flat, crit_inc = 5 + total('% critical strike chance', '% melee critical strike chance'), total('% increased critical strike chance')
    summary.append(('Critical strike', 'chance about %d%% (base 5 + %d flat, %d%% increased), multiplier +%d%%' % (
        min(100, crit_flat * (1 + crit_inc / 100)), crit_flat - 5, crit_inc, total('% critical strike multiplier'))))
    summary.append(('Speed', 'movement +%d%%, melee attack +%d%%, cast +%d%%' % (
        total('% increased movement speed'), total('% increased melee attack speed'), total('% increased cast speed'))))
    summary.append(('Damage', 'melee +%d%%, void +%d%%, physical +%d%%, fire +%d%%, spell +%d%%, all +%d%%' % (
        total('% increased melee damage'), total('% increased void damage'), total('% increased physical damage'),
        total('% increased fire damage'), total('% increased spell damage'), total('% increased damage'))))
    summary.append(('Leech', 'melee %.1f%%, all damage %.1f%%, leech rate +%d%%' % (
        total('% of melee damage leeched as health'), total('% of damage leeched as health'), total('% increased leech rate'))))
    skills = sorted((k[3:].title(), v['total']) for k, v in stats.items() if k.startswith('to ') and v['total'] and k != 'to all attributes')
    if skills:
        summary.append(('Skill levels', ', '.join('%s +%d' % (n, v) for n, v in skills)))
    return stats, summary


# ---------------------------------------------------------------- new characters

SLOT_CONTAINERS = {'head': 2, 'helmet': 2, 'body': 3, 'chest': 3, 'weapon': 4, 'mainhand': 4, 'offhand': 5,
                   'off-hand': 5, 'shield': 5, 'hands': 6, 'gloves': 6, 'waist': 7, 'belt': 7, 'feet': 8, 'boots': 8,
                   'finger1': 9, 'ring1': 9, 'finger2': 10, 'ring2': 10, 'neck': 11, 'amulet': 11, 'relic': 12}
ALTAR_CONTAINER = 123      # where the game keeps the equipped idol altar
BLESSING_CONTAINER = 33    # equipped blessings: one container per timeline
BLESSING_SLOTS = [33, 34, 35, 36, 37, 38, 39, 43, 44, 45]   # as seen on a character with all ten timelines blessed
PASSIVE_QUEST_POINTS = 14  # a level 100 character has 99 + 14 = 113 passive points (Maxroll planner)
SKILL_XP_MAX = 5700000     # skill experience at skill level 20
SKILL_POINTS = 20          # points a level 20 skill has on its own; gear bonuses come after loading, so a saved
                           # tree with more points than that is reset by the game
MASTERY_EVENT = 'EpochMasteryUnlock'
PROGRESS_FIELDS = [        # campaign and endgame state copied from the template character
    'unlockedWaypointScenes', 'openedOneShotCaches', 'portalUnlocked', 'reachedTown', 'savedQuests',
    'savedMonolithQuests', 'oneTimeEvents', 'focusedQuest', 'sceneProgresses', 'monolithRuns', 'maxCorruption',
    'timelineCompletion', 'timelineDifficultyCompletion', 'timelineDifficultyUnlocks', 'monolithEchoesConquered',
    'monolithTimelinesConquered', 'blessingsDiscovered', 'openBlessings', 'dungeonCompletion', 'factions',
    'arenaTiersCompleted', 'lastVisitedTownScene', 'competitiveCharacterVersion', 'cycle', 'omenWindowMinCampaignLevel',
    'championMinLevel', 'closedPassivesTooltip', 'closedSkillsTooltip', 'closedMonolithTooltip', 'closedIdolsTooltip',
    'closedTemporalShiftTooltip', 'closedMinSkillLevelTutorial', 'closedAddEquipmentTooltip',
    'closedForgingPotentialTooltip', 'closedUpgradeAffixTooltip', 'closedShatterEquipmentTooltip']
RESET_FIELDS = {'died': False, 'deaths': 0, 'respecs': 0, 'uniquesPickedUp': 0, 'totalPlaytimePlayed': 0.0,
                'levelTracking': {}, 'currentExp': 0, 'maxWave': 0, 'currentArenaRunWaves': 0,
                'previousArenaRunWaves': 0, 'monolithOptions': [], 'activeMonolithMods': [], 'monolithDepth': 0,
                'hasRerolledMonolithOptions': False, 'currentMonolithRunTimelineID': 0,
                'currentMonolithRunDifficultyIndex': 0, 'seqNo': 0, 'characterTreeNodeProgression': []}


def load_trees():
    """Per class: masteries and the passive / skill tree nodes (max points, mastery, requirement, links)."""
    return {int(k): v for k, v in json.loads(read_text('data', 'trees.json')).items()}


def load_skills():
    """Planner skill key -> {'name', 'treeId'}."""
    return json.loads(read_text('data', 'skills.json'))


def allocate(history, nodes, label=''):
    """Turns a planner point history (node id per point) into (nodeIDs, nodePoints, notes), capped at each
    node's maximum. Nodes of the other masteries stay: the game lets every mastery tree be entered up to
    its lock, only the chosen mastery's deeper nodes need the mastery."""
    counts = {}
    for nid in history:
        counts[int(nid)] = counts.get(int(nid), 0) + 1
    ids, points, notes = [], [], []
    for nid, n in counts.items():
        info = nodes.get(str(nid)) or nodes.get(nid)
        if info is None:
            notes.append('%s: node %d unknown, skipped' % (label, nid))
            continue
        if n > info[0] > 0:
            notes.append('%s: node %d (%s) capped at %d points' % (label, nid, info[-1], info[0]))
            n = info[0]
        ids.append(nid)
        points.append(n)
    return ids, points, notes


def next_character_slot(folder):
    chars = list_saves(folder)[0]
    used = [int(c.rsplit('_', 1)[1]) for c in chars if c.rsplit('_', 1)[1].isdigit()]
    return max(used, default=-1) + 1


MODES = {'Normal': (False, False), 'Solo Account Found': (True, False), 'Solo Character Found': (False, True)}


def plan_trees(stage, char_class, level, versions=None, trees=None, skills=None):
    """Passive tree, skill trees and ability bar for a preset at a level:
    (characterTree, skillTrees, abilityBar, weaverTree or None, notes)."""
    trees, skills = trees or load_trees(), dict(skills or load_skills())
    tree = trees[char_class]
    versions = versions or {}
    notes = []
    budget = level - 1 + PASSIVE_QUEST_POINTS
    history = list(stage.get('passives', []))
    if len(history) > budget:
        notes.append('passives: planner spends %d points, the first %d kept for level %d' % (len(history), budget, level))
        history = history[:budget]
    ids, points, n = allocate(history, tree['passives'], 'passives')
    notes += n
    character_tree = {'treeID': '', 'version': versions.get('', 12), 'nodeIDs': ids, 'nodePoints': points,
                      'unspentPoints': max(0, budget - sum(points)), 'nodesTaken': None}
    weaver = None
    if stage.get('weaver'):
        wids, wpoints = [], []
        for nid in stage['weaver']:
            if nid in wids:
                wpoints[wids.index(nid)] += 1
            else:
                wids.append(nid)
                wpoints.append(1)
        weaver = {'version': 9, 'nodeIDs': wids, 'nodePoints': wpoints}
    specialized = (stage.get('specializedSkills') or [])[:5]
    # A skill newer than the local data has no tree id: pair the unknown skill names with the planner's
    # tree ids that no known skill claims (by elimination), and trust the planner's allocation for them.
    unknown_names = [k for k in specialized if k and k not in skills]
    unclaimed = [t for t in stage.get('skillTrees', {}) if t not in {v['treeId'] for v in skills.values()}]
    if len(unknown_names) == 1 and len(unclaimed) == 1:
        skills[unknown_names[0]] = {'name': unknown_names[0], 'treeId': unclaimed[0]}
        notes.append('skill %s mapped to tree %s by elimination (newer than the local data)' % (unknown_names[0], unclaimed[0]))
    skill_trees, bar = [], []
    for slot, key in enumerate(specialized):
        info = skills.get(key or '')
        if not info:
            if key:
                notes.append('skill %s has no tree in the data, left unspecialized' % key)
            continue
        tid = info['treeId']
        nodes = tree['skills'].get(tid)
        history = list(stage.get('skillTrees', {}).get(tid, []))
        if len(history) > SKILL_POINTS:     # the planner counts gear bonuses; keep the first 20 picks (a valid prefix)
            notes.append('%s: planner spends %d points, the first %d kept (the rest comes from gear in game)' % (info['name'], len(history), SKILL_POINTS))
            history = history[:SKILL_POINTS]
        if nodes is None:       # tree not in the local data: take the planner's points as they are
            counts = {}
            for nid in history:
                counts[int(nid)] = counts.get(int(nid), 0) + 1
            ids, points, n = list(counts), list(counts.values()), ['%s: tree %s not in the local data, allocation unchecked' % (info['name'], tid)]
        else:
            ids, points, n = allocate(history, nodes, info['name'])
        notes += n
        skill_trees.append({'treeID': tid, 'slotNumber': slot, 'xp': SKILL_XP_MAX, 'version': versions.get(tid, 0),
                            'nodeIDs': ids, 'nodePoints': points, 'unspentPoints': 0, 'nodesTaken': None, 'abilityXP': 0.0})
    for key in (stage.get('activeSkills') or [None] * 5)[:5]:
        bar.append(skills.get(key or '', {}).get('treeId', ''))
    spare = [t['treeID'] for t in skill_trees if t['treeID'] not in bar]
    bar = [b or (spare.pop(0) if spare else '') for b in bar]
    return character_tree, skill_trees, (bar + [''] * 5)[:5], weaver, notes


def preset_items(db, stage):
    """The items of a preset: ([(slot container, item)], altar item or None, [idol items], [(index, blessing item)]).
    Gear with an unknown slot name is returned with container None."""
    gear = []
    for spec in stage.get('items', []):
        gear.append((SLOT_CONTAINERS.get(spec['slot'].lower()), spec_item(db, spec)))
    altar = spec_item(db, stage['altar']) if stage.get('altar') else None
    idols = guide_idols(db, dict(stage, altar=None))
    blessings = []
    for i, b in enumerate(stage.get('blessings') or []):
        if b and db.base(34, b['sub']) is not None:
            roll = min(255, max(0, round(255 * float(b.get('roll', 1)))))
            blessings.append((i, make_item(db, 34, b['sub'], fp=0, roll=roll)))
    return gear, altar, idols, blessings


def _entry(item, container, version=6):
    return {'itemData': None, 'data': encode(dict(item, version=version)), 'inventoryPosition': {'x': 0, 'y': 0},
            'quantity': 1, 'containerID': container, 'formatVersion': 2}


def blessing_slots(save):
    """The containers a character's equipped blessings sit in, in timeline order; the known layout otherwise."""
    slots = sorted({e.get('containerID') for e in save.items if e.get('containerID', 0) >= BLESSING_CONTAINER
                    and e.get('containerID') != ALTAR_CONTAINER and decode(e['data']) and decode(e['data'])['base'] == 34})
    return slots if len(slots) >= len(BLESSING_SLOTS) else BLESSING_SLOTS


def new_character(db, template, name, char_class, mastery, level=100, stage=None, slot_id=0, gear=True,
                  idols=True, blessings=True, mode='Normal', hardcore=False):
    """A campaign-complete character JSON built from a template character (its quests, waypoints, monolith
    and faction state are copied) with the class, mastery, level, passives, skills, gear, idols and blessings
    of a build preset (an imported guide stage with passive data), or empty trees without one.
    Returns (json, notes)."""
    import copy
    src = template.json
    j = {k: copy.deepcopy(v) for k, v in src.items() if k not in ('savedItems',)}
    for k in RESET_FIELDS:
        if k in j:
            j[k] = copy.deepcopy(RESET_FIELDS[k])
    for k in list(j):
        if k.endswith('Tracking'):
            j[k] = None
    solo_account, solo_character = MODES.get(mode, MODES['Normal'])
    j.update({'characterName': name, 'characterClass': char_class, 'chosenMastery': mastery,
              'originalMastery': mastery, 'level': level, 'id': str(slot_id), 'hardcore': bool(hardcore),
              'masochist': False, 'soloChallenge': solo_account, 'soloCharacterChallenge': solo_character})
    if 'slot' in j:
        j['slot'] = slot_id
    if MASTERY_EVENT not in j.setdefault('oneTimeEvents', []):
        j['oneTimeEvents'].append(MASTERY_EVENT)
    j['savedItems'] = []
    stage = stage or {}
    versions = {t['treeID']: t.get('version', 0) for t in src.get('savedSkillTrees', [])}
    versions[''] = src.get('savedCharacterTree', {}).get('version', 12)
    character_tree, skill_trees, bar, weaver, notes = plan_trees(stage, char_class, level, versions)
    j['savedCharacterTree'] = character_tree
    j['savedSkillTrees'] = skill_trees
    j['abilityBar'] = bar
    if weaver:
        j['savedWeaverTree'] = dict(src.get('savedWeaverTree', {}), **weaver)
    for k in ('werebearAbilityBar', 'sprigganFormAbilityBar', 'swarmbladeAbilityBar'):
        j[k] = []
    save = SaveFile.__new__(SaveFile)
    save.path, save.json = template.path, j
    gear_items, altar, idol_items, blessing_items = preset_items(db, stage)
    if gear:
        for container, item in gear_items:
            if container is None:
                notes.append('%s: unknown slot, put in the inventory' % item_title(db, item))
                add_items(db, save, [item])
            else:
                j['savedItems'].append(_entry(item, container))
        if altar:
            j['savedItems'].append(_entry(altar, ALTAR_CONTAINER))
    if idols:
        left = add_items(db, save, idol_items)
        if left:
            notes.append('%d idols did not fit in the inventory' % len(left))
    if blessings:
        slots = blessing_slots(template)
        for i, item in blessing_items:
            j['savedItems'].append(_entry(item, slots[i] if i < len(slots) else BLESSING_CONTAINER + i))
    return j, notes


def apply_build(db, save, stage, trees=True, gear='equip', idols='inventory', blessings=True, stash_tab=None,
                mastery=True):
    """Puts a build preset onto an existing character, keeping its name, level and progress.
    trees: replace passives, skill trees and the ability bar (passive budget from the character's level).
    gear: 'equip' (worn items move to the inventory), 'inventory', 'stash' (into stash_tab) or 'none'.
    idols: 'inventory', 'stash' or 'none'. blessings: replace the equipped blessings.
    mastery: switch to the preset's mastery when it differs. Returns notes; raises ValueError for a class mismatch."""
    j = save.json
    if stage.get('class') is not None and stage['class'] != j.get('characterClass'):
        raise ValueError('the preset is for a %s, this character is a %s' % (
            CLASSES.get(stage['class'], stage['class']), CLASSES.get(j.get('characterClass'), '?')))
    notes = []
    if mastery and stage.get('mastery') and stage['mastery'] != j.get('chosenMastery'):
        j['chosenMastery'] = stage['mastery']
        notes.append('mastery changed to %s' % load_trees()[j['characterClass']]['masteries'][stage['mastery'] - 1])
    if trees:
        versions = {t['treeID']: t.get('version', 0) for t in j.get('savedSkillTrees', [])}
        versions[''] = j.get('savedCharacterTree', {}).get('version', 12)
        character_tree, skill_trees, bar, weaver, n = plan_trees(stage, j['characterClass'], j.get('level', 1), versions)
        notes += n
        j['savedCharacterTree'] = character_tree
        j['savedSkillTrees'] = skill_trees
        j['abilityBar'] = bar
        if weaver:
            j['savedWeaverTree'] = dict(j.get('savedWeaverTree', {}), **weaver)
    gear_items, altar, idol_items, blessing_items = preset_items(db, stage)
    version = save.item_version()

    def place(items, where):
        if where == 'stash':
            if stash_tab is None:
                raise ValueError('no stash tab chosen')
            left = add_items(db, stash_tab, items)
        else:
            left = add_items(db, save, items)
        if left:
            notes.append('no room for %d item(s): %s' % (len(left), ', '.join(item_title(db, i) for i in left)))

    if gear == 'equip':
        worn = [e for e in save.items if e.get('containerID') in EQUIP_SLOTS or e.get('containerID') == ALTAR_CONTAINER]
        j['savedItems'] = [e for e in save.items if e not in worn]
        moved = [decode(e['data']) for e in worn]
        for container, item in gear_items:
            if container is None:
                notes.append('%s: unknown slot, put in the inventory' % item_title(db, item))
                moved.append(item)
            else:
                j['savedItems'].append(_entry(item, container, version))
        if altar:
            j['savedItems'].append(_entry(altar, ALTAR_CONTAINER, version))
        place([i for i in moved if i], 'inventory')
        if moved:
            notes.append('%d worn item(s) moved to the inventory' % len([i for i in moved if i]))
    elif gear in ('inventory', 'stash'):
        place([i for _, i in gear_items] + ([altar] if altar else []), gear)
    if idols in ('inventory', 'stash'):
        place(idol_items, idols)
    if blessings and blessing_items:
        slots = blessing_slots(save)
        keep = [e for e in save.items if not (e.get('containerID') in slots and decode(e['data']) and decode(e['data'])['base'] == 34)]
        j['savedItems'] = keep
        for i, item in blessing_items:
            j['savedItems'].append(_entry(item, slots[i] if i < len(slots) else BLESSING_CONTAINER + i, version))
    return notes


def write_new_character(folder, data, slot_id):
    """Writes a new character slot file (never overwrites) and returns its SaveFile."""
    path = os.path.join(folder, '1CHARACTERSLOT_BETA_%d' % slot_id)
    if os.path.exists(path):
        raise ValueError('%s already exists' % os.path.basename(path))
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(PREFIX + json.dumps(data, separators=(',', ':'), ensure_ascii=False))
    return SaveFile(path)


def _print_items(db, save):
    for e in save.items:
        item = decode(e['data'])
        where = CONTAINERS.get(e.get('containerID'), 'Container %s' % e.get('containerID'))
        pos = e['inventoryPosition']
        print('--- %s (%d,%d)' % (where if save.is_character else 'Stash', pos['x'], pos['y']))
        print(describe(db, item))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Last Epoch offline save tool')
    sub = parser.add_subparsers(dest='command', required=True)
    show = sub.add_parser('show', help='list the items in a character or stash tab file')
    show.add_argument('file')
    kit = sub.add_parser('kit', help='add a leveling gear set to a character inventory')
    kit.add_argument('file')
    kit.add_argument('--level', type=int, help='target level (default: character level)')
    kit.add_argument('--style', choices=list(STYLES), help='weapon style (default: as equipped)')
    kit.add_argument('--clear', action='store_true', help='empty the inventory first')
    gd = sub.add_parser('guide', help='add a build guide gear set to a character inventory or stash tab')
    gd.add_argument('file')
    gd.add_argument('--guide', type=int, default=0, help='guide index (see --list)')
    gd.add_argument('--stage', type=int, help='stage index; omit for every stage')
    gd.add_argument('--level', type=int, help='lower bases/tiers so the set is wearable at this level')
    gd.add_argument('--uniques', action='store_true', help='also add the uniques the guide recommends')
    gd.add_argument('--list', action='store_true', help='list guides and stages and exit')
    bak = sub.add_parser('backup', help='back up every save file in a folder (default: the game folder)')
    bak.add_argument('folder', nargs='?')
    dep = sub.add_parser('deploy', help='copy save files into the game folder, backing up the originals')
    dep.add_argument('files', nargs='+', help='edited save files to copy')
    dep.add_argument('--to', help='destination folder (default: the detected game folder)')
    args = parser.parse_args(argv)

    if args.command == 'backup':
        folder = args.folder or find_game_folder()
        if not folder:
            parser.error('game folder not found; pass a folder')
        print('Backed up %s to %s' % (folder, backup_folder(folder)))
        return 0
    if args.command == 'deploy':
        dest = args.to or find_game_folder()
        if not dest:
            parser.error('game folder not found; pass --to')
        src = os.path.dirname(os.path.abspath(args.files[0]))
        backup = deploy(src, [os.path.basename(f) for f in args.files], dest)
        print('Copied %d file(s) to %s. Originals backed up in %s' % (len(args.files), dest, backup))
        return 0

    db = Database()
    if args.command == 'guide' and args.list:
        for i, g in enumerate(load_guides()):
            print('%d: %s' % (i, g.get('title') or g['name']))
            for j, st in enumerate(g['stages']):
                print('   stage %d: %s (%d items)' % (j, st['name'], len(st['items'])))
        return 0
    save = SaveFile(args.file)
    if args.command == 'guide':
        guide = load_guides()[args.guide]
        stages = guide['stages'] if args.stage is None else [guide['stages'][args.stage]]
        items = [i for st in stages for i in guide_set(db, st, args.level, save.json.get('characterClass'))]
        if args.uniques:
            items += [make_unique(db, u) for u in guide.get('uniques', []) if u in db.uniques]
        left_over = add_items(db, save, items)
        backup = save.save()
        print('Added %d items from %s. Backup: %s' % (len(items) - len(left_over), guide['name'], backup))
        for item in left_over:
            print('No room for: ' + item_title(db, item))
        return 0
    if args.command == 'show':
        _print_items(db, save)
        return 0
    level = args.level or save.json.get('level', 1)
    style = args.style or default_style(save)
    if args.clear:
        clear_container(save)
    items = leveling_kit(db, level, save.json.get('characterClass'), style)
    left_over = add_items(db, save, items)
    backup = save.save()
    print('Added %d items for level %d (%s). Backup: %s' % (len(items) - len(left_over), level, style, backup))
    for item in left_over:
        print('No room for: ' + item_title(db, item))
    return 0


if __name__ == '__main__':
    sys.exit(main())
