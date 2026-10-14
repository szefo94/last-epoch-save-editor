"""Last Epoch-flavoured look for the editor: dark charcoal panels, parchment text, gold accents, and
rounded buttons drawn as image elements (ttk has no corner radius of its own). apply(root) must run
before any widget is created so the option database covers the plain Tk widgets too."""
import math
import tkinter as tk
from tkinter import ttk

BG = '#15161b'         # window background
PANEL = '#1f2129'      # frames, tabs, tree rows
FIELD = '#262933'      # entries, text boxes, lists
FIELD_LIGHT = '#2f333f'
BORDER = '#3a3e4b'
TEXT = '#e6ddc5'       # parchment
TEXT_DIM = '#9a937f'
GOLD = '#d4a93c'
GOLD_DIM = '#8f742c'
GOLD_LIGHT = '#f2cb5a'
SELECT = '#4a3d17'     # selected row
BUTTON = '#2c2f3a'
BUTTON_HOVER = '#3a3e4c'
BUTTON_PRESSED = '#1a1b22'
AMBER = '#f5b335'
RARITY_COLORS = {'Normal': '#c9c3b1', 'Magic': '#5f8fe0', 'Rare': '#e8cc4e', 'Exalted': '#b06cf0',
                 'Unique': '#f08a2e', 'Set': '#58c05a', 'Legendary': '#ff5c5c'}
HEAD_FONT = ('DejaVu Serif', 11, 'bold')
GLOW_STEPS = 10
_images = []           # keeps the PhotoImages alive


def blend(a, b, k):
    ra, ga, ba = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    rb, gb, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    return '#%02x%02x%02x' % (round(ra + (rb - ra) * k), round(ga + (gb - ga) * k), round(ba + (bb - ba) * k))


def rounded_image(fill, outline, size=20, radius=7):
    """A square image with a rounded, outlined rectangle; the corners outside it are transparent.
    Used as a stretchable ttk image element (its border slices keep the corners intact)."""
    img = tk.PhotoImage(width=size, height=size)
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            # distance from the nearest corner centre, for the rounded corners
            cx = radius if x < radius else (size - 1 - radius if x >= size - radius else x)
            cy = radius if y < radius else (size - 1 - radius if y >= size - radius else y)
            d = math.hypot(x - cx, y - cy)
            if d > radius + 0.5:
                row.append(fill)          # replaced by transparency below
            elif d > radius - 0.9 or x in (0, size - 1) or y in (0, size - 1):
                row.append(outline)
            else:
                row.append(fill)
        rows.append('{' + ' '.join(row) + '}')
    img.put(' '.join(rows))
    for y in range(size):
        for x in range(size):
            cx = radius if x < radius else (size - 1 - radius if x >= size - radius else x)
            cy = radius if y < radius else (size - 1 - radius if y >= size - radius else y)
            if math.hypot(x - cx, y - cy) > radius + 0.5:
                img.transparency_set(x, y, True)
    _images.append(img)
    return img


def button_element(style, name, fill, hover, pressed, outline, text_outline=None):
    style.element_create(name, 'image', rounded_image(fill, outline),
                         ('pressed', rounded_image(pressed, outline)),
                         ('active', rounded_image(hover, text_outline or outline)),
                         ('disabled', rounded_image(BG, BORDER)),
                         border=8, sticky='nsew')


