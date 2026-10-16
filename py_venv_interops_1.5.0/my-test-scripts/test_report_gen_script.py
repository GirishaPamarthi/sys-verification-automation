"""Shared Squish test-reporting setup for every test script in this folder.

Import this FIRST, before any `interops` import. At import time it does two things
that have to happen in that order:

  1. Puts the interops site-packages and the Squish runtime on sys.path, so the
     `squishtest` extension can be imported at all.
  2. Installs the compatibility shims interops needs to report under the standalone
     `squishtest` extension rather than squishrunner (see SHIMS below).

Typical use:

    import test_report_gen_script as reporting
    from interops.libraries.mosaiq import MosaiqAutController
    ...

    def main():
        sq = reporting.start_reporting("my_test_case", aut_name="accwin")
        MosaiqAutController.mosaiq_aut(...).start_aut()

        with reporting.test_section("Login"):
            reporting.VerifyThat(logged_in).equals(True) \\
                .andReportCritical("should log in")

        reporting.finish_reporting(sq)

`start_reporting()` must be called BEFORE start_aut(): it sets the report target,
the test case name and the AUT wrappers on the session.

--------------------------------------------------------------------------------
SHIMS -- why each one exists. All four were reproduced by running a real test.
--------------------------------------------------------------------------------

(1) `squishtest3` ships as an EMPTY directory in site-packages, so it imports as a
    namespace package with no attributes. interops' desktop.py and verify.py both
    do `import squishtest3 as sq`, after which every sq.test / sq.testSettings /
    sq.setTestResult raises AttributeError. Aliased onto the real extension.

(2) VerifyThat.verify() calls test.fixateResultContext(self.frames) to blame the
    caller's line. Standalone squishtest keeps no script ancestor stack, so any
    argument >= 1 raises "invalid ancestor stack frame number" at every call depth
    -- only 0 is accepted. Both context calls are no-ops here; pass/fail still
    record, the report just cites verify.py's line instead of the caller's.

(3) The shim in (2) cannot be a one-shot patch of squishtest.test: start_aut()
    overwrites that entry in the extension's module dict, so the next verification
    raises again. _SquishProxyModule re-wraps `test` on every attribute access and
    is installed as verify.py's module-global `sq` -- a deliberately narrow
    override, since nothing else in interops needs it.

(4) interops' Desktop.create_squish() calls
        setWrappersForApplication(aut, ('Windows'))
    where ('Windows') is parentheses around one string, so a str and not a tuple.
    Squish rejects it with "RuntimeError: The wrappers argument needs to be a
    list", meaning the shipped method can never complete. ReportingDesktop below
    overrides it rather than editing site-packages, so an interops reinstall
    cannot silently revert the fix.

Items (1) and (4) are bugs in interops 1.5.0 and are worth fixing upstream; this
module only works around them.
"""

import os
import shutil
import sys
import types

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

ROOT_ENV = r"C:\solver_automation\py_venv_interops_1.5.0"
SQUISH_ROOT = r"C:\Program Files (x86)\Squish for Windows 9.2.2"
# The executables and squishrunnerlib.dll live in a SEPARATE install from the data
# files. Report generators resolve their templates relative to this one.
SQUISH_RUNTIME_ROOT = r"C:\Program Files (x86)\squish_runtime"

RESULTS_ROOT = r"C:\solver_automation\test-results"
DEFAULT_REPORT_FORMAT = "html"

# Formats confirmed working on this machine. "xml" also works but Squish warns it
# is deprecated in favour of xml3. "html" additionally needs the webreport
# templates to be reachable -- see _require_html_prerequisites().
SUPPORTED_FORMATS = ("html", "xml3", "junit", "json", "stdout")

# Formats whose target is a directory rather than a single file.
_DIR_FORMATS = ("html", "json", "xml3")


