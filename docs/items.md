# Items

An item is a byte array in `data`. The names of bases, affixes and uniques come from
`data/bases.json`, `data/affixes.json` and `data/uniques.json`.

## Layout

```
version 6 (current):
  [6, id1, id2, id3, id4, base, sub, rarity, flag, imp1, imp2, imp3, ...]
version 2 (old files):
  [2, base, sub, rarity, flag, imp1, imp2, imp3, ...]
```

| Bytes | Meaning |
|---|---|
| `id1..id4` | A per-item id the game assigns; the editor randomises it for copies. |
| `base`, `sub` | Base type (0 helmet, 1 body armour, 2 belt, 3 boots, 4 gloves, 5 to 16 weapons, 17 quiver, 18 shield, 19 catalyst, 20 amulet, 21 ring, 22 relic, 25 to 33 idols, 34 blessing, 41 idol altar) and sub type (the base item within the type, e.g. Winged Blade). |
| `rarity` | See below. |
| `flag` | Always 0 in files seen so far. |
| `imp1..imp3` | Roll of each implicit, 0 to 255 (255 is the top of the range). |

Then for normal gear:

```
  forgingPotential, affixCount, then per affix: (tier << 4) | (affixId >> 8), affixId & 255, roll
```

and for uniques, sets and legendaries (`rarity` 7, 8 or 9):

```
  uniqueId (2 bytes), 8 roll bytes, legendaryAffixCount, then per affix the same 3 bytes
```

The 8 roll bytes map onto the unique's rolling mods through `rollIds` in `uniques.json`
(`[None, 0, 1, 2]` means the first mod is fixed and the next three use roll bytes 0 to 2).

## Rarity

The byte for normal gear is the affix count (1 to 4). The game shows **Exalted** for any gear with a
tier 6 or higher affix, **Rare** for 3 to 4 affixes, **Magic** for 1 to 2. Idols and altars never show
as exalted. 7 is **Unique**, 8 **Set**, 9 **Legendary** (a unique with extra affixes). The editor
derives the shown rarity from the content (`lesave.rarity_name`) and writes the affix count.

## Affixes and tiers

`affixId` indexes `affixes.json`; tiers are stored 0-based (byte 0 is T1). The game data defines up to
T8 (index 7); the field is 4 bits, and tiers up to 15 are accepted by the game, which is what the
"freaky" items relied on. Findings from testing on a live character:

* any affix works on any item type, including skill affixes of other classes' skills;
* the same affix may appear several times and stacks;
* more than four affixes on normal gear makes the game strip the item to white;
* legendaries accept four affixes at any tier and keep the unique's level requirement.

The roll byte is the position in the affix's range (`+(190-240) Mana` at 255 is 240).

## Level requirement

For normal gear the requirement is the highest of: the base's own level, every affix's minimum
level, and the tier formula `sum(TIER_REQ[tier]) + 2 * max - 10` with `TIER_REQ = [1, 3, 6, 10, 14, 15, 16]`
(four T8 affixes give 86, four T4 give 50). Uniques and legendaries use the unique's level, which is
why high-tier legendaries can be worn early.

## Special item kinds

* **Idols** (base 25 to 33) have no level requirement; small ones are universal, large ones class-specific (Solar, Rahyeh, Iron Omen for Sentinel). Their affixes have one or a few tiers.
* **Idol altars** (base 41) are gear-like with altar affixes 1088 to 1109. The game also gives them a corrupted affix whose format is unknown, so editor-made altars lack it.
* **Blessings** (base 34) have no affixes, only the implicit roll bytes.
* Materials, keys and the like are other base types without the gear layout; the editor lists them as "Other" and can only delete or move them.

## Icons

`data/icons.json` maps `"<base>_<sub>"` and unique ids to sprite names; `data/icons/<sprite>.png` is
the art, cut from the lastepochtools.com sprite sheet by `fetch_icons.py` (41.5 pixels per inventory cell).
