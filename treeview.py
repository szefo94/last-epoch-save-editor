"""Graphical passive and skill trees: nodes at the planner's positions with the game's icons, links
between them, left click to allocate a point and right click to take one back, within the rules the
game applies (node maximum, point budget, a linked node with enough points, mastery requirement)."""
import math
import tkinter as tk
from tkinter import ttk

import lesave as L
import theme

ZOOMS = [0.5, 0.75, 1.0, 1.5, 2.0]
ICON = 42                    # native sprite size
MASTERY_OPEN = 25            # nodes of another mastery open up to this requirement, deeper ones need the mastery
PANEL_GAP = 60


class TreeView(tk.Canvas):
    """nodes: {id: record} from trees2.json; alloc: {id: points}; budget: points available in total.
    on_change(alloc) is called after every successful click. For passives, pass masteries (names),
    chosen (1-3) and the records carry 'mastery' / 'req'; for skills they do not."""

    def __init__(self, parent, app, nodes, alloc, budget, on_change, masteries=None, chosen=None, title=''):
        super().__init__(parent, background=theme.BG, highlightthickness=0, cursor='hand2')
        self.app, self.nodes, self.alloc, self.budget, self.on_change = app, nodes, dict(alloc), budget, on_change
        self.masteries, self.chosen, self.title = masteries, chosen, title
        self.zoom = 1.0
        self.offset = [0, 0]
        self.images = {}
        self.tip = None
        self.layout()
        self.bind('<Configure>', lambda e: self.redraw())
        self.bind('<Button-1>', self.left)
        self.bind('<Button-3>', self.right)
        self.bind('<Motion>', self.hover)
        self.bind('<ButtonPress-2>', self.pan_start)
        self.bind('<B2-Motion>', self.pan_move)
        self.bind('<Control-Button-4>', lambda e: self.set_zoom(1))
        self.bind('<Control-Button-5>', lambda e: self.set_zoom(-1))
        self.bind('<Control-MouseWheel>', lambda e: self.set_zoom(1 if e.delta > 0 else -1))

    # ---------------------------------------------------------------- layout
    def layout(self):
        """Positions in tree units. Passive trees have four sections (class, then each mastery) that the
        planner stores in overlapping frames, so the masteries are stacked below the class tree."""
        self.pos = {}
        groups = {}
        for nid, n in self.nodes.items():
            groups.setdefault(n.get('mastery', 0), []).append(nid)
        y0 = 0
        self.sections = []
        self.section_root = {}
        for g in sorted(groups):
            ids = groups[g]
            ys = [self.nodes[i]['y'] for i in ids]
            top, bottom = min(ys), max(ys)
            self.section_root[g] = (0, y0 - top)        # the section's root sits at the planner's origin
            for i in ids:
                self.pos[i] = (self.nodes[i]['x'], self.nodes[i]['y'] - top + y0)
            label = (self.masteries[g - 1] if self.masteries and g else self.title) if g or self.masteries else self.title
            self.sections.append((label, y0 - PANEL_GAP / 2, y0 + bottom - top + PANEL_GAP / 2, g))
            y0 += bottom - top + PANEL_GAP + 40
        self.root_pos = self.section_root.get(0)
        xs = [p[0] for p in self.pos.values()]
        self.bounds = (min(xs) - 60, -PANEL_GAP, max(xs) + 60, y0)

    def to_screen(self, x, y):
        return (x - self.bounds[0]) * self.zoom + self.offset[0] + 20, (y - self.bounds[1]) * self.zoom + self.offset[1] + 20

    def set_zoom(self, step):
        i = ZOOMS.index(self.zoom)
        self.zoom = ZOOMS[max(0, min(len(ZOOMS) - 1, i + step))]
        self.redraw()

    def fit(self):
        w, h = self.winfo_width(), self.winfo_height()
        bw, bh = self.bounds[2] - self.bounds[0], self.bounds[3] - self.bounds[1]
        fitting = [z for z in ZOOMS if z * bw <= w - 40 and z * bh <= h - 40]
        self.zoom = max(fitting) if fitting else ZOOMS[0]
        self.offset = [0, 0]
        self.redraw()

    def pan_start(self, e):
        self.drag = (e.x, e.y)

    def pan_move(self, e):
        self.offset[0] += e.x - self.drag[0]
        self.offset[1] += e.y - self.drag[1]
        self.drag = (e.x, e.y)
        self.redraw()

    def icon(self, name):
        """The sprite for an icon name at the current zoom, or None. A '-hex' name is a hexagonal frame
        drawn over the plain icon, so it is returned as a list of layers."""
        key = (name, self.zoom)
        if key not in self.images:
            layers = []
            names = [name[:-4], name] if name.endswith('-hex') else [name]
            for candidate in names:
                png = L.read_bytes('data', 'tree_icons', candidate + '.png')
                if png:
                    img = tk.PhotoImage(data=png)
                    if self.zoom <= 0.5:
                        img = img.subsample(2)
                    elif self.zoom >= 1.5:
                        img = img.zoom(2)
                    layers.append(img)
            self.images[key] = layers
        return self.images[key]

    # ---------------------------------------------------------------- rules
    def spent(self, mastery=None):
        return sum(p for i, p in self.alloc.items() if mastery is None or self.nodes[i].get('mastery', 0) == mastery)

    def reachable(self, nid):
        n = self.nodes[nid]
        if not n['in']:
            return True
        for src, req in n['in']:
            if src == -1 or self.alloc.get(src, 0) >= max(1, req):
                return True
        return any(self.alloc.get(o, 0) > 0 for o in self.outs.get(nid, ()))

    @property
    def outs(self):
        if not hasattr(self, '_outs'):
            self._outs = {}
            for nid, n in self.nodes.items():
                for src, _ in n['in']:
                    self._outs.setdefault(src, []).append(nid)
        return self._outs

    def why_not(self, nid):
        """None when a point can be added, else the reason."""
        n = self.nodes[nid]
        if self.alloc.get(nid, 0) >= n['max']:
            return 'already at its maximum of %d' % n['max']
        if self.spent() >= self.budget:
            return 'no points left (%d of %d spent)' % (self.spent(), self.budget)
        m = n.get('mastery', 0)
        if m and self.chosen is not None and m != self.chosen and n.get('req', 0) >= MASTERY_OPEN:
            return 'needs the %s mastery' % (self.masteries[m - 1] if self.masteries else 'other')
        if n.get('req', 0) > self.spent(m if m else 0):
            return 'needs %d points in %s first (%d spent)' % (n['req'], self.masteries[m - 1] if m and self.masteries else 'the class tree', self.spent(m if m else 0))
        if not self.reachable(nid):
            return 'not connected to an allocated node'
        return None

    def orphaned_by(self, nid):
        """Nodes that would lose their only link if nid dropped to zero."""
        lost = []
        for o in self.outs.get(nid, ()):
            if self.alloc.get(o, 0) > 0:
                others = [s for s, r in self.nodes[o]['in'] if s != nid and (s == -1 or self.alloc.get(s, 0) >= max(1, r))]
                if not others and not any(self.alloc.get(x, 0) > 0 for x in self.outs.get(o, ()) if x != nid):
                    lost.append(o)
        return lost

    def left(self, e):
        nid = self.hit(e.x, e.y)
        if nid is None:
            return
        reason = self.why_not(nid)
        if reason:
            self.flash(nid)
            return self.app.say('%s: %s.' % (self.nodes[nid]['name'], reason))
        self.alloc[nid] = self.alloc.get(nid, 0) + 1
        self.on_change(self.alloc)
        self.redraw()
        self.app.say('%s: %d / %d.  %d of %d points spent.' % (self.nodes[nid]['name'], self.alloc[nid], self.nodes[nid]['max'], self.spent(), self.budget))

    def right(self, e):
        nid = self.hit(e.x, e.y)
        if nid is None or self.alloc.get(nid, 0) == 0:
            return
        if self.alloc[nid] == 1:
            lost = self.orphaned_by(nid)
            if lost:
                self.flash(nid)
                return self.app.say('%s: %s would be cut off.' % (self.nodes[nid]['name'], ', '.join(self.nodes[o]['name'] for o in lost)))
        self.alloc[nid] -= 1
        if self.alloc[nid] == 0:
            del self.alloc[nid]
        self.on_change(self.alloc)
        self.redraw()
        self.app.say('%s: %d / %d.  %d of %d points spent.' % (self.nodes[nid]['name'], self.alloc.get(nid, 0), self.nodes[nid]['max'], self.spent(), self.budget))

    # ---------------------------------------------------------------- drawing
    def hit(self, x, y):
        r = ICON * self.zoom / 2 + 4
        for nid, (px, py) in self.pos.items():
            sx, sy = self.to_screen(px, py)
            if abs(sx - x) <= r and abs(sy - y) <= r:
                return nid
        return None

    def flash(self, nid):
        sx, sy = self.to_screen(*self.pos[nid])
        r = ICON * self.zoom / 2 + 6
        item = self.create_oval(sx - r, sy - r, sx + r, sy + r, outline='#e04040', width=3)
        self.after(350, lambda: self.delete(item))

    def redraw(self):
        self.delete('all')
        z = self.zoom
        # backdrop: a soft ring per section, like the game's class tree discs
        for label, top, bottom, g in self.sections:
            x0, y0 = self.to_screen(self.bounds[0] + 20, top)
            x1, y1 = self.to_screen(self.bounds[2] - 20, bottom)
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
            for k in range(6, 0, -1):
                f = k / 6.0
                color = theme.blend(theme.BG, '#2a2614' if (self.chosen is None or g in (0, self.chosen)) else '#1e1e24', 0.9 * (1 - f) + 0.1)
                self.create_oval(cx - rx * f, cy - ry * f, cx + rx * f, cy + ry * f, fill=color, outline='')
            self.create_text(x0 + 8, y0 + 6, text=label, anchor='nw', fill=theme.GOLD_DIM, font=('DejaVu Serif', int(10 * max(z, 0.8)), 'bold'))
        # links (the root counts as always allocated)
        for nid, n in self.nodes.items():
            for src, req in n['in']:
                if src == -1 and n.get('mastery', 0) in self.section_root:
                    a = self.to_screen(*self.section_root[n.get('mastery', 0)])
                elif src in self.pos:
                    a = self.to_screen(*self.pos[src])
                else:
                    continue
                b = self.to_screen(*self.pos[nid])
                if src == -1:
                    on = self.alloc.get(nid, 0) > 0
                    self.create_line(a[0], a[1], b[0], b[1], fill=theme.GOLD if on else theme.BORDER, width=3 if on else 1.5)
                    continue
                on = self.alloc.get(nid, 0) > 0 and self.alloc.get(src, 0) >= max(1, req)
                self.create_line(a[0], a[1], b[0], b[1], fill=theme.GOLD if on else theme.BORDER, width=3 if on else 1.5)
                if req > 1:
                    self.create_text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, text=str(req), fill=theme.TEXT_DIM, font=('DejaVu Sans', 7))
        # nodes
        r = ICON * z / 2
        for g, (rx, ry) in self.section_root.items():
            sx, sy = self.to_screen(rx, ry)
            label = (self.masteries[g - 1] if g and self.masteries else self.title.split()[0])[:9]
            self.create_oval(sx - r - 6, sy - r - 6, sx + r + 6, sy + r + 6, fill=theme.PANEL, outline=theme.GOLD, width=2)
            self.create_text(sx, sy, text=label, fill=theme.GOLD, font=('DejaVu Serif', max(6, int(7 * z)), 'bold'))
        for nid, n in self.nodes.items():
            sx, sy = self.to_screen(*self.pos[nid])
            pts, mx = self.alloc.get(nid, 0), n['max']
            can = self.why_not(nid) is None
            ring = theme.GOLD_LIGHT if pts >= mx and mx else theme.GOLD if pts else (theme.TEXT_DIM if can else theme.BORDER)
            self.create_oval(sx - r - 3, sy - r - 3, sx + r + 3, sy + r + 3, fill=theme.PANEL, outline=ring, width=2 if pts else 1, tags='n%d' % nid)
            layers = self.icon(n['icon'])
            if layers:
                for img in layers:
                    self.create_image(sx, sy, image=img)
                if not pts and not can:
                    self.create_oval(sx - r, sy - r, sx + r, sy + r, fill=theme.BG, outline='', stipple='gray50')
            else:
                self.create_text(sx, sy, text=n['name'][:3], fill=theme.TEXT)
            if mx:
                self.create_text(sx, sy + r + 9, text='%d/%d' % (pts, mx), fill=theme.GOLD_LIGHT if pts else theme.TEXT_DIM, font=('DejaVu Sans', max(7, int(8 * z))))
        self.create_text(10, 10, anchor='nw', fill=theme.GOLD, font=('DejaVu Serif', 11, 'bold'),
                         text='%s   %d / %d points   (zoom %.2g, ctrl+wheel; middle drag to pan)' % (self.title, self.spent(), self.budget, z))

    def hover(self, e):
        nid = self.hit(e.x, e.y)
        if self.tip:
            self.delete(self.tip)
            self.delete(self.tip_bg)
            self.tip = None
        if nid is None:
            return
        n = self.nodes[nid]
        lines = [n['name'] + ('  (%s)' % self.masteries[n['mastery'] - 1] if n.get('mastery') and self.masteries else '')]
        lines += ['  ' + s for s in n.get('stats', [])]
        if n.get('bonus'):
            lines.append('  at %d points: %s' % (n.get('threshold', 0), '; '.join(n['bonus'])))
        if n.get('req'):
            lines.append('  needs %d points' % n['req'])
        if n.get('desc'):
            lines.append('  ' + n['desc'][:160])
        reason = self.why_not(nid)
        lines.append('  ' + ('left click: +1' if not reason else reason))
        x, y = min(e.x + 16, self.winfo_width() - 330), e.y + 16
        self.tip = self.create_text(x, y, anchor='nw', text='\n'.join(lines), fill=theme.TEXT, font=('DejaVu Sans', 9), width=320)
        bx = self.bbox(self.tip)
        self.tip_bg = self.create_rectangle(bx[0] - 6, bx[1] - 4, bx[2] + 6, bx[3] + 4, fill=theme.FIELD, outline=theme.GOLD_DIM)
        self.tag_raise(self.tip, self.tip_bg)