def _bootstrap_sys_path() -> None:
    """Put interops' site-packages and the Squish runtime on sys.path."""
    dotvenv = os.path.join(
        os.path.dirname(os.path.dirname(sys.executable)), "Lib", "site-packages"
    )
    # Prefer the root environment site-packages, because that is where interops is.
    for path in (os.path.join(ROOT_ENV, "Lib", "site-packages"), dotvenv):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    for path in (os.path.join(SQUISH_ROOT, "bin"),
                 os.path.join(SQUISH_ROOT, "lib", "python")):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_sys_path()


# ---------------------------------------------------------------------------
# Shims (see SHIMS in the module docstring)
# ---------------------------------------------------------------------------

import squishtest                                    # noqa: E402

sys.modules.setdefault("squishtest3", squishtest)     # shim (1)


class _ResultContextProxy:
    """Forwards to squishtest.test, neutralising squishrunner-only context calls."""

    def __init__(self, real_test):
        self._real_test = real_test

    def fixateResultContext(self, *args, **kwargs):   # shim (2)
        return None

    def restoreResultContext(self, *args, **kwargs):  # shim (2)
        return None

    def __getattr__(self, name):
        return getattr(self._real_test, name)


class _SquishProxyModule(types.ModuleType):           # shim (3)
    """Module stand-in that re-wraps `test` on every attribute access."""

    def __getattr__(self, name):
        attr = getattr(squishtest, name)
        return _ResultContextProxy(attr) if name == "test" else attr


try:
    import testData                                   # noqa: F401
except ImportError:
    _stub = types.ModuleType("testData")

    def _no_datasheet(row, field):
        raise RuntimeError("No Squish test datasheet available outside squishrunner")

    _stub.field = _no_datasheet
    sys.modules["testData"] = _stub


from interops.libraries.desktop.desktop import Desktop            # noqa: E402
from interops.libraries.verify import VerifyThat                  # noqa: E402
import interops.libraries.verify.verify as _verify_module         # noqa: E402

_verify_module.sq = _SquishProxyModule("squishtest3_proxy")       # shim (3)


class ReportingDesktop(Desktop):                                  # shim (4)
    """Desktop with the shipped setWrappersForApplication call corrected."""

    def create_squish(self):
        squishtest.testSettings.testCaseName = self.tname
        squishtest.setTestResult(self.tf, self.trname)
        squishtest.testSettings.setWrappersForApplication(self.aut, ["Windows"])
        squishtest.testSettings.logScreenshotOnFail = True
        return squishtest


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Re-exported so a test script needs only this module for its verifications.
test_section = Desktop.test_section


def default_report_dir(test_case_name: str) -> str:
    """<RESULTS_ROOT>/<test_case_name> -- one directory per test case."""
    return os.path.join(RESULTS_ROOT, test_case_name)


def _require_html_prerequisites() -> None:
    """Fail loudly if the html generator cannot find its templates.

    Without this check the failure mode is a silent process kill: the generator
    aborts at init, the interpreter exits with code 0, no traceback is printed and
    data/ is left empty, which looks like a test that simply produced no output.
    """
    webreport = os.path.join(SQUISH_RUNTIME_ROOT, "lib", "webreport")
    if os.path.isdir(webreport):
        return

    raise RuntimeError(
        "The html report generator cannot find its web report templates at\n"
        f"    {webreport}\n\n"
        "Squish is split across two installs on this machine: the executables and\n"
        f"squishrunnerlib.dll are in {SQUISH_RUNTIME_ROOT}\\bin, while the data\n"
        f"files are in {SQUISH_ROOT}. Report generators resolve their templates\n"
        "relative to the runtime install, which ships with bin/ only.\n\n"
        "Fix it by junctioning the missing directories in an ELEVATED shell -- all\n"
        "four, not just lib: with lib present but etc missing, Squish resolves its\n"
        "prefix to the runtime install, fails to read its config there, and even\n"
        '`import squishtest` starts failing with "LicenseError: Host not found".\n'
        + "".join(
            f'    mklink /J "{SQUISH_RUNTIME_ROOT}\\{d}" "{SQUISH_ROOT}\\{d}"\n'
            for d in ("etc", "lib", "python", "plugins")
        )
        + "\nOr sidestep it: pass report_format='xml3' and convert afterwards with\n"
        "xml3_to_html.py."
    )


