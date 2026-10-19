import sys, os, time

ROOT_ENV = r"C:\sys-verification-automation\py_venv_interops_1.5.0"
ROOT_SITE_PACKAGES = os.path.join(ROOT_ENV, "Lib", "site-packages")
DOTVENV_SITE_PACKAGES = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Lib", "site-packages")

# Prefer the root environment site-packages when available, because that is where interops is installed.
if os.path.isdir(ROOT_SITE_PACKAGES) and ROOT_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, ROOT_SITE_PACKAGES)

if os.path.isdir(DOTVENV_SITE_PACKAGES) and DOTVENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, DOTVENV_SITE_PACKAGES)

# Ensure Squish runtime paths are available so the squishtest extension can be imported.
SQUISH_ROOT = r"C:\Program Files (x86)\Squish for Windows 9.2.2"
SQUISH_BIN = os.path.join(SQUISH_ROOT, "bin")
SQUISH_PY = os.path.join(SQUISH_ROOT, "lib", "python")
for p in (SQUISH_BIN, SQUISH_PY):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from interops.libraries.monaco import MonacoAutController
from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.monaco.pages import MonacoLogin
from interops.libraries.monaco.interactions import MonacoDashboard
from interops.libraries.monaco.interactions import common_monaco_ops as CommonMonacoOps
from interops.libraries.monaco.interactions.objects.monaco_core_objects import MonacoCoreObjects
from interops.libraries.monaco.interactions.objects.monaco_dicom_export_objects import MonacoDicomExportObjects
from interops.libraries.squish_actions import CommonActions
from interops.libraries.monaco.pages import dicom_export_dialog
from interops.libraries.mosaiq.interactions import MosaiqDashboard, MosaiqDandI, MosaiqOpenPatient, MosaiqImageList, MosaiqTreatmentDeliveryTable, MosaiqRadiationPrescriptions, MosaiqROTreat, MosaiqSiteSetupDefinition, MosaiqCommonPopups
from interops.libraries.mosaiq.interactions.objects.mosaiq_core_objects import MosaiqCoreObjects
from interops.libraries.integrity.interactions.objects.integrity_objects import IntegrityCoreObjects
from interops.libraries.mosaiq.interactions.objects.mosaiq_d_and_i_objects import DandI
from interops.libraries.mosaiq.pages import Login, Logout
from interops.libraries.integrity import IntegrityAutController
from interops.libraries.integrity.test_tools.interactions import CrowbarFuncs
from remotesystem import RemoteSystem
import ctypes
import squishtest

# Fast-development switches
# Legacy implementation (kept for reference):
# USE_RUNNING_AUT = False   # True: attach to already-open AUTs, False: start AUTs
# Only Crowbar goes through _attach_or_start(); Monaco/Mosaiq call start_aut() directly.
# Crowbar is already running on the Integrity VM, so it must be attached to, not launched.
USE_RUNNING_AUT = True   # True: attach to already-open AUTs, False: start AUTs
SKIP_LOGIN = False        # True when sessions are already logged in
RUN_PHASE = "all"       # "all", "export", "promote"
ALLOW_AUT_START_FALLBACK_ON_ATTACH_FAIL = False  # False: never relaunch AUT when attach fails

# Server and Port configurations
MONACO_SERVER = "10.68.132.154"
MOSAIQ_SERVER = "10.68.132.189"
#MOSAIQ_SERVER = "10.68.132.74"
INTEGRITY_SERVER = "10.68.132.189"  # Example Integrity server address
SQUISH_SERVER_PORT = 4322
CROWBAR_SERVER_PORT = 50004

# Mosaiq image export selections
#MOSAIQ_IMAGE_EXPORT_PATIENT_MR = "TRN0028"
MOSAIQ_IMAGE_EXPORT_PATIENT_FIRST_NAME = "3DCRT"
MOSAIQ_IMAGE_EXPORT_DESTINATION = "Monaco_SCP"
MOSAIQ_IMAGE_EXPORT_PATIENT_MR = "T001"

