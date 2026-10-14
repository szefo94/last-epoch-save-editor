"""Warpath Void Knight (Maxroll "Echo Warpath Void Knight") gear for a level-55 Sentinel.

Every piece is a legendary on a unique a Sentinel can wear at level 55 (uniques from Sentinel guides,
items the character already wears, or class-neutral ones). Affixes follow the guide's priorities with
max rolls: Mana on most pieces (Warrior's Fury), T8 reduced Channel Cost on the helmet, void / melee
damage, melee attack speed, class skills, health, and a resistance budget that never pushes any single
resistance above 75% counting the uniques' own resistances. Crit comes from one package only.

Usage: python3 plans/void_knight_l55.py [--write] [--level N]
"""
import os, sys
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vk_common import *

TITLE = 'Warpath Void Knight, level 55 (uniques wearable now)'
CATEGORY, COLOR = 'void', 5

# --- set plans -------------------------------------------------------------------------------------
# (unique id, [affix ids]); 'RES' entries are resistance affixes whose tier the budget solver picks.
PLANS = {
    'VK Core': [
        (U['Decayed Skull'],                    [CHANNEL, MANA, HEALTH, HEALTH_PCT]),
        (U['Titan Heart'],                      [WARPATH, MANA, HEALTH, STR]),
        (U["Brewmaster's Buckle"],              [MANA, VOID_DMG, HEALTH, ('RES', ALL_RES)]),
        (U['Army of Skin'],                     [MOVE, VIT, HEALTH, ('RES', ELE_RES)]),
        (U['Falcon Fists'],                     [MELEE_AS, MANA, DEV_ORB, SHRED]),
        (U['Shadow Beacon'],                    [MELEE_CRIT, CRIT, CRIT, CRIT_MULTI]),
        (U['Locket of the Forgotten Knight'],   [CRIT_MULTI, MANA, VOID_PEN, HEALTH]),
        (U['Siphon of Anguish'],                [MANA, VOID_DMG, STR, ('RES', VOID_RES)]),
        (U['Carcinization of Momentum'],        [MANA, MELEE_DMG, HEALTH, ('RES', PHYS_RES)]),
        (U['Vortex Pennant'],                   [ANOMALY, ABYSSAL, MANA, AREA]),
    ],
    'VK Alt uniques': [
        (U['Peak of the Mountain'],             [CHANNEL, MANA, HEALTH, HEALTH_PCT]),   # crit from the helmet
        (U['The Kestrel'],                      [WARPATH, MANA, HEALTH, STR]),
        (U['Communion of the Erased'],          [MANA, VOID_DMG, HEALTH, ('RES', ALL_RES)]),
        (U['Darkstride'],                       [MOVE, VIT, HEALTH, ('RES', ELE_RES)]),
        (U['Swaddling of the Erased'],          [MELEE_AS, MANA, DEV_ORB, SHRED]),
        (U['Dreamthorn'],                       [MELEE_CRIT, CRIT, MELEE_VOID, CRIT_MULTI]),
        (U['Strong Mind'],                      [MANA, MANA_PCT, CRIT_MULTI, HEALTH]),
        (U['Siphon of Anguish'],                [MANA, VOID_DMG, STR, ('RES', VOID_RES)]),
        (U['Font of the Erased'],               [MANA, MELEE_DMG, HEALTH, ('RES', PHYS_RES)]),
        (U['Code of an Erased Sentinel'],       [ANOMALY, ABYSSAL, MANA, AREA]),
    ],
    'VK Max damage': [
        (U['Decayed Skull'],                    [CHANNEL, MANA, CHAN_DMG, VOID_DMG]),
        (U['Titan Heart'],                      [WARPATH, MANA, VOID_DMG, MELEE_DMG]),
        (U["Brewmaster's Buckle"],              [MANA, VOID_DMG, MELEE_AREA, ('RES', ALL_RES)]),
        (U['Army of Skin'],                     [MOVE, MELEE_AS, MELEE_VOID, ('RES', ELE_RES)]),
        (U['Falcon Fists'],                     [MELEE_AS, MANA, DEV_ORB, SHRED]),
        (U['Merophage'],                        [MELEE_CRIT, CRIT, CRIT, CRIT_MULTI]),
        (U['Locket of the Forgotten Knight'],   [CRIT_MULTI, MANA, VOID_PEN, MELEE_VOID]),
        (U['Siphon of Anguish'],                [MANA, VOID_DMG, MELEE_DMG, ('RES', VOID_RES)]),
        (U['Carcinization of Momentum'],        [MANA, MELEE_DMG, CRIT_MULTI, AREA]),
        (U['Vortex Pennant'],                   [ANOMALY, ABYSSAL, SMITE, VOID_CLEAVE]),
    ],
    'VK Tank': [
        (U['The Last Bear\'s Lament'],          [CHANNEL, MANA, HEALTH, ARMOR]),
        (U['Titan Heart'],                      [WARPATH, MANA, HEALTH, ENDUR]),
        (U["Brewmaster's Buckle"],              [MANA, HEALTH, ENDUR_THR, ('RES', ALL_RES)]),
        (U['Army of Skin'],                     [MOVE, VIT, HEALTH, ('RES', CHAN_RES)]),
        (U['Falcon Fists'],                     [MELEE_AS, MANA, HEALTH, CHAN_ENDUR]),
        (U['Shadow Beacon'],                    [MELEE_CRIT, CRIT, CRIT, CRIT_MULTI]),
        (U['Locket of the Forgotten Knight'],   [CRIT_MULTI, MANA, HEALTH, REGEN]),
        (U['Siphon of Anguish'],                [MANA, HEALTH, STR, ('RES', NECRO_RES)]),
        (U['Carcinization of Momentum'],        [MANA, HEALTH, ARMOR, ('RES', POISON_RES)]),
        (U['Vortex Pennant'],                   [ANOMALY, ABYSSAL, MANA, HEALTH_PCT]),
    ],
}

