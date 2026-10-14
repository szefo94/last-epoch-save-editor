"""Warpath Void Knight sets built on the guide's own Endgame and Aspirational uniques
(Maxroll "Echo Warpath Void Knight"), max rolls, for the "endgame" / "aspirational" stash categories.
Several bases need level 64-86; the sets are meant to be worn as the character grows into them.

Usage: python3 plans/void_knight_endgame.py [--write]
"""
import os, sys
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vk_common import *

TITLE = 'Warpath Void Knight, Endgame + Aspirational (guide uniques, level 64-86)'
GUIDE = L.load_guide('echo-warpath-void-knight-guide')
LEONINE, OPAL = (0, 61), (21, 10)           # the guide's rare bases (helmet, ring)
CRIT_PKG = [MELEE_CRIT, CRIT, MELEE_AS, VOID_PEN2]   # World Splitter already adds crit per max mana

def variants(head, body, belt, boots, gloves, weapon, neck, ring1, ring2, relic):
    return {
        'Core': [
            (head,   [CHANNEL, MANA, HEALTH_PCT, CRIT_TAKEN]),
            (body,   [WARPATH, MANA, HEALTH, HEALTH_PCT]),
            (belt,   [MANA, HEALTH, VOID_DMG, ('RES', ALL_RES)]),
            (boots,  [MOVE, VIT, HEALTH, ('RES', ELE_RES)]),
            (gloves, [MELEE_AS, MANA, DEV_ORB, SHRED]),
            (weapon, CRIT_PKG),
            (neck,   [CRIT_MULTI, MANA, VOID_PEN, HEALTH]),
            (ring1,  [MANA, VOID_DMG, STR, ('RES', VOID_RES)]),
            (ring2,  [MANA, MELEE_DMG, HEALTH, ('RES', PHYS_RES)]),
            (relic,  [ANOMALY, ABYSSAL, MANA, AREA]),
        ],
        'Max damage': [
            (head,   [CHANNEL, MANA, CHAN_DMG, VOID_DMG]),
            (body,   [WARPATH, MANA, VOID_DMG, MELEE_DMG]),
            (belt,   [MANA, VOID_DMG, MELEE_AREA, ('RES', ALL_RES)]),
            (boots,  [MOVE, MELEE_AS, MELEE_VOID, ('RES', ELE_RES)]),
            (gloves, [MELEE_AS, MANA, DEV_ORB, SHRED]),
            (weapon, CRIT_PKG),
            (neck,   [CRIT_MULTI, MANA, VOID_PEN, MELEE_VOID]),
            (ring1,  [MANA, VOID_DMG, MELEE_DMG, ('RES', VOID_RES)]),
            (ring2,  [MANA, MELEE_DMG, CRIT_MULTI, AREA]),
            (relic,  [ANOMALY, ABYSSAL, SMITE, VOID_CLEAVE]),
        ],
        'Tank': [
            (head,   [CHANNEL, MANA, HEALTH, ARMOR]),
            (body,   [WARPATH, MANA, HEALTH, ENDUR]),
            (belt,   [MANA, HEALTH, ENDUR_THR, ('RES', ALL_RES)]),
            (boots,  [MOVE, VIT, HEALTH, ('RES', CHAN_RES)]),
            (gloves, [MELEE_AS, MANA, HEALTH, CHAN_ENDUR]),
            (weapon, CRIT_PKG),
            (neck,   [CRIT_MULTI, MANA, HEALTH, REGEN]),
            (ring1,  [MANA, HEALTH, STR, ('RES', NECRO_RES)]),
            (ring2,  [MANA, HEALTH, ARMOR, ('RES', POISON_RES)]),
            (relic,  [ANOMALY, ABYSSAL, MANA, HEALTH_PCT]),
        ],
    }

STAGES = {
    'endgame': dict(
        sets=variants(LEONINE, U['Titan Heart'], U['Shattered Chains'], U['Army of Skin'], U['Falcon Fists'],
                      U['World Splitter'], U['Nihilis'], U['Siphon of Anguish'], U['Carcinization of Momentum'],
                      U['Anchor of Oblivion']),
        altars=[(11, [1089, 1101, 1097, 1093]), (3, [1089, 1101, 1097, 1093])],   # guide: Pyramidal; plus Spire
        stage='Endgame', color=3),
    'aspirational': dict(
        sets=variants(LEONINE, U['Titan Heart'], U['Shattered Chains'], U['Army of Skin'], U['Immortal Vise'],
                      U['World Splitter'], U['Nihilis'], U['Siphon of Anguish'], OPAL, U['Shattered Worlds']),
        altars=[(11, [1095, 1089, 1101, 1100]), (3, [1095, 1089, 1101, 1100])],
        stage='Aspirational', color=7),
}

def tabs(level=100):
    """(category, color, tab name, items, report) for every tab of both stages."""
    out = []
    for cat, cfg in STAGES.items():
        for vname, plan in cfg['sets'].items():
            items, totals, log = build(plan)
            name = 'VK %s: %s' % (cfg['stage'], vname)
            out.append((cat, cfg['color'], name, items, describe_set(name, items, totals, log, level)))
        stage = next(s for s in GUIDE['stages'] if s['name'] == cfg['stage'])
        extra = L.guide_idols(db, stage) + [altar(sub, af) for sub, af in cfg['altars']]
        report = '   idols %d, altars %d: %s' % (len(stage['idols']), len(cfg['altars']),
                                                ', '.join(L.item_title(db, i) for i in extra))
        out.append((cat, cfg['color'], 'VK %s: Idols + Altars' % cfg['stage'], extra, report))
    return out


if __name__ == '__main__':
    made = tabs()
    for _, _, _, _, report in made:
        print(report)
    if '--write' in sys.argv:
        for cat in STAGES:
            print(write_tabs([(n, i) for c, _, n, i, _ in made if c == cat], cat, STAGES[cat]['color']))