# Monaco plan export selections
MONACO_CLINIC = "Demo Clinic"
MONACO_CLINICONLY = "Clinic"
MONACO_PATIENT = "3DCRT"
MONACO_PLAN = "VMATPlan2"
#MONACO_PLAN = "MNCVMAT"
EXPORT_MODALITIES = ["Total Plan"]
EXPORT_DESTINATIONS = ["Mosaiq"]
ENABLE_MOSAIQ_IMAGE_EXPORT = True

# Mosaiq plan promotion selections
MOSAIQ_PROMOTE_PATIENT_LAST_NAME = "3DCRT"
PROMOTE_PLAN_NAMES = ["01_VMATPlan2"]

# Mosaiq Treatment Delivery selections
MOSAIQ_TREATMENT_SESSIONS_PATIENT_MR = "T001"
MOSAIQ_TREATMENT_DELIVERY_PATIENT_MR = "2007"


# Other configurations
DEMO_PROGRESS_OBSERVE_SECS = 2.0  # Increase to 3-5 for demos when transfer is very fast.
CONFIRM_PROMOTE = True   # True: click Promote, False: click Cancel
RADIATION_PRESCRIPTION_SITE = ""  # Optional. Set e.g. "ASITE1PHASE1" to update Rx Site after clicking Change.


def _find_window_handle_by_title(titleSearchText: str):
    """Returns the handle of the first visible top-level window whose title contains the
    given search text, or None. These are local OS-level windows outside of any Squish AUT
    context, so they're found via ctypes/user32 directly (pywin32's bundled DLLs in this
    venv are built for Python 3.8, not 3.10).

    :param str titleSearchText: Substring to match against candidate window titles.
    """
    user32 = ctypes.windll.user32
    matches = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

    def _enum_handler(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if titleSearchText in buffer.value:
                matches.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(_enum_handler), 0)
    return matches[0] if matches else None


def maximize_remote_desktop_window(titleSearchText: str) -> bool:
    """Maximizes the local Remote Desktop Connection (mstsc) / VM Connection window whose
    title contains the given search text (e.g. the remote host address).

    :param str titleSearchText: Substring to match against candidate window titles.
    :return: True if a matching window was found and maximized, otherwise False.
    """
    SW_MAXIMIZE = 3
    hwnd = _find_window_handle_by_title(titleSearchText)
    if hwnd is None:
        return False

    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    user32.SetForegroundWindow(hwnd)
    return True


def minimize_remote_desktop_window(titleSearchText: str) -> bool:
    """Minimizes the local Remote Desktop Connection (mstsc) / VM Connection window whose
    title contains the given search text (e.g. the remote host address).

    :param str titleSearchText: Substring to match against candidate window titles.
    :return: True if a matching window was found and minimized, otherwise False.
    """
    SW_MINIMIZE = 6
    hwnd = _find_window_handle_by_title(titleSearchText)
    if hwnd is None:
        return False

    ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
    return True


def drag_remote_desktop_window(titleSearchText: str, xOffset: int, yOffset: int, dx: int, dy: int = 0) -> bool:
    """Drags from a screen coordinate inside the local RDP/VM Connection window.

    Offsets are relative to the top-left corner of the local RDP window. Use this for
    local RDP chrome such as the horizontal scrollbar, which is outside the Squish AUT.

    :param str titleSearchText: Substring to match against candidate window titles.
    :param int xOffset: Start X offset from the RDP window's left edge.
    :param int yOffset: Start Y offset from the RDP window's top edge.
    :param int dx: Horizontal drag distance in pixels.
    :param int dy: Vertical drag distance in pixels.
    :return: True if a matching window was found and dragged, otherwise False.
    """
    hwnd = _find_window_handle_by_title(titleSearchText)
    if hwnd is None:
        return False

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    user32 = ctypes.windll.user32
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False

    start_x = rect.left + xOffset
    start_y = rect.top + yOffset
    end_x = start_x + dx
    end_y = start_y + dy

    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    user32.SetForegroundWindow(hwnd)
    user32.SetCursorPos(start_x, start_y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.1)
    user32.SetCursorPos(end_x, end_y)
    time.sleep(0.1)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return True


