"""Compatibility API; the shared exporter now lives in express_tally."""

from express_tally.integrations import tally_export as _implementation
from express_tally.integrations.tally_export import *  # noqa: F401,F403


def __getattr__(name):
	return getattr(_implementation, name)
