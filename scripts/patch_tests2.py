"""Patch TestNewToolDeclarations: tools moved out of main.py."""
import re

p = "tests/test_features.py"
src = open(p).read()

# Replace the three methods with regex-friendly substitution
repl1 = '''    def _decl_source(self):
        return (PROJECT / "core" / "tools" / "declarations.py").read_text()'''

src = re.sub(
    r'    def test_tool_declarations_exist\(self\):\s*\n\s*with open\(PROJECT / "main\.py"\) as f:\s*\n\s*content = f\.read\(\)',
    repl1 + '\n    def test_tool_declarations_exist(self):\n        content = self._decl_source()\n',
    src, flags=re.MULTILINE,
)
src = re.sub(
    r'    def test_dispatcher_entries_exist\(self\):\s*\n\s*with open\(PROJECT / "main\.py"\) as f:\s*\n\s*content = f\.read\(\)',
    '    def test_dispatcher_entries_exist(self):\n        content = self._decl_source()\n',
    src, flags=re.MULTILINE,
)
src = re.sub(
    r'    def test_imports_exist\(self\):\s*\n\s*with open\(PROJECT / "main\.py"\) as f:\s*\n\s*content = f\.read\(\)',
    '    def test_imports_exist(self):\n        content = self._decl_source()\n',
    src, flags=re.MULTILINE,
)
src = src.replace('f"Tool declaration \'{name}\' not found in main.py"',
                  'f"Tool declaration \'{name}\' not found in declarations.py"')
src = src.replace('assert f"from actions.{imp}" in content,',
                  'assert f"actions.{imp}" in content,')
open(p, "w").write(src)
print("patch2 OK")
