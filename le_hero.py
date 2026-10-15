#!/usr/bin/env python3
"""Last Epoch Hero Editor: the main front end, laid out like the Diablo II Hero Editor.
One character per window; everything about it in topic tabs with directly editable fields:

  Character   name, class, mastery, level, experience, modes, gold, stats overview
  Skills      passive nodes with + / - buttons and an unspent counter, specialized skills and their nodes
  Items       paper doll, idols, inventory and a stash tab side by side, drag and drop between them,
              the item editor on the right
  Quests      campaign quests, waypoint checklist, one-time events, copy progress from another character
  Monolith    timeline unlocks and completion, corruption, blessings per timeline
  Misc        factions, tutorial and UI flags

Edits change the loaded file in memory at once (the Save button glows); Save writes with a backup.
Run: ./le_hero.py [saves folder]
"""
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import lesave as L
import theme
from le_editor2 import CELL, AddPage, GridView, IconCache, ItemForm, SlotView, idol_grid_size

WAYPOINTS = ["Z22", "Z32", "Z52", "Z72", "Z92", "Z102", "A06", "A10", "A30", "A45", "A60TR", "A60", "A70", "EoT", "A90",
             "B10", "B20", "B25", "B30", "B33", "B7S10", "B40", "B1S40", "A50", "B40TR", "B50", "B60", "B80", "C10", "C20",
             "C30", "C35", "C40", "C50", "C60", "C70", "D05", "D20", "D30", "D40", "D60", "E10", "D80", "E20", "E30", "E40",
             "E50", "E60", "E80", "E90", "F10", "F40", "F50", "F1S10", "F80", "F70", "F90", "F100", "F110", "G40", "G60",
             "G70", "G80", "G90", "G96", "G110", "G115", "H10", "G2S10", "H40", "H50", "H70", "Bazaar", "Observatory",
             "H80", "H100", "H110", "H120", "I10", "I20", "I40", "I50", "I70", "I80", "I100", "I120", "I130", "I140",
             "M_Rest", "MonolithHub", "WeaversHub", "M_Knight"]
ACTS = {'Z': 'Prologue', 'A': 'Act 1', 'B': 'Act 2', 'C': 'Act 3', 'D': 'Act 4', 'E': 'Act 5', 'F': 'Act 6', 'G': 'Act 7',
        'H': 'Act 8', 'I': 'Act 9', 'M': 'Monolith', 'W': 'Weaver', 'E_': 'End of Time'}
FACTIONS = {0: 'Circle of Fortune', 2: "Merchant's Guild (trade)", 3: "Merchant's Guild"}
FLAGS = ['hardcore', 'masochist', 'soloChallenge', 'soloCharacterChallenge', 'portalUnlocked', 'reachedTown',
         'clickedUnlockMasteriesButton', 'minionAIToggle', 'closedPassivesTooltip', 'closedSkillsTooltip',
         'closedMonolithTooltip', 'closedIdolsTooltip', 'closedTemporalShiftTooltip', 'closedMinSkillLevelTutorial',
         'closedAddEquipmentTooltip', 'closedForgingPotentialTooltip', 'closedUpgradeAffixTooltip', 'closedShatterEquipmentTooltip']


def scrollable(parent):
    """A frame whose content scrolls vertically; returns (outer, inner). The wheel is handled by the app."""
    outer = ttk.Frame(parent)
    canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, background=theme.BG)
    bar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    inner = ttk.Frame(canvas)
    window = canvas.create_window((0, 0), window=inner, anchor='nw')
    inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
    return outer, inner


class SpawnDialog(tk.Toplevel):
    """The main editor's Add items page in a window, aimed at one grid cell."""

    def __init__(self, app, save, x, y, page):
        super().__init__(app)
        self.title('Add item at cell %d,%d' % (x, y))
        self.transient(app)
        self.geometry('560x640')
        outer, inner = scrollable(self)
        outer.pack(fill='both', expand=True)
        self.page = AddPage(inner, app)
        self.page.pack(fill='both', expand=True)
        self.page.cell_target = (save, x, y)
        self.page.target_box.set('Clicked cell %d,%d' % (x, y))
        self.page.tabs.select({'Unique': 0, 'Custom': 1}.get(page, 0))
        app.spawn = self


def labeled(parent, row, text, widget):
    ttk.Label(parent, text=text).grid(row=row, column=0, sticky='w', pady=2, padx=(0, 6))
    widget.grid(row=row, column=1, sticky='w', pady=2)
    return widget


class Tab(ttk.Frame):
    def __init__(self, app):
        super().__init__(app.book, padding=10)
        self.app, self.db = app, app.db

    @property
    def j(self):
        return self.app.char.json if self.app.char else None

    def load(self):
        pass


