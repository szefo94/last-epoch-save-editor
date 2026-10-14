# Builds: Maxroll import, character creation, applying presets

## Sources

* **Guide pages** (`https://maxroll.gg/last-epoch/build-guides/<slug>`) embed their planner JSON in the HTML.
* **Planner links** (`https://maxroll.gg/last-epoch/planner/<id>`) are fetched from `https://planners.maxroll.gg/profiles/le/<id>`, which returns the same JSON with `data` as a string.

`import_maxroll.load_build(url)` handles both and returns the guide dict; `import_maxroll.py <url>`
on the command line stores it as `data/guides/<slug>.json`.

## The guide JSON

```
name, title, source, planner, date, class, uniques (ids mentioned on the page)
stages: one per planner profile (character preset)
  name, levels [from, to], level
  items:  [{slot, base, sub, affixes [[id, tier], ...], unique?}]
  altar:  the idol altar item, if any
  idols:  [{base, sub, affixes}]
  class, mastery
  passives:     node ids in the order the points were spent
  weaver:       same for the Weaver tree
  skillTrees:   {treeId: [node ids in order]}
  activeSkills, specializedSkills: skill keys (Warpath, DevouringOrb, ...)
  blessings:    [{sub, roll} or null] by timeline
  quests:       quest ids the preset assumes done
```

Planner slot names: head, body, hands, waist, feet, finger1, finger2, neck, relic, weapon, offhand, altar.

## Tree data

`data/trees.json` is a compact copy of the LastEpochPlanner project's `TreeData/1_4/tree_<class>.json`:
per class its masteries, base stats (health, mana, attributes per level), the passive nodes
(`maxPoints`, mastery, requirement, links, per-point stats) and the skill tree nodes per tree id.
`data/skills.json` maps planner skill keys to tree ids. Node ids are the numeric suffix of the planner's
node names, which match the save file.

The data is from game version 1.4; skills added later (Radiant Lance, Summon Elemental) are mapped by
elimination from the planner's own tree ids and their allocation is written unchecked.

## Creating a character (`lesave.new_character`)

1. Copy a **template** character and keep its progress fields: quests, waypoints, scene progress, events, monolith and timeline state, factions, blessing pool, tutorial flags (`PROGRESS_FIELDS`).
2. Reset bookkeeping: deaths, playtime, level history, experience, arena and monolith run state (`RESET_FIELDS`).
3. Set identity: name, class, mastery, level, slot id, mode flags (Normal, Solo Account Found, Solo Character Found, hardcore).
4. Passives: the preset's point history up to the budget `level - 1 + 14`, each node capped at its maximum; the rest unspent.
5. Skills: one tree per specialized skill, the first 20 picks, experience at level 20, slot order as in the preset; the ability bar from the active skills, blanks filled with the other specialized skills.
6. Items: gear into the slot containers, the altar into container 123, idols into the inventory (idol grids differ per class), blessings into the template's blessing containers.

The result is a new slot file that never overwrites an existing one. Tested in game: the character
appears in the cycle list with its passives, skills and gear; the only failure found was skill trees
with more than 20 points, which is why they are capped.

## Applying a preset to an existing character (`lesave.apply_build`)

Same planning, different placement: the character keeps its name, level and progress; the passive
budget follows its level; the mastery switches when asked; gear can be worn (the worn items move to
the inventory), put in the inventory or a stash tab, or skipped; idols likewise; blessings replace the
equipped ones. The preset must be for the character's class. Nothing is written until Save changes.

## Importing all presets as stash tabs (`lesave.import_build_tabs`)

Creates a category `imported from "<build>"` with one tab per preset holding its gear, idols and
altar with max rolls, and a last tab with every unique the page mentions.

## Scripted plans

`plans/*.py` are hand-written sets (for example the Warpath Void Knight variants) with a resistance
budget solver and a single crit package; each exposes `tabs(level)` and the editor lists them on the
Add items page.
