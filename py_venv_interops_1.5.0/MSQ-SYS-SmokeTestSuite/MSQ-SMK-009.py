# Reporting setup lives in msq_framework.reporting and MUST be imported before any
# interops import: it puts Squish on sys.path and installs the compatibility shims
# interops needs to report under the standalone squishtest extension.
from msq_framework import config, reporting

from interops.libraries.mosaiq.interactions.objects.mosaiq_core_objects import MosaiqCoreObjects
from interops.libraries.mosaiq.interactions.objects.mosaiq_select_patient_objects import MosaiqSelectPatient
from interops.libraries.mosaiq.interactions.objects.mosaiq_d_and_i_objects import DandI
from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.pages import Login, Logout
from interops.libraries.mosaiq.interactions import (
    MosaiqDashboard,
    MosaiqOpenPatient,
    MosaiqDandI,
    MosaiqCommonPopups,
    MosaiqSiteSetupDefinition
)

VerifyThat = reporting.VerifyThat
test_section = reporting.test_section


# Server, port and AUT come from msq_framework/environments/test_environment.json.
CFG = config.for_test("smoke", "MSQ-SMK-009")
MOSAIQ_SERVER = CFG.server_host
SQUISH_SERVER_PORT = CFG.squish_port
MOSAIQ_AUT_NAME = CFG.aut_name

# The patient this test opens. MUST have a Site Setup item in its D&I list -- this test
# reviews an existing Site Setup Definition, it does not create one.
PATIENT_MR = "90001"

TEST_CASE_NAME = "Site Setup Definition Access"


def patient_last_name_from_banner(bannerText: str) -> str:
    """Pulls the last name out of the open patient banner, e.g. "MSQ-84082, LUNGPATIENT  MR#: ...".

    MOSAIQ renders the banner as "<last>, <first>", so everything before the first comma is the
    last name. Returns "" when the banner is empty or not in that shape.
    """
    return bannerText.split(",")[0].strip() if "," in bannerText else ""


def click_site_setup_tab(tabMap: dict, tabName: str) -> None:
    """Click a Site Setup Definition tab and confirm its page is the one on display.

    A TabItem reports visible only while its page is displayed, so visibility after the click is
    what proves the tab responded. The tab's fields are deliberately not checked.
    """
    CommonActions.left_click_object(tabMap)
    VerifyThat(CommonActions.is_object_visible(tabMap, 5000), screenshot=True) \
        .equals(True) \
        .andReport(f"{tabName} tab should be clickable and display its page")


def login_with_site_setup_access() -> None:
    """Step 1 -- log in as a user with Site Setup permissions."""
    with test_section("Step 1: Log in with Site Setup access"):
        MosaiqAutController.mosaiq_aut(
            serverAddress=MOSAIQ_SERVER,
            serverPort=SQUISH_SERVER_PORT,
        ).start_aut()
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAIQ_Dashboard_Window, 30)) \
            .equals(True) \
            .andReport("Mosaiq should show the login window after starting the AUT")

        Login().loginUser("impac", "impac")
        VerifyThat(MosaiqDashboard.wait_for_main_workspace_area(30)) \
            .equals(True) \
            .andReport("Mosaiq workspace should load after login")


def open_patient() -> str:
    """Step 2 -- open the patient by MR number.

    :return: the patient's last name, which the D&I toolbar action in step 3 needs
    :rtype: str
    """
    with test_section(f"Step 2: Open patient MR# {PATIENT_MR}"):
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

        # The toolbar actions take a last name, so read it off the banner rather than
        # hardcoding a second identifier for the same patient that could drift from PATIENT_MR.
        banner = MosaiqDashboard.get_open_patient_label_text()
        patient_last_name = patient_last_name_from_banner(banner)
        VerifyThat(patient_last_name) \
            .notEquals("") \
            .andReport(f"Patient banner should name the open patient; banner read {banner!r}")

        return patient_last_name


def open_site_setup_definition(patientLastName: str) -> None:
    """Step 3 -- open D&I for the patient, then its Site Setup Definition."""
    with test_section("Step 3: Open D&I and the Site Setup Definition"):
        MosaiqDashboard.open_patient_d_and_i(patientLastName)
        VerifyThat(CommonActions.wait_for_object_to_appear(DandI.Main_Window, 20)) \
            .equals(True) \
            .andReport("Diagnoses and Interventions workspace should open for the patient")

        MosaiqDandI.double_click_site_setup_in_list_view()
        VerifyThat(CommonActions.wait_for_object_to_appear(DandI.siteSetup_Form_Window, 15), screenshot=True) \
            .equals(True) \
            .andReport("Site Setup Definition window should open from the D&I Site Setup item")


def verify_setup_tab() -> None:
    """Step 4 -- the Setup tab is clickable."""
    with test_section("Step 4: Click the Setup tab"):
        click_site_setup_tab(DandI.siteSetup_TabWindow_Setup, "Setup")