# ------------------------------------------------------------------ Character
class CharacterTab(Tab):
    def __init__(self, app):
        super().__init__(app)
        left = ttk.LabelFrame(self, text='Character', padding=10)
        left.grid(row=0, column=0, sticky='nw')
        self.vars = {}
        self.name = labeled(left, 0, 'Name', ttk.Entry(left, width=24))
        self.name.bind('<FocusOut>', lambda e: self.set('characterName', self.name.get().strip()))
        self.klass = labeled(left, 1, 'Class', ttk.Combobox(left, state='readonly', width=14, values=[L.CLASSES[c] for c in sorted(L.CLASSES)]))
        self.klass.bind('<<ComboboxSelected>>', lambda e: self.class_changed())
        self.mastery = labeled(left, 2, 'Mastery', ttk.Combobox(left, state='readonly', width=14))
        self.mastery.bind('<<ComboboxSelected>>', lambda e: self.set('chosenMastery', self.mastery.current() + 1))
        self.level = tk.IntVar()
        labeled(left, 3, 'Level', ttk.Spinbox(left, from_=1, to=100, textvariable=self.level, width=6, command=lambda: self.set('level', self.level.get())))
        self.exp = tk.IntVar()
        labeled(left, 4, 'Experience', ttk.Spinbox(left, from_=0, to=10**9, textvariable=self.exp, width=10, command=lambda: self.set('currentExp', self.exp.get())))
        ttk.Button(left, text='Level 100', command=lambda: (self.level.set(100), self.exp.set(0), self.set('level', 100), self.set('currentExp', 0))).grid(row=5, column=1, sticky='w', pady=4)
        self.gold = tk.IntVar()
        labeled(left, 6, 'Gold (stash)', ttk.Spinbox(left, from_=0, to=10**9, textvariable=self.gold, width=10, command=self.set_gold))
        self.deaths = ttk.Label(left)
        labeled(left, 7, 'Deaths / playtime', self.deaths)
        for i, flag in enumerate(('hardcore', 'masochist', 'soloChallenge', 'soloCharacterChallenge')):
            v = tk.BooleanVar()
            self.vars[flag] = v
            ttk.Checkbutton(left, text={'soloChallenge': 'Solo Account Found', 'soloCharacterChallenge': 'Solo Character Found'}.get(flag, flag.title()),
                            variable=v, command=lambda f=flag: self.set(f, self.vars[f].get())).grid(row=8 + i, columnspan=2, sticky='w')
        self.points = ttk.Label(left, style='Dim.TLabel', wraplength=260, justify='left')
        self.points.grid(row=13, columnspan=2, sticky='w', pady=(8, 0))
        right = ttk.LabelFrame(self, text='Stats overview', padding=10)
        right.grid(row=0, column=1, sticky='nsew', padx=(12, 0))
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.summary = ttk.Treeview(right, columns=('value',), show='tree', height=22)
        self.summary.column('#0', width=150, stretch=False)
        self.summary.column('value', width=420)
        self.summary.pack(fill='both', expand=True)
        ttk.Label(right, style='Dim.TLabel', wraplength=520, justify='left', text=(
            'Sums of gear, idols, blessings, passives and class base; estimates (see the Stats page of the main editor).')).pack(anchor='w', pady=4)

    def set(self, key, value):
        if self.j is None:
            return
        self.j[key] = value
        self.app.changed('%s set.' % key)
        if key in ('level', 'chosenMastery', 'characterClass'):
            self.app.tabs['Skills'].load()
        self.refresh_summary()

    def set_gold(self):
        if self.app.stash:
            self.app.stash.json['gold'] = max(0, self.gold.get())
            self.app.dirty.add(self.app.stash)
            self.app.changed('Gold set.')

    def class_changed(self):
        if messagebox.askyesno('Change class', 'Changing the class keeps the trees, which then point at nodes of another class; '
                               'the game will reset them. Continue?'):
            self.set('characterClass', self.klass.current())
            self.fill_masteries()
        else:
            self.load()

    def fill_masteries(self):
        self.mastery['values'] = self.app.trees[self.klass.current()]['masteries']

    def load(self):
        j = self.j
        if not j:
            return
        self.name.delete(0, 'end')
        self.name.insert(0, j.get('characterName', ''))
        self.klass.current(j.get('characterClass', 0))
        self.fill_masteries()
        self.mastery.current(max(0, j.get('chosenMastery', 1) - 1))
        self.level.set(j.get('level', 1))
        self.exp.set(j.get('currentExp', 0))
        self.gold.set(self.app.stash.json.get('gold', 0) if self.app.stash else 0)
        self.deaths['text'] = '%d / %.1f h' % (j.get('deaths', 0), j.get('totalPlaytimePlayed', 0) / 3600)
        for flag, v in self.vars.items():
            v.set(bool(j.get(flag)))
        self.refresh_summary()

    def refresh_summary(self):
        j = self.j
        t = j.get('savedCharacterTree', {})
        spent = sum(t.get('nodePoints', []))
        self.points['text'] = 'Passives: %d spent, %d unspent in the file; budget at this level %d.' % (
            spent, t.get('unspentPoints', 0), j.get('level', 1) - 1 + L.PASSIVE_QUEST_POINTS)
        self.summary.delete(*self.summary.get_children())
        for label, text in L.character_stats(self.db, self.app.char, self.app.trees)[1]:
            self.summary.insert('', 'end', text=label, values=(text,))


