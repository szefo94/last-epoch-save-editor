#!/usr/bin/env python3
"""Last Epoch save editor. Run: ./le_editor2.py [saves folder]

Left half: a Stash page (categories > tabs > items, with the tab's grid) and a Character page (equipped
slots, idols, inventory and other containers, with paper doll and grids). Right half, scrollable: the
Item page (overview of the clicked item and a form for its base, affixes, tiers and every roll, copy /
move / delete) and the Add items page (uniques, custom items, guide sets, build plans, leveling kit).
"""
import datetime
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import lesave as L
import plans as P
import theme

DEFAULT_FOLDER = L.find_game_folder() or os.path.join(L.HERE, 'Saves', 'Saves')
RARITY_COLORS = theme.RARITY_COLORS
CELL = 17   # grid cell in pixels; item art is drawn at 0.4 of its native 41.5 px per cell
IDOLS, BLESSINGS = 29, range(33, 39)


def container_name(cid):
    if cid in L.CONTAINERS:
        return L.CONTAINERS[cid]
    if cid == IDOLS:
        return 'Idols'
    if cid in BLESSINGS:
        return 'Blessings'
    return 'Container %s' % cid


class IconCache:
    """Tk images of the item art in three sizes: 'full' (native), 'grid' (0.4x) and 'row' (about 22 px)."""

    def __init__(self):
        self.icons = L.Icons()
        self.cache = {}

    def get(self, item, mode='full'):
        sprite = self.icons.sprite(item)
        if not sprite:
            return None
        key = (sprite, mode)
        if key not in self.cache:
            png = self.icons.png(sprite)
            if not png:
                self.cache[key] = None
            else:
                img = tk.PhotoImage(data=png)
                if mode == 'grid':
                    img = img.zoom(2).subsample(5)
                elif mode == 'row':
                    img = img.subsample(max(1, -(-img.height() // 22)))
                self.cache[key] = img
        return self.cache[key]


class GridView(tk.Canvas):
    """One box per item on an inventory grid, with the item art; clicking a box calls on_pick(index)."""

    def __init__(self, parent, db, icons, on_pick):
        super().__init__(parent, background=theme.BG, highlightthickness=0)
        self.db, self.icons, self.on_pick = db, icons, on_pick
        self.bind('<Button-1>', self.click)

    def draw(self, save, container=None, selected=(), size=None):
        self.delete('all')
        if save is None:
            self.configure(width=12 * CELL + 2, height=2 * CELL)
            return
        w, h = size or (L.INVENTORY_SIZE if save.is_character else L.STASH_TAB_SIZE)
        self.configure(width=w * CELL + 2, height=h * CELL + 2)
        for x in range(w + 1):
            self.create_line(x * CELL + 1, 1, x * CELL + 1, h * CELL + 1, fill=theme.BORDER)
        for y in range(h + 1):
            self.create_line(1, y * CELL + 1, w * CELL + 1, y * CELL + 1, fill=theme.BORDER)
        for i, e in enumerate(save.items):
            if save.is_character and e.get('containerID') != container:
                continue
            item = L.decode(e['data'])
            iw, ih = self.db.size(item['base'], item['sub']) if item else (1, 1)
            x0, y0 = e['inventoryPosition']['x'] * CELL + 2, e['inventoryPosition']['y'] * CELL + 2
            color = RARITY_COLORS.get(L.rarity_name(item), '#999') if item else '#777'
            sel = i in selected
            tag = ('idx%d' % i,)
            self.create_rectangle(x0, y0, x0 + iw * CELL - 1, y0 + ih * CELL - 1, fill=color,
                                  outline=theme.GOLD_LIGHT if sel else theme.BG, width=2 if sel else 1, tags=tag)
            img = self.icons.get(item, 'grid')
            if img:
                self.create_image(x0 + iw * CELL // 2, y0 + ih * CELL // 2, image=img, tags=tag)

    def click(self, event):
        hit = [t for t in self.gettags('current') if t.startswith('idx')]
        if hit:
            self.on_pick(int(hit[0][3:]))


# Paper doll: slot container id -> (x, y, w, h) in cells.
SLOT_LAYOUT = {2: (3, 0, 2, 2), 11: (5, 0, 1, 1), 4: (0, 1, 2, 4), 3: (3, 2, 2, 3), 5: (6, 1, 2, 3),
               6: (0, 5, 2, 2), 9: (2, 5, 1, 1), 7: (3, 5, 2, 1), 10: (5, 5, 1, 1), 8: (6, 5, 2, 2), 12: (3, 6, 2, 3)}
SLOT_SIZE = (8, 9)
SLOT_SHORT = {9: 'R1', 10: 'R2', 11: 'Amu', 5: 'Off', 12: 'Relic'}


class SlotView(tk.Canvas):
    """The wielded items drawn on a paper doll; clicking an item calls on_pick(index)."""

    def __init__(self, parent, db, icons, on_pick):
        super().__init__(parent, background=theme.BG, highlightthickness=0,
                         width=SLOT_SIZE[0] * CELL + 2, height=SLOT_SIZE[1] * CELL + 2)
        self.db, self.icons, self.on_pick = db, icons, on_pick
        self.bind('<Button-1>', self.click)

    def draw(self, save, selected=()):
        self.delete('all')
        worn = {}
        if save is not None:
            worn = {e.get('containerID'): i for i, e in enumerate(save.items) if e.get('containerID') in SLOT_LAYOUT}
        for cid, (x, y, w, h) in SLOT_LAYOUT.items():
            x0, y0 = x * CELL + 2, y * CELL + 2
            self.create_rectangle(x0, y0, x0 + w * CELL - 1, y0 + h * CELL - 1, fill=theme.PANEL, outline=theme.BORDER)
            if cid not in worn:
                self.create_text(x0 + w * CELL // 2, y0 + h * CELL // 2, text=SLOT_SHORT.get(cid, L.CONTAINERS[cid]),
                                 fill=theme.TEXT_DIM, font=('DejaVu Sans', 7))
                continue
            i = worn[cid]
            item = L.decode(save.items[i]['data'])
            sel = i in selected
            tag = ('idx%d' % i,)
            color = RARITY_COLORS.get(L.rarity_name(item), '#999') if item else '#777'
            self.create_rectangle(x0, y0, x0 + w * CELL - 1, y0 + h * CELL - 1, fill=color,
                                  outline=theme.GOLD_LIGHT if sel else theme.BG, width=2 if sel else 1, tags=tag)
            img = self.icons.get(item, 'grid')
            if img:
                self.create_image(x0 + w * CELL // 2, y0 + h * CELL // 2, image=img, tags=tag)

    def click(self, event):
        hit = [t for t in self.gettags('current') if t.startswith('idx')]
        if hit:
            self.on_pick(int(hit[0][3:]))


def idol_grid_size(db, save):
    """Cells of the idol grid: at least 5 x 5, grown to fit whatever is placed."""
    w = h = 5
    if save is not None:
        for e in save.items:
            if e.get('containerID') == IDOLS:
                item = L.decode(e['data'])
                iw, ih = db.size(item['base'], item['sub']) if item else (1, 1)
                w, h = max(w, e['inventoryPosition']['x'] + iw), max(h, e['inventoryPosition']['y'] + ih)
    return w, h


class ItemForm(ttk.Frame):
    """Overview plus editor for one item of one save file."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app, self.db = app, app.db
        self.save = self.index = self.item = None
        self.all_affixes = [self.db.affix_label(a) for a, t in sorted(self.db.affixes) if t == 0]
        top = ttk.Frame(self)
        top.pack(fill='x')
        self.picture = tk.Label(top, background=theme.BG, width=90, height=170)
        self.picture.pack(side='left', padx=(0, 8))
        titles = ttk.Frame(top)
        titles.pack(side='left', fill='both', expand=True)
        self.head = ttk.Label(titles, style='Head.TLabel', text='Click an item on the left', wraplength=300, justify='left')
        self.head.pack(anchor='w')
        self.where = ttk.Label(titles, style='Dim.TLabel', wraplength=320, justify='left')
        self.where.pack(anchor='w')
        self.text = tk.Text(self, height=12, wrap='word', state='disabled')
        self.text.pack(fill='both', expand=True, pady=6)

        f = ttk.LabelFrame(self, text='Edit', padding=8)
        f.pack(fill='x')
        ttk.Label(f, text='Base:').grid(row=0, column=0, sticky='w')
        self.base_box = ttk.Combobox(f, state='readonly', width=44)
        self.base_box.grid(row=0, column=1, columnspan=3, sticky='w', pady=2)
        self.base_box.bind('<<ComboboxSelected>>', lambda e: self.base_changed())
        ttk.Label(f, text='Affixes (type to filter), tier, roll %:').grid(row=1, columnspan=4, sticky='w', pady=(6, 2))
        self.rows = []
        for i in range(L.MAX_AFFIXES):
            box = ttk.Combobox(f, width=46, values=self.all_affixes)
            box.grid(row=2 + i, column=0, columnspan=2, sticky='w', pady=1)
            box.bind('<KeyRelease>', lambda e, b=box: self.filter(b))
            box.bind('<<ComboboxSelected>>', lambda e: self.preview())
            tier, roll = tk.IntVar(value=1), tk.IntVar(value=100)
            ttk.Spinbox(f, from_=1, to=L.MAX_TIER_NIBBLE + 1, textvariable=tier, width=3, command=self.preview).grid(row=2 + i, column=2)
            ttk.Spinbox(f, from_=0, to=100, textvariable=roll, width=4, command=self.preview).grid(row=2 + i, column=3)
            self.rows.append((box, tier, roll))
        r = 2 + L.MAX_AFFIXES
        ttk.Label(f, text='Base mods (implicits and unique mods), roll %:').grid(row=r, columnspan=4, sticky='w', pady=(8, 2))
        self.mods_frame = ttk.Frame(f)
        self.mods_frame.grid(row=r + 1, columnspan=4, sticky='ew')
        self.mod_rows = []      # (kind, index, IntVar): kind 'imp' -> implicits[index], 'uni' -> rolls[index]
        r += 1
        self.info = ttk.Label(f, wraplength=430, justify='left', style='Dim.TLabel')
        self.info.grid(row=r + 1, columnspan=4, sticky='w', pady=4)
        row = ttk.Frame(f)
        row.grid(row=r + 2, columnspan=4, sticky='w')
        ttk.Button(row, text='Apply', command=self.apply).pack(side='left')
        ttk.Button(row, text='Add copy', command=self.add_copy).pack(side='left', padx=3)
        ttk.Button(row, text='Max rolls', command=self.max_rolls).pack(side='left')
        ttk.Button(row, text='Revert', command=lambda: self.show(self.save, self.index)).pack(side='left', padx=3)
        row2 = ttk.Frame(f)
        row2.grid(row=r + 3, columnspan=4, sticky='w', pady=(4, 0))
        ttk.Button(row2, text='Copy to inventory', command=lambda: self.copy_to('inventory')).pack(side='left')
        ttk.Button(row2, text='Copy to stash tab', command=lambda: self.copy_to('stash')).pack(side='left', padx=3)
        ttk.Button(row2, text='Delete', command=self.delete).pack(side='left')
        self.set_enabled(False)

    def set_enabled(self, on):
        state = 'normal' if on else 'disabled'
        for child in self.winfo_children():
            if isinstance(child, ttk.LabelFrame):
                for w in child.winfo_children():
                    if isinstance(w, ttk.Frame) and w is not self.mods_frame:
                        for b in w.winfo_children():
                            b['state'] = state
                    elif isinstance(w, (ttk.Spinbox, ttk.Combobox)):
                        w['state'] = state if not isinstance(w, ttk.Combobox) or w is not self.base_box else ('readonly' if on else 'disabled')
        if not on:
            self.build_mod_rows(None)

    def build_mod_rows(self, item):
        """One roll spinbox per implicit of the base and per rolling mod of the unique."""
        for w in self.mods_frame.winfo_children():
            w.destroy()
        self.mod_rows = []
        if not item:
            return
        b = self.db.base(item['base'], item['sub']) or {}
        rows = [('imp', i, L.clean(t)) for i, t in enumerate(b.get('implicits', [])[:3])]
        if item['unique'] is not None and item['unique'] in self.db.uniques:
            u = self.db.uniques[item['unique']]
            for text, rid in zip(u['mods'], u.get('rollIds', [])):
                if rid is not None and rid < len(item['rolls']):
                    rows.append(('uni', rid, L.clean(text)))
        for kind, index, text in rows:
            source = item['implicits'] if kind == 'imp' else item['rolls']
            var = tk.IntVar(value=round(source[index] / 2.55) if index < len(source) else 100)
            row = len(self.mod_rows)
            ttk.Label(self.mods_frame, text=('* ' if kind == 'uni' else '  ') + text, wraplength=380, justify='left').grid(row=row, column=0, sticky='w')
            ttk.Spinbox(self.mods_frame, from_=0, to=100, textvariable=var, width=4, command=self.preview).grid(row=row, column=1, sticky='e', padx=(6, 0))
            self.mod_rows.append((kind, index, var))
        self.mods_frame.columnconfigure(0, weight=1)

    def filter(self, box):
        words = box.get().lower().split()
        box['values'] = [a for a in self.all_affixes if all(w in a.lower() for w in words)]

    def set_text(self, text):
        self.text['state'] = 'normal'
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', text)
        self.text['state'] = 'disabled'

    def show(self, save, index):
        """Loads item `index` of `save` into the overview and the form."""
        self.save, self.index = save, index
        entry = save.items[index]
        item = L.decode(entry['data'])
        self.item = item
        where = container_name(entry.get('containerID')) if save.is_character else save.json.get('displayName', save.name)
        pos = entry['inventoryPosition']
        self.where['text'] = '%s, %s at %d,%d' % (save.name, where, pos['x'], pos['y'])
        self.set_picture(item)
        if not item:
            self.head['text'] = L.item_title(self.db, None)
            self.set_text('Not an equipment item; it can only be deleted.')
            self.set_enabled(False)
            return
        self.set_enabled(True)
        self.head['text'] = '%s  [%s]' % (L.item_title(self.db, item), L.rarity_name(item))
        self.set_text(L.describe(self.db, item))
        self.set_picture(item)
        subs = self.db.subtypes(item['base'])
        self.base_box['values'] = ['%d: %s (level %d)' % (b['subTypeID'], b['name'], b['req']['level']) for b in subs]
        self.base_box.set(next((v for v in self.base_box['values'] if v.startswith('%d:' % item['sub'])), ''))
        self.base_box['state'] = 'readonly' if item['unique'] is None else 'disabled'
        for i, (box, tier, roll) in enumerate(self.rows):
            box['values'] = self.all_affixes
            if i < len(item['affixes']):
                a, t, r = item['affixes'][i]
                box.set(next((v for v in self.all_affixes if v.startswith('%d:' % a)), str(a)))
                tier.set(t + 1)
                roll.set(round(r / 2.55))
            else:
                box.set('')
                tier.set(1)
                roll.set(100)
        self.build_mod_rows(item)
        self.preview()

    def set_picture(self, item):
        img = self.app.icons.get(item, 'full') if item else None
        self.picture.configure(image=img or '', width=90 if img is None else img.width(),
                               height=170 if img is None else img.height())
        self.picture.image = img

    def build(self):
        """The edited item, or None (with the reason in the info label)."""
        if not self.item:
            self.app.say('Click an equipment item first.')
            return None
        item = dict(self.item)
        if self.base_box.get() and item['unique'] is None:
            item['sub'] = int(self.base_box.get().split(':')[0])
        affixes = []
        for box, tier, roll in self.rows:
            text = box.get().strip()
            if not text:
                continue
            try:
                a, t, r = int(text.split(':')[0]), int(tier.get()) - 1, int(roll.get())
            except (tk.TclError, ValueError):
                self.info['text'] = 'Pick affixes from the list; tier and roll must be numbers.'
                return None
            if (a, 0) not in self.db.affixes:
                self.info['text'] = 'Unknown affix %d.' % a
                return None
            affixes.append((a, min(max(t, 0), L.MAX_TIER_NIBBLE), min(max(round(r * 2.55), 0), 255)))
        implicits, rolls = list(self.item['implicits']), list(self.item['rolls'])
        try:
            for kind, index, var in self.mod_rows:
                value = min(max(round(int(var.get()) * 2.55), 0), 255)
                (implicits if kind == 'imp' else rolls)[index] = value
        except (tk.TclError, ValueError):
            self.info['text'] = 'Rolls must be numbers.'
            return None
        item['affixes'] = affixes
        item['implicits'] = implicits
        if item['unique'] is not None:
            item['rolls'] = rolls
        item['rarity'] = L.rarity_byte(item)
        return item

    def base_changed(self):
        item = self.build()
        if item is not None:
            self.item = item
            self.build_mod_rows(item)
            self.preview()

    def preview(self):
        item = self.build()
        if item is None:
            return
        self.set_picture(item)
        notes = ['%s [%s], requires level %d' % (L.item_title(self.db, item), L.rarity_name(item),
                                                 L.item_req(self.db, item))]
        for a, t, _ in item['affixes']:
            if (a, t) not in self.db.affixes:
                notes.append('affix %d has no T%d in the game data' % (a, t + 1))
        ids = [a for a, _, _ in item['affixes']]
        if len(set(ids)) != len(ids):
            notes.append('duplicate affixes stack (tested)')
        self.info['text'] = '; '.join(notes)

    def max_rolls(self):
        for _, _, roll in self.rows:
            roll.set(100)
        for _, _, var in self.mod_rows:
            var.set(100)
        self.preview()

    def apply(self):
        item = self.build()
        if item is None:
            return
        entry = self.save.items[self.index]
        entry['data'] = L.encode(dict(item, version=self.save.item_version()))
        self.app.changed(self.save, 'Changed %s.' % L.item_title(self.db, item))
        self.show(self.save, self.index)

    def add_copy(self):
        item = self.build()
        if item is None:
            return
        entry = self.save.items[self.index]
        container = entry.get('containerID', L.INVENTORY_ID)
        if self.save.is_character and container not in (L.INVENTORY_ID,):
            container = L.INVENTORY_ID    # worn or idol items are copied into the inventory
        self.app.put(self.save, [dict(item, uid=None)], container)

    def copy_to(self, where):
        item = self.build()
        if item is None:
            return
        if where == 'inventory':
            if not self.app.char:
                return self.app.say('No character loaded.')
            self.app.put(self.app.char, [dict(item, uid=None)], L.INVENTORY_ID)
        else:
            tab = self.app.current_tab()
            if tab is None:
                return self.app.say('Select a stash tab on the Stash page first.')
            self.app.put(tab, [dict(item, uid=None)])

    def delete(self):
        if self.save is None:
            return
        name = L.item_title(self.db, self.item)
        del self.save.items[self.index]
        self.save, self.index, self.item = None, None, None
        self.head['text'] = 'Click an item on the left'
        self.where['text'] = ''
        self.set_text('')
        self.set_picture(None)
        self.set_enabled(False)
        self.app.changed(None, 'Deleted %s.' % name)


class AddPage(ttk.Frame):
    """Creates items: uniques, custom items, leveling kits, guide sets and build plans. They go to
    the character inventory or to the stash tab selected on the Stash page."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app, self.db = app, app.db
        row = ttk.Frame(self)
        row.pack(fill='x')
        ttk.Label(row, text='Put new items into:').pack(side='left')
        self.target_box = ttk.Combobox(row, state='readonly', width=24, values=['Character inventory', 'Selected stash tab'])
        self.target_box.current(0)
        self.target_box.pack(side='left', padx=4)
        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True, pady=6)
        tabs.add(self._unique_tab(tabs), text='Unique')
        tabs.add(self._custom_tab(tabs), text='Custom')
        tabs.add(self._guide_tab(tabs), text='Guide')
        tabs.add(self._plans_tab(tabs), text='Plans')
        tabs.add(self._kit_tab(tabs), text='Kit')

    def put(self, items):
        if not items:
            return self.app.say('Nothing to add.')
        if self.target_box.current() == 0:
            if not self.app.char:
                return self.app.say('No character loaded.')
            self.app.put(self.app.char, items, L.INVENTORY_ID)
        else:
            tab = self.app.current_tab()
            if tab is None:
                return self.app.say('Select a stash tab on the Stash page first.')
            self.app.put(tab, items)

    def level(self, var, default=1):
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return default

    # -- unique
    def _unique_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        row = ttk.Frame(f)
        row.pack(fill='x')
        ttk.Label(row, text='Search:').pack(side='left')
        self.unique_filter = tk.StringVar()
        ttk.Entry(row, textvariable=self.unique_filter, width=18).pack(side='left', padx=4)
        ttk.Label(row, text='Max level:').pack(side='left')
        self.unique_level = tk.IntVar(value=100)
        ttk.Spinbox(row, from_=0, to=100, textvariable=self.unique_level, width=5).pack(side='left', padx=4)
        self.unique_filter.trace_add('write', lambda *a: self.fill_uniques())
        self.unique_level.trace_add('write', lambda *a: self.fill_uniques())
        self.unique_list = tk.Listbox(f, height=12, exportselection=False)
        self.unique_list.pack(fill='both', expand=True, pady=4)
        self.unique_list.bind('<<ListboxSelect>>', lambda e: self.show_unique())
        self.unique_text = tk.Text(f, height=8, wrap='word', state='disabled')
        self.unique_text.pack(fill='x')
        ttk.Button(f, text='Add unique (max rolls)', command=self.add_unique).pack(anchor='w', pady=6)
        self.fill_uniques()
        return f

    def unique_label(self, uid):
        u = self.db.uniques[uid]
        return 'L%d  %s  (%s)' % (self.db.unique_req(uid), u['name'], self.db.type_names.get(u['baseTypeID'], '?'))

    def fill_uniques(self):
        max_level = self.level(self.unique_level, 100)
        text = self.unique_filter.get().lower()
        self.unique_ids = [u for u in sorted(self.db.uniques, key=lambda u: (self.db.unique_req(u), u))
                           if self.db.unique_req(u) <= max_level and text in self.unique_label(u).lower()]
        self.unique_list.delete(0, 'end')
        self.unique_list.insert('end', *[self.unique_label(u) for u in self.unique_ids])

    def show_unique(self):
        sel = self.unique_list.curselection()
        if sel:
            self.app.set_text(self.unique_text, L.describe(self.db, L.make_unique(self.db, self.unique_ids[sel[0]])))

    def add_unique(self):
        sel = self.unique_list.curselection()
        if sel:
            self.put([L.make_unique(self.db, self.unique_ids[sel[0]])])

    # -- custom item
    def _custom_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        ttk.Label(f, text='Type:').grid(row=0, column=0, sticky='w')
        self.type_box = ttk.Combobox(f, state='readonly', width=36,
                                     values=['%d: %s' % (t, self.db.type_names[t]) for t in sorted(L.SIZES) if t in self.db.type_names])
        self.type_box.grid(row=0, column=1, columnspan=2, sticky='w')
        self.type_box.bind('<<ComboboxSelected>>', lambda e: self.fill_bases())
        ttk.Label(f, text='Base:').grid(row=1, column=0, sticky='w', pady=4)
        self.base_box = ttk.Combobox(f, state='readonly', width=36)
        self.base_box.grid(row=1, column=1, columnspan=2, sticky='w')
        ttk.Label(f, text='Affixes (type to filter), tier:').grid(row=2, columnspan=3, sticky='w', pady=(8, 2))
        self.affix_rows = []
        for i in range(L.MAX_AFFIXES):
            box = ttk.Combobox(f, width=44, values=self.app.form.all_affixes)
            box.grid(row=3 + i, column=0, columnspan=2, sticky='w', pady=1)
            box.bind('<KeyRelease>', lambda e, b=box: self.app.form.filter(b))
            tier = tk.IntVar(value=1)
            ttk.Spinbox(f, from_=1, to=L.MAX_TIER_NIBBLE + 1, textvariable=tier, width=3).grid(row=3 + i, column=2, sticky='w')
            self.affix_rows.append((box, tier))
        ttk.Button(f, text='Add item (max rolls)', command=self.add_custom).grid(row=8, columnspan=3, sticky='w', pady=8)
        ttk.Label(f, wraplength=400, justify='left', style='Dim.TLabel', text=(
            'Any affix works on any slot and tiers above T7 are accepted (tested). A normal item needs '
            'level sum(tier values) + 2 x highest - 10, so four T8 affixes mean level 86; legendaries on a '
            'unique keep the unique\'s level instead (make one with the Item page: add affixes to a unique).')
        ).grid(row=9, columnspan=3, sticky='w')
        return f

    def fill_bases(self):
        base_type = int(self.type_box.get().split(':')[0])
        self.base_box['values'] = ['%d: %s (level %d)' % (b['subTypeID'], b['name'], b['req']['level'])
                                   for b in self.db.subtypes(base_type)]
        self.base_box.current(0)

    def add_custom(self):
        if not self.type_box.get() or not self.base_box.get():
            return self.app.say('Choose a type and base first.')
        affixes = []
        for box, tier in self.affix_rows:
            text = box.get().strip()
            if not text:
                continue
            try:
                affixes.append((int(text.split(':')[0]), int(tier.get()) - 1))
            except (tk.TclError, ValueError):
                return self.app.say('Pick affixes from the list.')
        self.put([L.make_item(self.db, int(self.type_box.get().split(':')[0]), int(self.base_box.get().split(':')[0]), affixes, fp=0)])

    # -- guide sets
    def _guide_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        self.guides = L.load_guides()
        ttk.Label(f, text='Guide:').grid(row=0, column=0, sticky='w')
        self.guide_box = ttk.Combobox(f, state='readonly', width=40, values=[g.get('title') or g['name'] for g in self.guides])
        self.guide_box.grid(row=0, column=1, columnspan=3, sticky='w')
        self.guide_box.bind('<<ComboboxSelected>>', lambda e: self.fill_stages())
        self.stage_list = tk.Listbox(f, height=4, exportselection=False)
        self.stage_list.grid(row=1, columnspan=4, sticky='ew', pady=4)
        self.stage_list.bind('<<ListboxSelect>>', lambda e: self.show_stage())
        self.guide_fit = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text='Make wearable at level', variable=self.guide_fit, command=self.show_stage).grid(row=2, column=0, columnspan=2, sticky='w')
        self.guide_level = tk.IntVar(value=1)
        ttk.Spinbox(f, from_=1, to=100, textvariable=self.guide_level, width=5, command=self.show_stage).grid(row=2, column=2, sticky='w')
        self.guide_text = tk.Text(f, height=10, wrap='word', state='disabled')
        self.guide_text.grid(row=3, columnspan=4, sticky='nsew', pady=4)
        row = ttk.Frame(f)
        row.grid(row=4, columnspan=4, sticky='w')
        ttk.Button(row, text='Add stage set', command=self.add_stage).pack(side='left')
        ttk.Button(row, text='Add stage idols', command=self.add_stage_idols).pack(side='left', padx=4)
        ttk.Button(row, text='Stage as legendaries', command=self.add_stage_legendaries).pack(side='left')
        ttk.Button(row, text='Guide uniques', command=self.add_guide_uniques).pack(side='left', padx=4)
        ttk.Label(f, wraplength=400, justify='left', style='Dim.TLabel', text=(
            'Sets are the planner items with max rolls. Ticked, bases and tiers are lowered so the set '
            'can be worn at the level. "Stage as legendaries" puts the stage\'s affixes at top tier on the '
            'guide\'s uniques (or the best unique of the slot at that level), topped up with the worn items\' mods. '
            'New guides: "Import build..." on the Stash page.')).grid(row=5, columnspan=4, sticky='w', pady=4)
        if self.guides:
            self.guide_box.current(0)
            self.fill_stages()
        return f

    def current_guide(self):
        return self.guides[self.guide_box.current()] if self.guides and self.guide_box.current() >= 0 else None

    def reload_guides(self):
        self.guides = L.load_guides()
        self.guide_box['values'] = [g.get('title') or g['name'] for g in self.guides]

    def fill_stages(self):
        guide = self.current_guide()
        self.stage_list.delete(0, 'end')
        if not guide:
            return
        for st in guide['stages']:
            self.stage_list.insert('end', '%s  (%d items, %d idols)' % (st['name'], len(st['items']), len(st.get('idols', []))))
        level = self.app.char.json.get('level', 1) if self.app.char else 1
        self.stage_list.selection_set(next((i for i, st in enumerate(guide['stages']) if st['levels'][0] <= level <= st['levels'][1]), 0))
        self.guide_level.set(level)
        self.show_stage()

    def stage_items(self, stage):
        level = self.level(self.guide_level) if self.guide_fit.get() else None
        return L.guide_set(self.db, stage, level, self.app.char.json.get('characterClass') if self.app.char else None)

    def picked_stage(self):
        guide, sel = self.current_guide(), self.stage_list.curselection()
        if not guide or not sel:
            self.app.say('Pick a guide stage first.')
            return None, None
        return guide, guide['stages'][sel[0]]

    def show_stage(self):
        guide, stage = self.current_guide(), None
        sel = self.stage_list.curselection()
        if guide and sel:
            stage = guide['stages'][sel[0]]
            items = self.stage_items(stage) + L.guide_idols(self.db, stage)
            self.app.set_text(self.guide_text, '\n\n'.join(L.describe(self.db, i) for i in items))

    def add_stage(self):
        guide, stage = self.picked_stage()
        if stage:
            self.put(self.stage_items(stage))

    def add_stage_idols(self):
        guide, stage = self.picked_stage()
        if stage:
            self.put(L.guide_idols(self.db, stage))

    def add_stage_legendaries(self):
        guide, stage = self.picked_stage()
        if not stage:
            return
        fill = list(dict.fromkeys(a for i in L.equipped_items(self.app.char) for a, _, _ in i['affixes'])) if self.app.char else []
        self.put(L.guide_upgrade(self.db, guide, self.level(self.guide_level), fill or [2, 89, 5, 6, 36, 46, 28], stages=[stage]))

    def add_guide_uniques(self):
        guide = self.current_guide()
        if guide:
            self.put([L.make_unique(self.db, u) for u in guide.get('uniques', []) if u in self.db.uniques])

    # -- build plans
    def _plans_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        ttk.Label(f, wraplength=400, justify='left', text=(
            'Sets from the scripts in the plans folder: every variant becomes one stash tab in the category '
            'the plan names. Preview, then add one tab\'s items, or write all tabs into the loaded stash.')
        ).grid(columnspan=3, sticky='w', pady=(0, 6))
        self.plans = P.available()
        ttk.Label(f, text='Plan:').grid(row=1, column=0, sticky='w')
        self.plan_box = ttk.Combobox(f, state='readonly', width=44, values=[t for _, t in self.plans])
        self.plan_box.grid(row=1, column=1, columnspan=2, sticky='w')
        if self.plans:
            self.plan_box.current(0)
        ttk.Label(f, text='Level (for warnings):').grid(row=2, column=0, sticky='w', pady=4)
        self.plan_level = tk.IntVar(value=55)
        ttk.Spinbox(f, from_=1, to=100, textvariable=self.plan_level, width=5).grid(row=2, column=1, sticky='w')
        ttk.Button(f, text='Preview', command=self.preview_plan).grid(row=2, column=2, sticky='w')
        self.plan_list = tk.Listbox(f, height=6, exportselection=False)
        self.plan_list.grid(row=3, columnspan=3, sticky='ew')
        self.plan_list.bind('<<ListboxSelect>>', lambda e: self.show_plan_tab())
        self.plan_text = tk.Text(f, height=10, wrap='none', state='disabled', font=('TkFixedFont', 8))
        self.plan_text.grid(row=4, columnspan=3, sticky='nsew', pady=4)
        row = ttk.Frame(f)
        row.grid(row=5, columnspan=3, sticky='w')
        ttk.Button(row, text='Add this tab\'s items', command=self.add_plan_tab).pack(side='left')
        ttk.Button(row, text='Write all tabs to stash', command=self.write_plan).pack(side='left', padx=4)
        self.plan_tabs = []
        return f

    def preview_plan(self):
        if not self.plans:
            return self.app.say('No plan modules found.')
        self.plan_tabs = P.load(self.plans[self.plan_box.current()][0]).tabs(self.level(self.plan_level, 55))
        self.plan_list.delete(0, 'end')
        for cat, _, tab, items, _ in self.plan_tabs:
            self.plan_list.insert('end', '%s  /  %s  (%d items)' % (cat, tab, len(items)))
        self.plan_list.selection_set(0)
        self.show_plan_tab()
        self.app.say('%d tab(s) planned; nothing written yet.' % len(self.plan_tabs))

    def show_plan_tab(self):
        sel = self.plan_list.curselection()
        if sel and self.plan_tabs:
            self.app.set_text(self.plan_text, self.plan_tabs[sel[0]][4])

    def add_plan_tab(self):
        sel = self.plan_list.curselection()
        if not sel or not self.plan_tabs:
            return self.app.say('Preview a plan and pick a tab first.')
        self.put(self.plan_tabs[sel[0]][3])

    def write_plan(self):
        if not self.plan_tabs:
            return self.app.say('Preview a plan first.')
        groups = {}
        for cat, color, tab, items, _ in self.plan_tabs:
            groups.setdefault((cat, color), []).append((tab, items))
        self.app.write_tabs(groups)

    # -- leveling kit
    def _kit_tab(self, parent):
        f = ttk.Frame(parent, padding=8)
        ttk.Label(f, wraplength=400, justify='left', text=(
            'One item per slot wearable at the level: the best base for that level with health, resistances, '
            'movement speed, attributes and damage at the highest tiers the level allows, max rolls.')
        ).grid(columnspan=2, sticky='w', pady=(0, 8))
        ttk.Label(f, text='Level:').grid(row=1, column=0, sticky='w')
        self.kit_level = tk.IntVar(value=1)
        ttk.Spinbox(f, from_=1, to=100, textvariable=self.kit_level, width=6).grid(row=1, column=1, sticky='w')
        ttk.Label(f, text='Weapon style:').grid(row=2, column=0, sticky='w', pady=6)
        self.kit_style = ttk.Combobox(f, state='readonly', values=list(L.STYLES), width=22)
        self.kit_style.grid(row=2, column=1, sticky='w')
        ttk.Button(f, text='Add leveling kit', command=self.add_kit).grid(row=3, columnspan=2, sticky='w', pady=8)
        return f

    def add_kit(self):
        if not self.app.char:
            return self.app.say('No character loaded.')
        self.put(L.leveling_kit(self.db, self.level(self.kit_level), self.app.char.json.get('characterClass'),
                                self.kit_style.get() or L.default_style(self.app.char)))


class ApplyBuildDialog(tk.Toplevel):
    """Puts a Maxroll preset onto the loaded character: trees, gear (worn / inventory / stash tab / skip),
    idols, blessings. Nothing is written until Save changes."""

    def __init__(self, app):
        super().__init__(app)
        self.app, self.db = app, app.db
        self.title('Apply build to ' + (app.char.json.get('characterName', '') if app.char else '?'))
        self.transient(app)
        self.builds = []
        f = ttk.Frame(self, padding=10)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text='Build preset:').grid(row=0, column=0, sticky='w')
        self.build_box = ttk.Combobox(f, state='readonly', width=46)
        self.build_box.grid(row=0, column=1, columnspan=2, sticky='w', pady=2)
        ttk.Label(f, text='Maxroll link:').grid(row=1, column=0, sticky='w')
        self.url = tk.StringVar()
        ttk.Entry(f, textvariable=self.url, width=36).grid(row=1, column=1, sticky='w', pady=2)
        ttk.Button(f, text='Fetch', command=self.fetch).grid(row=1, column=2, sticky='w')
        self.trees = tk.BooleanVar(value=True)
        self.mastery = tk.BooleanVar(value=True)
        self.bless = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text='Passives, skill trees and ability bar', variable=self.trees).grid(row=2, columnspan=3, sticky='w', pady=(8, 0))
        ttk.Checkbutton(f, text='Switch mastery if the preset differs', variable=self.mastery).grid(row=3, columnspan=3, sticky='w')
        ttk.Checkbutton(f, text='Replace equipped blessings', variable=self.bless).grid(row=4, columnspan=3, sticky='w')
        ttk.Label(f, text='Gear:').grid(row=5, column=0, sticky='nw', pady=(8, 0))
        self.gear = tk.StringVar(value='equip')
        g = ttk.Frame(f)
        g.grid(row=5, column=1, columnspan=2, sticky='w', pady=(8, 0))
        for value, text in (('equip', 'Wear it; the worn items move to the inventory'), ('inventory', 'Put it in the inventory'),
                            ('stash', 'Put it in the stash tab selected on the Stash page'), ('none', 'Skip')):
            ttk.Radiobutton(g, text=text, value=value, variable=self.gear).pack(anchor='w')
        ttk.Label(f, text='Idols:').grid(row=6, column=0, sticky='nw', pady=(8, 0))
        self.idols = tk.StringVar(value='inventory')
        g = ttk.Frame(f)
        g.grid(row=6, column=1, columnspan=2, sticky='w', pady=(8, 0))
        for value, text in (('inventory', 'Inventory'), ('stash', 'Selected stash tab'), ('none', 'Skip')):
            ttk.Radiobutton(g, text=text, value=value, variable=self.idols).pack(anchor='w')
        self.info = ttk.Label(f, wraplength=440, justify='left', style='Dim.TLabel', text=(
            'The character keeps its name, level and progress. Passive points follow its level, skill trees get '
            'the first 20 picks; the rest is left to spend in game. The preset must be for the same class.'))
        self.info.grid(row=7, columnspan=3, sticky='w', pady=6)
        row = ttk.Frame(f)
        row.grid(row=8, columnspan=3, sticky='w')
        ttk.Button(row, text='Apply', command=self.apply).pack(side='left')
        ttk.Button(row, text='Cancel', command=self.destroy).pack(side='left', padx=4)
        self.fill_builds()

    def fill_builds(self, select=None):
        char_class = self.app.char.json.get('characterClass') if self.app.char else None
        self.builds = []
        for g in L.load_guides():
            for st in g['stages']:
                if st.get('passives') and (char_class is None or st.get('class') == char_class):
                    self.builds.append(('%s - %s' % (g.get('name') or g.get('title'), st['name']), st))
        self.build_box['values'] = [b for b, _ in self.builds]
        if self.builds:
            self.build_box.current(0)
        if select is not None:
            self.build_box.current(select)

    def fetch(self):
        url = self.url.get().strip()
        if not url:
            return
        self.info['text'] = 'Downloading...'
        self.update_idletasks()
        try:
            import import_maxroll
            guide = import_maxroll.load_build(url)
        except Exception as e:
            self.info['text'] = 'Fetch failed: %s' % e
            return
        L.save_guide(guide, url.rstrip('/').rsplit('/', 1)[-1])
        self.app.add_page.reload_guides()
        self.fill_builds()
        first = next((i for i, (b, st) in enumerate(self.builds) if st in guide['stages']), None)
        if first is None:
            self.info['text'] = 'Fetched "%s", but it is not for this class (%s).' % (guide.get('name'), guide.get('class'))
            return
        self.build_box.current(first)
        self.info['text'] = 'Fetched "%s": %d preset(s) for this class.' % (guide.get('name'), len(guide['stages']))

    def apply(self):
        app = self.app
        if not app.char:
            return app.say('No character loaded.')
        if not self.builds or self.build_box.current() < 0:
            return app.say('No preset for this class; fetch one.')
        stage = self.builds[self.build_box.current()][1]
        tab = app.current_tab() if 'stash' in (self.gear.get(), self.idols.get()) else None
        if 'stash' in (self.gear.get(), self.idols.get()) and tab is None:
            return app.say('Select a stash tab on the Stash page first.')
        try:
            notes = L.apply_build(self.db, app.char, stage, trees=self.trees.get(), gear=self.gear.get(),
                                  idols=self.idols.get(), blessings=self.bless.get(), stash_tab=tab, mastery=self.mastery.get())
        except ValueError as e:
            return app.say('Not applied: %s' % e)
        if tab is not None:
            app.dirty.add(tab)
        app.changed(app.char, 'Applied "%s" to %s.' % (self.builds[self.build_box.current()][0], app.char.json.get('characterName')))
        app.stats_page.refresh()
        if notes:
            messagebox.showinfo('Apply build', '\n'.join(notes), parent=app)
        self.destroy()


class NewCharacterDialog(tk.Toplevel):
    """Creates a new character slot: campaign state copied from an existing character, class / mastery /
    level chosen here, and optionally the passives, skills, gear, idols and blessings of a build preset
    (an imported Maxroll guide stage, or a link fetched right here)."""

    def __init__(self, app):
        super().__init__(app)
        self.app, self.db = app, app.db
        self.title('New character')
        self.transient(app)
        self.trees = L.load_trees()
        self.builds = []            # (label, stage) of presets with passive data
        f = ttk.Frame(self, padding=10)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text='Name:').grid(row=0, column=0, sticky='w')
        self.name = tk.StringVar(value='New Hero')
        ttk.Entry(f, textvariable=self.name, width=30).grid(row=0, column=1, columnspan=2, sticky='w', pady=2)
        ttk.Label(f, text='Campaign state from:').grid(row=1, column=0, sticky='w')
        chars = app.char_files
        labels = list(app.char_box['values'])
        self.template_box = ttk.Combobox(f, state='readonly', width=44, values=labels)
        self.template_box.grid(row=1, column=1, columnspan=2, sticky='w', pady=2)
        if labels:
            best = max(range(len(chars)), key=lambda i: L.SaveFile(os.path.join(app.folder, chars[i])).json.get('level', 0))
            self.template_box.current(best)
        ttk.Label(f, text='Build preset:').grid(row=2, column=0, sticky='w')
        self.build_box = ttk.Combobox(f, state='readonly', width=44)
        self.build_box.grid(row=2, column=1, columnspan=2, sticky='w', pady=2)
        self.build_box.bind('<<ComboboxSelected>>', lambda e: self.build_picked())
        ttk.Label(f, text='Maxroll link:').grid(row=3, column=0, sticky='w')
        self.url = tk.StringVar()
        ttk.Entry(f, textvariable=self.url, width=34).grid(row=3, column=1, sticky='w', pady=2)
        ttk.Button(f, text='Fetch', command=self.fetch).grid(row=3, column=2, sticky='w')
        ttk.Label(f, text='Class:').grid(row=4, column=0, sticky='w')
        self.class_box = ttk.Combobox(f, state='readonly', width=16, values=[L.CLASSES[c] for c in sorted(L.CLASSES)])
        self.class_box.grid(row=4, column=1, sticky='w', pady=2)
        self.class_box.bind('<<ComboboxSelected>>', lambda e: self.fill_masteries())
        ttk.Label(f, text='Mastery:').grid(row=5, column=0, sticky='w')
        self.mastery_box = ttk.Combobox(f, state='readonly', width=16)
        self.mastery_box.grid(row=5, column=1, sticky='w', pady=2)
        ttk.Label(f, text='Level:').grid(row=6, column=0, sticky='w')
        self.level = tk.IntVar(value=100)
        ttk.Spinbox(f, from_=1, to=100, textvariable=self.level, width=5).grid(row=6, column=1, sticky='w', pady=2)
        ttk.Label(f, text='Mode:').grid(row=6, column=2, sticky='e')
        self.mode_box = ttk.Combobox(f, state='readonly', width=20, values=list(L.MODES))
        self.mode_box.current(0)
        self.mode_box.grid(row=7, column=2, sticky='w')
        self.hardcore = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text='Hardcore', variable=self.hardcore).grid(row=7, column=1, sticky='w')
        self.gear = tk.BooleanVar(value=True)
        self.idols = tk.BooleanVar(value=True)
        self.bless = tk.BooleanVar(value=True)
        row = ttk.Frame(f)
        row.grid(row=8, columnspan=3, sticky='w', pady=4)
        ttk.Checkbutton(row, text='Wear the preset gear', variable=self.gear).pack(side='left')
        ttk.Checkbutton(row, text='Idols to inventory', variable=self.idols).pack(side='left', padx=6)
        ttk.Checkbutton(row, text='Blessings', variable=self.bless).pack(side='left')
        self.info = ttk.Label(f, wraplength=440, justify='left', style='Dim.TLabel', text=(
            'Quests, waypoints, monolith and faction progress are copied from the chosen character, so pick a '
            'finished one. Passive points: level - 1 + 14; the preset allocation is applied and the rest stays '
            'unspent. Idols go to the inventory because idol grids differ per class. Solo Character Found '
            'characters cannot use the stash, so give them their items through the inventory.'))
        self.info.grid(row=9, columnspan=3, sticky='w', pady=4)
        row = ttk.Frame(f)
        row.grid(row=10, columnspan=3, sticky='w')
        ttk.Button(row, text='Create', command=self.create).pack(side='left')
        ttk.Button(row, text='Cancel', command=self.destroy).pack(side='left', padx=4)
        self.fill_builds()
        if app.char:
            self.class_box.current(app.char.json.get('characterClass', 0))
            self.fill_masteries()
            self.mastery_box.current(max(0, app.char.json.get('chosenMastery', 1) - 1))

    def fill_builds(self, keep=None):
        self.builds = [('No build: empty trees, no gear', None)]
        for g in L.load_guides():
            for st in g['stages']:
                if st.get('passives'):
                    self.builds.append(('%s - %s' % (g.get('name') or g.get('title'), st['name']), st))
        self.build_box['values'] = [b for b, _ in self.builds]
        self.build_box.current(keep if keep is not None else 0)

    def fetch(self):
        url = self.url.get().strip()
        if not url:
            return
        self.info['text'] = 'Downloading...'
        self.update_idletasks()
        try:
            import import_maxroll
            guide = import_maxroll.load_build(url)
        except Exception as e:
            self.info['text'] = 'Fetch failed: %s' % e
            return
        L.save_guide(guide, url.rstrip('/').rsplit('/', 1)[-1])
        self.app.add_page.reload_guides()
        self.fill_builds()
        first = next((i for i, (b, st) in enumerate(self.builds) if st and st in guide['stages']), None)
        if first is None:
            self.info['text'] = 'Fetched, but the build has no passive data.'
            return
        self.build_box.current(first)
        self.build_picked()
        self.info['text'] = 'Fetched "%s": %d preset(s).' % (guide.get('name'), len(guide['stages']))

    def build_picked(self):
        stage = self.builds[self.build_box.current()][1]
        if stage and stage.get('class') is not None:
            self.class_box.current(stage['class'])
            self.fill_masteries()
            self.mastery_box.current(max(0, (stage.get('mastery') or 1) - 1))

    def fill_masteries(self):
        self.mastery_box['values'] = self.trees[self.class_box.current()]['masteries']
        self.mastery_box.current(0)

    def create(self):
        app = self.app
        if self.template_box.current() < 0:
            return self.app.say('Pick a character to copy the campaign state from.')
        name = self.name.get().strip()
        if not name:
            return self.app.say('Enter a name.')
        try:
            level = max(1, min(100, int(self.level.get())))
        except (tk.TclError, ValueError):
            return self.app.say('Level must be a number.')
        game = L.find_game_folder()
        if game and os.path.realpath(app.folder) == os.path.realpath(game) and L.game_running():
            return self.app.say('Last Epoch is running: close it before creating a character.')
        template = L.SaveFile(os.path.join(app.folder, app.char_files[self.template_box.current()]))
        stage = self.builds[self.build_box.current()][1]
        slot = L.next_character_slot(app.folder)
        data, notes = L.new_character(self.db, template, name, self.class_box.current(), self.mastery_box.current() + 1,
                                      level, stage, slot, self.gear.get(), self.idols.get(), self.bless.get(),
                                      self.mode_box.get(), self.hardcore.get())
        try:
            save = L.write_new_character(app.folder, data, slot)
        except (OSError, ValueError) as e:
            return self.app.say('Could not create the character: %s' % e)
        if app.dirty:
            app.dirty.clear()
        app.load_folder(app.folder)
        app.char_box.current(app.char_files.index(save.name))
        app.load_character()
        app.say('Created %s "%s" (level %d %s %s, %s%s). %s' % (
            save.name, name, level, L.CLASSES[self.class_box.current()], self.mastery_box.get(), self.mode_box.get(),
            ', hardcore' if self.hardcore.get() else '',
            ('Notes: ' + '; '.join(notes)) if notes else ''))
        if notes:
            messagebox.showinfo('New character', 'Created with notes:\n\n' + '\n'.join(notes), parent=app)
        self.destroy()


