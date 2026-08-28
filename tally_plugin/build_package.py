"""Build the dependency-free Windows bridge distribution zip."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PLUGIN_DIR = Path(__file__).resolve().parent
APP_DIR = PLUGIN_DIR.parent
OUTPUT_DIR = APP_DIR / "dist"
OUTPUT_FILE = OUTPUT_DIR / "SRV-Tally-Bridge-1.0.0.zip"


def build():
	OUTPUT_DIR.mkdir(exist_ok=True)
	with ZipFile(OUTPUT_FILE, "w", ZIP_DEFLATED) as archive:
		archive.write(APP_DIR / "srv_erp" / "__init__.py", "srv_erp/__init__.py")
		for source in sorted((APP_DIR / "srv_erp" / "tally_bridge").glob("*.py")):
			archive.write(source, f"srv_erp/tally_bridge/{source.name}")
		for filename in (
			"README.md",
			"SRVERPBridge.tdl",
			"start-bridge.cmd",
			"tally-bridge.example.json",
		):
			archive.write(PLUGIN_DIR / filename, filename)
	return OUTPUT_FILE


if __name__ == "__main__":
	print(build())
