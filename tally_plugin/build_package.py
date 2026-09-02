"""Build the Tally bridge distribution zip."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PLUGIN_DIR = Path(__file__).resolve().parent
APP_DIR = PLUGIN_DIR.parent
OUTPUT_DIR = APP_DIR / "dist"
OUTPUT_FILE = OUTPUT_DIR / "SRV-Tally-Bridge-Windows-x64.zip"


def build(executable, output_file=OUTPUT_FILE):
	output_file = Path(output_file).resolve()
	executable = Path(executable).resolve()
	if not executable.is_file():
		raise FileNotFoundError(f"Windows executable not found: {executable}")
	output_file.parent.mkdir(parents=True, exist_ok=True)
	with ZipFile(output_file, "w", ZIP_DEFLATED) as archive:
		archive.write(executable, "SRVTallyBridge.exe")
		for filename in (
			"README.md",
			"SRVERPBridge.tdl",
			"start-bridge.cmd",
			"tally-bridge.example.json",
		):
			archive.write(PLUGIN_DIR / filename, filename)
	return output_file


def _parser():
	parser = argparse.ArgumentParser(description="Build the SRV Tally Bridge ZIP")
	parser.add_argument("--output", default=str(OUTPUT_FILE), help="Output ZIP path")
	parser.add_argument("--executable", required=True, help="Standalone Windows executable")
	return parser


if __name__ == "__main__":
	args = _parser().parse_args()
	print(build(args.executable, args.output))