def scroll_remote_desktop_window_horizontally(titleSearchText: str, dx: int, xOffset: int = 300, yOffsetFromBottom: int = 18) -> bool:
    """Drags the local RDP horizontal scrollbar by a horizontal pixel distance.

    Tune xOffset if the scrollbar thumb starts at a different location.
    """
    hwnd = _find_window_handle_by_title(titleSearchText)
    if hwnd is None:
        return False

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    rect = RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False

    return drag_remote_desktop_window(
        titleSearchText,
        xOffset=xOffset,
        yOffset=(rect.bottom - rect.top) - yOffsetFromBottom,
        dx=dx,
        dy=0,
    )

# Function to start or attach to an AUT, with optional fallback to starting the AUT if attach fails.
def _attach_or_start(aut_controller, aut_name: str) -> None:
    if USE_RUNNING_AUT:
        try:
            # launch_new_startwinaut helps when no existing startwinaut is attached to the running AUT yet.
            aut_controller.attach_to_aut(launch_new_startwinaut=True, get_running_aut_pid_retries=3)
            return
        except Exception as e:
            if not ALLOW_AUT_START_FALLBACK_ON_ATTACH_FAIL:
                raise RuntimeError(
                    f"Attach failed for {aut_name}: {e}. "
                    "Auto-fallback to start_aut() is disabled to avoid launching a second AUT instance. "
                    "If you want fallback, set ALLOW_AUT_START_FALLBACK_ON_ATTACH_FAIL=True."
                )

            print(f"Attach failed for {aut_name}: {e}. Falling back to start_aut().")

    aut_controller.start_aut()

# Log in to Mosaiq.
def login_mosaiq():
    mosaiq_aut = MosaiqAutController.mosaiq_aut(serverAddress=MOSAIQ_SERVER, serverPort=SQUISH_SERVER_PORT)
    mosaiq_aut.start_aut()
    mosaiq_login = Login()
    mosaiq_login.loginUser("impac", "impac")
    print("Logged in to Mosaiq")
    '''
    try:
        CommonActions.set_context_application_to_foreground(MosaiqCoreObjects.mOSAIQ_Main_Window)
        MosaiqDashboard.maximise_mosaiq_window()
    except Exception as e:
        print(f"Could not maximize Mosaiq window: {e}")
    return mosaiq_aut
    '''

# Log in to Monaco
def login_monaco() -> None:
    monaco_aut = MonacoAutController.monaco_aut(serverAddress=MONACO_SERVER, serverPort=SQUISH_SERVER_PORT)
    monaco_aut.start_aut()

    try:
        CommonActions.wait_for_object_exists(MonacoCoreObjects.user_Validation_Dialog, 2000)
        CommonActions.move_windows_object(MonacoCoreObjects.user_Validation_Dialog, 600, 400)
    except Exception as e:
        print(f"Could not move User Validation dialog: {e}")

    monaco_login = MonacoLogin()
    monaco_login.loginUser("impac", "impac")
    print("Logged in to Monaco")

    try:
        monaco_main_window = CommonActions.wait_for_object_exists(MonacoCoreObjects.monaco_Main_Window, 8000)
        CommonActions.set_context_application_to_foreground(monaco_main_window)
        CommonActions.maximise_windows_object(monaco_main_window)
    except Exception as e:
        print(f"Could not maximize Monaco window: {e}")

    try:
        CommonActions.wait_for_object_exists(MonacoCoreObjects.patient_Selection_Dialog, 20000)
        CommonActions.move_windows_object(MonacoCoreObjects.patient_Selection_Dialog, 600, 400)
    except Exception as e:
        print(f"Could not move Patient Selection dialog: {e}")

# Function to export images from Mosaiq for a specific patient and destination to Monaco.
def mosaiq_image_export() -> None:
    MosaiqDashboard.open_select_patient()
    MosaiqOpenPatient.typeText_in_patient_mr_number(MOSAIQ_IMAGE_EXPORT_PATIENT_MR)
    MosaiqOpenPatient.click_apply_filters_button()
    MosaiqOpenPatient.click_first_search_result()

    if not MosaiqDashboard.wait_for_patient_to_open(25):
        raise AssertionError(f"Failed to open patient MR Number: {MOSAIQ_IMAGE_EXPORT_PATIENT_MR}")

    MosaiqDashboard.open_patient_images(MOSAIQ_IMAGE_EXPORT_PATIENT_MR)
    MosaiqImageList.click_on_export_image_window()
    MosaiqImageList.click_on_export_location_on_export_image_window(MOSAIQ_IMAGE_EXPORT_DESTINATION)
    MosaiqImageList.click_on_export_button_on_export_image_window()
    bring_sending_dicom_progress_to_front_remote()


