### Srv Erp

Custom frappe application for SRV Electricals.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-15
bench install-app srv_erp
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/srv_erp
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit

### TallyPrime Control Centre

The reusable `express_tally` app supplies a single Windows Control Centre for
manual and automatic ERPNext ↔ TallyPrime flows. SRV registers its Sales Order
and Delivery Note policy with that connector. Build the Windows package from the
`erpnext-tally-connector` app with:

```bash
npm --prefix ../erpnext-tally-connector/control-centre run build
powershell -ExecutionPolicy Bypass -File ../erpnext-tally-connector/tally_plugin/build-windows.ps1
```

Installation, security, and operating instructions are in
`apps/erpnext-tally-connector/tally_plugin/README.md`.
