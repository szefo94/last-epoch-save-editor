"""Build plans: modules with a tabs(level) function returning
(category, color, tab name, items, report) tuples, plus a TITLE. The editor lists them on its Build plans tab;
each can also be run from the shell (python3 plans/<name>.py [--write])."""
import importlib
import os
import sys

import lesave as L


def available():
    """[(module name, title)] of the plan modules that ship with the tool."""
    out = []
    for name in L.list_files('plans'):
        if name.endswith('.py') and not name.startswith('_') and name != 'vk_common.py':
            mod = load(name[:-3])
            if hasattr(mod, 'tabs'):
                out.append((name[:-3], getattr(mod, 'TITLE', name[:-3])))
    return out


def load(name):
    return importlib.import_module('plans.' + name)
