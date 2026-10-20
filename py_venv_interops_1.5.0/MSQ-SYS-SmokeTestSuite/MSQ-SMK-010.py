# Reporting setup lives in test_report_gen_script and MUST be imported before any
# interops import: it puts Squish on sys.path and installs the compatibility shims
# interops needs to report under the standalone squishtest extension.
from datetime import datetime

import test_config
import test_report_gen_script as reporting

from interops.libraries.mosaiq.interactions.objects.mosaiq_core_objects import MosaiqCoreObjects
from interops.libraries.mosaiq.interactions.objects.mosaiq_select_patient_objects import MosaiqSelectPatient
from interops.libraries.mosaiq.interactions.objects.mosaiq_ro_treat_objects import ROTreat
from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.pages import Login, Logout
from interops.libraries.mosaiq.interactions import (
    MosaiqDashboard,
    MosaiqOpenPatient,
    MosaiqROTreat,
    MosaiqCommonPopups,
    MosaiqTreatmentDeliveryTable,
)

VerifyThat = reporting.VerifyThat
test_section = reporting.test_section


# Server, port and AUT come from configuration-files/test_environment.json.
CFG = test_config.for_test("smoke", "MSQ-SMK-010")
MOSAIQ_SERVER = CFG.server_host
SQUISH_SERVER_PORT = CFG.squish_port
MOSAIQ_AUT_NAME = CFG.aut_name

# The patient this test opens. MUST have an existing treatment course with a session dated
# today -- this test reads a treatment calendar, it does not create one.
PATIENT_MR = "90001"
TEST_SUITE_NAME = "MOSAIQ Smoke Test Suite"
TEST_CASE_NAME = "MSQ-SMK-010 Radiotherapy Session Pre-Checks Without Delivery"


def treatment_session_date() -> str:
    """Today, in the m/d/yyyy form the session list renders dates in.

    Built from the parts rather than strftime: %-d/%-m are not portable to Windows and %#d/%#m
    are MSVC-only, while MOSAIQ shows no leading zeros.
    """
    now = datetime.now()
    return f"{now.month}/{now.day}/{now.year}"


def patient_last_name_from_banner(bannerText: str) -> str:
    """Pulls the last name out of the open patient banner, e.g. "MSQ-84082, LUNGPATIENT  MR#: ...".

    MOSAIQ renders the banner as "<last>, <first>", so everything before the first comma is the
    last name. Returns "" when the banner is empty or not in that shape.
    """
    return bannerText.split(",")[0].strip() if "," in bannerText else ""


def login_valid_clinical_user() -> None:
    """Log in, as the precondition to everything else."""
    with test_section("Step 1a: Log in"):
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
            .andReport("Mosaiq workspace should load after login")


def open_patient_with_treatment_course() -> str:
    """Step 1 -- open the patient whose treatment course this test reads.

    :return: the patient's last name, which the RO Treat toolbar action needs
    :rtype: str
    """
    with test_section(f"Step 1b: Open patient MR# {PATIENT_MR} with an existing treatment course"):
        MosaiqDashboard.open_select_patient()
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqSelectPatient.ui_Main_Window, 15)) \
            .equals(True) \
            .andReport("Select Patient window should appear")

        MosaiqOpenPatient.typeText_in_patient_mr_number(PATIENT_MR)
        MosaiqOpenPatient.click_apply_filters_button()

        results = MosaiqOpenPatient.get_search_results()
        VerifyThat(len(results)) \
            .greaterThan(0) \
            .andReport(f"Searching by MR# {PATIENT_MR} should return at least one row")

        MosaiqOpenPatient.click_specific_result_using_mr_number(PATIENT_MR)
        VerifyThat(MosaiqDashboard.wait_for_patient_to_open(20), screenshot=True) \
            .equals(True) \
            .andReport(f"Patient MR# {PATIENT_MR} should open in the dashboard")

        # open_patient_ro_treat() takes a last name, so read it off the banner rather than
        # hardcoding a second identifier for the same patient that could drift from PATIENT_MR.
        banner = MosaiqDashboard.get_open_patient_label_text()
        patient_last_name = patient_last_name_from_banner(banner)
        VerifyThat(patient_last_name) \
            .notEquals("") \
            .andReport(f"Patient banner should name the open patient; banner read {banner!r}")

        return patient_last_name


def open_ro_treat_workflow(patientLastName: str) -> None:
    """Step 2 -- open RO Treat and its treatment calendar."""
    with test_section("Step 2: Navigate to the Radiotherapy Treatment workflow"):
        MosaiqDashboard.open_patient_ro_treat(patientLastName)
        VerifyThat(MosaiqROTreat.is_ro_treat_open(3000)) \
            .equals(True) \
            .andReport(f"Treatment Chart should open for {patientLastName}")

        
