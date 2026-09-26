"""Builds the standalone Windows release: dist/WomboCombo/ and dist/WomboCombo-windows.zip.

    python build.py

Needs the app's requirements plus PyInstaller (pip install pyinstaller). The zip is what users
download: they unzip it anywhere and run WomboCombo.exe, with no Python install.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
APP = os.path.join(DIST, "WomboCombo")

README = """Wombo Combo
===========

Run WomboCombo.exe. The first time, it opens a short warm-up: press Space (or Start on your
controller) and press each input as it reaches the white line. No controller? WASD moves,
U I O punch, J K L kick.

The full user guide is User guide\\USER_GUIDE.md (F1 in the app opens it too).
Settings are kept in %APPDATA%\\wombocombo. Logs, if something goes wrong, are in
%USERPROFILE%\\.kivy\\logs.
"""


def main():
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "WomboCombo.spec"], cwd=HERE,
                   check=True)
    # Next to the exe, where people look: how to start, and the guide.
    with open(os.path.join(APP, "README.txt"), "w") as fout:
        fout.write(README)
    shutil.copytree(os.path.join(HERE, "docs"), os.path.join(APP, "User guide"), dirs_exist_ok=True)
    archive = shutil.make_archive(os.path.join(DIST, "WomboCombo-windows"), "zip", DIST, "WomboCombo")
    size = sum(os.path.getsize(os.path.join(root, name)) for root, _, names in os.walk(APP) for name in names)
    print(f"Built {APP} ({size / 1e6:.0f} MB) and {archive} ({os.path.getsize(archive) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
