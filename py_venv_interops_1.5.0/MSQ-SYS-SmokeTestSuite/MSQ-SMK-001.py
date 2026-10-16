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
from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.pages import Login
from interops.libraries.mosaiq.pages import Logout
from interops.libraries.mosaiq.interactions import (
    MosaiqDashboard,
    MosaiqOpenPatient,
    MosaiqChart,
    MosaiqDandI,
    MosaiqDiagnosesProblemsAndStaging,
    MosaiqSchedule,
)

VerifyThat = reporting.VerifyThat
test_section = reporting.test_section

MOSAIQ_SERVER = "10.68.134.200"
SQUISH_SERVER_PORT = 4322

TEST_CASE_NAME = "MOSAIQ Client Launch and Valid User Login"
MOSAIQ_AUT_NAME = "accwin"  # matches MosaiqAutController._aut_name


def close_mosaiq() -> None:
    """Teardown -- exit MOSAIQ so the next case starts from a clean launch.

    run_smoke_suite.py runs each case in its own subprocess, but they all drive one AUT on the
    Squish server, and start_aut() calls startApplication() unconditionally rather than
    attaching to a running instance. Logging out at the end of this case is not enough: it
    leaves MOSAIQ running at the login window, so the next case launches a second instance on
    top of it and its own login window check fails.

    Never raises: teardown must not mask the failure that brought the test here, and the AUT may
    already be gone or never have got far enough to offer a File menu.
    """
    try:
        Logout().exitApplication()
    except Exception as error:
        print(f"MOSAIQ teardown skipped: {error}")


def run_test() -> None:
    with test_section("Start Mosaiq AUT from configured workstation"):
        MosaiqAutController.mosaiq_aut(
            serverAddress=MOSAIQ_SERVER,
            serverPort=SQUISH_SERVER_PORT,
        ).start_aut()
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAIQ_Dashboard_Window, 30)) \
            .equals(True) \
            .andReport("Mosaiq workspace should show the login window after starting the AUT")
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.dashboard_Username_TextBox, 30)) \
            .equals(True) \
            .andReport("The Username field should be visible before login")
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.dashboard_Password_TextBox, 30)) \
            .equals(True) \
            .andReport("The Password field should be visible before login")

    with test_section("Enter valid credentials and click Login/OK"):
        Login().loginUser("impac", "impac")
        VerifyThat(MosaiqDashboard.wait_for_main_workspace_area(30)) \
            .equals(True) \
            .andReport("Mosaiq home shell should load after a successful login")

    with test_section("Verify home shell - menus, toolbar, workspace"):
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAIQ_MenuBar, 15)).equals(True).andReport("MOSAIQ home shell should expose the menu bar")
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAQIQ_ToolbarDockArea, 15)).equals(True).andReport("MOSAIQ home shell should expose the toolbar dock area")
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAQIQ_RightToolbarPanelArea, 15)).equals(True).andReport("MOSAIQ home shell should expose the right toolbar panel")
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAIQ_Home_Workspace_Area, 15)).equals(True).andReport("MOSAIQ home shell should expose the workspace area")

    # with test_section("Verify logged-in user identity is displayed"):
    #     VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.loggedInUser_Identity_Label, 15)).equals(True).andReport("Logged-in user identity label should be visible in the session header")

    with test_section("Log out and close without error"):
        Logout().logoutUser()
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.dashboard_Username_TextBox, 30)) \
            .equals(True) \
            .andReport("The login form should reappear after logout")
        Logout().exitApplication()
        VerifyThat(CommonActions.wait_for_object_to_disappear(MosaiqCoreObjects.mOSAIQ_Main_Window, 30)) \
            .equals(True) \
            .andReport("Mosaiq should close cleanly without leaving a live AUT instance")


def main() -> None:
    sq = reporting.start_reporting(TEST_CASE_NAME, aut_name=MOSAIQ_AUT_NAME)

    try:
        run_test()
    finally:
        # finally, so a critical verification aborting the run still logs the verification
        # count and still leaves the AUT closed for the next case in the suite.
        reporting.finish_reporting(sq)
        close_mosaiq()


if __name__ == "__main__":
    main()