# ------------------------------------------------------------------ Skills
class SkillsTab(Tab):
    def __init__(self, app):
        super().__init__(app)
        left = ttk.LabelFrame(self, text='Passive tree', padding=8)
        left.grid(row=0, column=0, sticky='nsew')
        self.passives = ttk.Treeview(left, columns=('id', 'points', 'max'), height=18)
        for col, text, width in (('#0', 'Node', 220), ('id', 'Id', 40), ('points', 'Points', 60), ('max', 'Max', 40)):
            self.passives.heading(col, text=text)
            self.passives.column(col, width=width, anchor='w' if col == '#0' else 'e')
        self.passives.pack(fill='both', expand=True)
        row = ttk.Frame(left)
        row.pack(fill='x', pady=4)
        ttk.Button(row, text='+', width=3, command=lambda: self.bump('passive', 1)).pack(side='left')
        ttk.Button(row, text='-', width=3, command=lambda: self.bump('passive', -1)).pack(side='left', padx=2)
        ttk.Button(row, text='Max', width=5, command=lambda: self.bump('passive', 99)).pack(side='left')
        self.unspent = tk.IntVar()
        ttk.Label(row, text='  Unspent:').pack(side='left')
        ttk.Spinbox(row, from_=0, to=200, textvariable=self.unspent, width=4, command=self.set_unspent).pack(side='left')
        row2 = ttk.Frame(left)
        row2.pack(fill='x')
        self.node_box = ttk.Combobox(row2, width=34)
        self.node_box.pack(side='left')
        ttk.Button(row2, text='Add node', command=self.add_passive).pack(side='left', padx=4)
        ttk.Button(row2, text='Reset tree', command=self.reset_passives).pack(side='left')
        right = ttk.LabelFrame(self, text='Specialized skills', padding=8)
        right.grid(row=0, column=1, sticky='nsew', padx=(12, 0))
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.skills = ttk.Treeview(right, columns=('tree', 'points', 'xp'), height=6)
        for col, text, width in (('#0', 'Slot / skill', 200), ('tree', 'Tree', 70), ('points', 'Points', 60), ('xp', 'XP', 90)):
            self.skills.heading(col, text=text)
            self.skills.column(col, width=width, anchor='w' if col == '#0' else 'e')
        self.skills.pack(fill='x')
        self.skills.bind('<<TreeviewSelect>>', lambda e: self.fill_skill_nodes())
        row = ttk.Frame(right)
        row.pack(fill='x', pady=4)
        self.skill_box = ttk.Combobox(row, state='readonly', width=24)
        self.skill_box.pack(side='left')
        ttk.Button(row, text='Specialize in slot', command=self.specialize).pack(side='left', padx=4)
        ttk.Button(row, text='Max XP', command=self.max_xp).pack(side='left')
        ttk.Button(row, text='Remove', command=self.unspecialize).pack(side='left', padx=4)
        self.nodes = ttk.Treeview(right, columns=('id', 'points', 'max'), height=10)
        for col, text, width in (('#0', 'Skill node', 220), ('id', 'Id', 40), ('points', 'Points', 60), ('max', 'Max', 40)):
            self.nodes.heading(col, text=text)
            self.nodes.column(col, width=width, anchor='w' if col == '#0' else 'e')
        self.nodes.pack(fill='both', expand=True)
        row = ttk.Frame(right)
        row.pack(fill='x', pady=4)
        ttk.Button(row, text='+', width=3, command=lambda: self.bump('skill', 1)).pack(side='left')
        ttk.Button(row, text='-', width=3, command=lambda: self.bump('skill', -1)).pack(side='left', padx=2)
        self.skill_node_box = ttk.Combobox(row, width=28)
        self.skill_node_box.pack(side='left', padx=6)
        ttk.Button(row, text='Add node', command=self.add_skill_node).pack(side='left')
        ttk.Label(right, style='Dim.TLabel', wraplength=420, justify='left', text=(
            'A level 20 skill owns 20 points; more than that in the file is reset by the game. Nodes are listed '
            'by the planner data; the game checks that each node is connected.')).pack(anchor='w')

    # -- passives
    def tree(self):
        return self.app.trees[self.j.get('characterClass', 0)]

    def load(self):
        if not self.j:
            return
        t = self.j.setdefault('savedCharacterTree', {'treeID': '', 'version': 12, 'nodeIDs': [], 'nodePoints': [], 'unspentPoints': 0, 'nodesTaken': None})
        self.passives.delete(*self.passives.get_children())
        nodes = self.tree()['passives']
        for nid, pts in zip(t['nodeIDs'], t['nodePoints']):
            info = nodes.get(str(nid))
            self.passives.insert('', 'end', iid='p%d' % nid, text=info[4] if info else 'node %d' % nid, values=(nid, pts, info[0] if info else '?'))
        self.unspent.set(t.get('unspentPoints', 0))
        self.node_box['values'] = ['%s: %s (max %d)' % (nid, info[4], info[0]) for nid, info in sorted(nodes.items(), key=lambda kv: int(kv[0]))]
        self.skills.delete(*self.skills.get_children())
        names = self.tree().get('skillNames', {})
        for st in self.j.get('savedSkillTrees', []):
            self.skills.insert('', 'end', iid='s%d' % st['slotNumber'], text='%d  %s' % (st['slotNumber'], names.get(st['treeID'], st['treeID'])),
                               values=(st['treeID'], sum(st['nodePoints']), st['xp']))
        self.skill_box['values'] = ['%s (%s)' % (label, tid) for tid, label in sorted(names.items(), key=lambda kv: kv[1])]
        self.nodes.delete(*self.nodes.get_children())

    def bump(self, kind, delta):
        if kind == 'passive':
            sel = self.passives.selection()
            if not sel:
                return self.app.say('Select a node.')
            nid = int(sel[0][1:])
            t = self.j['savedCharacterTree']
            i = t['nodeIDs'].index(nid)
            info = self.tree()['passives'].get(str(nid))
            limit = info[0] if info else 99
            t['nodePoints'][i] = max(0, min(limit, t['nodePoints'][i] + delta))
            if t['nodePoints'][i] == 0:
                del t['nodeIDs'][i]
                del t['nodePoints'][i]
            self.app.changed('Passive changed.')
            self.load()
            if t['nodeIDs'] and nid in t['nodeIDs']:
                self.passives.selection_set('p%d' % nid)
        else:
            st = self.current_skill()
            sel = self.nodes.selection()
            if not st or not sel:
                return self.app.say('Select a skill node.')
            nid = int(sel[0][1:])
            i = st['nodeIDs'].index(nid)
            info = self.tree()['skills'].get(st['treeID'], {}).get(str(nid))
            limit = info[0] if info else 99
            st['nodePoints'][i] = max(0, min(limit, st['nodePoints'][i] + delta))
            if st['nodePoints'][i] == 0:
                del st['nodeIDs'][i]
                del st['nodePoints'][i]
            self.app.changed('Skill node changed.')
            slot = st['slotNumber']
            self.load()
            self.skills.selection_set('s%d' % slot)
            self.fill_skill_nodes()

    def set_unspent(self):
        self.j['savedCharacterTree']['unspentPoints'] = max(0, self.unspent.get())
        self.app.changed('Unspent points set.')

    def add_passive(self):
        text = self.node_box.get()
        if not text or ':' not in text:
            return self.app.say('Pick a node from the list.')
        nid = int(text.split(':')[0])
        t = self.j['savedCharacterTree']
        if nid not in t['nodeIDs']:
            t['nodeIDs'].append(nid)
            t['nodePoints'].append(1)
            self.app.changed('Node added.')
            self.load()
            self.passives.selection_set('p%d' % nid)

    def reset_passives(self):
        if messagebox.askyesno('Reset', 'Remove every passive point? They become unspent.'):
            t = self.j['savedCharacterTree']
            t['unspentPoints'] = self.j.get('level', 1) - 1 + L.PASSIVE_QUEST_POINTS
            t['nodeIDs'], t['nodePoints'] = [], []
            self.app.changed('Passives reset.')
            self.load()

    # -- skills
    def current_skill(self):
        sel = self.skills.selection()
        if not sel:
            return None
        slot = int(sel[0][1:])
        return next((st for st in self.j.get('savedSkillTrees', []) if st['slotNumber'] == slot), None)

    def fill_skill_nodes(self):
        self.nodes.delete(*self.nodes.get_children())
        st = self.current_skill()
        if not st:
            return
        nodes = self.tree()['skills'].get(st['treeID'], {})
        for nid, pts in zip(st['nodeIDs'], st['nodePoints']):
            info = nodes.get(str(nid))
            self.nodes.insert('', 'end', iid='n%d' % nid, text=info[2] if info else 'node %d' % nid, values=(nid, pts, info[0] if info else '?'))
        self.skill_node_box['values'] = ['%s: %s (max %d)' % (nid, info[2], info[0]) for nid, info in sorted(nodes.items(), key=lambda kv: int(kv[0]))]

    def specialize(self):
        text = self.skill_box.get()
        if not text:
            return self.app.say('Pick a skill.')
        tid = text.rsplit('(', 1)[1].rstrip(')')
        trees = self.j.setdefault('savedSkillTrees', [])
        used = {st['slotNumber'] for st in trees}
        slot = next((s for s in range(5) if s not in used), None)
        if slot is None:
            return self.app.say('All five slots are used; remove one first.')
        if any(st['treeID'] == tid for st in trees):
            return self.app.say('Already specialized.')
        trees.append({'treeID': tid, 'slotNumber': slot, 'xp': L.SKILL_XP_MAX, 'version': 0, 'nodeIDs': [], 'nodePoints': [],
                      'unspentPoints': L.SKILL_POINTS, 'nodesTaken': None, 'abilityXP': 0.0})
        bar = self.j.setdefault('abilityBar', [''] * 5)
        if tid not in bar and '' in bar:
            bar[bar.index('')] = tid
        self.app.changed('Specialized %s.' % tid)
        self.load()

    def max_xp(self):
        st = self.current_skill()
        if st:
            st['xp'] = L.SKILL_XP_MAX
            self.app.changed('Skill XP maxed.')
            self.load()

    def unspecialize(self):
        st = self.current_skill()
        if st and messagebox.askyesno('Remove', 'Remove this specialization?'):
            self.j['savedSkillTrees'].remove(st)
            self.app.changed('Specialization removed.')
            self.load()

    def add_skill_node(self):
        st = self.current_skill()
        text = self.skill_node_box.get()
        if not st or ':' not in text:
            return self.app.say('Select a skill and pick a node.')
        nid = int(text.split(':')[0])
        if nid not in st['nodeIDs']:
            st['nodeIDs'].append(nid)
            st['nodePoints'].append(1)
            self.app.changed('Skill node added.')
            slot = st['slotNumber']
            self.load()
            self.skills.selection_set('s%d' % slot)
            self.fill_skill_nodes()


