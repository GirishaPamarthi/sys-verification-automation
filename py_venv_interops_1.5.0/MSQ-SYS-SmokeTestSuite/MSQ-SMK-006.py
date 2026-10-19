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

from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.interactions import MosaiqDashboard, MosaiqOpenPatient, MosaiqQCL
from interops.libraries.mosaiq.pages import Login, Logout

# Server and Port configurations
MONACO_SERVER = "10.68.132.154"
MOSAIQ_SERVER = "10.68.132.189"
SQUISH_SERVER_PORT = 4322

# Log in to Mosaiq.
def login_mosaiq():
    mosaiq_aut = MosaiqAutController.mosaiq_aut(serverAddress=MOSAIQ_SERVER, serverPort=SQUISH_SERVER_PORT)
    mosaiq_aut.start_aut()
    mosaiq_login = Login()
    mosaiq_login.loginUser("impac", "impac")

# Select the Quality Check List (QCL) worklist.
def open_qcl_worklist():
    MosaiqDashboard.open_QCL_tasks()
    time.sleep(0.3)
    if not MosaiqQCL.wait_for_qcl_window():
        raise RuntimeError("Quality Check List Tasks window did not open successfully")
    print("Quality Check List Tasks window opened successfully")

    # Print the Quality Check List (QCL) tasks.
def print_qcl_list():
    MosaiqQCL.verify_qcl_has_entries()
    task_and_department = MosaiqQCL.read_qcl_task_and_department()
    print(f"QCL tasks (name, department): {task_and_department}")
    MosaiqQCL.print_qcl_row(0)
    MosaiqQCL.print_qcl_row_with_headers(0)

# Verify the details of the first QCL task.
def verify_qcl_details():
    MosaiqQCL.compare_first_qcl_row_after_double_click()

def close_qcl_details_window():
    CommonActions.press_key_sequence("<Alt+l>")
    MosaiqQCL.click_close_button()

# Log out of Mosaiq.
def logout() -> None:
    mosaiq_logout = Logout()
    mosaiq_logout.logoutUser()
   
# Main function to run the smoke test.
def main() -> None:
    login_mosaiq()
    try:
        open_qcl_worklist()
        print_qcl_list()
        verify_qcl_details()
        close_qcl_details_window()
    finally:
        logout()
   
if __name__ == "__main__":
    main()










    











