# Save files

## Where they are

| Platform | Folder |
|---|---|
| Steam Deck / Linux (Proton) | `~/.local/share/Steam/steamapps/compatdata/899770/pfx/drive_c/users/steamuser/AppData/LocalLow/Eleventh Hour Games/Last Epoch/Saves` |
| Windows | `%USERPROFILE%\AppData\LocalLow\Eleventh Hour Games\Last Epoch\Saves` |

`lesave.find_game_folder()` tries these in order. The editor opens the first one that exists.

## What is in the folder

| File | Role |
|---|---|
| `1CHARACTERSLOT_BETA_<n>` | One character. `n` is the slot number; the file's `id` field is the same number as a string. |
| `STASH_CYCLE_<cycle>_<n>` | A stash for a cycle (season). `STASH_0` is the legacy stash, `STASH_CYCLE_2_2_1` an older cycle, `STASH_CYCLE_8_0` the current one. |
| `STASH_CYCLE_8_0_TAB_<n>` | One stash tab. Listed in the stash file's `tabsv2`. |
| `Epoch_Local_Global_Data_Beta` | Lists the stash files (`stashes`). Characters are not listed anywhere; the game scans for slot files. |
| `*.bak` | The game's own previous copies. |
| `steam_autocloud.vdf` | Steam Cloud sync description. |

A character shows in the game's list for the cycle its `cycle` field names. All characters made by
this editor get the cycle of the template character (8 at the time of writing).

## Format

Every file is the five letters `EPOCH` followed by one JSON document with no whitespace. That is all:
no compression, no checksum, no encryption. The editor reads it with `SaveFile(path)`, keeps the
parsed document in `.json`, and writes it back with `save()`, which first copies the original into
`backups/<timestamp>_edit/`.

The game rewrites a file whenever it saves (zone change, logout, autosave), and it keeps the
previous version as `.bak`. Files written by the editor are picked up on the next load; the
character select screen reads the slot files when it opens, so the game must be closed while
editing, and the editor refuses to save while a Last Epoch process is running.

## Steam Cloud

Offline characters are synced by Steam Cloud like any other file in the folder. Edited files have
newer timestamps and win the sync; nothing in this project turns Cloud off. If Steam ever shows a
conflict dialog, pick the local copy.

## Backups made by the editor

| Folder suffix | When |
|---|---|
| `_edit` | before every file the editor overwrites |
| `_game` | the game's files replaced by "Send to game" |
| `_full` | a snapshot of a whole folder on request |
| `_regen_skills`, `_full_before_tierlist` | labelled snapshots from scripted batch jobs |

Backups live in `backups/` next to the editor (next to the `.pyz` or binary for packaged builds).
Restoring is copying the file back; the editor has no restore button yet.
