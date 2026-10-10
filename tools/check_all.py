"""Runs every check: the unit tests, then the UI checks (each in its own run of the app).

usage: python tools/check_all.py          everything
       python tools/check_all.py --unit   just the unit tests (a second or so)

The UI checks open the app's window for a couple of minutes each; leave the mouse and keyboard alone
while they run. docshots isn't run here: it rewrites the guide's screenshots (run it on its own).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_CHECKS = ("smoke", "displays", "overlay", "export")


def main():
    failed = []
    unit = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "tests"], cwd=ROOT)
    if unit.returncode:
        failed.append("unit tests")
    if "--unit" not in sys.argv:
        harness = os.path.join(ROOT, "tools", "ui_check", "harness.py")
        for check in UI_CHECKS:
            print(f"\n== UI check: {check}")
            script = os.path.join(ROOT, "tools", "ui_check", "checks", check + ".py")
            run = subprocess.run([sys.executable, harness, script, ROOT], cwd=ROOT, capture_output=True, text=True)
            print("\n".join(line for line in run.stdout.splitlines()
                            if line.startswith(("PASS", "FAIL", "done", "Traceback", "  ")) or "Error" in line), flush=True)
            if run.returncode:
                failed.append(f"UI check {check}")
    print("\nAll checks passed." if not failed else f"\nFailed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
