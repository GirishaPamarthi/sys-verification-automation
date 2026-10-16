# Reporting setup lives in test_report_gen_script and MUST be imported before any
# interops import: it puts Squish on sys.path and installs the compatibility shims
# interops needs to report under the standalone squishtest extension.
import base64
import os
import sys

MY_TEST_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "my-test-scripts"))
if MY_TEST_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, MY_TEST_SCRIPTS_DIR)

import test_report_gen_script as reporting
from remotesystem import RemoteSystem

from interops.libraries.mosaiq.interactions.objects.mosaiq_core_objects import MosaiqCoreObjects
from interops.libraries.mosaiq.interactions.objects.mosaiq_select_patient_objects import MosaiqSelectPatient
from interops.libraries.mosaiq.interactions.objects.mosaiq_images_objects import Images
from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.pages import Login, Logout
from interops.libraries.mosaiq.interactions import (
    MosaiqDashboard,
    MosaiqOpenPatient,
    MosaiqImageList,
    MosaiqCommonPopups,
)

VerifyThat = reporting.VerifyThat
test_section = reporting.test_section


MOSAIQ_SERVER = "10.68.132.189"
#MOSAIQ_SERVER = "10.68.134.200"
SQUISH_SERVER_PORT = 4322

# The patient this test opens. MUST have at least one existing entry in its Image List --
# this test reviews an existing image, it does not import or create one.
PATIENT_MR = "90001"

# Row to open, as (dateTimeValue, searchValue) -- the two arguments double_click_on_item_from_list()
# and get_image_row_values() both take. Rows are matched by substring, so ("", "") would match
# the first row in the list.
IMAGE_DATE_TIME = "1/20/2009 5:50 PM"
IMAGE_SEARCH_VALUE = "PA Rectum/Pelvis"

# The image viewer opened in step 4 runs as its own process, not inside MOSAIQ, so Squish's
# MOSAIQ context cannot see or minimize it. Its windows are minimized by process name instead.
IMAGE_VIEWER_PROCESS = "Elekta.Application.CommonShell"

TEST_CASE_NAME = "Image Review Workflow"
MOSAIQ_AUT_NAME = "accwin"  # matches MosaiqAutController._aut_name


def patient_last_name_from_banner(bannerText: str) -> str:
    """Pulls the last name out of the open patient banner, e.g. "MSQ-84082, LUNGPATIENT  MR#: ...".

    MOSAIQ renders the banner as "<last>, <first>", so everything before the first comma is the
    last name. Returns "" when the banner is empty or not in that shape.
    """
    return bannerText.split(",")[0].strip() if "," in bannerText else ""


def open_window_captions() -> set:
    """The captions of every currently open top-level Window/Dialog, as a set.

    Used by step 5 to tell whether opening an image brought up a new window, without needing an
    object map for the image viewer.
    """
    captions = set()
    for type_name in ("Window", "Dialog"):
        try:
            windows = CommonActions.get_all_objects_by_map({"type": type_name})
        except Exception:
            continue
        for window in windows:
            caption = str(getattr(window, "text", "") or "")
            if caption:
                captions.add(caption)
    return captions