# ------------------------------------------------------------------ Items
class ItemsTab(Tab):
    """Paper doll, idols, inventory and a stash tab as grids with drag and drop; the item editor beside them."""

    def __init__(self, app):
        super().__init__(app)
        grids = ttk.Frame(self)
        grids.grid(row=0, column=0, sticky='nw')
        self.views = {}
        for col, (key, title) in enumerate((('slots', 'Wielded'), ('idols', 'Idols'), ('inv', 'Inventory'))):
            f = ttk.Frame(grids)
            f.grid(row=0, column=col, sticky='n', padx=(0, 10))
            ttk.Label(f, text=title, style='Head.TLabel').pack(anchor='w')
            if key == 'slots':
                v = SlotView(f, self.db, app.icons, lambda i: self.pick(self.app.char, i))
            else:
                v = GridView(f, self.db, app.icons, (lambda k: lambda i: self.pick(self.app.char, i))(key))
            v.pack(anchor='w')
            self.views[key] = v
        f = ttk.Frame(grids)
        f.grid(row=1, column=0, columnspan=3, sticky='w', pady=(8, 0))
        row = ttk.Frame(f)
        row.pack(fill='x')
        ttk.Label(row, text='Stash', style='Head.TLabel').pack(side='left')
        ttk.Label(row, text=' category').pack(side='left')
        self.cat_box = ttk.Combobox(row, state='readonly', width=18)
        self.cat_box.pack(side='left', padx=4)
        self.cat_box.bind('<<ComboboxSelected>>', lambda e: self.fill_tabs())
        ttk.Label(row, text='tab').pack(side='left')
        self.tab_box = ttk.Combobox(row, state='readonly', width=30)
        self.tab_box.pack(side='left', padx=4)
        self.tab_box.bind('<<ComboboxSelected>>', lambda e: self.draw())
        self.views['stash'] = GridView(f, self.db, app.icons, lambda i: self.pick(self.tab(), i))
        self.views['stash'].pack(anchor='w')
        ttk.Label(grids, style='Dim.TLabel', wraplength=560, justify='left', text=(
            'Drag an item between the inventory, the stash tab and the idol grid; drop on an empty spot. '
            'Click an item to edit it on the right; right-click a cell to add, paste, edit or delete there.')
        ).grid(row=2, column=0, columnspan=3, sticky='w', pady=4)
        for key in ('inv', 'stash', 'idols'):
            self.views[key].on_menu = (lambda k: lambda e, x, y, i: self.grid_menu(e, k, x, y, i))(key)
        for key, v in self.views.items():
            v.bind('<ButtonPress-1>', lambda e, k=key: self.drag_start(e, k), add='+')
            v.bind('<ButtonRelease-1>', lambda e, k=key: self.drag_end(e, k), add='+')
        self.drag = None
        outer, inner = scrollable(self)
        outer.grid(row=0, column=1, sticky='nsew', padx=(12, 0))
        self.form = ItemForm(inner, app)
        self.form.pack(fill='both', expand=True)
        app.form = self.form
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

    def tab(self):
        name = self.tab_box.get().split('  [', 1)[-1].rstrip(']') if self.tab_box.get() else None
        return self.app.tabs_files.get(name)

    def save_for(self, key):
        return self.tab() if key == 'stash' else self.app.char

    def load(self):
        cats = L.stash_categories(self.app.stash) if self.app.stash else {0: 'General'}
        self.cat_box['values'] = ['%d: %s' % (i, n) for i, n in sorted(cats.items())]
        if self.cat_box['values'] and not self.cat_box.get():
            self.cat_box.current(0)
        self.fill_tabs(keep=self.tab_box.get())

    def fill_tabs(self, keep=None):
        cat = int(self.cat_box.get().split(':')[0]) if self.cat_box.get() else 0
        values = ['%s  [%s]' % (t.json.get('displayName', n), n) for n, t in self.app.tabs_files.items() if t.json.get('categoryId', 0) == cat]
        self.tab_box['values'] = values
        if keep in values:
            self.tab_box.set(keep)
        elif values:
            self.tab_box.current(0)
        else:
            self.tab_box.set('')
        self.draw()

    def grid_menu(self, event, key, x, y, index):
        save = self.save_for(key)
        if save is None:
            return self.app.say('Choose a stash tab first.')
        container = {'inv': L.INVENTORY_ID, 'idols': 29, 'stash': L.INVENTORY_ID}[key]
        menu = tk.Menu(self, tearoff=0, background=theme.PANEL, foreground=theme.TEXT,
                       activebackground=theme.SELECT, activeforeground=theme.GOLD_LIGHT)
        menu.add_command(label='Cell %d,%d' % (x, y), state='disabled')
        menu.add_separator()
        if index is None:
            if key != 'idols':
                menu.add_command(label='Add unique here...', command=lambda: SpawnDialog(self.app, save, x, y, 'Unique'))
                menu.add_command(label='Add custom item here...', command=lambda: SpawnDialog(self.app, save, x, y, 'Custom'))
            if self.form.item:
                menu.add_command(label='Paste a copy of %s here' % L.item_title(self.db, self.form.item),
                                 command=lambda: self.app.put_here(save, x, y, dict(self.form.build() or self.form.item, uid=None), container))
        else:
            menu.add_command(label='Copy to inventory', command=lambda: self.form.copy_to('inventory'))
            menu.add_command(label='Copy to stash tab', command=lambda: self.form.copy_to('stash'))
            menu.add_separator()
            menu.add_command(label='Delete', command=self.form.delete)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def draw(self, selected=()):
        char = self.app.char
        self.views['slots'].draw(char, selected)
        self.views['idols'].draw(char, 29, selected, size=idol_grid_size(self.db, char))
        self.views['inv'].draw(char, L.INVENTORY_ID, selected)
        self.views['stash'].draw(self.tab(), selected=selected)

    def pick(self, save, index):
        if save is None:
            return
        self.form.show(save, index)
        self.draw({index} if save is self.app.char else ())

    # drag and drop between grids
    def drag_start(self, event, key):
        v = self.views[key]
        hit = [t for t in v.gettags('current') if t.startswith('idx')]
        if hit:
            self.drag = (key, int(hit[0][3:]))

    def drag_end(self, event, key):
        if not self.drag:
            return
        src_key, index = self.drag
        self.drag = None
        target = self.winfo_containing(event.x_root, event.y_root)
        dst_key = next((k for k, v in self.views.items() if v is target), None)
        if dst_key is None or dst_key == 'slots':
            return
        src = self.tab() if src_key == 'stash' else self.app.char
        dst = self.tab() if dst_key == 'stash' else self.app.char
        if src is None or dst is None:
            return
        x = (event.x_root - target.winfo_rootx() - 2) // CELL
        y = (event.y_root - target.winfo_rooty() - 2) // CELL
        if dst_key == src_key and src.items[index]['inventoryPosition'] == {'x': x, 'y': y}:
            return
        entry = src.items[index]
        item = L.decode(entry['data'])
        if not item:
            return self.app.say('Only equipment items can be moved.')
        container = {'inv': L.INVENTORY_ID, 'idols': 29, 'stash': None}[dst_key]
        del src.items[index]
        try:
            L.place_item(self.db, dst, item, x, y, container if container else L.INVENTORY_ID)
        except ValueError as e:
            src.items.insert(index, entry)
            return self.app.say('Cannot drop there: %s' % e)
        if src is not dst:
            self.app.dirty.add(src)
        self.app.dirty.add(dst)
        self.app.changed('Moved %s.' % L.item_title(self.db, item))


