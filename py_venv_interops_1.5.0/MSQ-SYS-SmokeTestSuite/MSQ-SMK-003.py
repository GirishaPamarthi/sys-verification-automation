# Reporting setup lives in test_report_gen_script and MUST be imported before any
# interops import: it puts Squish on sys.path and installs the compatibility shims
# interops needs to report under the standalone squishtest extension.
import time

import test_config
import test_report_gen_script as reporting

from interops.libraries.mosaiq.interactions.objects.mosaiq_core_objects import MosaiqCoreObjects
from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.pages import Login, Logout
from interops.libraries.mosaiq.interactions import (
    MosaiqDashboard,
    MosaiqCommonPopups,
)

VerifyThat = reporting.VerifyThat
test_section = reporting.test_section


# Server, port and AUT come from configuration-files/test_environment.json.
CFG = test_config.for_test("smoke", "MSQ-SMK-003")
MOSAIQ_SERVER = CFG.server_host
SQUISH_SERVER_PORT = CFG.squish_port
MOSAIQ_AUT_NAME = CFG.aut_name

# Panes asserted on in step 4. Every one of these is mapped in mosaiq_core_objects.py:117-123.
EXPECTED_HOME_TABS = (
    "Work List",
    "QCL",
    "Survivorship",
    "Patient List",
    "Eligibility",
    "Links and Mail",
    "Schedule",
)

# Step 5 selects this pane, step 6 switches to the other one.
PANE_UNDER_TEST = "Work List"
PANE_TO_SWITCH_TO = "Patient List"

# Step 3's "without delay" budget, in seconds. wait_for_main_workspace_area() is given a longer
# timeout than this so a slow load is reported as slow rather than as a hard failure to load.
WORKSPACE_LOAD_BUDGET_SECS = 15

TEST_CASE_NAME = "MOSAIQ Home Workspace Panes"


def login_valid_clinical_user() -> None:
    """Step 1 -- log in with a valid clinical user."""
    with test_section("Step 1: Log in"):
        MosaiqAutController.mosaiq_aut(
            serverAddress=MOSAIQ_SERVER,
            serverPort=SQUISH_SERVER_PORT,
        ).start_aut()
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAIQ_Dashboard_Window, 30)) \
            .equals(True) \
            .andReportCritical("Mosaiq should show the login window after starting the AUT")

        Login().loginUser("impac", "impac")
        VerifyThat(MosaiqDashboard.wait_for_main_workspace_area(20)) \
            .equals(True) \
            .andReportCritical("Mosaiq workspace should load after login")


def navigate_to_home_workspace() -> None:
    """Step 2 -- click the Home toolbar item."""
    with test_section("Step 2: Navigate to Home workspace"):
        MosaiqDashboard.open_home()
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAIQ_Home_Workspace_Area, 20)) \
            .equals(True) \
            .andReportCritical("Home workspace area should be present after clicking Home")


def verify_workspace_loads_cleanly() -> None:
    """Step 3 -- workspace loads inside the budget and raises no error dialog."""
    with test_section("Step 3: Verify workspace loads without delay or UI error"):
        started = time.perf_counter()
        loaded = MosaiqDashboard.wait_for_main_workspace_area(20)
        elapsed = time.perf_counter() - started

        VerifyThat(loaded) \
            .equals(True) \
            .andReportCritical("Home workspace tab area should load")

        # Separate assertion from the one above so a slow-but-successful load is reported as a
        # timing failure rather than being mistaken for the workspace failing to load at all.
        VerifyThat(round(elapsed, 2)) \
            .lessThan(WORKSPACE_LOAD_BUDGET_SECS) \
            .andReport(f"Home workspace should load in under {WORKSPACE_LOAD_BUDGET_SECS}s")

        # acknowledge_error_dialog() returns True only when it found and dismissed an error,
        # so False is the passing result here.
        VerifyThat(MosaiqCommonPopups.acknowledge_error_dialog()) \
            .equals(False) \
            .andReport("No error dialog should be raised while loading the Home workspace")


