# The character file

`1CHARACTERSLOT_BETA_<n>` holds everything about one character. The fields below are grouped by
what they decide; names are the JSON keys.

## Identity

| Field | Meaning |
|---|---|
| `characterName` | Display name. Letters only is safest; the editor's generated names are camel case without spaces. |
| `characterClass` | 0 Primalist, 1 Mage, 2 Sentinel, 3 Acolyte, 4 Rogue. |
| `chosenMastery` | 1, 2 or 3 in the order of the class's masteries (Sentinel: Void Knight, Forge Guard, Paladin). 0 before a mastery is chosen. |
| `originalMastery` | The mastery first picked, kept when the mastery is changed later. |
| `id`, `slot` | The slot number as a string (and as a number in older files). Must match the file name. |
| `cycle` | The cycle the character belongs to; decides which character list shows it. |
| `hardcore`, `masochist`, `soloChallenge`, `soloCharacterChallenge` | Hardcore, Masochist, Solo Account Found and Solo Character Found flags. |
| `createdAt`, `lastPlayed`, `totalPlaytimePlayed`, `died`, `deaths` | Bookkeeping. |

## Level and experience

`level` and `currentExp` (experience inside the current level). `levelTracking` keeps, per level
reached, a completion date, playtime and a large `snapshot` string; it is purely a record and may be
empty. The passive point budget is `level - 1` plus the quest rewards (14 on a finished campaign, so 113 at level 100).

## Passive tree

```json
"savedCharacterTree": {"treeID": "", "version": 12, "nodeIDs": [0, 49, 2], "nodePoints": [8, 8, 5],
                       "unspentPoints": 0, "nodesTaken": null}
```

`nodeIDs[i]` has `nodePoints[i]` points. The ids are the numbers in the planner data's node names
(`Sentinel-54` is id 54, "Void Well"). The three mastery branches share the class's id space; every
branch can be entered up to its lock, nodes past it need `chosenMastery`. `unspentPoints` is what the
game shows as available; it recomputes the total from level and quests on load and refunds anything
over budget. `savedWeaverTree` has the same shape for the Weaver tree.

## Skills

```json
"savedSkillTrees": [{"treeID": "va53st", "slotNumber": 3, "xp": 5700000, "version": 2,
                     "nodeIDs": [12, 14], "nodePoints": [3, 4], "unspentPoints": 0,
                     "nodesTaken": null, "abilityXP": 0.0}]
```

One entry per specialized skill. `treeID` is the skill's tree id (Warpath `va53st`, Devouring Orb
`do5vr`, Anomaly `an0my`; the map is in `data/skills.json`). `slotNumber` is the specialization slot
0 to 4, `xp` the skill experience (5,700,000 is level 20). A level 20 skill owns 20 points; the
bonus points from "+X to skill" gear only exist after the character is loaded, so a saved tree with
more than 20 points is reset by the game. The editor therefore writes at most the first 20 picks.

`abilityBar` lists five tree ids, the skills on the bar (unspecialized skills use their tree id too).
The transform bars (`werebearAbilityBar` and friends) are the same for shapeshift forms.

## Items

All items of a character are in one list, `savedItems`; `containerID` says where each one is:

| Container | Holds | Grid |
|---|---|---|
| 1 | Inventory | 12 x 8 cells |
| 2 Helmet, 3 Body, 4 Weapon, 5 Off-hand, 6 Gloves, 7 Belt, 8 Boots, 9 Ring 1, 10 Ring 2, 11 Amulet, 12 Relic | Worn gear | one item each, position 0,0 |
| 29 | Idols | class-specific grid, 5 x 5 for a Sentinel with all idol quests done |
| 32 | A second bag seen on long-played characters (materials and spare gear) | |
| 33 to 45 | Equipped blessings, one container per timeline (33 to 39 and 43 to 45 on a character with all ten) | |
| 82 to 85, 124 to 128 | Weapon swap set and further bags | |
| 123 | The equipped idol altar | |

Every entry is `{"itemData": null, "data": [...], "inventoryPosition": {"x": 0, "y": 0}, "quantity": 1,
"containerID": 1, "formatVersion": 2}`; the `data` bytes are explained in [items.md](items.md).
Items occupy `width x height` cells from their position; the editor places new items in the first
free spot and refuses when nothing fits.

## Campaign progress

There is no "act completed" flag. Progress is the union of:

| Field | Meaning |
|---|---|
| `savedQuests` | One record per quest met: `questID`, `questStepID`, `state`, `completeObjectives`, `failedObjectives`, `objectiveProgress`, `trackStatus`. A finished campaign character carries about 87 records. `state` is 0 for finished and unfinished quests alike; completion is the step and objective lists. |
| `unlockedWaypointScenes` | Scene codes of unlocked waypoints (`Z22`, `A10`, `EoT`, `MonolithHub`, ...). |
| `sceneProgresses` | Per scene a packed `savedProgress` number (doors opened, chests looted). |
| `oneTimeEvents` | Named events that already happened (`EpochMasteryUnlock`, `Reached EoT`, cinematics seen). The mastery unlock event is what lets the character pick a mastery. |
| `openedOneShotCaches`, `portalUnlocked`, `reachedTown`, `lastVisitedTownScene`, `focusedQuest` | Smaller records. |
| `omenWindowMinCampaignLevel`, `championMinLevel` | Thresholds the game tracks for late-campaign events. |

Quest rewards (passive points, idol slots) are granted when the quest record completes, which is why a
character with a copied quest list has the full idol grid and all passive points.

## Monolith, dungeons, arena

`monolithRuns` (one per timeline and difficulty with the echo web, stability and mods),
`timelineCompletion`, `timelineDifficultyCompletion`, `timelineDifficultyUnlocks` (one entry per
timeline with a `progress` pair), `maxCorruption`, `monolithEchoesConquered`, `monolithTimelinesConquered`,
`savedMonolithQuests`, the `currentMonolithRun*` fields, `dungeonCompletion`, `arenaTiersCompleted`,
`maxWave`, `currentArenaRunWaves`.

## Blessings

`openBlessings` is the pool of blessings discovered (sub type plus three roll bytes). The equipped
ones are items of base type 34 in the containers 33 and up, one per timeline.

## Factions and other systems

`factions` is keyed by faction id: 0 Circle of Fortune (with lens slots in `factionSpecific`), 2 and 3
the Merchant's Guild side; each has `isMember`, `rank`, `reputation`, `favor`. `nemesisData`,
`timeBeastData`, `rageOfMorditasData` and the `*Tracking` fields hold endgame system state;
`soulEmbers`, `lanternLuminance` belong to dungeons.

## Tutorial and UI flags

`closed*Tooltip`, `clickedUnlockMasteriesButton`, `moveButtonBehaviour`, `minionAIToggle`. Copying them
from a played character avoids the tutorial popups on a created one.

## What the editor does with all this

* Editing items touches only `savedItems`.
* "Apply build" replaces `savedCharacterTree`, `savedSkillTrees`, `abilityBar`, `chosenMastery` and the gear containers.
* "New character" copies every progress record from a template character, resets the bookkeeping, and sets identity and build; see [builds.md](builds.md).