# Idols: the guide's Sentinel idols (Iron Omen / Solar / Rahyeh) plus universal Weaver idols. (base, sub, [affixes])
IDOLS = [
    (29, 12, [276, 211]), (29, 12, [276, 211]),            # Grand Iron Omen: cast Smite on throwing hit + armor shred
    (30, 12, [279, 211]),                                  # Large Iron Omen: void damage if echoed
    (31, 7, [124, 326, 894]), (31, 7, [124, 326, 894]),    # Heretical Ornate Solar: vitality, melee void, move/damage
    (30, 7, [281, 211, 892]),                              # Heretical Large Rahyeh: inspiration, shred, crit
    (26, 1, [843, 854]), (26, 1, [843, 854]), (26, 1, [843, 854]), (26, 1, [843, 854]),  # Minor Weaver: mana
    (26, 1, [843, 851]), (27, 1, [862, 872]),              # Minor Weaver mana + ele res; Humble Weaver vit + melee
]
# Idol altars (base 41). The game also gives altars a corrupted affix, which this editor cannot write.
ALTARS = [
    ('T8', 3, [1089, 1095, 1101, 1100], 7),   # Spire (no level req, +Mana per refracted idol implicit)
    ('T8', 3, [1093, 1094, 1101, 1098], 7),   # Spire: prefix/suffix effect, mana per refracted, regen per Ornate
    ('T4', 3, [1089, 1095, 1101, 1100], 3),   # Spire at T4: safe if altars follow the gear level formula
    ('T8', 5, [1089, 1095, 1101, 1100], 7),   # Visage (no level req, health per Omen idol implicit)
    ('T8', 4, [1089, 1095, 1101, 1100], 7),   # Carcinised (req 32, armor per refracted idol implicit)
    ('T4', 4, [1089, 1095, 1101, 1100], 3),
    ('T8', 0, [1089, 1095, 1101, 1100], 7),   # Twisted (plain)
]


def tabs(level=55):
    """(category, color, tab name, items, report) for every tab of this plan."""
    out = []
    for name, plan in PLANS.items():
        items, totals, log = build(plan)
        out.append((CATEGORY, COLOR, name, items, describe_set(name, items, totals, log, level)))
    altars = [altar(sub, af, tier) for tag, sub, af, tier in ALTARS]
    report = '\n'.join('altar %s req %d: %s' % (L.item_title(db, it), L.item_req(db, it),
                       ' | '.join('T%d %s' % (t + 1, db.affix_text(a, t)[:40]) for a, t, _ in it['affixes'])) for it in altars)
    out.append((CATEGORY, COLOR, 'VK Idols + Altars', idols(IDOLS) + altars, report))
    return out


if __name__ == '__main__':
    level = int(sys.argv[sys.argv.index('--level') + 1]) if '--level' in sys.argv else 55
    made = tabs(level)
    for _, _, _, _, report in made:
        print(report)
    if '--write' in sys.argv:
        print(write_tabs([(n, i) for _, _, n, i, _ in made], CATEGORY, COLOR))
