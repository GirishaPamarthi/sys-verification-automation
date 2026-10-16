# Reporting setup lives in test_report_gen_script and MUST be imported before any
# interops import: it puts Squish on sys.path and installs the compatibility shims
# interops needs to report under the standalone squishtest extension.
import os
import sys

MY_TEST_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "my-test-scripts"))
if MY_TEST_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, MY_TEST_SCRIPTS_DIR)

import test_report_gen_script as reporting

from interops.libraries.mosaiq.interactions.objects.mosaiq_core_objects import MosaiqCoreObjects
from interops.libraries.mosaiq.interactions.objects.mosaiq_select_patient_objects import MosaiqSelectPatient
from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.pages import Login, Logout
from interops.libraries.mosaiq.interactions import (
    MosaiqDashboard,
    MosaiqOpenPatient,
    MosaiqDemographicsUpdate,
)

VerifyThat = reporting.VerifyThat
test_section = reporting.test_section


MOSAIQ_SERVER = "10.68.134.200"
SQUISH_SERVER_PORT = 4322

PATIENT_MR = "84082"
PATIENT_FIRST_NAME = "LUNGPATIENT"
PATIENT_LAST_NAME = "MSQ-84082"
PATIENT_BIRTHDATE = "1/24/1989"
PATIENT_GENDER = "Female"

TEST_CASE_NAME = "MOSAIQ Client Patient Search and Patient Chart Open"
MOSAIQ_AUT_NAME = "accwin"  # matches MosaiqAutController._aut_name


def login_valid_clinical_user() -> None:
    """Step 1 -- log in with a valid clinical user."""
    with test_section("Step 1: Log in with valid clinical user"):
        MosaiqAutController.mosaiq_aut(
            serverAddress=MOSAIQ_SERVER,
            serverPort=SQUISH_SERVER_PORT,
        ).start_aut()
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAIQ_Dashboard_Window, 30)) \
            .equals(True) \
            .andReport("Mosaiq should show the login window after starting the AUT")

        Login().loginUser("impac", "impac")
        VerifyThat(MosaiqDashboard.wait_for_main_workspace_area(20)) \
            .equals(True) \
            .andReport("Mosaiq workspace should load after login with a valid clinical user")


def open_select_patient() -> None:
    """Step 2 -- open the Select Patient window from File > Open Patient Chart."""
    with test_section("Step 2: Open Select Patient"):
        MosaiqDashboard.open_select_patient()
        # MosaiqSelectPatient.ui_Main_Window, not a core object: the Select Patient window is a
        # top-level window in its own right, not a child of the MOSAIQ main window.
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqSelectPatient.ui_Main_Window, 15)) \
            .equals(True) \
            .andReport("Select Patient window should appear")


def search_for_patient() -> None:
    """Step 3 -- filter the patient grid by MR number and confirm the row comes back."""
    with test_section(f"Step 3: Search by ID (MR# {PATIENT_MR})"):
        MosaiqOpenPatient.typeText_in_patient_mr_number(PATIENT_MR)
        MosaiqOpenPatient.click_apply_filters_button()

        # greaterThan: the filter must actually match something before we click a row.
        results = MosaiqOpenPatient.get_search_results()
        VerifyThat(len(results)) \
            .greaterThan(0) \
            .andReport(f"Searching by MR# {PATIENT_MR} should return at least one row")

        # notEquals(None): the grid must actually hold a row for this MR number.
        # Uses the same lookup the select/click helpers use, so it asserts the thing the next
        # step depends on. Do NOT assert on getattr(row, "text", "") -- these grid objects
        # expose no `text`, so the fallback silently yields [''] and the check fails for no reason.
        matching_row = CommonActions.get_child_object_by_value(results, PATIENT_MR)
        VerifyThat(matching_row) \
            .notEquals(None) \
            .andReport(f"Search grid should contain a row for MR# {PATIENT_MR}")


def select_patient_from_results() -> None:
    """Step 4 -- highlight the result row without opening it, then commit with Select."""
    with test_section("Step 4: Select patient from result list"):
        # Single click only: the row is highlighted and the Select Patient window stays open.
        # click_specific_result_using_mr_number() would double-click and open the chart here,
        # collapsing steps 4 and 5 into one and leaving the Select button untested.
        MosaiqOpenPatient.select_specific_result_using_mr_number(PATIENT_MR)

        # The Select button is disabled until a row is highlighted, so this asserts the
        # selection landed rather than just that the click was dispatched.
        VerifyThat(MosaiqOpenPatient.is_select_button_enabled()) \
            .equals(True) \
            .andReport(f"Select button should be enabled once MR# {PATIENT_MR} is highlighted")

        MosaiqOpenPatient.click_select_button()
        VerifyThat(CommonActions.wait_for_object_to_disappear(MosaiqSelectPatient.ui_Main_Window, 15)) \
            .equals(True) \
            .andReport("Select Patient window should close after clicking Select")