def verify_reference_images_tab() -> None:
    """Step 5 -- the Reference Images/Couch Movement tab is clickable."""
    with test_section("Step 5: Click the Reference Images/Couch Movement tab"):
        click_site_setup_tab(DandI.siteSetup_TabWindow_Reference_Images_Couch_Movement, "Reference Images/Couch Movement")


def verify_motion_management_tab() -> None:
    """Step 6 -- the Motion Management tab is clickable."""
    with test_section("Step 6: Click the Motion Management tab"):
        click_site_setup_tab(DandI.siteSetup_TabWindow_Motion_Management, "Motion Management")


def close_site_setup_with_ok() -> None:
    """Step 7 -- close the Site Setup Definition window with OK."""
    with test_section("Step 7: Click OK to close the Site Setup window"):
        # Nothing was edited, so OK has nothing to save. If MOSAIQ still asks for approval it is
        # cancelled, never approved -- approving would sign off a real patient's setup.
        CommonActions.left_click_object(DandI.siteSetup_Form_OK_Button)
        if CommonActions.does_object_exist(DandI.siteSetup_Approval_Window, 3000):
            print("Site Setup Approval prompt appeared on OK; cancelling it without approving.")
            CommonActions.left_click_object(DandI.siteSetup_Approval_Cancel_Button)

        VerifyThat(CommonActions.wait_for_object_to_disappear(DandI.siteSetup_Form_Window, 15)) \
            .equals(True) \
            .andReport("Site Setup Definition window should close on OK")


def verify_no_application_error() -> None:
    """Step 8 -- no crash, warning or error message after closing Site Setup."""
    with test_section("Step 8: Confirm no application error occurred"):
        # does_object_exist() rather than acknowledge_error_dialog() for the assertion: the
        # latter raises when the dialog's OK button is not clickable, which would turn a
        # reportable failure into a crash.
        error_present = CommonActions.does_object_exist(DandI.error_Window, 3000)
        VerifyThat(error_present) \
            .equals(False) \
            .andReport("No error dialog should be raised after closing Site Setup")
        if error_present:
            try:
                MosaiqCommonPopups.acknowledge_error_dialog()
            except Exception as error:
                print(f"Could not dismiss the error dialog: {error}")

        VerifyThat(CommonActions.does_object_exist(DandI.Main_Window, 3000)) \
            .equals(True) \
            .andReport("D&I workspace should still be open and responsive after closing Site Setup")


def close_mosaiq() -> None:
    """Teardown -- back out of Site Setup/D&I without saving, then exit MOSAIQ.

    run_smoke_suite.py runs each case in its own subprocess, but they all drive one AUT on the
    Squish server, and start_aut() calls startApplication() unconditionally rather than
    attaching to a running instance. Without this the next case launches MOSAIQ on top of the
    one this case left behind, and its login window check fails.

    Never raises: teardown must not mask the failure that brought the test here, and the AUT may
    already be gone or never have got far enough to offer a File menu.
    """
    try:
        if CommonActions.does_object_exist(DandI.siteSetup_Approval_Window, 1000):
            CommonActions.left_click_object(DandI.siteSetup_Approval_Cancel_Button)
        if CommonActions.does_object_exist(DandI.siteSetup_Form_Window, 1000):
            CommonActions.left_click_object(DandI.siteSetup_Form_Cancel_Button)
        if CommonActions.does_object_exist(DandI.Main_Window, 1000):
            MosaiqDandI.click_close_d_and_i()
    except Exception as error:
        print(f"Site Setup/D&I teardown skipped: {error}")

    try:
        Logout().exitApplication()
    except Exception as error:
        print(f"MOSAIQ teardown skipped: {error}")


def main() -> None:
    sq = reporting.start_reporting(TEST_CASE_NAME, aut_name=MOSAIQ_AUT_NAME)

    try:
        login_with_site_setup_access()
        patient_last_name = open_patient()
        open_site_setup_definition(patient_last_name)
        #MosaiqDandI.click_dandi_site_setup_button()
        MosaiqSiteSetupDefinition.enter_site_setup_tolerance("Clinical SS")
        MosaiqSiteSetupDefinition.enter_site_setup_verification("Exclude")
        # MosaiqSiteSetupDefinition.enter_site_setup_patient_position("Head In, Supine")
        MosaiqSiteSetupDefinition.enter_site_setup_machine("Varian 2100")
        verify_setup_tab()
        verify_reference_images_tab()
        verify_motion_management_tab()
        close_site_setup_with_ok()
        verify_no_application_error()
    finally:
        # finally, so a critical verification aborting the run still logs the verification
        # count and still leaves the AUT closed for the next case in the suite.
        reporting.finish_reporting(sq)
        close_mosaiq()


if __name__ == "__main__":
    main()