def verify_panes_visible_and_labelled() -> None:
    """Step 4 -- every expected pane tab is present, visible and carries its label."""
    with test_section("Step 4: Verify panes visible and labeled"):
        for tab_name in EXPECTED_HOME_TABS:
            # is_home_tab_present(), NOT a visibility check: a TabItem's `visible` attribute
            # reports whether that tab's page is the one on display, so every unselected tab
            # reads False even though its header is sitting in the strip. Presence of a TabItem
            # matching on text, plus enabled, is what "visible and labeled" means here.
            VerifyThat(MosaiqDashboard.is_home_tab_present(tab_name, 5)) \
                .equals(True) \
                .andReport(f"Home workspace should show a '{tab_name}' pane tab")


def select_pane_and_confirm_data() -> None:
    """Step 5 -- select a pane and confirm it renders content."""
    with test_section(f"Step 5: Select the {PANE_UNDER_TEST} pane and confirm data is displayed"):
        MosaiqDashboard.click_home_tab(PANE_UNDER_TEST)
        VerifyThat(MosaiqDashboard.is_home_tab_selected(PANE_UNDER_TEST)) \
            .equals(True) \
            .andReport(f"{PANE_UNDER_TEST} pane should be the selected tab after clicking it")

        # Counts the grid's Data Panel, so an empty pane that still draws its column headers
        # cannot pass. Work List is the pane asserted on because it is the one that carries
        # rows on a fresh login -- Patient List renders its headers with no data behind them.
        VerifyThat(MosaiqDashboard.get_home_pane_row_count(PANE_UNDER_TEST)) \
            .greaterThan(0) \
            .andReport(f"{PANE_UNDER_TEST} pane grid should display at least one data row")


def switch_to_another_pane() -> None:
    """Step 6 -- switch panes and confirm the selection moved."""
    with test_section(f"Step 6: Switch to the {PANE_TO_SWITCH_TO} pane"):
        MosaiqDashboard.click_home_tab(PANE_TO_SWITCH_TO)

        VerifyThat(MosaiqDashboard.is_home_tab_selected(PANE_TO_SWITCH_TO)) \
            .equals(True) \
            .andReport(f"{PANE_TO_SWITCH_TO} pane should be selected after switching")

        # Asserting the previous tab gave up selection is what makes this a switch rather than
        # just a second click landing somewhere.
        VerifyThat(MosaiqDashboard.is_home_tab_selected(PANE_UNDER_TEST)) \
            .equals(False) \
            .andReport(f"{PANE_UNDER_TEST} pane should no longer be selected after switching")

        VerifyThat(MosaiqCommonPopups.acknowledge_error_dialog()) \
            .equals(False) \
            .andReport("Switching panes should not raise an error dialog")


def close_mosaiq() -> None:
    """Teardown -- exit MOSAIQ so the next case starts from a clean launch.

    run_smoke_suite.py runs each case in its own subprocess, but they all drive one AUT on the
    Squish server, and start_aut() calls startApplication() unconditionally rather than
    attaching to a running instance. Without this the second case launches MOSAIQ on top of the
    one the first case left behind, and step 1's login window check fails.

    Never raises: teardown must not mask the failure that brought the test here, and the AUT may
    already be gone or never have got far enough to offer a File menu.
    """
    try:
        Logout().exitApplication()
    except Exception as error:
        print(f"MOSAIQ teardown skipped: {error}")


def main() -> None:
    sq = reporting.start_reporting(TEST_CASE_NAME, aut_name=MOSAIQ_AUT_NAME)

    try:
        login_valid_clinical_user()
        navigate_to_home_workspace()
        verify_workspace_loads_cleanly()
        verify_panes_visible_and_labelled()
        select_pane_and_confirm_data()
        switch_to_another_pane()
    finally:
        # finally, so a critical verification aborting the run still logs the verification
        # count and still leaves the AUT closed for the next case in the suite.
        reporting.finish_reporting(sq)
        close_mosaiq()


if __name__ == "__main__":
    main()