def bring_sending_dicom_progress_to_front(wait_timeout_secs: int = 17) -> bool:
    """Bring the 'Sending DICOM data' progress UI to foreground when export starts."""
    deadline = time.time() + wait_timeout_secs
    observe_until = None
    seen_once = False

    # Quick polling so we can catch short-lived progress UI and keep it visible while it exists.
    while time.time() < deadline:
        progress_obj = CommonActions.find_any_object([DandI.sending_Dicom_Data_Message_Pane], 200)

        if progress_obj is not None:
            if not seen_once:
                seen_once = True
                observe_until = time.time() + DEMO_PROGRESS_OBSERVE_SECS

            try:
                CommonActions.left_click_object(progress_obj)
            except Exception:
                pass

            try:
                CommonActions.set_context_application_to_foreground(progress_obj)
            except Exception:
                pass

            if observe_until is not None and time.time() >= observe_until:
                return True

            time.sleep(0.1)
            continue

        # If it was already seen and has disappeared, we are done.
        if seen_once:
            return True

        time.sleep(0.05)

    return seen_once


# PowerShell script run directly on the Mosaiq server (via RemoteSystem) to find and foreground
# the DICOM Export progress window using plain Win32 calls - no Squish object queries.
_BRING_DICOM_PROGRESS_TO_FRONT_PS_SCRIPT = r'''
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class DicomProgressWin32 {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Auto)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$script:dicomProgressFound = $false
$callback = {
    param([IntPtr]$hWnd, [IntPtr]$lParam)
    if ([DicomProgressWin32]::IsWindowVisible($hWnd)) {
        $sb = New-Object System.Text.StringBuilder 256
        [DicomProgressWin32]::GetWindowText($hWnd, $sb, 256) | Out-Null
        $title = $sb.ToString()
        if ($title -like "DICOM Export - *" -or $title -like "Sending DICOM data*") {
            [DicomProgressWin32]::ShowWindow($hWnd, 9) | Out-Null
            [DicomProgressWin32]::SetForegroundWindow($hWnd) | Out-Null
            $script:dicomProgressFound = $true
            return $false
        }
    }
    return $true
}
[DicomProgressWin32]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null
if ($script:dicomProgressFound) { Write-Output "FOUND" } else { Write-Output "NOTFOUND" }
'''

def bring_sending_dicom_progress_to_front_remote(retries: int = 24, delay_between_secs: float = 0.25) -> bool:
    """Bring the 'Sending DICOM data' progress window to the foreground.

    Legacy bring_sending_dicom_progress_to_front() polled via CommonActions.find_any_object(),
    but each of those calls costs several seconds of fixed round-trip latency on this connection
    regardless of the local timeout passed in - far slower than the progress window's own
    lifetime when the export itself is fast, so it almost always missed the window entirely.

    This instead runs a single Win32 EnumWindows/SetForegroundWindow script directly on the
    Mosaiq server's OS via RemoteSystem, bypassing Squish's slower object-introspection protocol.
    Retries for a few seconds in case the popup has not appeared yet.
    """
    remote_system = RemoteSystem(host=MOSAIQ_SERVER, port=SQUISH_SERVER_PORT)
    for _ in range(retries):
        try:
            exit_code, stdout, stderr = remote_system.execute(
                ["powershell", "-NoProfile", "-Command", _BRING_DICOM_PROGRESS_TO_FRONT_PS_SCRIPT]
            )
            if "FOUND" in (stdout or ""):
                return True
        except Exception as e:
            print(f"bring_sending_dicom_progress_to_front_remote attempt failed: {e}")
        time.sleep(delay_between_secs)
    return False