class StatsPage(ttk.Frame):
    """Totals of what the character carries (worn gear, idols, blessings, passives, class base):
    a summary of the derived numbers and a tree of every stat with its sources."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app, self.db = app, app.db
        self.trees = L.load_trees()
        row = ttk.Frame(self)
        row.pack(fill='x')
        self.head = ttk.Label(row, style='Head.TLabel', text='No character')
        self.head.pack(side='left')
        ttk.Button(row, text='Refresh', command=self.refresh).pack(side='right')
        self.summary = ttk.Treeview(self, columns=('value',), show='tree', height=20)
        self.summary.column('#0', width=130, stretch=False)
        self.summary.column('value', width=320)
        self.summary.pack(fill='x', pady=6)
        ttk.Label(self, text='Every stat and where it comes from (type to filter):').pack(anchor='w')
        self.filter = tk.StringVar()
        self.filter.trace_add('write', lambda *a: self.fill_tree())
        ttk.Entry(self, textvariable=self.filter, width=30).pack(anchor='w', pady=2)
        self.tree = ttk.Treeview(self, columns=('value',), height=24)
        self.tree.heading('#0', text='Stat / source')
        self.tree.heading('value', text='Value')
        self.tree.column('#0', width=330)
        self.tree.column('value', width=90, anchor='e')
        self.tree.pack(fill='both', expand=True)
        ttk.Label(self, wraplength=440, justify='left', style='Dim.TLabel', text=(
            'Numbers are the sums of the mod lines at their rolls. Conditional mods ("while channelling", '
            '"per 100 mana") are summed like any other and skill tree nodes are not included, so treat the '
            'summary as an estimate; health leaves out the vitality bonus.')).pack(anchor='w', pady=4)
        self.stats, self.lines = {}, []

    def refresh(self):
        save = self.app.char
        if not save:
            self.head['text'] = 'No character'
            return
        self.stats, self.lines = L.character_stats(self.db, save, self.trees)
        j = save.json
        self.head['text'] = '%s, level %s %s' % (j.get('characterName'), j.get('level'), L.CLASSES.get(j.get('characterClass'), ''))
        self.summary.delete(*self.summary.get_children())
        for label, text in self.lines:
            self.summary.insert('', 'end', text=label, values=(text,))
        self.fill_tree()

    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        words = self.filter.get().lower().split()
        for key, e in sorted(self.stats.items(), key=lambda kv: (-abs(kv[1]['total']), kv[0])):
            if not e['sources'] or (words and not all(w in key for w in words)):
                continue
            node = self.tree.insert('', 'end', text=key, values=('%g' % round(e['total'], 1),))
            for source, value in e['sources']:
                self.tree.insert(node, 'end', text=source, values=('%g' % round(value, 1),))


class App(tk.Tk):
    def __init__(self, folder):
        super().__init__()
        self.title('Last Epoch Save Editor')
        self.geometry('1280x760')
        self.glow_styles = theme.apply(self)
        self.db = L.Database()
        self.icons = IconCache()
        self.style = ttk.Style(self)
        self.bind_all('<Button-4>', self.wheel_anywhere, add='+')
        self.bind_all('<Button-5>', self.wheel_anywhere, add='+')
        self.bind_all('<MouseWheel>', self.wheel_anywhere, add='+')
        self.folder = folder
        self.char = self.stash = None
        self.tabs = {}        # stash tab file name -> SaveFile
        self.dirty = set()
        self._build()
        self.load_folder(folder)

    # ------------------------------------------------------------ layout
    def _build(self):
        top = ttk.Frame(self, padding=6)
        top.pack(fill='x')
        ttk.Button(top, text='Saves folder...', command=self.browse).pack(side='left')
        ttk.Label(top, text='  Character:').pack(side='left')
        self.char_box = ttk.Combobox(top, state='readonly', width=40)
        self.char_box.pack(side='left')
        self.char_box.bind('<<ComboboxSelected>>', lambda e: self.load_character())
        self.save_button = ttk.Button(top, text='Save changes', command=self.save)
        self.save_button.pack(side='right')
        self.glow_phase = None      # None = not glowing; otherwise the animation step
        ttk.Button(top, text='Reload', command=lambda: self.load_folder(self.folder)).pack(side='right', padx=4)
        ttk.Button(top, text='Send to game...', command=self.send_to_game).pack(side='right')
        ttk.Button(top, text='Backup folder', command=self.backup).pack(side='right', padx=4)
        ttk.Button(top, text='New character...', command=lambda: NewCharacterDialog(self)).pack(side='right')
        self.status = ttk.Label(self, anchor='w', style='Status.TLabel')
        self.status.pack(fill='x', side='bottom')

        body = ttk.Panedwindow(self, orient='horizontal')
        body.pack(fill='both', expand=True, padx=6, pady=4)
        self.pages = ttk.Notebook(body)
        body.add(self.pages, weight=1)
        self.pages.add(self._stash_page(self.pages), text='Stash')
        self.pages.add(self._char_page(self.pages), text='Character')
        right = ttk.Frame(body)
        body.add(right, weight=1)
        self.right_pages = ttk.Notebook(right)
        self.right_pages.pack(fill='both', expand=True)
        self.form = ItemForm(self.scrollable(self.right_pages, 'Item'), self)
        self.form.pack(fill='both', expand=True)
        self.add_page = AddPage(self.scrollable(self.right_pages, 'Add items'), self)
        self.add_page.pack(fill='both', expand=True)
        self.stats_page = StatsPage(self.scrollable(self.right_pages, 'Stats'), self)
        self.stats_page.pack(fill='both', expand=True)
        self.after(150, lambda: body.sashpos(0, max(560, self.winfo_width() - 520)))   # a wider right panel

    def wheel_anywhere(self, event):
        """Scrolls the right-hand page when the wheel turns over any widget inside it."""
        widget = event.widget
        while widget is not None and not isinstance(widget, tk.Canvas):
            if isinstance(widget, (tk.Text, tk.Listbox, ttk.Treeview, ttk.Combobox)):
                return
            widget = getattr(widget, 'master', None)
        if isinstance(widget, tk.Canvas) and widget.winfo_toplevel() is self and widget.cget('yscrollcommand'):
            widget.yview_scroll(-3 if (event.num == 4 or event.delta > 0) else 3, 'units')

    def scrollable(self, notebook, title):
        """A notebook page whose content scrolls vertically (mouse wheel too). Returns the inner frame."""
        outer = ttk.Frame(notebook)
        notebook.add(outer, text=title)
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        return inner

    def _tree(self, parent):
        cols = ('rarity', 'req', 'affixes')
        tree = ttk.Treeview(parent, columns=cols, selectmode='browse')
        tree.heading('#0', text='Item')
        tree.column('#0', width=230)
        for col, text, width in zip(cols, ('Rarity', 'Lvl', 'Affixes'), (70, 35, 300)):
            tree.heading(col, text=text)
            tree.column(col, width=width, stretch=(col == 'affixes'))
        scroll = ttk.Scrollbar(parent, orient='vertical', command=tree.yview)
        tree['yscrollcommand'] = scroll.set
        return tree, scroll

    def _stash_page(self, parent):
        f = ttk.Frame(parent, padding=4)
        row = ttk.Frame(f)
        row.pack(fill='x')
        ttk.Label(row, text='Stash:').pack(side='left')
        self.stash_box = ttk.Combobox(row, state='readonly', width=22)
        self.stash_box.pack(side='left', padx=4)
        self.stash_box.bind('<<ComboboxSelected>>', lambda e: self.load_stash())
        ttk.Label(row, text='Gold:').pack(side='left')
        self.gold = tk.StringVar()
        ttk.Entry(row, textvariable=self.gold, width=10).pack(side='left', padx=2)
        ttk.Button(row, text='Set', command=self.set_gold).pack(side='left')
        ttk.Button(row, text='New category', command=self.new_category).pack(side='right')
        ttk.Button(row, text='New tab', command=self.new_tab).pack(side='right', padx=4)
        ttk.Button(row, text='Rename', command=self.rename).pack(side='right')
        ttk.Button(row, text='Import build...', command=self.import_build).pack(side='right', padx=4)
        mid = ttk.Frame(f)
        mid.pack(fill='both', expand=True, pady=4)
        self.stash_tree, scroll = self._tree(mid)
        self.stash_tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='left', fill='y')
        self.stash_tree.bind('<<TreeviewSelect>>', lambda e: self.stash_pick())
        self.stash_grid = GridView(f, self.db, self.icons, lambda i: self.pick_from_grid('stash', i))
        self.stash_grid.pack(anchor='w')
        return f

    def _char_page(self, parent):
        f = ttk.Frame(parent, padding=4)
        row = ttk.Frame(f)
        row.pack(fill='x')
        self.char_info = ttk.Label(row, style='Dim.TLabel')
        self.char_info.pack(side='left')
        ttk.Button(row, text='Apply build...', command=lambda: ApplyBuildDialog(self)).pack(side='right')
        mid = ttk.Frame(f)
        mid.pack(fill='both', expand=True, pady=4)
        self.char_tree, scroll = self._tree(mid)
        self.char_tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='left', fill='y')
        self.char_tree.bind('<<TreeviewSelect>>', lambda e: self.char_pick())
        bottom = ttk.Frame(f)
        bottom.pack(fill='x')
        col = ttk.Frame(bottom)
        col.pack(side='left', anchor='n', padx=(0, 8))
        ttk.Label(col, text='Wielded').pack(anchor='w')
        self.slot_view = SlotView(col, self.db, self.icons, lambda i: self.pick_from_grid('char', i))
        self.slot_view.pack(anchor='w')
        col = ttk.Frame(bottom)
        col.pack(side='left', anchor='n', padx=(0, 8))
        ttk.Label(col, text='Idols').pack(anchor='w')
        self.idol_grid = GridView(col, self.db, self.icons, lambda i: self.pick_from_grid('char', i))
        self.idol_grid.pack(anchor='w')
        col = ttk.Frame(bottom)
        col.pack(side='left', anchor='n')
        row = ttk.Frame(col)
        row.pack(fill='x')
        ttk.Label(row, text='Inventory').pack(side='left')
        ttk.Button(row, text='Clear', command=self.clear_inventory).pack(side='right')
        self.char_grid = GridView(col, self.db, self.icons, lambda i: self.pick_from_grid('char', i))
        self.char_grid.pack(anchor='w')
        return f

    def draw_character(self, selected=()):
        self.char_grid.draw(self.char, L.INVENTORY_ID, selected)
        self.idol_grid.draw(self.char, IDOLS, selected, size=idol_grid_size(self.db, self.char))
        self.slot_view.draw(self.char, selected)

    # ------------------------------------------------------------ loading
    def browse(self):
        folder = filedialog.askdirectory(initialdir=self.folder, title='Last Epoch Saves folder')
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder):
        if self.dirty and not messagebox.askyesno('Reload', 'Discard unsaved changes?'):
            return
        self.folder = folder
        self.dirty.clear()
        self.tabs.clear()
        chars = stashes = []
        if os.path.isdir(folder):
            chars, stashes, _ = L.list_saves(folder)
        self.char_files = chars
        labels = []
        for name in chars:
            j = L.SaveFile(os.path.join(folder, name)).json
            labels.append('%s  -  %s, level %s %s' % (name, j.get('characterName'), j.get('level'),
                                                    L.CLASSES.get(j.get('characterClass'), '')))
        self.char_box['values'] = labels
        self.stash_box['values'] = stashes
        if not chars:
            return self.say('No character files found in ' + folder)
        newest = max(range(len(chars)), key=lambda i: os.path.getmtime(os.path.join(folder, chars[i])))
        self.char_box.current(newest)
        self.load_character()

    def load_character(self):
        self.char = L.SaveFile(os.path.join(self.folder, self.char_files[self.char_box.current()]))
        j = self.char.json
        self.char_info['text'] = '%s, level %s %s, %d items in the file' % (
            j.get('characterName'), j.get('level'), L.CLASSES.get(j.get('characterClass'), ''), len(self.char.items))
        stashes = list(self.stash_box['values'])
        cycle = j.get('cycle')
        match = [s for s in stashes if cycle is not None and ('CYCLE_%s_' % cycle) in s] or stashes
        if match:
            self.stash_box.set(match[0])
            self.load_stash()
        else:
            self.stash = None
            self.fill_stash_tree()
        self.fill_char_tree()
        if hasattr(self, 'stats_page'):
            self.stats_page.refresh()
        if hasattr(self, 'add_page'):
            self.add_page.kit_level.set(j.get('level', 1))
            self.add_page.kit_style.set(L.default_style(self.char))
            self.add_page.unique_level.set(j.get('level', 100))
            self.add_page.fill_stages()
        self.say('Loaded %s.' % self.char.name)

    def load_stash(self):
        self.stash = L.SaveFile(os.path.join(self.folder, self.stash_box.get()))
        self.gold.set(str(self.stash.json.get('gold', 0)))
        self.tabs.clear()
        for name in self.stash.json.get('tabsv2', []):
            path = os.path.join(self.folder, name)
            if os.path.isfile(path):
                self.tabs[name] = L.SaveFile(path)
        self.fill_stash_tree()

    def item_values(self, item):
        if not item:
            return (L.item_title(self.db, None), '', '', '')
        affixes = '; '.join('T%d %s' % (t + 1, self.db.affix_text(a, t)) for a, t, _ in item['affixes'])
        return (L.item_title(self.db, item), L.rarity_name(item), L.item_req(self.db, item), affixes)

    def fill_stash_tree(self, keep=None):
        tree = self.stash_tree
        tree.delete(*tree.get_children())
        if not self.stash:
            return
        cats = L.stash_categories(self.stash)
        nodes = {}
        for cid, name in sorted(cats.items()):
            nodes[cid] = tree.insert('', 'end', iid='cat:%d' % cid, text='%s  (category %d)' % (name, cid), open=True)
        for name, tab in self.tabs.items():
            cid = tab.json.get('categoryId', 0)
            if cid not in nodes:
                nodes[cid] = tree.insert('', 'end', iid='cat:%d' % cid, text='Category %d' % cid, open=True)
            node = tree.insert(nodes[cid], 'end', iid='tab:' + name, open=(name == keep),
                               text='%s  [%s]' % (tab.json.get('displayName', name), name),
                               values=('', '', '%d items' % len(tab.items)))
            for i, e in enumerate(tab.items):
                item = L.decode(e['data'])
                text, rarity, req, affixes = self.item_values(item)
                tree.insert(node, 'end', iid='it:%s:%d' % (name, i), text=text, values=(rarity, req, affixes),
                            image=self.icons.get(item, 'row') or '')
        if keep in self.tabs:
            tree.see('tab:' + keep)
        self.stash_grid.draw(self.tabs.get(keep))

    def fill_char_tree(self, open_groups=None):
        tree = self.char_tree
        tree.delete(*tree.get_children())
        if not self.char:
            return
        groups = {}
        for i, e in enumerate(self.char.items):
            groups.setdefault(e.get('containerID'), []).append(i)
        order = [L.INVENTORY_ID] + list(L.EQUIP_SLOTS) + [IDOLS] + sorted(c for c in groups if c not in L.CONTAINERS and c != IDOLS)
        for cid in order:
            if cid not in groups and cid != L.INVENTORY_ID:
                continue
            node = tree.insert('', 'end', iid='grp:%s' % cid, text=container_name(cid), open=cid in (L.INVENTORY_ID, IDOLS) or cid in L.EQUIP_SLOTS,
                               values=('', '', '%d items' % len(groups.get(cid, []))))
            for i in groups.get(cid, []):
                item = L.decode(self.char.items[i]['data'])
                text, rarity, req, affixes = self.item_values(item)
                tree.insert(node, 'end', iid='it:char:%d' % i, text=text, values=(rarity, req, affixes),
                            image=self.icons.get(item, 'row') or '')
        self.draw_character()

    # ------------------------------------------------------------ selection
    def current_tab(self):
        sel = self.stash_tree.selection()
        if not sel:
            return None
        iid = sel[0]
        if iid.startswith('tab:'):
            return self.tabs.get(iid[4:])
        if iid.startswith('it:'):
            return self.tabs.get(iid.split(':')[1])
        return None

    def stash_pick(self):
        sel = self.stash_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.startswith('it:'):
            _, name, index = iid.split(':')
            index = int(index)
            self.stash_grid.draw(self.tabs[name], selected={index})
            self.form.show(self.tabs[name], index)
        elif iid.startswith('tab:'):
            self.stash_grid.draw(self.tabs[iid[4:]])

    def char_pick(self):
        sel = self.char_tree.selection()
        if not sel or not sel[0].startswith('it:'):
            return
        index = int(sel[0].split(':')[2])
        self.draw_character(selected={index})
        self.form.show(self.char, index)

    def pick_from_grid(self, which, index):
        if which == 'char':
            self.char_tree.selection_set('it:char:%d' % index)
            self.char_tree.see('it:char:%d' % index)
        else:
            tab = self.current_tab()
            if tab:
                iid = 'it:%s:%d' % (tab.name, index)
                self.stash_tree.selection_set(iid)
                self.stash_tree.see(iid)

    # ------------------------------------------------------------ changes
    def say(self, text):
        self.status['text'] = text
        self.update_glow()

    # ------------------------------------------------------------ unsaved-changes glow
    def update_glow(self):
        """Pulses the Save button in amber while there are unsaved changes."""
        if self.dirty and self.glow_phase is None:
            self.glow_phase = 0
            self.pulse()
        elif not self.dirty and self.glow_phase is not None:
            self.glow_phase = None
            self.save_button.configure(style='TButton', text='Save changes')

    def pulse(self):
        if self.glow_phase is None:
            return
        if not self.dirty:
            self.update_glow()
            return
        import math
        k = 0.5 + 0.5 * math.sin(self.glow_phase / 9.0)       # subtle to medium: the glow styles span 15-60 % amber
        self.save_button.configure(style=self.glow_styles[round(k * (len(self.glow_styles) - 1))], text='Save changes *')
        self.glow_phase += 1
        self.after(60, self.pulse)

    def set_text(self, widget, text):
        widget['state'] = 'normal'
        widget.delete('1.0', 'end')
        widget.insert('1.0', text)
        widget['state'] = 'disabled'

    def write_tabs(self, groups):
        """Writes {(category name, color): [(tab name, items)]} into the loaded stash as new tabs."""
        if not self.stash:
            return self.say('No stash loaded.')
        if self.dirty:
            return self.say('Save your changes first.')
        game = L.find_game_folder()
        if game and os.path.realpath(self.folder) == os.path.realpath(game) and L.game_running():
            return self.say('Last Epoch is running: close it before writing stash tabs.')
        count = sum(len(t) for t in groups.values())
        if not messagebox.askyesno('Write tabs', 'Create %d stash tab(s) in categories %s of %s?' % (
                count, ', '.join('"%s"' % c for c, _ in groups), self.stash.name)):
            return
        notes = []
        for (cat, color), tabs in groups.items():
            existing = L.stash_categories(self.stash)
            cat_id = next((i for i, n in existing.items() if n.lower() == cat.lower()), None)
            if cat_id is None:
                cat_id = L.add_stash_category(self.stash, cat, color=color)
            for tab, items in tabs:
                t = L.add_stash_tab(self.stash, self.folder, tab, cat_id)
                left = L.add_items(self.db, t, items)
                if left:
                    notes.append('no room in %s for %d item(s)' % (tab, len(left)))
                t.save()
        backup = self.stash.save()
        self.load_stash()
        self.say('Wrote %d tab(s). Backup in %s. %s' % (count, os.path.dirname(backup), '; '.join(notes)))

    def changed(self, save, message):
        if save is not None:
            self.dirty.add(save)
        else:
            self.dirty |= {s for s in [self.char] + list(self.tabs.values()) if s}
        keep = self.current_tab()
        self.fill_stash_tree(keep.name if keep else None)
        if keep and self.stash_tree.exists('tab:' + keep.name):
            self.stash_tree.selection_set('tab:' + keep.name)     # keep the tab as the target for adds
        self.fill_char_tree()
        if hasattr(self, 'stats_page'):
            self.stats_page.refresh()
        self.say(message + '  (not saved yet)')

    def put(self, save, items, container=L.INVENTORY_ID):
        left = L.add_items(self.db, save, items, container)
        message = 'Added %d item(s) to %s.' % (len(items) - len(left), save.name)
        if left:
            message += ' No room for %d.' % len(left)
        self.changed(save, message)

    def clear_inventory(self):
        if self.char and messagebox.askyesno('Clear', 'Remove every item from the character inventory?'):
            L.clear_container(self.char)
            self.changed(self.char, 'Inventory cleared.')

    def set_gold(self):
        if not self.stash:
            return self.say('No stash loaded.')
        try:
            self.stash.json['gold'] = max(0, int(self.gold.get()))
        except ValueError:
            return self.say('Gold must be a number.')
        self.dirty.add(self.stash)
        self.say('Gold set to %d  (not saved yet)' % self.stash.json['gold'])

    def new_category(self):
        if not self.stash:
            return self.say('No stash loaded.')
        name = simpledialog.askstring('New category', 'Category name:', parent=self)
        if name:
            cid = L.add_stash_category(self.stash, name.strip(), color=10)
            self.dirty.add(self.stash)
            self.fill_stash_tree()
            self.say('Category "%s" (%d) added  (not saved yet)' % (name, cid))

    def new_tab(self):
        if not self.stash:
            return self.say('No stash loaded.')
        if self.dirty:
            return self.say('Save your changes first (a new tab writes the stash file).')
        sel = self.stash_tree.selection()
        cid = 0
        if sel:
            iid = sel[0]
            if iid.startswith('cat:'):
                cid = int(iid[4:])
            elif iid.startswith('tab:'):
                cid = self.tabs[iid[4:]].json.get('categoryId', 0)
            elif iid.startswith('it:'):
                cid = self.tabs[iid.split(':')[1]].json.get('categoryId', 0)
        cats = L.stash_categories(self.stash)
        name = simpledialog.askstring('New tab', 'Tab name (in category "%s"):' % cats.get(cid, cid), parent=self)
        if name is None:
            return
        try:
            tab = L.add_stash_tab(self.stash, self.folder, name.strip() or None, cid)
        except (OSError, ValueError) as e:
            return self.say('Could not create tab: %s' % e)
        self.stash.save()
        self.load_stash()
        self.stash_tree.selection_set('tab:' + tab.name)
        self.say('Created %s "%s".' % (tab.name, tab.json['displayName']))

    def import_build(self):
        """Downloads a Maxroll build guide or planner and writes one stash tab per character preset
        into a category named after the build."""
        if not self.stash:
            return self.say('No stash loaded.')
        if self.dirty:
            return self.say('Save your changes first (importing writes the stash file).')
        url = simpledialog.askstring('Import build', 'Maxroll build guide or planner link:', parent=self)
        if not url:
            return
        self.say('Downloading %s ...' % url.strip())

        def work():
            try:
                import import_maxroll
                guide = import_maxroll.load_build(url.strip())
            except Exception as e:     # network / page format problems are reported, not raised
                self.after(0, lambda: self.say('Import failed: %s' % e))
                return
            self.after(0, lambda: self.finish_import(guide, url.strip()))
        threading.Thread(target=work, daemon=True).start()

    def finish_import(self, guide, url):
        game = L.find_game_folder()
        if game and os.path.realpath(self.folder) == os.path.realpath(game) and L.game_running():
            return self.say('Last Epoch is running: close it, then import again.')
        try:
            cat, tabs = L.import_build_tabs(self.db, self.stash, self.folder, guide)
        except (OSError, ValueError) as e:
            return self.say('Import failed: %s' % e)
        self.stash.save()
        L.save_guide(guide, url.rstrip('/').rsplit('/', 1)[-1])
        self.add_page.reload_guides()
        self.load_stash()
        self.stash_tree.selection_set('tab:' + tabs[0].name)
        self.stash_tree.see('tab:' + tabs[0].name)
        self.say('Imported "%s": %d tab(s) in category %d.' % (guide.get('name'), len(tabs), cat))

    def rename(self):
        sel = self.stash_tree.selection()
        if not sel:
            return self.say('Select a category or tab first.')
        iid = sel[0]
        if iid.startswith('cat:'):
            cid = int(iid[4:])
            cat = next(c for c in self.stash.json.get('categories', []) if c['categoryId'] == cid)
            name = simpledialog.askstring('Rename category', 'Name:', initialvalue=cat['displayName'], parent=self)
            if name:
                cat['displayName'] = name.strip()
                self.changed(self.stash, 'Category renamed.')
        elif iid.startswith('tab:'):
            tab = self.tabs[iid[4:]]
            name = simpledialog.askstring('Rename tab', 'Name:', initialvalue=tab.json.get('displayName', ''), parent=self)
            if name:
                tab.json['displayName'] = name.strip()
                self.changed(tab, 'Tab renamed.')

    # ------------------------------------------------------------ files
    def save(self):
        if not self.dirty:
            return self.say('Nothing to save.')
        game = L.find_game_folder()
        if game and os.path.realpath(self.folder) == os.path.realpath(game) and L.game_running():
            return self.say('Last Epoch is running: close it before saving.')
        backup = ''
        for s in list(self.dirty):
            backup = s.save()
        count = len(self.dirty)
        self.dirty.clear()
        self.say('Saved %d file(s). Originals backed up in %s' % (count, os.path.dirname(backup)))

    def backup(self):
        if not os.path.isdir(self.folder):
            return self.say('Folder not found: ' + self.folder)
        out = L.backup_folder(self.folder, 'full')
        self.say('Backed up %d file(s) to %s' % (len(os.listdir(out)), out))

    def send_to_game(self):
        dest = L.find_game_folder()
        if not dest:
            return self.say('Game folder not found.')
        if os.path.realpath(dest) == os.path.realpath(self.folder):
            return self.say('You are already editing the game folder; just save.')
        if self.dirty:
            return self.say('Save your changes first.')
        if not self.char:
            return self.say('Load a character first.')
        names = [self.char.name] + ([self.stash.name] + list(self.tabs) if self.stash else [])
        if L.game_running():
            return self.say('Close Last Epoch first.')
        if not messagebox.askyesno('Send to game', 'Copy %d file(s) into\n%s ?\nThe game\'s files are backed up first.' % (len(names), dest)):
            return
        backup = L.deploy(self.folder, names, dest)
        self.say('Copied %d file(s). Originals in %s' % (len(names), backup))

    def report_callback_exception(self, exc, value, tb):
        import traceback
        messagebox.showerror('Error', ''.join(traceback.format_exception(exc, value, tb))[-1500:])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if '--selftest' in argv:   # used by build.py: load everything without opening a window
        db = L.Database()
        print('affixes %d, bases %d, uniques %d, guides %d, icons %d, plans %s, backups -> %s' % (
            len(db.affixes), len(db.bases), len(db.uniques), len(L.load_guides()), len(L.Icons().bases),
            [n for n, _ in P.available()], L.BACKUP_ROOT))
        return 0
    App(argv[0] if argv else DEFAULT_FOLDER).mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