# ------------------------------------------------------------------ Quests and waypoints
class QuestsTab(Tab):
    def __init__(self, app):
        super().__init__(app)
        left = ttk.LabelFrame(self, text='Waypoints (click to toggle)', padding=8)
        left.grid(row=0, column=0, sticky='nsew')
        self.wp = ttk.Treeview(left, columns=('on',), height=24)
        self.wp.heading('#0', text='Scene')
        self.wp.heading('on', text='Unlocked')
        self.wp.column('#0', width=200)
        self.wp.column('on', width=80, anchor='center')
        self.wp.pack(fill='both', expand=True)
        self.wp.bind('<Button-1>', self.toggle_wp)
        row = ttk.Frame(left)
        row.pack(fill='x', pady=4)
        ttk.Button(row, text='Unlock all', command=lambda: self.set_all_wp(True)).pack(side='left')
        ttk.Button(row, text='Lock all', command=lambda: self.set_all_wp(False)).pack(side='left', padx=4)
        right = ttk.LabelFrame(self, text='Quests and events', padding=8)
        right.grid(row=0, column=1, sticky='nsew', padx=(12, 0))
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.quests = ttk.Treeview(right, columns=('step', 'done', 'state'), height=16)
        for col, text, width in (('#0', 'Quest id', 80), ('step', 'Step', 60), ('done', 'Objectives done', 110), ('state', 'State', 50)):
            self.quests.heading(col, text=text)
            self.quests.column(col, width=width, anchor='e' if col != '#0' else 'w')
        self.quests.pack(fill='both', expand=True)
        self.events = ttk.Label(right, style='Dim.TLabel', wraplength=420, justify='left')
        self.events.pack(anchor='w', pady=4)
        row = ttk.Frame(right)
        row.pack(fill='x')
        ttk.Button(row, text='Copy campaign progress from...', command=self.copy_progress).pack(side='left')
        ttk.Button(row, text='Remove quest', command=self.remove_quest).pack(side='left', padx=4)
        ttk.Label(right, style='Dim.TLabel', wraplength=420, justify='left', text=(
            'Quest names are not in the data; records are shown by id. "Copy campaign progress" takes quests, '
            'waypoints, scenes, events, monolith and faction state from another character, the way New character does.')).pack(anchor='w')

    def load(self):
        j = self.j
        if not j:
            return
        self.wp.delete(*self.wp.get_children())
        have = set(j.get('unlockedWaypointScenes', []))
        groups = {}
        for code in WAYPOINTS + sorted(have - set(WAYPOINTS)):
            act = ACTS.get(code[0], 'Other') if code[0] in 'ZABCDEFGHI' else 'Hubs'
            if act not in groups:
                groups[act] = self.wp.insert('', 'end', iid='g' + act, text=act, open=True)
            self.wp.insert(groups[act], 'end', iid='w' + code, text=code, values=('yes' if code in have else '-',))
        self.quests.delete(*self.quests.get_children())
        for q in j.get('savedQuests', []):
            self.quests.insert('', 'end', iid='q%d' % q['questID'], text=str(q['questID']),
                               values=(q.get('questStepID'), len(q.get('completeObjectives', [])), q.get('state')))
        self.events['text'] = '%d quest records, %d one-time events, %d scene records, mastery %s.' % (
            len(j.get('savedQuests', [])), len(j.get('oneTimeEvents', [])), len(j.get('sceneProgresses', [])),
            'unlocked' if L.MASTERY_EVENT in j.get('oneTimeEvents', []) else 'locked')

    def toggle_wp(self, event):
        iid = self.wp.identify_row(event.y)
        if not iid or not iid.startswith('w'):
            return
        code = iid[1:]
        wps = self.j.setdefault('unlockedWaypointScenes', [])
        if code in wps:
            wps.remove(code)
        else:
            wps.append(code)
        self.app.changed('Waypoint %s toggled.' % code)
        self.load()

    def set_all_wp(self, on):
        self.j['unlockedWaypointScenes'] = list(WAYPOINTS) if on else []
        self.app.changed('Waypoints changed.')
        self.load()

    def remove_quest(self):
        sel = self.quests.selection()
        if sel:
            qid = int(sel[0][1:])
            self.j['savedQuests'] = [q for q in self.j['savedQuests'] if q['questID'] != qid]
            self.app.changed('Quest %d removed.' % qid)
            self.load()

    def copy_progress(self):
        others = [c for c in self.app.char_files if c != self.app.char.name]
        if not others:
            return self.app.say('No other character.')
        pick = simpledialog.askstring('Copy progress', 'Character file to copy from:\n' + '\n'.join(others), initialvalue=others[-1], parent=self.app)
        if not pick or pick not in others:
            return
        src = L.SaveFile(os.path.join(self.app.folder, pick)).json
        import copy
        for k in L.PROGRESS_FIELDS:
            if k in src:
                self.j[k] = copy.deepcopy(src[k])
        self.app.changed('Progress copied from %s.' % pick)
        self.app.load_tabs()


