# Squish Reporting Helper

This folder contains a shared test-reporting helper for Squish-based automation scripts that use the InterOps libraries from this environment.

The main entry point is:

- `test_report_gen_script.py`

It bootstraps the Squish runtime and InterOps environment, applies compatibility shims, and exposes the helper functions needed to start a Squish report, log verifications, and finish the run cleanly.

## What this script does

At import time, the script:

1. Adds the InterOps site-packages directory and Squish runtime paths to `sys.path`.
2. Makes the standalone `squishtest` extension available the same way the InterOps library expects it.
3. Patches a few Squish/InterOps compatibility issues that appear in this environment.
4. Exposes a simple public API for test scripts.

This lets a script do the usual pattern:

```python
import test_report_gen_script as reporting
from interops.libraries.mosaiq import MosaiqAutController

sq = reporting.start_reporting("my_test_case", aut_name="accwin")
MosaiqAutController.mosaiq_aut(...).start_aut()

with reporting.test_section("Login"):
    reporting.VerifyThat(logged_in).equals(True) \
        .andReportCritical("should log in")

reporting.finish_reporting(sq)
```

## Prerequisites

This helper expects:

- the root project environment at `C:\solver_automation\py_venv_interops_mim_remote_server`
- Squish for Windows 9.2.2 installed at `C:\Program Files (x86)\Squish for Windows 9.2.2`
- the Squish runtime install at `C:\Program Files (x86)\squish_runtime`
- InterOps installed into the project virtual environment

## Public API

### `start_reporting(test_case_name, aut_name, report_dir=None, report_format="html", screenshot_dir=None)`

Initializes the Squish report and returns the configured `squishtest` module.

Parameters:

- `test_case_name`: name recorded in the report
- `aut_name`: AUT name registered with Squish, such as `accwin`
- `report_dir`: output directory; defaults to `C:\solver_automation\test-results\<test_case_name>`
- `report_format`: one of `html`, `xml3`, `junit`, `json`, or `stdout`
- `screenshot_dir`: directory for screenshot captures; defaults to `<report_dir>\screenshots`

Important:

- call this before starting the AUT
- it configures the report target, test case name, and wrappers for the session

### `finish_reporting(sq)`

Writes the verification summary and returns the report landing path.

### `test_section`

Re-exported from `Desktop.test_section` so you can wrap blocks with a Squish test section label.

### `default_report_dir(test_case_name)`

Returns the default report output directory for a test case.

### `report_landing_path(report_dir, report_format="html")`

Returns the specific file or directory a human should open for the generated report.

## Supported report formats

The helper accepts these formats:

- `html`
- `xml3`
- `junit`
- `json`
- `stdout`

`html`, `json`, and `xml3` produce directory-based outputs; the other formats produce file outputs.

## Compatibility shims included

This helper intentionally applies a few targeted workarounds for the current environment:

- it aliases the empty `squishtest3` package to the real `squishtest` module
- it neutralizes Squish runner-only result-context calls used by `VerifyThat`
- it wraps `squishtest.test` so the standalone environment does not crash on missing runner state
- it fixes the invalid wrapper argument passed to `setWrappersForApplication()`

These are documented inline in the script itself and are intended as a workaround for the local Squish + InterOps combination.

## Typical script pattern

```python
import test_report_gen_script as reporting

sq = reporting.start_reporting(
    "login_test",
    aut_name="accwin",
    report_format="html",
)

with reporting.test_section("Login"):
    # test actions and assertions
    pass

reporting.finish_reporting(sq)
```

## Troubleshooting

### HTML reports fail silently

The script performs a preflight check for the Squish web-report templates. If they are not reachable from the runtime install, it raises a clear error with fix instructions.

### `squishtest` import errors

Verify that the Squish runtime and project `site-packages` paths are present in `sys.path` before the InterOps imports happen.

### `setWrappersForApplication` error

The script corrects the wrapper list to use `['Windows']` instead of the invalid `('Windows')` form.

## Notes

This helper is designed specifically for local standalone Squish execution in this repository. It is not a general-purpose replacement for the normal Squish runner environment.
