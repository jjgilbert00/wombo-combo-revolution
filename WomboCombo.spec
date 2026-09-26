# PyInstaller build for a standalone Windows release: no Python needed to run it.
# Build with `python build.py` (which runs this and zips the result), or `pyinstaller WomboCombo.spec`.
from kivy.tools.packaging.pyinstaller_hooks import get_deps_minimal, hookspath, runtime_hooks
from kivy_deps import angle, glew, sdl2
from PyInstaller.utils.hooks import collect_all

# Kivy's providers for windows, text and images only; the app uses no Kivy video, audio or camera.
kivy_deps = get_deps_minimal(video=None, audio=None, camera=None, spelling=None)
ffmpeg_datas, ffmpeg_binaries, ffmpeg_hidden = collect_all("imageio_ffmpeg")  # Bundles the ffmpeg executable.

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=kivy_deps["binaries"] + ffmpeg_binaries,
    datas=[
        ("images", "images"),  # Button icons.
        ("samples/*.json", "samples"),  # The warm-up and sample combos.
        ("docs", "docs"),  # The user guide, opened from F1.
    ] + ffmpeg_datas,
    hiddenimports=kivy_deps["hiddenimports"] + ffmpeg_hidden + [
        "pynput.keyboard._win32", "pynput.mouse._win32",  # Chosen at runtime, so not found by analysis.
        "win32timezone",
    ],
    hookspath=hookspath(),
    runtime_hooks=runtime_hooks(),
    excludes=kivy_deps["excludes"] + ["tkinter", "moviepy", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WomboCombo",
    console=False,  # A windowed app; logs go to %USERPROFILE%\.kivy\logs.
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *[Tree(path) for path in (sdl2.dep_bins + glew.dep_bins + angle.dep_bins)],
    strip=False,
    upx=False,  # UPX-packed executables are flagged by antivirus far more often.
    name="WomboCombo",
)
