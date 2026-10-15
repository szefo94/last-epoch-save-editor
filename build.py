#!/usr/bin/env python3
"""Builds a runnable single-file version of the editor and installs a desktop launcher.

  python3 build.py            -> dist/LE_Save_Editor.pyz  (needs only python3 + tkinter, as on SteamOS)
                                 add --hero when running it for the Hero Editor layout
  python3 build.py --binary   -> dist/LE_Save_Editor      (PyInstaller one-file binary, no Python needed;
                                 needs PyInstaller: python3 -m venv v && v/bin/pip install pyinstaller)
  python3 build.py --install  -> also writes a "LE Save Editor" entry to the application menu and Desktop

The .pyz is a zip archive with a shebang: double-click it in Dolphin, run ./dist/LE_Save_Editor.pyz, or
python3 dist/LE_Save_Editor.pyz [saves folder]. Backups land in a backups/ folder next to the file.
"""
import os
import shutil
import stat
import subprocess
import sys
import zipapp

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, 'dist')
NAME = 'LE_Save_Editor'
SOURCES = ['lesave.py', 'le_editor2.py', 'le_hero.py', 'theme.py', 'import_maxroll.py', 'fetch_icons.py']
FOLDERS = ['data', 'plans']
ICON = os.path.join(DIST, 'le_save_editor.svg')
ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect x="4" y="4" width="56" height="56" rx="10" fill="#2b2b2b" stroke="#c9a240" stroke-width="3"/>
<g stroke="#444" stroke-width="1.5"><path d="M16 16h32M16 28h32M16 40h32M16 52h32M16 16v36M28 16v36M40 16v36M48 16v36"/></g>
<rect x="17" y="17" width="10" height="22" fill="#ff8c8c"/><rect x="29" y="17" width="10" height="10" fill="#d8a0ff"/>
<rect x="41" y="29" width="6" height="22" fill="#ffe27a"/><rect x="29" y="41" width="10" height="10" fill="#8fb8ff"/>
</svg>
'''
DESKTOP = '''[Desktop Entry]
Type=Application
Name=LE Save Editor
Comment=Last Epoch offline save editor
Exec={exec}
Icon={icon}
Terminal=false
Categories=Game;Utility;
'''


def stage():
    """Copies the sources into a clean build folder (no caches, backups or saves)."""
    build = os.path.join(HERE, 'build', 'stage')
    shutil.rmtree(build, ignore_errors=True)
    os.makedirs(build)
    for name in SOURCES:
        shutil.copy2(os.path.join(HERE, name), build)
    for name in FOLDERS:
        shutil.copytree(os.path.join(HERE, name), os.path.join(build, name),
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    with open(os.path.join(build, '__main__.py'), 'w') as f:
        f.write('import sys\n'
                'argv = sys.argv[1:]\n'
                'if "--hero" in argv:\n'
                '    argv.remove("--hero")\n'
                '    import le_hero as app\n'
                'else:\n'
                '    import le_editor2 as app\n'
                'sys.exit(app.main(argv))\n')
    return build


def build_pyz():
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, NAME + '.pyz')
    zipapp.create_archive(stage(), out, interpreter='/usr/bin/env python3', compressed=True)
    os.chmod(out, os.stat(out).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    selftest([sys.executable, out])
    print('built %s (%d KB)' % (out, os.path.getsize(out) // 1024))
    return out


def selftest(cmd):
    check = subprocess.run(cmd + ['--selftest'], capture_output=True, text=True)
    if check.returncode:
        sys.exit('self test of %s failed:\n%s' % (cmd[-1], check.stderr))
    print('  ' + check.stdout.strip())


def build_binary():
    """One-file binary through PyInstaller (from the current interpreter's environment or a venv)."""
    candidates = [sys.executable] + [os.path.join(HERE, v, 'bin', 'python') for v in ('venv', '.venv', 'pyi_venv')]
    python = next((p for p in candidates if os.path.exists(p) and
                   subprocess.run([p, '-m', 'PyInstaller', '--version'], capture_output=True).returncode == 0), None)
    if not python:
        sys.exit('PyInstaller not found. Create a venv and install it:\n'
                 '  python3 -m venv pyi_venv && pyi_venv/bin/pip install pyinstaller')
    src = stage()
    hidden = ['--hidden-import=plans.' + n[:-3] for n in os.listdir(os.path.join(src, 'plans'))
              if n.endswith('.py') and n != '__init__.py']
    cmd = [python, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--name', NAME,
           '--distpath', DIST, '--workpath', os.path.join(HERE, 'build', 'pyinstaller'),
           '--specpath', os.path.join(HERE, 'build'),
           '--add-data', os.path.join(src, 'data') + os.pathsep + 'data',
           '--add-data', os.path.join(src, 'plans') + os.pathsep + 'plans',
           '--paths', src] + hidden + [os.path.join(src, '__main__.py')]
    subprocess.run(cmd, check=True)
    out = os.path.join(DIST, NAME)
    selftest([out])
    print('built %s (%d MB)' % (out, os.path.getsize(out) // 2**20))
    return out


def install(target):
    os.makedirs(DIST, exist_ok=True)
    with open(ICON, 'w') as f:
        f.write(ICON_SVG)
    exec_line = '"%s"' % target if not target.endswith('.pyz') else '/usr/bin/env python3 "%s"' % target
    apps = os.path.expanduser('~/.local/share/applications')
    os.makedirs(apps, exist_ok=True)
    entry = DESKTOP.format(exec=exec_line, icon=ICON)
    for path in (os.path.join(apps, 'le-save-editor.desktop'), os.path.expanduser('~/Desktop/LE Save Editor.desktop')):
        if os.path.isdir(os.path.dirname(path)):
            with open(path, 'w') as f:
                f.write(entry)
            os.chmod(path, 0o755)
            print('installed', path)
    subprocess.run(['update-desktop-database', apps], capture_output=True)


if __name__ == '__main__':
    target = build_binary() if '--binary' in sys.argv else build_pyz()
    if '--install' in sys.argv:
        install(target)