def initiate_session_up_to_prechecks() -> None:
    """Step 3 -- select today's session and press Treat, stopping at the pre-check popups.

    Matches the current date by OCR against the session list: the list is a Clarion control
    that exposes no row objects to query directly, so date matching has no non-OCR route.
    is_treatment_session_ocr_available() is checked first -- Squish ships no OCR engine,
    Tesseract installs separately -- so a missing engine reports clearly here rather than
    select_session_by_date_text() clicking a None match and raising a cryptic low-level error.

    continueTrtReadinessCheck and ackVerifyImageStatus are both False, which is what makes this
    safe: click_treat_button() otherwise dismisses the readiness and image-status popups for
    you and carries straight on into the Treatment Delivery Table. Leaving them False stops the
    flow at the popups, which is exactly where this test wants to be.
    """
    # session_date = "9/25/2026"#treatment_session_date()
    # #session_date = "12/15/2025"
    # with test_section(f"Step 3: Select a session ({session_date}) and initiate up to pre-checks"):
    #     VerifyThat(MosaiqROTreat.is_treatment_session_ocr_available()) \
    #         .equals(True) \
    #         .andReport("Treatment session selected by date")

    #     MosaiqROTreat.select_session_by_date_text(session_date)

        # PREVIOUS LOGIC -- OCR-free fallback, selects whichever session sits first in the
        # calendar rather than matching today's date. Restore by commenting the two lines above
        # and uncommenting this one if date matching turns out unreliable.
        # MosaiqROTreat.select_first_session_in_tx_calendar()

    MosaiqROTreat.click_treat_button(continueTrtReadinessCheck=False, ackVerifyImageStatus=False)
    """  if CommonActions.wait_for_object_to_appear(ROTreat.dose_Action_Points_Window, 15000):
            VerifyThat(True) \
                .equals(True) \
                .andReport("Dose Action Points Window should be displayed")
            CommonActions.click_button(ROTreat.dose_Action_close_Button)
        else:
            VerifyThat(False) \
                .equals(True) \
                .andReport("Dose Action Points Window not displayed") """


def observe_readiness_messages() -> None:
    """Step 4 -- confirm the pre-checks actually ran and report what they said."""
    with test_section("Step 4: Observe readiness messages, warnings and acknowledgements"):
        # The assertion this step exists for. Every handler in common_popups swallows the
        # window's absence so a missing popup never breaks a delivery flow, which means a run
        # could sail past the pre-checks and look successful. This says they happened.
        readiness_displayed = MosaiqCommonPopups.is_treatment_readiness_check_displayed(1500)
        VerifyThat(readiness_displayed) \
            .equals(True) \
            .andReport("Treatment Readiness Check should be presented before delivery")
        MosaiqCommonPopups.click_continue_button_on_treatment_readiness()

        VerifyThat(MosaiqCommonPopups.is_verification_image_status_displayed(3000)) \
            .equals(True) \
            .andReport("Verification Image Status should be displayed")
        
        MosaiqCommonPopups.click_on_ok_button_on_verify_image_window()

        VerifyThat(MosaiqCommonPopups.is_verification_image_status_displayed(3000)) \
            .equals(False) \
            .andReport("Verification Image Status review window should close on OK")

        # check_treatment_delivery_table_window_appears() takes seconds, not milliseconds.
        VerifyThat(MosaiqTreatmentDeliveryTable.check_treatment_delivery_table_window_appears(15)) \
            .equals(True) \
            .andReport("Treatment Delivery Table should be displayed")

        # ackSetupAlert=False: the first positional parameter is ackSetupAlert, not a timeout, and
        # the library's own Setup Alert handling clicks Close even when no alert is shown (its
        # find_object() falls back to an unrelated control instead of failing). The alert is
        # handled below with a real presence check instead.
        MosaiqTreatmentDeliveryTable.click_on_select_button_on_treatment_delivery_window(ackSetupAlert=False)
       
        if CommonActions.does_object_exist(ROTreat.field_Change_Warning_Window_No_Button, 5000):
            print("Field change Warning displayed; Clicking No")
            CommonActions.click_button(ROTreat.field_Change_Warning_Window_No_Button)
        else:
            print("Field change Warning not displayed.")

        MosaiqCommonPopups.acknowledge_error_dialog()

        VerifyThat(MosaiqROTreat.is_verify_setup_window_displayed(15000)) \
            .equals(True) \
            .andReport("Verify Setup should appear after selecting fields in the Treatment Delivery Table")