# Selects a patient -> selects a plan -> activates the Output tab -> clicks DICOM Export -> selects modalities and destinations -> clicks Export.
def monaco_plan_export() -> None:
    # Move the Clinic/Patient Selection dialog to the left so it isn't hidden behind the main window.
    MonacoDashboard.select_clinic(MONACO_CLINIC)
    MonacoDashboard.search_for_patient(MONACO_PATIENT)
    MonacoDashboard.select_patient_from_clinic_list(MONACO_PATIENT)
    MonacoDashboard.select_plan(MONACO_PLAN)
    
    main_window = CommonActions.wait_for_object_exists(MonacoCoreObjects.monaco_Main_Window, 8000)
    CommonActions.set_context_application_to_foreground(main_window)
    CommonActions.maximise_windows_object(main_window)
    activate_output_tab(main_window)
    #click_dicom_export_button(main_window)
    click_dicom_export_button_ctrlkey(main_window)
    acknowledge_monaco_dialog_if_present()

    export_dialog = dicom_export_dialog.DICOMExport()

    try:
        CommonActions.wait_for_object_exists(MonacoDicomExportObjects.dICOM_Export_Dialog, 8000)
        CommonActions.move_windows_object(MonacoDicomExportObjects.dICOM_Export_Dialog, 600, 400)
    except Exception as e:
        print(f"Could not move DICOM Export dialog: {e}")

    export_dialog.select_modalities(EXPORT_MODALITIES)
    export_dialog.click_export()
    
# Function to activate the Output tab in Monaco's main window.
def activate_output_tab(main_window) -> None:
    output_tab_image_path = os.path.join(
        ROOT_ENV, "Lib", "site-packages", "interops", "libraries", "monaco", "interactions",
        "images", "monaco_output_tab_icon.png")

    if os.path.exists(output_tab_image_path):
        try:
            _t0 = time.time()
            search_options = {"timeout": 3000, "threshold": 95.0}
            output_tab_img_obj = CommonActions.wait_for_image_object(output_tab_image_path, search_options, main_window)
            print(f"[activate_output_tab] image match: {time.time() - _t0:.2f}s, found={output_tab_img_obj is not None}")
            if output_tab_img_obj is not None:
                CommonActions.left_click_object_no_move(output_tab_img_obj)
                time.sleep(0.5)
                return
        except Exception as e:
            print(f"Image match for Output tab failed, falling back: {e}")
    else:
        print(f"[activate_output_tab] reference image not found at: {output_tab_image_path}")

    output_tab_obj = CommonActions.find_any_object([MonacoCoreObjects.toolBar_Output_TabItem], timeout=800)
    if output_tab_obj is not None:
        CommonActions.left_click_object(output_tab_obj)
        time.sleep(1)
        return

    output_tab = CommonActions.get_object_by_ocr_text_in_object(main_window, "Output")
    if output_tab is None:
        raise RuntimeError("Could not locate the 'Output' ribbon tab via OCR.")
    CommonActions.click_screen_area_object(output_tab)
    time.sleep(1)

# Function to click the DICOM Export button in Monaco's Output ribbon.
def click_dicom_export_button(main_window) -> None:
    dicom_export = CommonActions.find_any_object([MonacoCoreObjects.output_Toolbar_Dicom_Export_Button], 2000)
    #dicom_export = CommonActions.find_any_object([MonacoCoreObjects.manual_Dicom_Export_menu_item], 2000)
    if dicom_export is not None:
        print(f"[click_dicom_export_button] found via object tree: {dicom_export}")
        CommonActions.click_button(dicom_export)
        return

    for ocr_label in ("DICOM Export", "DICOM", "Export"):
        dicom_export = CommonActions.get_object_by_ocr_text_in_object(main_window, ocr_label)
        if dicom_export is not None:
            print(f"[click_dicom_export_button] found via OCR '{ocr_label}': {dicom_export}")
            CommonActions.click_screen_area_object(dicom_export)
            return

    raise RuntimeError(
        "Could not locate the 'DICOM Export' button on the Output ribbon via the object tree or OCR."
    )

# Function to click the DICOM Export button in Monaco's Output ribbon using control keys shortcut
def click_dicom_export_button_ctrlkey(main_window) -> None:
    print(f"[click_dicom_export_button_ctrlkey] found via control E keyboard shortcut")
    CommonActions.press_key_sequence("<Ctrl+E>")
    return


# Function to acknowledge any Monaco dialog that may appear, such as confirmation or error dialogs.
def acknowledge_monaco_dialog_if_present() -> None:
    if CommonActions.find_any_object([MonacoCoreObjects.monaco_Dialog], 5000) is None:
        return
    try:
        CommonActions.left_click_object(MonacoCoreObjects.monaco_Dialog_OK_Button)
    except Exception:
        CommonActions.press_enter_key()
    time.sleep(1)