class TreeWindow(tk.Toplevel):
    """A window with a TreeView for the passive tree or one skill tree of the loaded character."""

    def __init__(self, app, tree_id=None):
        super().__init__(app)
        self.app = app
        j = app.char.json
        trees = L.load_trees2()
        cls = trees[j.get('characterClass', 0)]
        if tree_id is None:
            nodes = {int(k): v for k, v in cls['passives'].items()}
            t = j.setdefault('savedCharacterTree', {'treeID': '', 'version': 12, 'nodeIDs': [], 'nodePoints': [], 'unspentPoints': 0, 'nodesTaken': None})
            alloc = dict(zip(t['nodeIDs'], t['nodePoints']))
            budget = j.get('level', 1) - 1 + L.PASSIVE_QUEST_POINTS
            title = '%s passives' % cls['name']
            masteries, chosen = cls['masteries'], j.get('chosenMastery') or None
        else:
            nodes = {int(k): v for k, v in cls['skills'].get(tree_id, {}).items()}
            t = next(st for st in j['savedSkillTrees'] if st['treeID'] == tree_id)
            alloc = dict(zip(t['nodeIDs'], t['nodePoints']))
            budget = L.SKILL_POINTS
            title = cls.get('skillNames', {}).get(tree_id, tree_id)
            masteries = chosen = None
        self.record = t
        self.title('%s - %s' % (title, j.get('characterName', '')))
        self.geometry('1180x720')
        top = ttk.Frame(self, padding=4)
        top.pack(fill='x')
        ttk.Button(top, text='Fit', command=lambda: self.view.fit()).pack(side='left')
        ttk.Button(top, text='Zoom +', command=lambda: self.view.set_zoom(1)).pack(side='left', padx=4)
        ttk.Button(top, text='Zoom -', command=lambda: self.view.set_zoom(-1)).pack(side='left')
        ttk.Button(top, text='Clear all points', command=self.clear).pack(side='left', padx=12)
        ttk.Label(top, style='Dim.TLabel', text='Left click: add a point. Right click: take one back. Hover for the node\'s stats.').pack(side='left')
        ttk.Button(top, text='Close', command=self.destroy).pack(side='right')
        self.view = TreeView(self, app, nodes, alloc, budget, self.apply, masteries, chosen, title)
        self.view.pack(fill='both', expand=True)
        self.after(100, self.view.fit)

    def apply(self, alloc):
        items = sorted(alloc.items())
        self.record['nodeIDs'] = [i for i, _ in items]
        self.record['nodePoints'] = [p for _, p in items]
        if 'unspentPoints' in self.record:
            self.record['unspentPoints'] = max(0, self.view.budget - sum(self.record['nodePoints']))
        self.app.changed('Tree changed.')
        if hasattr(self.app, 'tabs') and 'Skills' in self.app.tabs:
            self.app.tabs['Skills'].load()

    def clear(self):
        self.view.alloc = {}
        self.apply({})
        self.view.redraw()
