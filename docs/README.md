# Documentation

A walk through Last Epoch's offline save system as this editor understands it, and through the
editor itself. Everything here was read from real save files of a Steam Deck installation (game
version 1.5, cycle 8); field names are quoted as they appear in the files.

| Page | Contents |
|---|---|
| [save-files.md](save-files.md) | The Saves folder, file naming, the `EPOCH` + JSON format, backups and Steam Cloud |
| [character.md](character.md) | A character file: identity, level, masteries, passive and skill trees, item containers, quests, campaign and monolith progress, blessings, factions, flags |
| [items.md](items.md) | The item byte array: bases, rarity, affixes, tiers, rolls, uniques, legendaries, level requirement, idols, altars, blessings |
| [stash.md](stash.md) | The stash file, categories, tab files, gold and materials |
| [builds.md](builds.md) | Maxroll guide and planner import, the guide JSON, tree data, creating characters and applying presets |
| [architecture.md](architecture.md) | The editor's modules, data files, build and packaging |

## How the pieces depend on each other

```mermaid
graph TD
    subgraph Game files
        G[Epoch_Local_Global_Data_Beta<br/>lists the stashes]
        C[1CHARACTERSLOT_BETA_n<br/>one file per character]
        S[STASH_CYCLE_8_0<br/>stash: gold, categories, tab list]
        T[STASH_CYCLE_8_0_TAB_n<br/>one file per stash tab]
        G --> S
        S --> T
    end

    subgraph Editor
        H[le_hero.py<br/>Hero Editor window]
        E[le_editor2.py<br/>browser layout, item widgets]
        L[lesave.py<br/>save and item library]
        TH[theme.py]
        IM[import_maxroll.py]
        PL[plans/*.py<br/>scripted stash sets]
        FI[fetch_icons.py]
        B[build.py<br/>pyz, binary, launcher]
        H --> E
        H --> L
        H --> TH
        E --> L
        E --> TH
        E --> IM
        E --> PL
        PL --> L
        IM --> L
        B --> H
    end

    subgraph Data
        D1[data/bases.json<br/>data/affixes.json<br/>data/uniques.json]
        D2[data/trees.json<br/>data/skills.json]
        D3[data/guides/*.json]
        D4[data/icons/*.png<br/>data/icons.json]
    end

    subgraph Outside
        MR[maxroll.gg guides<br/>planners.maxroll.gg API]
        LEP[LastEpochPlanner repo<br/>bases, affixes, uniques, trees]
        LET[lastepochtools.com<br/>item sprite sheet]
    end

    L --> C
    L --> S
    L --> T
    L --> D1
    L --> D2
    L --> D3
    L --> D4
    IM --> MR
    IM --> D3
    FI --> LET
    FI --> D4
    LEP -.-> D1
    LEP -.-> D2
```

Solid arrows are code reading or writing something; dotted arrows are where the data was taken
from once and converted.

## How a character's state is decided

The game does not keep one "progress" number. What you see in the character list and in game is
the sum of several independent records in the character file:

```mermaid
graph LR
    LV[level, currentExp] --> PP[passive points = level - 1 + quest rewards]
    Q[savedQuests<br/>quest records with completed objectives] --> PP
    Q --> IDG[idol grid size]
    Q --> CAMP[campaign position]
    W[unlockedWaypointScenes] --> CAMP
    SC[sceneProgresses, oneTimeEvents] --> CAMP
    M[chosenMastery + EpochMasteryUnlock event] --> TREE[which passive and skill nodes are usable]
    PT[savedCharacterTree] --> TREE
    ST[savedSkillTrees, abilityBar] --> SKILLS[specialized skills and bar]
    IT[savedItems by containerID] --> GEAR[worn gear, idols, inventory, blessings]
    MO[monolithRuns, timeline* lists] --> END[monolith unlocks and corruption]
    F[factions] --> END
```

Each of these is described field by field in [character.md](character.md).
