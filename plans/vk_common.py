"""Shared helpers for the Void Knight set plans: affix ids, a resistance budget solver that keeps
every resistance from items (uniques' own mods included) at or below 75%, altar items, and the
stash writer. Plans are lists of (unique id or (base, sub) for a rare, [affix ids]); a ('RES', id)
entry is a resistance affix whose tier the solver picks."""
import os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))
import lesave as L

db = L.Database()
U = {d['name']: u for u, d in db.uniques.items()}

MANA, CHANNEL, MANA_PCT = 34, 369, 331
MELEE_AS, MELEE_DMG, MELEE_VOID, VOID_DMG, VOID_PEN, VOID_PEN2 = 2, 89, 76, 15, 0, 723
CRIT, MELEE_CRIT, CRIT_MULTI = 5, 62, 6
HEALTH, HEALTH_PCT, STR, VIT, ARMOR, ENDUR, ENDUR_THR, REGEN, CRIT_TAKEN = 36, 52, 501, 505, 31, 92, 425, 90, 715
MOVE, AREA, MELEE_AREA, SHRED = 28, 101, 671, 86
CHAN_DMG, CHAN_ENDUR, CHAN_RES = 103, 656, 104
WARPATH, DEV_ORB, ANOMALY, ABYSSAL, SMITE, VOID_CLEAVE, VOLATILE = 561, 562, 560, 567, 603, 653, 566
ALL_RES, ELE_RES, VOID_RES, PHYS_RES, NECRO_RES, POISON_RES = 46, 80, 7, 45, 10, 19

ELEMENTS = ['fire', 'cold', 'lightning', 'void', 'necrotic', 'poison', 'physical']
RES_COVERS = {ALL_RES: ELEMENTS, ELE_RES: ['fire', 'cold', 'lightning'], VOID_RES: ['void'],
              PHYS_RES: ['physical'], NECRO_RES: ['necrotic'], POISON_RES: ['poison'], CHAN_RES: ELEMENTS}
RES_CAP = 75


def max_value(text):
    m = re.search(r'\(?(-?[\d.]+)-?([\d.]+)?\)?%', text)
    return float(m.group(2) or m.group(1)) if m else 0.0


def base_resists(base_type, sub_type, unique_id=None):
    """Max-roll resistances a base's implicits and a unique's mods grant, per element."""
    b = db.base(base_type, sub_type) or {}
    mods = list(b.get('implicits', [])) + (db.uniques[unique_id]['mods'] if unique_id is not None else [])
    out = dict.fromkeys(ELEMENTS, 0.0)
    for m in mods:
        m = L.clean(m)
        if 'Resistance' not in m or 'Minion' in m or 'Transformed' in m:
            continue
        v = max_value(m)
        for e in ELEMENTS:
            if e.title() in m or 'All Resistances' in m or ('Elemental Resistance' in m and e in ('fire', 'cold', 'lightning')):
                out[e] += v
    return out


def budget_tier(affix_id, totals, cap=RES_CAP):
    for t in range(L.max_tier(db, affix_id), -1, -1):
        v = max_value(db.affix_text(affix_id, t))
        if all(totals[e] + v <= cap for e in RES_COVERS[affix_id]):
            return t, v
    return None, 0


def build(plan):
    """Items for a plan, with the resistance budget applied. Returns (items, totals, log)."""
    items, totals, log = [], dict.fromkeys(ELEMENTS, 0.0), []
    for base, _ in plan:
        r = base_resists(*((db.uniques[base]['baseTypeID'], db.uniques[base]['subTypeID'], base) if isinstance(base, int) else (base[0], base[1])))
        for e in ELEMENTS:
            totals[e] += r[e]
    for base, affixes in plan:
        if isinstance(base, int):
            item = L.make_unique(db, base)
            item['rarity'] = 9
        else:
            item = L.make_item(db, base[0], base[1], fp=0)
            item['rarity'] = 4
        name = L.item_title(db, item)
        for a in affixes:
            if isinstance(a, tuple):
                t, v = budget_tier(a[1], totals)
                if t is None or v < 5:
                    log.append('%s: no room for %s' % (name, db.affix_text(a[1], 0)))
                    continue
                for e in RES_COVERS[a[1]]:
                    totals[e] += v
                item['affixes'].append((a[1], t, 255))
                log.append('%s: T%d %s' % (name, t + 1, db.affix_text(a[1], t)))
            else:
                item['affixes'].append((a, L.max_tier(db, a), 255))
        items.append(item)
    return items, totals, log


def problems(item, level):
    out = []
    if len(item['affixes']) > L.MAX_AFFIXES:
        out.append('>4 affixes')
    if L.item_req(db, item) > level:
        out.append('req %d' % L.item_req(db, item))
    for a, _, _ in item['affixes']:
        if db.affixes.get((a, 0), {}).get('level', 0) > level:
            out.append('affix %d needs level %d' % (a, db.affixes[(a, 0)]['level']))
    return out


def altar(sub, affix_ids, tier=7):
    """An idol altar (base 41). The game also gives altars a corrupted affix the editor cannot write."""
    it = L.make_item(db, 41, sub, [(a, tier) for a in affix_ids], fp=0)
    it['rarity'] = 4
    return it


def idols(specs):
    return [L.make_item(db, b, s, [(a, 0) for a in af], fp=0) for b, s, af in specs]


def describe_set(name, items, totals, log, level):
    """Text report of a set: every item with its affixes, level problems, and the resistance totals."""
    lines = ['== ' + name]
    for it in items:
        p = problems(it, level)
        lines.append('   %-30s req %2d  %s%s' % (L.item_title(db, it), L.item_req(db, it),
                     ' | '.join('T%d %s' % (t + 1, db.affix_text(a, t)[:42]) for a, t, _ in it['affixes']),
                     ('  !! ' + ', '.join(p)) if p else ''))
    lines.append('   resistances incl. uniques (max rolls): ' + ', '.join('%s %d' % (e, v) for e, v in totals.items()))
    lines.append('   ' + '; '.join(log))
    lines.append('   flat Mana from affixes: +%d' % sum(240 for i in items for a, _, _ in i['affixes'] if a == MANA))
    return '\n'.join(lines)


def write_tabs(tabs, category_name, color=5, folder=None, stash=None, check_game=True):
    """Writes (tab name, items) pairs into a stash under a category, creating it if needed.
    Default: the live game stash. Returns a message."""
    if check_game and subprocess.run(['pgrep', '-f', '-i', 'last ?epoch'], capture_output=True).returncode == 0:
        raise RuntimeError('Last Epoch is running - close it first')
    folder = folder or L.find_game_folder()
    if stash is None:
        stash = L.SaveFile(os.path.join(folder, 'STASH_CYCLE_8_0'))
    cat = next((i for i, n in L.stash_categories(stash).items() if n.lower() == category_name.lower()), None)
    if cat is None:
        cat = L.add_stash_category(stash, category_name, color=color)
    notes = []
    for name, items in tabs:
        tab = L.add_stash_tab(stash, folder, name, cat)
        left = L.add_items(db, tab, items)
        if left:
            notes.append('no room in %s for %s' % (name, ', '.join(L.item_title(db, i) for i in left)))
        tab.save()
    backup = stash.save()
    return 'Written: category "%s" (%d), %d tab(s), backup %s. %s' % (
        category_name, cat, len(tabs), backup, ' '.join(notes))