# ------------------------------------------------------------------ Monolith and blessings
class MonolithTab(Tab):
    def __init__(self, app):
        super().__init__(app)
        left = ttk.LabelFrame(self, text='Timelines', padding=8)
        left.grid(row=0, column=0, sticky='nsew')
        self.tl = ttk.Treeview(left, columns=('unlock', 'done', 'diff'), height=12)
        for col, text, width in (('#0', 'Timeline', 80), ('unlock', 'Unlocks', 90), ('done', 'Completion', 90), ('diff', 'Difficulty', 90)):
            self.tl.heading(col, text=text)
            self.tl.column(col, width=width, anchor='center')
        self.tl.pack(fill='x')
        row = ttk.Frame(left)
        row.pack(fill='x', pady=4)
        ttk.Button(row, text='Unlock all (normal + empowered)', command=self.unlock_all).pack(side='left')
        grid = ttk.Frame(left)
        grid.pack(fill='x', pady=4)
        self.corr = tk.IntVar()
        labeled(grid, 0, 'Max corruption', ttk.Spinbox(grid, from_=0, to=10000, textvariable=self.corr, width=7, command=lambda: self.setnum('maxCorruption', self.corr)))
        self.echoes = tk.IntVar()
        labeled(grid, 1, 'Echoes conquered', ttk.Spinbox(grid, from_=0, to=100000, textvariable=self.echoes, width=7, command=lambda: self.setnum('monolithEchoesConquered', self.echoes)))
        self.tls = tk.IntVar()
        labeled(grid, 2, 'Timelines conquered', ttk.Spinbox(grid, from_=0, to=100, textvariable=self.tls, width=7, command=lambda: self.setnum('monolithTimelinesConquered', self.tls)))
        right = ttk.LabelFrame(self, text='Blessings (one per timeline container)', padding=8)
        right.grid(row=0, column=1, sticky='nsew', padx=(12, 0))
        self.columnconfigure(1, weight=1)
        self.bless = ttk.Treeview(right, columns=('name', 'roll'), height=12)
        for col, text, width in (('#0', 'Container', 80), ('name', 'Blessing', 260), ('roll', 'Roll %', 60)):
            self.bless.heading(col, text=text)
            self.bless.column(col, width=width)
        self.bless.pack(fill='both', expand=True)
        row = ttk.Frame(right)
        row.pack(fill='x', pady=4)
        names = sorted((b['subTypeID'], b['name']) for b in self.db.bases.values() if b['baseTypeID'] == 34)
        self.bless_box = ttk.Combobox(row, width=36, values=['%d: %s' % n for n in names])
        self.bless_box.pack(side='left')
        self.bless_box.bind('<KeyRelease>', lambda e: self.app.filter_box(self.bless_box, ['%d: %s' % n for n in names]))
        ttk.Button(row, text='Set in container', command=self.set_blessing).pack(side='left', padx=4)
        ttk.Button(row, text='Remove', command=self.remove_blessing).pack(side='left')

    def load(self):
        j = self.j
        if not j:
            return
        self.tl.delete(*self.tl.get_children())
        by = lambda key: {t['timelineID']: t['progress'] for t in j.get(key, [])}
        un, done, diff = by('timelineDifficultyUnlocks'), by('timelineCompletion'), by('timelineDifficultyCompletion')
        for tid in sorted(set(un) | set(done) | set(range(1, 11))):
            self.tl.insert('', 'end', iid='t%d' % tid, text=str(tid), values=(un.get(tid, '-'), done.get(tid, '-'), diff.get(tid, '-')))
        self.corr.set(j.get('maxCorruption', 0))
        self.echoes.set(j.get('monolithEchoesConquered', 0))
        self.tls.set(j.get('monolithTimelinesConquered', 0))
        self.bless.delete(*self.bless.get_children())
        for c in L.BLESSING_SLOTS:
            e = next((e for e in self.app.char.items if e.get('containerID') == c), None)
            item = L.decode(e['data']) if e else None
            self.bless.insert('', 'end', iid='b%d' % c, text=str(c),
                              values=(L.item_title(self.db, item) if item else '-', round(item['implicits'][0] / 2.55) if item else ''))

    def setnum(self, key, var):
        self.j[key] = max(0, var.get())
        self.app.changed('%s set.' % key)

    def unlock_all(self):
        self.j['timelineDifficultyUnlocks'] = [{'timelineID': t, 'progress': [0, 1]} for t in range(1, 11)]
        self.app.changed('Timelines unlocked.')
        self.load()

    def set_blessing(self):
        sel = self.bless.selection()
        text = self.bless_box.get()
        if not sel or ':' not in text:
            return self.app.say('Select a container and pick a blessing.')
        c = int(sel[0][1:])
        sub = int(text.split(':')[0])
        self.app.char.json['savedItems'] = [e for e in self.app.char.items if e.get('containerID') != c]
        self.app.char.items.append(L._entry(L.make_item(self.db, 34, sub, fp=0), c, self.app.char.item_version()))
        self.app.changed('Blessing set.')
        self.load()

    def remove_blessing(self):
        sel = self.bless.selection()
        if sel:
            c = int(sel[0][1:])
            self.app.char.json['savedItems'] = [e for e in self.app.char.items if e.get('containerID') != c]
            self.app.changed('Blessing removed.')
            self.load()


