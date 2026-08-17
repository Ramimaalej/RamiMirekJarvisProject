"""Patch test_all.py: TOOL_DECLARATIONS moved to core/tools/declarations.py."""
p = "tests/test_all.py"
src = p and open(p).read()

new = src.replace(
    '''    def _get_tools():
        with open(PROJECT / "main.py") as f:
            src = f.read()
        mod = types.ModuleType("_tools")
        mod.__file__ = str(PROJECT / "main.py")
        code = compile(src, str(PROJECT / "main.py"), "exec")
        exec(code, mod.__dict__)
        return mod.TOOL_DECLARATIONS''',
    '''    def _get_tools():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_decl", str(PROJECT / "core" / "tools" / "declarations.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.TOOL_DECLARATIONS''',
)
open(p, "w").write(new)
print("patched:", "core/tools/decorations" in open(p).read() and "NO" or "OK")