# Function to promote a treatment plan in Mosaiq for a specific patient.
def promote_plan() -> None:
    #MosaiqDashboard.open_select_patient()
    #MosaiqOpenPatient.typeText_in_patient_mr_number(MOSAIQ_IMAGE_EXPORT_PATIENT_MR)
    #MosaiqOpenPatient.click_apply_filters_button()
    #MosaiqOpenPatient.click_first_search_result()

    MosaiqDashboard.open_patient_d_and_i(MOSAIQ_PROMOTE_PATIENT_LAST_NAME)
    MosaiqDandI.select_last_item_in_list_view()
    MosaiqDandI.click_d_and_i_promote_button()
    if CONFIRM_PROMOTE:
        resolve_promote_errors_by_ignoring(wait_timeout_ms=3000)
        CommonActions.wait_for_object_to_disappear(DandI.promotePlan_Main_Dialog, timeoutInSecs=5)

    
# Radiation Prescription workflow: select Rad Rx site item, open Rad Rx, then click Change.
def set_fractionation_pattern() -> None:
    #MosaiqDashboard.open_select_patient()
    #MosaiqOpenPatient.typeText_in_patient_mr_number(MOSAIQ_IMAGE_EXPORT_PATIENT_MR)
    #MosaiqOpenPatient.click_apply_filters_button()
    #MosaiqOpenPatient.click_first_search_result()
    #MosaiqDashboard.open_patient_d_and_i(MOSAIQ_PROMOTE_PATIENT_LAST_NAME)

    #MosaiqDandI.click_refresh_d_and_i_button()
    MosaiqDandI.select_radiation_in_list_view()
    #MosaiqDandI.select_specified_item_in_list_view("Rad Rx: 3DCRT")
    #MosaiqDandI.select_option_from_main_list_view("Rad Rx: 3DCRT")
    MosaiqDandI.open_rad_rx_window()
    MosaiqRadiationPrescriptions.click_rad_rx_change_button()
    MosaiqRadiationPrescriptions.click_rad_rx_fractionation_pattern_dropdown()
    MosaiqRadiationPrescriptions.click_rad_rx_wave_setup_form_ok_button()
    CommonActions.press_enter_key()
    #time.sleep(1)
    #MosaiqRadiationPrescriptions.click_rad_rx_ok_button()
    #time.sleep(2)
    MosaiqRadiationPrescriptions.click_rad_rx_close_button()
    