# ------------------------------------------------------------------ Misc
class MiscTab(Tab):
    def __init__(self, app):
        super().__init__(app)
        left = ttk.LabelFrame(self, text='Factions', padding=8)
        left.grid(row=0, column=0, sticky='nw')
        self.fvars = {}
        for r, (fid, name) in enumerate(FACTIONS.items()):
            ttk.Label(left, text=name).grid(row=r, column=0, sticky='w', padx=(0, 8))
            for c, key in enumerate(('rank', 'reputation', 'favor')):
                v = tk.IntVar()
                self.fvars[(fid, key)] = v
                ttk.Label(left, text=key, style='Dim.TLabel').grid(row=r, column=1 + 2 * c, sticky='e')
                ttk.Spinbox(left, from_=0, to=10**7, textvariable=v, width=8, command=lambda f=fid, k=key: self.set_faction(f, k)).grid(row=r, column=2 + 2 * c, padx=(2, 8))
        right = ttk.LabelFrame(self, text='Flags', padding=8)
        right.grid(row=0, column=1, sticky='nw', padx=(12, 0))
        self.flags = {}
        for i, flag in enumerate(FLAGS):
            v = tk.BooleanVar()
            self.flags[flag] = v
            ttk.Checkbutton(right, text=flag, variable=v, command=lambda f=flag: self.set_flag(f)).grid(row=i % 9, column=i // 9, sticky='w', padx=(0, 12))

    def load(self):
        j = self.j
        if not j:
            return
        for (fid, key), v in self.fvars.items():
            v.set(j.get('factions', {}).get(str(fid), {}).get(key, 0))
        for flag, v in self.flags.items():
            v.set(bool(j.get(flag)))

    def set_faction(self, fid, key):
        f = self.j.setdefault('factions', {}).setdefault(str(fid), {'id': fid, 'isMember': True, 'hasEverJoined': True, 'rank': 0, 'reputation': 0, 'favor': 0, 'factionSpecific': {}})
        f[key] = max(0, self.fvars[(fid, key)].get())
        f['isMember'] = f['hasEverJoined'] = True
        self.app.changed('Faction %s set.' % key)

    def set_flag(self, flag):
        self.j[flag] = self.flags[flag].get()
        self.app.changed('%s set.' % flag)


# ------------------------------------------------------------------ Application
class HeroEditor(tk.Tk):
    def __init__(self, folder):
        super().__init__()
        self.title('Last Epoch Hero Editor')
        self.geometry('1280x780')
        self.glow_styles = theme.apply(self)
        self.db = L.Database()
        self.icons = IconCache()
        self.trees = L.load_trees()
        self.folder = folder
        self.char = self.stash = None
        self.char_files, self.tabs_files = [], {}
        self.dirty = set()
        self.glow_phase = None
        self.form = None
        for seq in ('<Button-4>', '<Button-5>', '<MouseWheel>'):
            self.bind_all(seq, self.wheel_anywhere, add='+')
        top = ttk.Frame(self, padding=6)
        top.pack(fill='x')
        ttk.Button(top, text='Saves folder...', command=self.browse).pack(side='left')
        ttk.Label(top, text='  Character:').pack(side='left')
        self.char_box = ttk.Combobox(top, state='readonly', width=42)
        self.char_box.pack(side='left')
        self.char_box.bind('<<ComboboxSelected>>', lambda e: self.load_character())
        self.save_button = ttk.Button(top, text='Save', command=self.save)
        self.save_button.pack(side='right')
        ttk.Button(top, text='Reload', command=lambda: self.load_folder(self.folder)).pack(side='right', padx=4)
        ttk.Button(top, text='Backup folder', command=self.backup).pack(side='right')
        self.status = ttk.Label(self, anchor='w', style='Status.TLabel')
        self.status.pack(fill='x', side='bottom')
        self.book = ttk.Notebook(self)
        self.book.pack(fill='both', expand=True, padx=6, pady=4)
        self.tabs = {}
        for name, cls in (('Character', CharacterTab), ('Skills', SkillsTab), ('Items', ItemsTab),
                          ('Quests', QuestsTab), ('Monolith', MonolithTab), ('Misc', MiscTab)):
            self.tabs[name] = cls(self)
            self.book.add(self.tabs[name], text=name)
        self.load_folder(folder)

    # the pieces ItemForm expects from an app
    def say(self, text):
        self.status['text'] = text
        self.update_glow()

    def set_text(self, widget, text):
        widget['state'] = 'normal'
        widget.delete('1.0', 'end')
        widget.insert('1.0', text)
        widget['state'] = 'disabled'

    def filter_box(self, box, values):
        words = box.get().lower().split()
        box['values'] = [v for v in values if all(w in v.lower() for w in words)]

    def current_tab(self):
        return self.tabs['Items'].tab()

    def put(self, save, items, container=L.INVENTORY_ID):
        left = L.add_items(self.db, save, items, container)
        self.dirty.add(save)
        self.changed('Added %d item(s).' % (len(items) - len(left)) + (' No room for %d.' % len(left) if left else ''))

    def put_here(self, save, x, y, item, container=L.INVENTORY_ID):
        try:
            L.place_item(self.db, save, item, x, y, container)
        except ValueError as e:
            return self.say('Cannot place it: %s' % e)
        self.dirty.add(save)
        self.changed('Placed %s at %d,%d.' % (L.item_title(self.db, item), x, y))

    def write_tabs(self, groups):
        self.say('Writing whole stash tabs is a main editor feature; add one tab\'s items instead.')

    def wheel_anywhere(self, event):
        widget = event.widget
        while widget is not None and not isinstance(widget, tk.Canvas):
            if isinstance(widget, (tk.Text, tk.Listbox, ttk.Treeview, ttk.Combobox)):
                return
            widget = getattr(widget, 'master', None)
        if isinstance(widget, tk.Canvas) and widget.cget('yscrollcommand'):
            widget.yview_scroll(-3 if (event.num == 4 or event.delta > 0) else 3, 'units')

    def changed(self, message, save=None):
        """Marks a file dirty and refreshes; accepts (message, save) and the item form's (save, message)."""
        if isinstance(message, L.SaveFile) or (message is None and isinstance(save, str)):
            message, save = save, message
        if save is not None:
            self.dirty.add(save)
        elif self.char:
            self.dirty.add(self.char)
        self.say(message + '  (not saved)')
        self.tabs['Items'].draw()
        self.tabs['Character'].refresh_summary()

    def current_tab_or_none(self):
        return self.tabs['Items'].tab()

    def update_glow(self):
        if self.dirty and self.glow_phase is None:
            self.glow_phase = 0
            self.pulse()
        elif not self.dirty and self.glow_phase is not None:
            self.glow_phase = None
            self.save_button.configure(style='TButton', text='Save')

    def pulse(self):
        if self.glow_phase is None:
            return
        if not self.dirty:
            return self.update_glow()
        import math
        k = 0.5 + 0.5 * math.sin(self.glow_phase / 9.0)
        self.save_button.configure(style=self.glow_styles[round(k * (len(self.glow_styles) - 1))], text='Save *')
        self.glow_phase += 1
        self.after(60, self.pulse)

    # loading
    def browse(self):
        folder = filedialog.askdirectory(initialdir=self.folder, title='Last Epoch Saves folder')
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder):
        if self.dirty and not messagebox.askyesno('Reload', 'Discard unsaved changes?'):
            return
        self.folder = folder
        self.dirty.clear()
        self.update_glow()
        chars, stashes, _ = L.list_saves(folder) if os.path.isdir(folder) else ([], [], [])
        self.char_files, self.stash_files = chars, stashes
        labels = []
        for name in chars:
            j = L.SaveFile(os.path.join(folder, name)).json
            labels.append('%s  -  %s, level %s %s' % (name, j.get('characterName'), j.get('level'), L.CLASSES.get(j.get('characterClass'), '')))
        self.char_box['values'] = labels
        if not chars:
            return self.say('No character files in ' + folder)
        newest = max(range(len(chars)), key=lambda i: os.path.getmtime(os.path.join(folder, chars[i])))
        self.char_box.current(newest)
        self.load_character()

    def load_character(self):
        self.char = L.SaveFile(os.path.join(self.folder, self.char_files[self.char_box.current()]))
        cycle = self.char.json.get('cycle')
        match = [s for s in self.stash_files if cycle is not None and ('CYCLE_%s_' % cycle) in s] or self.stash_files
        self.stash = L.SaveFile(os.path.join(self.folder, match[0])) if match else None
        self.tabs_files = {}
        if self.stash:
            for name in self.stash.json.get('tabsv2', []):
                path = os.path.join(self.folder, name)
                if os.path.isfile(path):
                    self.tabs_files[name] = L.SaveFile(path)
        self.load_tabs()
        self.say('Loaded %s.' % self.char.name)

    def load_tabs(self):
        for t in self.tabs.values():
            t.load()

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
        out = L.backup_folder(self.folder, 'full')
        self.say('Backed up %d file(s) to %s' % (len(os.listdir(out)), out))

    def report_callback_exception(self, exc, value, tb):
        import traceback
        messagebox.showerror('Error', ''.join(traceback.format_exception(exc, value, tb))[-1500:])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if '--selftest' in argv:   # used by build.py: load everything without opening a window
        db = L.Database()
        print('affixes %d, bases %d, uniques %d, guides %d, icons %d, classes %d, backups -> %s' % (
            len(db.affixes), len(db.bases), len(db.uniques), len(L.load_guides()), len(L.Icons().bases),
            len(L.load_trees()), L.BACKUP_ROOT))
        return 0
    folder = argv[0] if argv else (L.find_game_folder() or os.path.join(L.HERE, 'Saves', 'Saves'))
    HeroEditor(folder).mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
