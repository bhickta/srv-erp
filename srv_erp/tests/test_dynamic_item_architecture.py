import ast
import unittest
from pathlib import Path

DYNAMIC_ITEM_PACKAGE = Path(__file__).resolve().parents[1] / "masters" / "dynamic_item"
MAX_MODULE_LINES = 250


class TestDynamicItemArchitecture(unittest.TestCase):
	def test_service_is_an_import_only_compatibility_facade(self):
		tree = parse_module(DYNAMIC_ITEM_PACKAGE / "service.py")
		definitions = [
			node
			for node in ast.walk(tree)
			if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
		]
		self.assertEqual(definitions, [], "service.py must remain an import-only compatibility facade")

	def test_implementation_modules_stay_focused(self):
		for path in DYNAMIC_ITEM_PACKAGE.glob("*.py"):
			with self.subTest(module=path.name):
				line_count = len(path.read_text(encoding="utf-8").splitlines())
				self.assertLessEqual(
					line_count,
					MAX_MODULE_LINES,
					f"{path.name} exceeds the {MAX_MODULE_LINES}-line module boundary",
				)

	def test_implementation_modules_do_not_depend_on_service_facade(self):
		for path in DYNAMIC_ITEM_PACKAGE.glob("*.py"):
			if path.name == "service.py":
				continue
			with self.subTest(module=path.name):
				imports = imported_modules(parse_module(path))
				self.assertNotIn("srv_erp.masters.dynamic_item.service", imports)


def parse_module(path: Path) -> ast.Module:
	return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.Module) -> set[str]:
	modules = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.ImportFrom) and node.module:
			modules.add(node.module)
		elif isinstance(node, ast.Import):
			modules.update(alias.name for alias in node.names)
	return modules