def _clear_stale_report_data(report_dir: str, report_format: str) -> None:
    """Remove a leftover <report_dir>/data before an html run.

    The html generator refuses an output directory whose data/ holds no result file
    ("Directory '<dir>/data' exists but does not contain result file") and fails the
    same silent way as above. A run that died part-way leaves exactly that state, so
    the next run cannot start until data/ is cleared.
    """
    if report_format != "html":
        return

    data_dir = os.path.join(report_dir, "data")
    # Only ever touch this one path, and never follow a link out of it.
    if os.path.isdir(data_dir) and not os.path.islink(data_dir):
        shutil.rmtree(data_dir)


def report_landing_path(report_dir: str, report_format: str = DEFAULT_REPORT_FORMAT) -> str:
    """The file or directory a human should open to read the report."""
    if report_format == "html":
        return os.path.join(report_dir, "index.html")
    if report_format == "xml3":
        return os.path.join(report_dir, "results.xml")
    if report_format in _DIR_FORMATS:
        return report_dir
    suffix = "xml" if report_format == "junit" else "txt"
    return os.path.join(report_dir, f"results-{report_format}.{suffix}")


def start_reporting(
    test_case_name: str,
    aut_name: str,
    report_dir: str = None,
    report_format: str = DEFAULT_REPORT_FORMAT,
    screenshot_dir: str = None,
):
    """Configure the Squish report and return the configured squishtest module.

    Call BEFORE start_aut(): this sets the report target, the test case name and the
    AUT wrappers on the session.

    :param test_case_name: name recorded as the test case in the report
    :param aut_name: AUT name as registered with squishserver, e.g. "accwin" for
                     Mosaiq -- see each interops AutController's _aut_name
    :param report_dir: output directory; defaults to <RESULTS_ROOT>/<test_case_name>
    :param report_format: one of SUPPORTED_FORMATS
    :param screenshot_dir: where VerifyThat(..., screenshot=True) images go;
                           defaults to <report_dir>/screenshots
    :return: the squishtest module, already configured
    """
    if report_format not in SUPPORTED_FORMATS:
        raise ValueError(
            f"report_format {report_format!r} is not one of {SUPPORTED_FORMATS}"
        )
    if report_format == "html":
        _require_html_prerequisites()

    report_dir = report_dir or default_report_dir(test_case_name)
    screenshot_dir = screenshot_dir or os.path.join(report_dir, "screenshots")

    os.makedirs(screenshot_dir, exist_ok=True)
    _clear_stale_report_data(report_dir, report_format)

    # Directory-target formats want the directory; file-target formats want a file.
    # Names are format-specific so switching format does not overwrite the previous
    # report -- xml3 already writes its own results.xml into report_dir.
    target = report_dir
    if report_format not in _DIR_FORMATS:
        suffix = "xml" if report_format == "junit" else "txt"
        target = os.path.join(report_dir, f"results-{report_format}.{suffix}")

    sq = ReportingDesktop(
        tst_name=test_case_name,
        tst_report_name=target,
        tst_format=report_format,
        tst_aut_name=aut_name,
    ).create_squish()

    VerifyThat.setScreenshotPath(screenshot_dir)

    # Stashed so finish_reporting() can report where the output went.
    sq._report_dir = report_dir
    sq._report_format = report_format
    return sq


def finish_reporting(sq) -> str:
    """Log the verification count, print where the report landed, return that path."""
    count = VerifyThat.verification_count
    sq.test.log(f"Completed {count} verifications")

    report_dir = getattr(sq, "_report_dir", None)
    report_format = getattr(sq, "_report_format", DEFAULT_REPORT_FORMAT)
    if not report_dir:
        return ""

    landing = report_landing_path(report_dir, report_format)
    print(f"{count} verifications; {report_format} report written to: {landing}")
    return landing