def resolve_promote_errors_by_ignoring(wait_timeout_ms: int = 7000) -> bool:
    """If a promote validation/error UI appears, select rows and choose Ignore.

    Returns True when an Ignore action was performed, otherwise False.
    """
    promote_dialog = CommonActions.find_any_object([DandI.promotePlan_Main_Dialog], wait_timeout_ms)
    if promote_dialog is None:
        return False

    # First click the Action-column marker (typically shown as "??") to select the target row.
    searchable_regions = [promote_dialog]
    for container_map in (
        {"container": DandI.promotePlan_Main_Dialog, "type": "Tree"},
        {"container": DandI.promotePlan_Main_Dialog, "type": "ListView"},
        {"container": DandI.promotePlan_Main_Dialog, "type": "Table"},
    ):
        try:
            searchable_regions.append(CommonActions.find_object(container_map, timeout=1000))
        except Exception:
            continue

    # Preferred path: click the error row by stable business text first.
    selected_target_row = False
    for region_obj in searchable_regions:
        for row_text in ("Control Points", "Control Point"):
            try:
                row_obj = CommonActions.get_object_by_ocr_text_in_object(region_obj, row_text, 1000)
                if row_obj is not None:
                    CommonActions.click_screen_area_object(row_obj)
                    selected_target_row = True
                    break
            except Exception:
                continue
        if selected_target_row:
            break

    # Final fallback: select all rows when neither row text nor marker could be selected.
    if not selected_target_row:
        for container_map in (
            {"container": DandI.promotePlan_Main_Dialog, "type": "Tree"},
            {"container": DandI.promotePlan_Main_Dialog, "type": "ListView"},
            {"container": DandI.promotePlan_Main_Dialog, "type": "Table"},
        ):
            try:
                container_obj = CommonActions.find_object(container_map, timeout=1000)
                CommonActions.left_click_object(container_obj)
                CommonActions.press_key_sequence("<Ctrl+a>")
                break
            except Exception:
                continue

    ignore_selected = False
    try:
        CommonActions.left_click_object(DandI.promotePlan_Ignore_Button)
        ignore_selected = True
    except Exception:
        ignore_selected = False

    if not ignore_selected:
        # Fallback only if the mapped locator misses on this session.
        ignore_candidates = [
            {"container": DandI.promotePlan_Main_Dialog, "text": "Ignore (XX)", "type": "RadioButton"},
            {"container": DandI.promotePlan_Main_Dialog, "text": "Ignore", "type": "RadioButton"},
            {"text": "Ignore (XX)", "type": "RadioButton"},
            {"text": "Ignore", "type": "RadioButton"},
            {"text": "Ignore", "type": "Button"},
        ]
        ignore_obj = CommonActions.find_any_object(ignore_candidates, 1500)
        if ignore_obj is None:
            return False
        CommonActions.left_click_object(ignore_obj)

    CommonActions.left_click_object(DandI.promotePlan_Promote_Button)

    # If an apply/OK action is needed on the same prompt, confirm it.
    ok_obj = CommonActions.find_any_object(
        [
            {"container": DandI.promotePlan_Main_Dialog, "text": "OK", "type": "Button"},
            {"text": "OK", "type": "Button"},
            {"text": "Apply", "type": "Button"},
        ],
        1200,
    )
    '''
    if ok_obj is not None:
        CommonActions.left_click_object(ok_obj)
    '''
    return True


# Adds treatment sessions for a specific patient in Mosaiq.
def add_treatment_sessions() -> None:
    #MosaiqDashboard.open_select_patient()
    #MosaiqOpenPatient.typeText_in_patient_mr_number(MOSAIQ_TREATMENT_SESSIONS_PATIENT_MR)
    #MosaiqOpenPatient.click_apply_filters_button()
    #MosaiqOpenPatient.click_specific_result_using_mr_number(MOSAIQ_TREATMENT_SESSIONS_PATIENT_MR)
    
    MosaiqDashboard.open_patient_ro_treat(MOSAIQ_TREATMENT_SESSIONS_PATIENT_MR)
    treatment_session_pane = MosaiqROTreat.open_tx_calendar()
    
    MosaiqROTreat.click_insert_sessions_tab(treatment_session_pane)
    MosaiqROTreat.select_course_prescription_by_name("3DCRT")
    #MosaiqROTreat.set_session_start_date("09/8/2026")
    MosaiqROTreat.click_insert_sessions_button()
    MosaiqROTreat.clear_insert_sessions_dialog()
    MosaiqROTreat.click_schedule_all_fields()
    MosaiqROTreat.click_fields_to_be_scheduled_add_all_button()
    MosaiqROTreat.click_fields_to_be_scheduled_ok_button() 
    MosaiqROTreat.click_schedule_fields_button()
    
    MosaiqROTreat.open_treatment_status()
    MosaiqROTreat.select_approved_status_in_record_status()
    MosaiqROTreat.enter_record_status_signature_password("impac")
    MosaiqROTreat.click_record_status_ok_button()
    MosaiqROTreat.click_close_patient_ro_treat()

    
