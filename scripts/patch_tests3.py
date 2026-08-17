"""Patch 3 (regex): point TestMainToolDeclarations at new locations."""
import re

p = "tests/test_features.py"
src = open(p).read()

# 1. test_new_tools_in_declarations: main.py -> core/tools/declarations.py
src = re.sub(
    r'(    def test_new_tools_in_declarations\(self\):\n)\s*with open\(PROJECT / "main\.py"\) as f:\n\s*tree = ast\.parse\(f\.read\(\)\)',
    r'\1        with open(PROJECT / "core" / "tools" / "declarations.py") as f:\n            tree = ast.parse(f.read())',
    src,
)

# 2. dispatcher + imports methods of TestMainToolDeclarations: use executor.py
src = re.sub(
    r'(    def (test_dispatcher_entries_exist|test_imports_exist)\(self\):\n)\s*with open\(PROJECT / "main\.py"\) as f:\n\s*content = f\.read\(\)',
    r'\1        with open(PROJECT / "core" / "tools" / "executor.py") as f:\n            content = f.read()',
    src,
)

open(p, "w").write(src)
print("patch3 regex OK")

# Also make TestNewToolDeclarations dispatcher/imports point to executor
p2 = "tests/test_features.py"
src2 = open(p2).read()
# the _decl_source method currently points to declarations.py (added by patch2)
src2 = src2.replace(
    '    def test_dispatcher_entries_exist(self):\n        content = self._decl_source()\n',
    '    def test_dispatcher_entries_exist(self):\n        content = (PROJECT / "core" / "tools" / "executor.py").read_text()\n',
)
src2 = src2.replace(
    '    def test_imports_exist(self):\n        content = self._decl_source()\n',
    '    def test_imports_exist(self):\n        content = (PROJECT / "core" / "tools" / "executor.py").read_text()\n',
)
open(p2, "w").write(src2)
print("patch3 newtools -> executor OK")
