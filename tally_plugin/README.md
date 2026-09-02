# SRV ERPNext–TallyPrime Bridge

This Windows-only package runs on the computer where TallyPrime is open. It pulls
submitted, unacknowledged Sales Orders and Delivery Notes from ERPNext, creates their required
Tally masters, imports inventory **Sales vouchers** through Tally's local HTTP gateway,
and acknowledges each confirmed result back to ERPNext.

The old manual Tally JSON exporter is not used by this bridge.

## Requirements

- TallyPrime 7.x with the target company loaded and **Maintain Inventory** enabled.
- If ERPNext documents can have zero-value item rows (as the current Delivery
  Notes do), enable **Allow zero-valued transactions** for the Sales voucher
  type in TallyPrime.
- Tally HTTP Server enabled on port 9000: **F1 → Settings → Advanced
  Configuration → Enable HTTP Server**.
- No Python installation is required on Windows when the package contains
  `SRVTallyBridge.exe`.
- An ERPNext API user with the **Tally Sync User** role, API key, and API
  secret. Give that user additional roles only if the generic API command must
  call other protected ERPNext methods.
- HTTPS on the ERPNext server when the bridge connects over a network.

## Install on the Tally computer

1. Download `SRV-Tally-Bridge-Windows-x64.zip` from the
   [Tally Bridge Latest](https://github.com/bhickta/srv-erp/releases/tag/tally-bridge-latest)
   GitHub release, then extract it to a fixed folder such as
   `C:\SRV-Tally-Bridge`.
2. Copy `tally-bridge.example.json` to `tally-bridge.json`.
3. Set `frappe_url`, API credentials, ERPNext company, and the exact loaded
   Tally company. Keep `target_id` stable and unique for this Tally data set.
4. Confirm the extracted folder contains `SRVTallyBridge.exe`, then double-click
   `start-bridge.cmd`. It checks the loaded Tally company before
   every batch and refuses to write if it does not match.
5. Optional: in TallyPrime, open **F1 → TDL & Add-On → Manage Local TDL**, load
   `SRVERPBridge.tdl`, and restart TallyPrime. The Gateway menu then includes
   **ERPNext Sales Sync**.

Before clicking the menu option, keep `start-bridge.cmd` running. Confirm the
local trigger is available by opening `http://127.0.0.1:8765/health` in a
browser. If an older TDL reports **Description not found**, replace it with the
current `SRVERPBridge.tdl`, reload the TDL, and restart TallyPrime.

`start-bridge.cmd` runs in click-only mode: synchronization starts only from
the Tally menu. API credentials never appear in the TDL source. To enable
automatic polling instead, run the `serve` command without `--no-poll`.

Leave the launcher window running. Confirm `http://127.0.0.1:8765/health` opens
before clicking the Tally menu. The click returns immediately and synchronization
continues in the background; view progress at
`http://127.0.0.1:8765/sync-status`.

## Check and operate from Command Prompt

From the extracted folder:

```bat
SRVTallyBridge.exe --config tally-bridge.json status
SRVTallyBridge.exe --config tally-bridge.json sync --limit 5
SRVTallyBridge.exe --config tally-bridge.json serve --no-poll
```

For automatic polling every configured interval, use:

```bat
SRVTallyBridge.exe --config tally-bridge.json serve
```

The bridge also provides a generic authenticated Frappe API caller:

```bat
SRVTallyBridge.exe --config tally-bridge.json api GET /api/resource/Company
SRVTallyBridge.exe --config tally-bridge.json api POST /api/method/my_app.api.run --data "{\"name\":\"value\"}"
```

Frappe permissions still apply. The generic caller does not bypass the API
user's assigned roles.

## Build the standalone Windows package

Push bridge or plugin changes to the `version-15` branch. GitHub Actions builds
the executable on Windows, stores the ZIP as a workflow artifact, and updates
the rolling **Tally Bridge Latest** prerelease asset. The workflow can also be
run manually from the repository's **Actions** page without publishing a release.

For a local Windows build from a repository checkout, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tally_plugin\build-windows.ps1
```

The generated package is `dist\SRV-Tally-Bridge-Windows-x64.zip`. Python and
PyInstaller are build-time requirements only; they are not required on the
Tally computer.

## Sync behavior

- Only submitted Sales Orders and Delivery Notes are pulled.
- Each ERPNext Sales Order and Delivery Note is entered as a separate Tally
  **Sales** voucher in accounting mode with inventory allocations. The original ERPNext document number is
  stored as the reference (and party bill reference for valued documents); the
  visible voucher number follows the Sales voucher type's numbering configuration. No Tally Sales Order or
  Delivery Note voucher type is created.
- The bridge uses stock quantities and stock UOMs, preserving total line values
  even when ERPNext sells an item in a conversion UOM such as Box.
- Required units, stock groups, godowns, customer/sales/tax ledgers, and stock
  items are imported in dependency order using TallyPrime's native JSON format.
- Vouchers use Tally's XML format so validation failures include the detailed
  `LINEERROR` text in the ERPNext sync log.
- The deterministic Tally GUID, stable target ID, and immutable ERPNext sync log
  make retries idempotent, including a lost acknowledgement response.
- A changed submitted document is returned as an Alter operation.
- A failure is logged but remains pending for the next retry. Tally responses
  containing `LINEERROR`, `ERRORS`, or `EXCEPTIONS` are never acknowledged as
  successful.
- Logs are visible in ERPNext under **Tally Sync Log**.

## Educational Mode limitation

TallyPrime Educational Mode accepts transaction dates only on the 1st, 2nd,
or last day of a month. Documents on other dates remain pending with Tally's
voucher-date error until TallyPrime is activated; the bridge does not change
ERPNext document dates by default. For a test company, set
`voucher_date_override` in `tally-bridge.json` to an allowed date such as
`2026-08-01`. The bridge then uses that Tally voucher date and records the
original ERPNext date in the narration. Leave this option as `null` for normal,
licensed operation.

## Security

Protect `tally-bridge.json`; it contains an API secret. Environment variables
`SRV_TALLY_API_KEY` and `SRV_TALLY_API_SECRET` override credentials in the file
and are preferred for managed deployments. The local trigger listens only on
`127.0.0.1` by default.