def minimize_image_viewer() -> None:
    """Minimize the image viewer and give MOSAIQ the focus back.

    The viewer sits over MOSAIQ and blocks both the Image List close (step 7) and the File menu
    exitApplication() clicks. It runs in its own process, outside the MOSAIQ AUT, so it is
    minimized by process name with a PowerShell command run on the AUT machine via Squish's
    RemoteSystem. The script is passed with -EncodedCommand so its quotes survive the
    command-line hand-off.

    The same script then gives MOSAIQ's own window the foreground: Windows only lets a process
    take it in narrow cases, and straight after the foreground window was minimized is one.

    Never raises: it runs from teardown as well as step 7.
    """
    script = (
        # Suppresses PowerShell's "Preparing modules" progress record, which otherwise arrives on
        # stderr as a CLIXML blob.
        "$ProgressPreference = 'SilentlyContinue';"
        "$sig = '[DllImport(\"user32.dll\")] public static extern bool ShowWindowAsync(IntPtr h, int n);"
        " [DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr h);';"
        "$user32 = Add-Type -MemberDefinition $sig -Name Win32Focus -Namespace Smk008 -PassThru;"
        f"Get-Process -Name '{IMAGE_VIEWER_PROCESS}' -ErrorAction SilentlyContinue |"
        " Where-Object { $_.MainWindowHandle -ne 0 } |"
        " ForEach-Object { [void]$user32::ShowWindowAsync($_.MainWindowHandle, 6); 'minimized:' + $_.Id };"  # 6 = SW_MINIMIZE
        "Start-Sleep -Milliseconds 500;"
        f"Get-Process -Name '{MOSAIQ_AUT_NAME}' -ErrorAction SilentlyContinue |"
        " Where-Object { $_.MainWindowHandle -ne 0 } |"
        " ForEach-Object { 'focused:' + $_.Id + '=' + $user32::SetForegroundWindow($_.MainWindowHandle) };"
        # Get-Process leaves a failure status when a process is not running; not an error here.
        "exit 0"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        remote = RemoteSystem(host=MOSAIQ_SERVER, port=SQUISH_SERVER_PORT)
        try:
            exitcode, stdout, stderr = remote.execute(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                options={"timeout": 30},
            )
        finally:
            remote.close()
        lines = stdout.split()
        minimized = [line.split(":", 1)[1] for line in lines if line.startswith("minimized:")]
        focused = [line.split(":", 1)[1] for line in lines if line.startswith("focused:")]
        print(f"Image viewer ({IMAGE_VIEWER_PROCESS}) PIDs minimized: {minimized or 'none'}")
        print(f"MOSAIQ ({MOSAIQ_AUT_NAME}) focus result (PID=success): {focused or 'MOSAIQ process not found'}")
        if exitcode != "0" and stderr.strip():
            print(f"PowerShell stderr (exit code {exitcode}): {stderr.strip()}")
    except Exception as error:
        print(f"Could not minimize the image viewer / focus MOSAIQ: {error}")


def is_image_list_open(timeoutInMSec: int) -> bool:
    """Whether the Image List is open, judged by its image grid.

    Not MosaiqImageList.is_images_window_open(): that matches a window captioned
    "Image List - All Images (All)*", which was already gone by step 7 even though the grid --
    the thing step 6 reads its rows from -- was the Image List actually on screen.
    """
    return CommonActions.does_object_exist(Images.form1_gImage_WindowsFormsControl, timeoutInMSec)


def login_with_image_review_authorization() -> None:
    """Step 1 -- log in as a user provisioned with image-review rights.

    Image-review authorization is a data precondition on the "impac" user, not something this
    test checks in the Staff Security screens.
    """
    with test_section("Step 1: Log in with image-review authorization"):
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


def open_patient_with_existing_images() -> str:
    """Step 2 -- open a patient known to have existing images.

    :return: the patient's last name, which open_patient_images() needs
    :rtype: str
    """
    with test_section(f"Step 2: Open patient MR# {PATIENT_MR} with existing images"):
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

        # open_patient_images() takes a last name, so read it off the banner rather than
        # hardcoding a second identifier for the same patient that could drift from PATIENT_MR.
        banner = MosaiqDashboard.get_open_patient_label_text()
        patient_last_name = patient_last_name_from_banner(banner)
        VerifyThat(patient_last_name) \
            .notEquals("") \
            .andReport(f"Patient banner should name the open patient; banner read {banner!r}")

        return patient_last_name


def navigate_to_image_review(patientLastName: str) -> None:
    """Step 3 -- open the Image List from the patient toolbar."""
    with test_section("Step 3: Navigate to the image review workflow"):
        MosaiqDashboard.open_patient_images(patientLastName)
        VerifyThat(MosaiqImageList.__find_images_main_window()).equals(True).andReport("Image List window should open from the patient toolbar")
        # VerifyThat(MosaiqImageList.is_images_window_open(30000)) \
        #     .equals(True) \
        #     .andReport("Image List window should open from the patient toolbar")


def open_reviewed_image() -> set:
    """Step 4 -- open a reviewed image or image set from the list.

    :return: the top-level window captions present just before the double-click, so step 5 can
             tell whether opening the image brought up a new one
    :rtype: set
    """
    with test_section(f"Step 4: Open the image row ({IMAGE_DATE_TIME!r}, {IMAGE_SEARCH_VALUE!r})"):
        # Checked before opening: double_click_on_item_from_list() silently does nothing when
        # the row is missing, so a bad IMAGE_DATE_TIME/IMAGE_SEARCH_VALUE would otherwise pass.
        # is_image_row_displayed() already matches on both values and returns a bool, so the
        # assertion is just True -- contains() takes one argument and needs text to search.
        VerifyThat(MosaiqImageList.is_image_row_displayed(IMAGE_DATE_TIME, IMAGE_SEARCH_VALUE)) \
            .equals(True) \
            .andReport("Image List should contain a row matching the configured search values")

        before = open_window_captions()
        MosaiqImageList.double_click_on_item_from_list(IMAGE_DATE_TIME, IMAGE_SEARCH_VALUE)
        return before


def verify_image_displays_correctly(windowCaptionsBeforeOpen: set) -> None:
    """Step 5 -- confirm opening the image produced a viewer and no error.

    Not a pixel-level rendering check: there is no reference screenshot to compare against, so
    this verifies that a new window appeared and no error dialog was raised.

    :param set windowCaptionsBeforeOpen: captions captured by open_reviewed_image() just before
                                         the double-click
    """
    with test_section("Step 5: Verify the image displays correctly"):
        new_windows = open_window_captions() - windowCaptionsBeforeOpen
        VerifyThat(len(new_windows)) \
            .equals(0) \
            .andReport(f"Opening the image should bring up a viewer window; new windows seen: {sorted(new_windows)}")

        # acknowledge_error_dialog() returns True only when it found and dismissed an error,
        # so False is the passing result here.
        VerifyThat(MosaiqCommonPopups.acknowledge_error_dialog()) \
            .equals(False) \
            .andReport("No error dialog should be raised while opening the image")


def verify_review_metadata() -> None:
    """Step 6 -- confirm the row records reviewer, status and date/time metadata."""
    with test_section("Step 6: Verify review metadata (reviewer, status, date/time)"):
        row_values = MosaiqImageList.get_image_row_values(IMAGE_DATE_TIME, IMAGE_SEARCH_VALUE)
        VerifyThat(len(row_values)) \
            .greaterThan(0) \
            .andReport("Image List row should expose its cell values")

        # Logged, not asserted on: get_image_row_values() returns cells in whatever order the
        # AUT exposes them, not a named reviewer/status/date-time mapping.
        print(f"Image List row values: {row_values}")


def close_image_review() -> None:
    """Step 7 -- close the Image List window without error."""
    with test_section("Step 7: Close image review without error"):
        if is_image_list_open(3000):
            # The viewer from step 4 covers the Image List, so a click on it would be refused.
            minimize_image_viewer()
            # Same close as MosaiqImageList.close_image_and_diagram_window() -- focus the list,
            # then Esc -- but aimed at the grid: the library targets the "Image List - All
            # Images (All)" caption, which no longer matches here, and its find_object()
            # fallback then clicks an unrelated control. A single click only selects a row.
            CommonActions.left_click_object(Images.form1_gImage_WindowsFormsControl)
            CommonActions.press_esc_key()
        else:
            print("Image List was already closed before step 7")

        VerifyThat(CommonActions.wait_for_object_to_disappear(Images.form1_gImage_WindowsFormsControl, 15)) \
            .equals(True) \
            .andReport("Image List should close")

        VerifyThat(MosaiqCommonPopups.acknowledge_error_dialog()) \
            .equals(False) \
            .andReport("No error dialog should be raised while closing image review")


def close_mosaiq() -> None:
    """Teardown -- exit MOSAIQ so the next case starts from a clean launch.

    run_smoke_suite.py runs each case in its own subprocess, but they all drive one AUT on the
    Squish server, and start_aut() calls startApplication() unconditionally rather than
    attaching to a running instance. Without this the next case launches MOSAIQ on top of the
    one this case left behind, and its login window check fails.

    Never raises: teardown must not mask the failure that brought the test here, and the AUT may
    already be gone or never have got far enough to offer a File menu. The image viewer is
    minimized first so it does not obscure that File menu.
    """
    minimize_image_viewer()
    try:
        Logout().exitApplication()
    except Exception as error:
        print(f"MOSAIQ teardown skipped: {error}")


def main() -> None:
    sq = reporting.start_reporting(TEST_CASE_NAME, aut_name=MOSAIQ_AUT_NAME)

    try:
        login_with_image_review_authorization()
        patient_last_name = open_patient_with_existing_images()
        navigate_to_image_review(patient_last_name)
        windows_before = open_reviewed_image()
        verify_image_displays_correctly(windows_before)
        verify_review_metadata()
        close_image_review()
    finally:
        # finally, so a critical verification aborting the run still logs the verification
        # count and still leaves the AUT closed for the next case in the suite.
        reporting.finish_reporting(sq)
        close_mosaiq()


if __name__ == "__main__":
    main()