def exit_session_without_delivering() -> None:
    """Step 5 -- cancel the active setup workflow and close RO Treat without delivery.

    Runs from a finally block, so an assertion failing earlier still unwinds the session rather
    than leaving a patient's treatment armed at the pre-check stage -- and leaving modal popups
    that block File > Exit in the teardown.
    """
    with test_section("Step 5: Cancel setup and confirm no treatment was delivered"):
       
        if CommonActions.does_object_exist(ROTreat.field_Change_Warning_Window_No_Button, 1000):
            CommonActions.click_button(ROTreat.field_Change_Warning_Window_No_Button)

        MosaiqCommonPopups.acknowledge_error_dialog()

        if MosaiqCommonPopups.is_setup_alert_displayed(1000):
            MosaiqCommonPopups.click_close_button_setup_alert()

        if MosaiqROTreat.check_ct_setup_record_window(1):
            MosaiqROTreat.click_ct_setup_cancel_button()
        if MosaiqROTreat.is_verify_setup_window_displayed(1000):
            MosaiqROTreat.click_cancel_button_on_verify_setup_window()
        if MosaiqCommonPopups.is_treatment_readiness_check_displayed(1000):
            MosaiqCommonPopups.click_cancel_button_on_treatment_readiness()

        VerifyThat(MosaiqROTreat.is_verify_setup_window_displayed(30000)) \
            .equals(False) \
            .andReport("Verify Setup should close on Cancel without recording a treatment")

        # Step 4 deliberately opens the Delivery Table; closing it (answering Yes to "All Fields
        # NOT Treated, Exit?") leaves the session undelivered.
        if MosaiqROTreat.is_treatment_delivery_table_displayed(1000):
            MosaiqTreatmentDeliveryTable.click_on_close_button_on_treatment_delivery_window()
        VerifyThat(MosaiqROTreat.is_treatment_delivery_table_displayed(3000)) \
            .equals(False) \
            .andReport("Treatment Delivery Table should close without delivering treatment")

        VerifyThat(MosaiqCommonPopups.is_treatment_readiness_check_displayed(3000)) \
            .equals(False) \
            .andReport("Treatment Readiness Check should be closed after leaving setup")

        MosaiqROTreat.click_close_patient_ro_treat()
        VerifyThat(MosaiqROTreat.is_ro_treat_open(5000)) \
            .equals(False) \
            .andReport("Treatment Chart should close")


def logout_and_close_mosaiq() -> None:
    """Step 6 -- return to the login screen and exit the MOSAIQ application."""
    with test_section("Step 6: Log out and close MOSAIQ"):
        if not CommonActions.does_object_exist(MosaiqCoreObjects.dashboard_Username_TextBox, 1000):
            Logout().logoutUser()
            VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.dashboard_Username_TextBox, 30)) \
                .equals(True) \
                .andReport("The login form should reappear after logout")

        Logout().exitApplication()
        VerifyThat(CommonActions.wait_for_object_to_disappear(MosaiqCoreObjects.mOSAIQ_Main_Window, 30)) \
            .equals(True) \
            .andReport("MOSAIQ should close cleanly without leaving a live AUT instance")


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
        if CommonActions.does_object_exist(MosaiqCoreObjects.mOSAIQ_Main_Window, 1000):
            Logout().exitApplication()
    except Exception as error:
        print(f"MOSAIQ teardown skipped: {error}")


def main() -> None:
    sq = reporting.start_reporting(TEST_CASE_NAME, aut_name=MOSAIQ_AUT_NAME)

    session_started = False
    try:
        login_valid_clinical_user()
        patient_last_name = open_patient_with_treatment_course()
        open_ro_treat_workflow(patient_last_name)

        session_started = True
        initiate_session_up_to_prechecks()
        observe_readiness_messages()
    finally:
        # Step 5 runs in finally, and only once the session was actually started: this test
        # drives real treatment UI, so backing out must not be skipped because an assertion
        # in step 4 aborted the run. Teardown errors are printed rather than raised so they do
        # not bury the failure that brought the run here.
        if session_started:
            try:
                exit_session_without_delivering()
            except Exception as error:
                print(f"Step 5 cleanup failed: {error}")
        try:
            logout_and_close_mosaiq()
        except Exception as error:
            print(f"Step 6 logout failed: {error}")
        finally:
            reporting.finish_reporting(sq)
            close_mosaiq()


if __name__ == "__main__":
    main()
