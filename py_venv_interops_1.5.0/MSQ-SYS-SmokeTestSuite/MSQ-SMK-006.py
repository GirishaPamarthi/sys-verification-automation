import time

from msq_framework import config

from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.interactions import MosaiqDashboard, MosaiqOpenPatient, MosaiqQCL
from interops.libraries.mosaiq.pages import Login, Logout

# Server, port and AUT come from msq_framework/environments/test_environment.json.
CFG = config.for_test("smoke", "MSQ-SMK-006")
MOSAIQ_SERVER = CFG.server_host
SQUISH_SERVER_PORT = CFG.squish_port

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










    











