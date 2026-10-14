# Last Epoch Save Editor

A desktop editor for **Last Epoch offline (single player) save files**, written in Python with Tkinter.
Built and tested on a Steam Deck, it runs anywhere Python 3 with Tk is available and ships as a single
file for Linux.

![Last Epoch Save Editor](docs/screenshot.png)

## What it does

- **Browse** the stash (categories, tabs, items) and the character (equipped slots on a paper doll,
  idols, inventory, blessings) with the real item art.
- **Edit any item**: base, up to four affixes with tier and roll, every implicit and unique mod roll,
  copy or move items between inventory, stash tabs and characters, delete, max rolls. Rarity is shown
  the way the game decides it (Magic, Rare, Exalted, Unique, Set, Legendary).
- **Create items**: uniques with max rolls, custom items, leveling kits, legendary sets, and complete
  stash sets from scripted build plans.
- **Import Maxroll builds** (guide pages or planner links): one stash tab per character preset with its
  gear, idols, altar and blessings; apply a preset to an existing character (passives, skill trees,
  ability bar, gear, idols, blessings); or create a new level 100 character from a preset with the
  campaign completed, in Normal, Solo Account Found or Solo Character Found mode.
- **Character stats overview**: resistances, health, mana, attributes, crit, speed, damage and leech
  summed from everything the character carries, each stat expandable to its sources.
- **Safety**: every write goes through a timestamped backup folder, the editor refuses to write while
  the game runs, and a Send to game step copies edited files into the game's folder with a backup.

## Running

```
python3 le_editor2.py            # opens the game's Saves folder when it finds it
python3 build.py --install       # builds dist/LE_Save_Editor.pyz and a desktop launcher (Linux)
python3 build.py --binary        # PyInstaller one-file binary (needs PyInstaller in a venv)
```

The game's Saves folder is found automatically on Steam Deck / Proton (`compatdata/899770`) and on
Windows (`AppData/LocalLow/Eleventh Hour Games/Last Epoch/Saves`). Close Last Epoch before saving.

Item pictures are not in the repository: run `python3 fetch_icons.py` once (needs Pillow, or `--tk`)
to cut them from the lastepochtools.com sprite sheet into `data/icons/`.

## Command line

```
python3 lesave.py show <save file>              # list the items in a character or stash tab
python3 lesave.py kit <character> --level 40    # add a leveling gear set
python3 lesave.py backup                        # back up the game folder
python3 import_maxroll.py <maxroll guide or planner URL>
python3 plans/void_knight_endgame.py --write    # a scripted stash set
```

## Save format notes

Save files are the text `EPOCH` followed by JSON. Items are byte arrays in `savedItems`; the layout,
level requirement formula, stash categories and tabs, passive and skill trees, quest and progress fields
are documented in `lesave.py`. Game data (bases, affixes, uniques, passive and skill trees) comes from
the open-source [LastEpochPlanner](https://github.com/Musholic/LastEpochPlanner) project.

## Disclaimer

For offline characters only. Last Epoch is a trademark of Eleventh Hour Games; this project is not
affiliated with them. Use at your own risk and keep the backups.
