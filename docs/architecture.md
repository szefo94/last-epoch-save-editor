# Architecture

## Modules

| Module | Role |
|---|---|
| `lesave.py` | The library: file access (`SaveFile`, `find_game_folder`, backups, deploy), game data (`Database`, `Icons`), item encode/decode and creation, level requirement, rarity, stash categories and tabs, guide sets, character stats, character creation and preset application. Also a small command line (`show`, `kit`, `guide`, `backup`, `deploy`). |
| `le_hero.py` | The main window: `HeroEditor` with the Character, Skills, Items, Quests, Monolith and Misc tabs, drag and drop between grids, the spawn dialog; reuses the item widgets of `le_editor2`. |
| `le_editor2.py` | The browser layout: `App` (toolbar, Stash and Character pages, scrollable right notebook), `ItemForm` (overview and editor), `AddPage` (unique, custom item, guide sets, plans, leveling kit), `StatsPage`, `GridView`, `SlotView`, `IconCache`, the New character and Apply build dialogs. |
| `theme.py` | Colours, fonts and ttk styles in the game's look; rounded buttons are image elements; the glow styles for the Save button. |
| `import_maxroll.py` | Maxroll guide and planner download and conversion to the guide JSON. |
| `plans/` | Scripted stash sets; `vk_common.py` holds the shared affix ids, resistance budget and stash writer. |
| `fetch_icons.py` | Downloads the lastepochtools.com sprite sheet and database bundle and cuts the item art. |
| `build.py` | Builds `dist/LE_Save_Editor.pyz` (zipapp), optionally a PyInstaller binary, and installs a desktop launcher. |

`lesave` reads its data files through `read_text` / `read_bytes`, which look inside the `.pyz`
archive when the editor runs packaged; backups then go next to the archive.

## Data files

| File | From |
|---|---|
| `data/bases.json`, `data/affixes.json`, `data/uniques.json` | LastEpochPlanner project (game data extraction) |
| `data/trees.json`, `data/skills.json` | LastEpochPlanner `TreeData/1_4`, compacted |
| `data/guides/*.json` | `import_maxroll.py` |
| `data/icons/*.png`, `data/icons.json` | `fetch_icons.py` (not in the repository) |

## Safety model

* Every write goes through `SaveFile.save()` or `write_new_character()`; the former backs up first, the latter never overwrites.
* Writes to the game's own folder are refused while a `Last Epoch` process exists.
* The classic "work on a copy, then Send to game" flow still exists: the editor can open any folder and copy the edited files into the game folder with a backup of the originals.

## Packaging

```
python3 build.py             # dist/LE_Hero_Editor.pyz, runs with the system python3 + tkinter
python3 build.py --binary    # PyInstaller one-file binary (PyInstaller from a venv)
python3 build.py --install   # launchers "LE Hero Editor" and "LE Hero Editor (browser layout)"
```

The packaged build starts the Hero Editor; `--browser` starts the browser layout.

The pyz is about 5 MB with the icons; the binary about 25 MB.