# Treatment delivery workflow
def treatment_delivery() -> None:
    MosaiqDashboard.open_select_patient()
    MosaiqOpenPatient.typeText_in_patient_mr_number(MOSAIQ_TREATMENT_DELIVERY_PATIENT_MR)
    MosaiqOpenPatient.click_apply_filters_button()
    MosaiqOpenPatient.click_specific_result_using_mr_number(MOSAIQ_TREATMENT_DELIVERY_PATIENT_MR)
    MosaiqDashboard.open_patient_ro_treat(MOSAIQ_TREATMENT_DELIVERY_PATIENT_MR)
    #MosaiqROTreat.select_session_by_date_text("2/02/2026")
    MosaiqROTreat.click_treat_button()
    MosaiqTreatmentDeliveryTable.click_on_select_button_on_treatment_delivery_window()

    crowbar_aut = IntegrityAutController.crowbar_aut(serverAddress=INTEGRITY_SERVER, serverPort=CROWBAR_SERVER_PORT)
    _attach_or_start(crowbar_aut, "Crowbar")

    #CommonActions.set_context_application_to_foreground(IntegrityCoreObjects.integrity_Main_Window)
    #CrowbarFuncs.set_app_window_to_foreground()
    CrowbarFuncs.disengage_fkp_start_beam_button()
    #CommonActions.set_context_application_to_foreground(MosaiqCoreObjects.mOSAIQ_Main_Window)
    #CommonActions.maximize_window()

    MosaiqROTreat.check_record_treatment_window()
    MosaiqROTreat.enter_note_in_record_treatment_window("Treatment was successful.")
    MosaiqROTreat.click_record_treatment_record_button()
    MosaiqTreatmentDeliveryTable.click_on_close_button_on_treatment_delivery_window()

 
# Generates a treatment report for a specific patient in Mosaiq.
def generate_treatment_report() -> None:
    #MosaiqDashboard.open_select_patient()
    #MosaiqOpenPatient.typeText_in_patient_mr_number(MOSAIQ_TREATMENT_DELIVERY_PATIENT_MR)
    #MosaiqOpenPatient.click_apply_filters_button()
    #MosaiqOpenPatient.click_specific_result_using_mr_number(MOSAIQ_TREATMENT_DELIVERY_PATIENT_MR)
    #MosaiqDashboard.open_patient_ro_treat(MOSAIQ_TREATMENT_DELIVERY_PATIENT_MR)

    
    MosaiqROTreat.right_click_on_treatment_calendar_session()
    # Legacy implementation (kept for reference): no RDP viewport adjustment after Print OK.
    # MosaiqROTreat.click_daily_reports__on_treatment_calender_session_popup_window()
    MosaiqROTreat.click_daily_reports__on_treatment_calender_session_popup_window(
        after_print_ok=lambda: scroll_remote_desktop_window_horizontally(MOSAIQ_SERVER, dx=300),
        after_report_close=lambda: scroll_remote_desktop_window_horizontally(MOSAIQ_SERVER, dx=-300),
    )
    MosaiqROTreat.click_close_patient_ro_treat()


def logout() -> None:
    mosaiq_logout = Logout()
    mosaiq_logout.logoutUser()

    
def main() -> None:
       
    mosaiq_aut = login_mosaiq()
    mosaiq_image_export()
    time.sleep(15)  # Wait for the DICOM export to complete before proceeding.

    
    try:
        minimize_remote_desktop_window(MOSAIQ_SERVER)
    except Exception as e:
        print(f"Could not minimize Mosaiq Remote Desktop window: {e}")

    try:
        maximize_remote_desktop_window(MONACO_SERVER)
    except Exception as e:
        print(f"Could not maximize Monaco Remote Desktop window: {e}")

    login_monaco()
    monaco_plan_export()

    try:
        minimize_remote_desktop_window(MONACO_SERVER)
    except Exception as e:
        print(f"Could not minimize Monaco Remote Desktop window: {e}")

    try:
        maximize_remote_desktop_window(MOSAIQ_SERVER)
    except Exception as e:
        print(f"Could not maximize Mosaiq Remote Desktop window: {e}")

    '''
    try:
        CommonActions.set_context_application_to_foreground(MonacoCoreObjects.monaco_Main_Window)
        CommonActions.minimize_window()
    except Exception as e:
       print(f"Could not minimize Monaco window: {e}")

    try:
       minimize_remote_desktop_window(MONACO_SERVER)
    except Exception as e:
       print(f"Could not minimize Monaco Remote Desktop window: {e}")
    
    
    try:
        CommonActions.set_context_application_to_foreground(MosaiqCoreObjects.mOSAIQ_Main_Window)
        MosaiqDashboard.maximise_mosaiq_window()
    except Exception as e:
        print(f"Could not maximize Mosaiq window: {e}")
    '''

    promote_plan()
    #set_fractionation_pattern()
    add_treatment_sessions()
    treatment_delivery()
    generate_treatment_report()
    logout()
    
    
if __name__ == "__main__":
    main()










    











