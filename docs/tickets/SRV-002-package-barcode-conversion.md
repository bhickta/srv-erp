# SRV-002: Package conversion value in barcode

Priority: 2
Status: Implemented.

Append the selected package UOM conversion value and PKG to each newly generated barcode, for example PBC-2026-24234-20PKG. Preserve the configured naming-series prefix/date/serial. Do not append the stock UOM name. Support fractional factors without unnecessary zeroes. Existing printed barcode values remain valid. Validate generation, uniqueness and scan resolution.

Deliverable: Separate production and dev PRs. Merge dev only after validation; leave production open.

Implementation: Resolve and validate the selected UOM conversion once per generation batch, then append -<value>PKG to the configured series. This is the generation-time conversion value; barcode resolution and stock transaction quantity rules continue to use the existing UOM logic. No historical identifiers are rewritten.

Validation: All 17 dev package-barcode tests pass (20 pass on production, whose baseline includes three additional tests), including whole/fractional/stock-UOM factors, uniqueness, custom series, scan round-trips, legacy labels and invalid factors before batch creation.