def open_patient_chart() -> None:
    """Step 5 -- confirm the patient opened, then open the Chart view."""
    with test_section("Step 5: Open the patient chart"):
        # andReportCritical: a failure here aborts the test instead of cascading.
        # A screenshot is attached to the report for this step.
        VerifyThat(MosaiqDashboard.wait_for_patient_to_open(15), screenshot=True) \
            .equals(True) \
            .andReportCritical(f"Patient MR# {PATIENT_MR} should open in the dashboard")

        VerifyThat(MosaiqDashboard.is_patient_chart_open()) \
            .equals(True) \
            .andReport("Open Patient toolbar label should confirm a chart is open")

        # PATIENT_MR is the only identifier this test actually knows, so the patient banner is
        # checked against it. open_chart_for_current_patient() is used instead of
        # open_patient_chart(lastName) for the same reason: the last name would have to be
        # scraped off the demographics page first, and those name fields are mapped by global
        # Edit occurrence, so they are not a safe thing to gate the run on.
        VerifyThat(MosaiqDashboard.is_patient_open_by_value(PATIENT_MR, 15)) \
            .equals(True) \
            .andReportCritical(f"Open patient banner should name MR# {PATIENT_MR}, not another patient")

        MosaiqDashboard.open_chart_for_current_patient()
        VerifyThat(MosaiqDashboard.wait_for_patient_chart_view(20)) \
            .equals(True) \
            .andReportCritical(f"Chart view should load for MR# {PATIENT_MR}")


def verify_demographics_and_chart_content() -> None:
    """Step 6 -- read back the chart's patient banner and the core demographics fields."""
    with test_section("Step 6: Verify demographics and core chart content"):
        # The chart view is open from step 5, so the banner is the chart's own statement of
        # who is loaded. Logged as evidence for the report as well as asserted on.
        VerifyThat(MosaiqDashboard.get_open_patient_label_text()) \
            .contains(PATIENT_MR) \
            .andReport(f"Chart patient banner should still identify MR# {PATIENT_MR}")

        MosaiqDashboard.open_file_demographics()
        MosaiqDemographicsUpdate.await_demographics()

        # firstname_Edit / lastname_Edit are mapped as bare global Edit occurrences with no
        # container, so they only land on the right controls while the Name/IDs tab is the one
        # showing. Select it explicitly rather than relying on it being the default tab.
        MosaiqDemographicsUpdate.click_name_ids_tab()
        VerifyThat(MosaiqDemographicsUpdate.get_lastname()) \
            .equals(PATIENT_LAST_NAME) \
            .andReport("Demographics last name should be populated")
        VerifyThat(MosaiqDemographicsUpdate.get_firstname()) \
            .equals(PATIENT_FIRST_NAME) \
            .andReport("Demographics first name should be populated")

        # Birthdate and gender live on the Personal tab, so it has to be selected first.
        MosaiqDemographicsUpdate.click_personal_tab()
        VerifyThat(MosaiqDemographicsUpdate.get_birthdate()) \
            .equals(PATIENT_BIRTHDATE) \
            .andReport("Demographics birthdate should be populated")
        VerifyThat(MosaiqDemographicsUpdate.get_gender()) \
            .equals(PATIENT_GENDER) \
            .andReport("Demographics gender should be populated")


def close_patient_chart() -> None:
    """Step 7 -- close the chart and confirm no patient is left open."""
    with test_section("Step 7: Close the patient chart"):
        MosaiqDashboard.close_patient_chart()

        # The "*MR#*" toolbar label is the same object is_patient_chart_open() keys off, so
        # waiting for it to disappear is the direct inverse of the step 5 assertion.
        VerifyThat(MosaiqDashboard.wait_for_patient_chart_to_close(15)) \
            .equals(True) \
            .andReport("Open Patient toolbar label should disappear after closing the chart")

        VerifyThat(MosaiqDashboard.is_patient_chart_open()) \
            .equals(False) \
            .andReport("No patient chart should be open after Close Patient Chart")


def close_mosaiq() -> None:
    """Teardown -- exit MOSAIQ so the next case starts from a clean launch.

    run_smoke_suite.py runs each case in its own subprocess, but they all drive one AUT on the
    Squish server, and start_aut() calls startApplication() unconditionally rather than
    attaching to a running instance. Without this the next case launches MOSAIQ on top of the
    one this case left behind, and its login window check fails.

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
        open_select_patient()
        search_for_patient()
        select_patient_from_results()
        open_patient_chart()
        verify_demographics_and_chart_content()
        close_patient_chart()
    finally:
        # finally, so a critical verification aborting the run still logs the verification
        # count and still leaves the AUT closed for the next case in the suite.
        reporting.finish_reporting(sq)
        close_mosaiq()


if __name__ == "__main__":
    main()
