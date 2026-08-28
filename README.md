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

### TallyPrime Bridge

The automated ERPNext-to-TallyPrime Sales Order and Delivery Note bridge is independent of the
legacy manual JSON exporter. Build its Windows package with:

```bash
python tally_plugin/build_package.py
```

Installation, security, TDL loading, and operating instructions are in
[`tally_plugin/README.md`](tally_plugin/README.md).
