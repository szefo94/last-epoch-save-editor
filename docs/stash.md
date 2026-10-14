# The stash

The stash of a cycle is `STASH_CYCLE_<cycle>_<n>` plus one file per tab.

## The stash file

| Field | Meaning |
|---|---|
| `tabsv2` | The tab file names, in order. `tabs` and `savedStashItems` are the old pre-tab format, empty now. |
| `categories` | Tab folders: `categoryId`, `displayName`, `iconId`, `colorId`, `displayOrder`, `folderPriority`, `dirty`. Category 0 is "General". |
| `gold`, `ancientBones` | Currencies. |
| `savedShards`, `savedResonances`, `materialsList`, `wovenEchoesList`, `keysList` | The crafting, materials, woven echo and key tabs; materials are item entries like gear but with their own base types. |
| `unlockedBlessings` | Blessing sub types the account has seen. |
| `factions` | Account-level faction ranks and reputation, Circle of Fortune lenses. |
| `monolithTimeline*`, `optionalChaptersCompleted`, `highestCorruption`, `savedQuests`, `dungeonCompletion` | Account-wide progress mirrors. |
| `soloChallengeCharacterId`, `soloChallengeStashName`, `stashType` | Solo challenge stash binding. |
| `keysTabUnlocked`, `wovenEchoesTabUnlocked`, `giftingTabUnlocked`, `stashTabsCreated`, `craftingIsLocked`, `viewed*Tooltip` | Flags. |
| `id`, `partitionKey`, `seqNo`, `_etag`, `version` | Bookkeeping shared by all save files. |

Solo Character Found characters cannot open the stash at all.

## Tab files

```json
{"displayOrder": 0, "tabId": 0, "categoryId": 0, "iconId": 1, "colorId": 10, "displayName": "1",
 "tabPriority": null, "ignoreFolderPriority": false, "savedItems": [...],
 "id": "STASH_CYCLE_8_0_TAB_0", "partitionKey": "...", "seqNo": 12, "_etag": null, "version": 0}
```

A tab is a 12 x 17 grid; items are entries like the character's but without `containerID`. New tabs
take the next number after the highest in `tabsv2` and must be registered there. The editor creates
them with `add_stash_tab`, which also sets `stashTabsCreated`. Tabs bought in game have been seen to
coexist with editor-made ones without renumbering.

## What the editor writes

* Item edits in a tab change only that tab file.
* New tabs and categories change the stash file as well, so the editor saves immediately when it creates them and asks for pending changes to be saved first.
* Gold is edited in the stash file.