def apply(root):
    """Applies the theme to a Tk root. Returns the list of glow style names for the Save button."""
    style = ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=BG)
    for cls, opts in {'Text': dict(background=FIELD, foreground=TEXT, insertBackground=GOLD, selectBackground=SELECT,
                                   selectForeground=TEXT, relief='flat', highlightThickness=1, highlightBackground=BORDER,
                                   highlightColor=GOLD_DIM, borderWidth=0),
                      'Listbox': dict(background=FIELD, foreground=TEXT, selectBackground=SELECT, selectForeground=GOLD_LIGHT,
                                      relief='flat', highlightThickness=1, highlightBackground=BORDER, highlightColor=GOLD_DIM,
                                      borderWidth=0),
                      'Canvas': dict(background=PANEL, highlightThickness=0),
                      'Toplevel': dict(background=BG),
                      'Label': dict(background=BG, foreground=TEXT)}.items():
        for key, value in opts.items():
            root.option_add('*%s.%s' % (cls, key), value)
    style.configure('.', background=BG, foreground=TEXT, fieldbackground=FIELD, bordercolor=BORDER,
                    darkcolor=BG, lightcolor=PANEL, troughcolor=BG, selectbackground=SELECT, selectforeground=TEXT,
                    insertcolor=GOLD, font=('DejaVu Sans', 10))
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=TEXT)
    style.configure('Dim.TLabel', foreground=TEXT_DIM)
    style.configure('Head.TLabel', foreground=GOLD, font=HEAD_FONT)
    style.configure('Status.TLabel', background=PANEL, foreground=TEXT_DIM, padding=4)
    style.configure('TLabelframe', background=BG, bordercolor=GOLD_DIM, relief='solid')
    style.configure('TLabelframe.Label', background=BG, foreground=GOLD, font=HEAD_FONT)
    # rounded buttons
    button_element(style, 'Rounded.border', BUTTON, BUTTON_HOVER, BUTTON_PRESSED, BORDER, GOLD_DIM)
    style.layout('TButton', [('Rounded.border', {'sticky': 'nsew', 'children': [
        ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
    style.configure('TButton', foreground=TEXT, padding=(10, 2), background=BG, anchor='center')
    style.map('TButton', foreground=[('disabled', TEXT_DIM), ('active', GOLD_LIGHT)], background=[])
    glow = []
    for i in range(GLOW_STEPS):
        k = i / (GLOW_STEPS - 1)
        fill = blend(BUTTON, AMBER, 0.15 + 0.45 * k)
        name = 'Glow%d.border' % i
        button_element(style, name, fill, blend(fill, '#ffffff', 0.1), blend(fill, BG, 0.3), blend(BORDER, AMBER, k), AMBER)
        sname = 'Glow%d.TButton' % i
        style.layout(sname, [(name, {'sticky': 'nsew', 'children': [
            ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
        style.configure(sname, foreground=blend(TEXT, '#1a1200', 0.3 + 0.5 * k), padding=(10, 2))
        glow.append(sname)
    # the rest of ttk
    style.configure('TCheckbutton', background=BG, foreground=TEXT, indicatorcolor=FIELD, indicatormargin=4)
    style.map('TCheckbutton', indicatorcolor=[('selected', GOLD), ('pressed', GOLD_DIM)], background=[('active', BG)])
    style.configure('TRadiobutton', background=BG, foreground=TEXT, indicatorcolor=FIELD)
    style.map('TRadiobutton', indicatorcolor=[('selected', GOLD), ('pressed', GOLD_DIM)], background=[('active', BG)])
    for w in ('TEntry', 'TSpinbox', 'TCombobox'):
        style.configure(w, fieldbackground=FIELD, foreground=TEXT, bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD,
                        arrowcolor=GOLD, insertcolor=GOLD, padding=3, background=FIELD, selectbackground=SELECT)
        style.map(w, fieldbackground=[('readonly', FIELD), ('disabled', BG)], foreground=[('disabled', TEXT_DIM)],
                  bordercolor=[('focus', GOLD_DIM)], arrowcolor=[('disabled', TEXT_DIM)])
    root.option_add('*TCombobox*Listbox.background', FIELD)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', SELECT)
    root.option_add('*TCombobox*Listbox.selectForeground', GOLD_LIGHT)
    style.configure('TNotebook', background=BG, bordercolor=BORDER, tabmargins=(2, 4, 2, 0))
    style.configure('TNotebook.Tab', background=PANEL, foreground=TEXT_DIM, padding=(12, 5), bordercolor=BORDER)
    style.map('TNotebook.Tab', background=[('selected', FIELD_LIGHT)], foreground=[('selected', GOLD)],
              expand=[('selected', (1, 1, 1, 0))])
    style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=PANEL, darkcolor=PANEL, rowheight=26)
    style.map('Treeview', background=[('selected', SELECT)], foreground=[('selected', GOLD_LIGHT)])
    style.configure('Treeview.Heading', background=FIELD_LIGHT, foreground=GOLD, bordercolor=BORDER, relief='flat',
                    font=('DejaVu Sans', 10, 'bold'), padding=4)
    style.map('Treeview.Heading', background=[('active', BORDER)])
    style.configure('TScrollbar', background=FIELD_LIGHT, troughcolor=BG, bordercolor=BG, arrowcolor=GOLD, lightcolor=FIELD_LIGHT, darkcolor=FIELD_LIGHT)
    style.map('TScrollbar', background=[('active', BORDER)])
    style.configure('TPanedwindow', background=BG)
    style.configure('Sash', sashthickness=6, gripcount=0, background=BORDER)
    style.configure('TSeparator', background=BORDER)
    return glow
