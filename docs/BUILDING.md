# Building a release

The download is a standalone Windows build made with [PyInstaller](https://pyinstaller.org): a folder
containing `WomboCombo.exe` and everything it needs. Users don't need Python.

```
pip install -r requirements.txt
pip install pyinstaller
python build.py
```

This makes:

- `dist/WomboCombo/`: the app. Run `WomboCombo.exe` from it to try the build.
- `dist/WomboCombo-windows.zip`: the same folder zipped. This is what users download.

`WomboCombo.spec` says what goes in:
- Kivy's window, text and image providers, and its SDL2/GLEW/ANGLE DLLs;
- the ffmpeg executable from imageio-ffmpeg (for video);
- the app's `images/`, `samples/` and `docs/`.

`build.py` runs it, then adds a `README.txt` and a `User guide` folder next to the exe, and zips
the folder.

Notes:
- It's a one-folder build rather than a single exe. It starts faster, since nothing is
  unpacked on each launch, and antivirus is less suspicious of it. UPX compression is off for
  the same reason.
- The demo feature's `vgamepad` isn't bundled, since it needs the ViGEmBus driver installed on
  the user's PC anyway. Without it the app runs normally, and Demo explains what to install.
- The exe isn't code-signed, so Windows SmartScreen warns about an unknown publisher on first run.
  Signing it would need a code-signing certificate.
- Logs from the built app go to `%USERPROFILE%\.kivy\logs`, and settings to
  `%APPDATA%\wombocombo\wombocombo.ini`.
