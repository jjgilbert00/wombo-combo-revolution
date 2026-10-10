"""Static checks over the app's own modules, quick enough to run before anything else:

- every `from module import name` from the app's modules finds that name (catches a move that
  missed an import);
- no imported name goes unused;
- no name is used that's neither defined nor imported anywhere in its module (roughly: it doesn't
  follow scopes, so it catches typos and missed imports, not every shadowing);
- no widget class shares its name with one of Kivy's built-in style rules (Kivy applies rules by
  class name, so a class called Switch would be drawn as Kivy's switch).

usage: python tools/static_check.py [repository dir]. The exit code is the number of problems.
"""
import ast
import builtins
import glob
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = (".claude/", "build/", "dist/", ".venv/", "BLOG/", "tools/ui_check/shots/")
files = [f.replace("\\", "/") for f in glob.glob(os.path.join(ROOT, "**/*.py"), recursive=True)]
files = [f for f in files if not os.path.relpath(f, ROOT).replace("\\", "/").startswith(SKIP)]


def module_path(module):
    base = os.path.join(ROOT, *module.split("."))
    for candidate in (base + ".py", os.path.join(base, "__init__.py")):
        if os.path.exists(candidate):
            return candidate
    for extra in ("tests", "tools/ui_check", "tools/ui_check/checks"):  # Test and check helpers.
        candidate = os.path.join(ROOT, extra, *module.split(".")) + ".py"
        if os.path.exists(candidate):
            return candidate
    return None


def top_level_names(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Tuple):
                    names |= {e.id for e in target.elts if isinstance(e, ast.Name)}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
    return names


problems = 0
for path in files:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and module_path(node.module):
            target = top_level_names(module_path(node.module))
            for alias in node.names:
                if alias.name not in target and not os.path.exists(
                        os.path.join(ROOT, *node.module.split("."), alias.name + ".py")):
                    print(f"{path}:{node.lineno}: {node.module} has no {alias.name}")
                    problems += 1
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported[a.asname or a.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    exported = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            exported = {e.value for e in node.value.elts}
    for name, line in imported.items():
        if name not in used and name not in exported and not path.endswith("helpers.py"):
            print(f"{path}:{line}: unused import {name}")
            problems += 1
    # Names loaded but never bound anywhere in the module (a missed import after a move).
    bound = set(imported) | set(dir(builtins)) | {"__file__", "__name__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
            if hasattr(node, "args"):
                for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                    bound.add(arg.arg)
                if node.args.vararg:
                    bound.add(node.args.vararg.arg)
                if node.args.kwarg:
                    bound.add(node.args.kwarg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound |= set(node.names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in bound:
            print(f"{path}:{node.lineno}: undefined name {node.id}")
            problems += 1
# Widget classes named like one of Kivy's style rules.
try:
    import kivy
    style = open(os.path.join(os.path.dirname(kivy.__file__), "data", "style.kv"), encoding="utf-8").read()
    rules = {name.strip().split("@")[0] for line in style.splitlines() if line.startswith("<")
             for name in line.strip().strip("<>:").split(",")}
except (ImportError, OSError):
    rules = set()
for path in files:
    for node in ast.parse(open(path, encoding="utf-8").read()).body:
        if isinstance(node, ast.ClassDef) and node.name in rules and node.bases:
            bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
            if bases & {"Widget", "ButtonBehavior", "Label", "Button", "BoxLayout", "FloatLayout", "RelativeLayout"}:
                print(f"{path}:{node.lineno}: class {node.name} would pick up Kivy's <{node.name}> style rule")
                problems += 1

print(f"{problems} problems in {len(files)} files")
sys.exit(min(problems, 100))
