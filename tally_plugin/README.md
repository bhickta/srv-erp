# SRV ERPNext–TallyPrime Bridge

This package runs on the Windows computer where TallyPrime is open. It pulls
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
- Python 3.10 or newer on the Tally Windows computer.
- An ERPNext API user with the **Tally Sync User** role, API key, and API
  secret. Give that user additional roles only if the generic API command must
  call other protected ERPNext methods.
- HTTPS on the ERPNext server when the bridge connects over a network.

## Install on the Tally computer

1. Extract `SRV-Tally-Bridge-1.0.0.zip` to a fixed folder such as
   `C:\SRV-Tally-Bridge`.
2. Copy `tally-bridge.example.json` to `tally-bridge.json`.
3. Set `frappe_url`, API credentials, ERPNext company, and the exact loaded
   Tally company. Keep `target_id` stable and unique for this Tally data set.
4. Double-click `start-bridge.cmd`. It checks the loaded Tally company before
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

## Check and operate from Command Prompt

From the extracted folder:

```bat
py -3 -m srv_erp.tally_bridge --config tally-bridge.json status
py -3 -m srv_erp.tally_bridge --config tally-bridge.json sync --limit 5
py -3 -m srv_erp.tally_bridge --config tally-bridge.json serve --no-poll
```

For automatic polling every configured interval, use:

```bat
py -3 -m srv_erp.tally_bridge --config tally-bridge.json serve
```

The bridge also provides a generic authenticated Frappe API caller:

```bat
py -3 -m srv_erp.tally_bridge --config tally-bridge.json api GET /api/resource/Company
py -3 -m srv_erp.tally_bridge --config tally-bridge.json api POST /api/method/my_app.api.run --data "{\"name\":\"value\"}"
```

Frappe permissions still apply. The generic caller does not bypass the API
user's assigned roles.

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
