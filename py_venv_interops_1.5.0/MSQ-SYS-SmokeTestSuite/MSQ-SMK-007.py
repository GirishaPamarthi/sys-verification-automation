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
from interops.libraries.mosaiq.interactions import MosaiqDashboard, MosaiqOpenPatient, MosaiqCodeCapture
from interops.libraries.mosaiq.pages import Login, Logout

# Server and Port configurations
MONACO_SERVER = "10.68.132.154"
MOSAIQ_SERVER = "10.68.132.189"
SQUISH_SERVER_PORT = 4322
MOSAIQ_ORDERS_PATIENT_MR = "90001"

# Pre-requisites: Ensure that the patient with MR ID specified in MOSAIQ_ORDERS_PATIENT_MR exists in the database and has 
# some codes captured. Or change the patient ID to a different one that has codes captured.

# Log in to Mosaiq.
def login_mosaiq():
    mosaiq_aut = MosaiqAutController.mosaiq_aut(serverAddress=MOSAIQ_SERVER, serverPort=SQUISH_SERVER_PORT)
    mosaiq_aut.start_aut()
    mosaiq_login = Login()
    mosaiq_login.loginUser("impac", "impac")

# Select a patient.
def select_patient():
    MosaiqDashboard.open_select_patient()
    MosaiqOpenPatient.typeText_in_patient_mr_number(MOSAIQ_ORDERS_PATIENT_MR)
    MosaiqOpenPatient.click_apply_filters_button()
    MosaiqOpenPatient.select_first_search_result()
    #MosaiqOpenPatient.click_first_search_result()

# Open the patient code summary section.
def open_patient_code_summary():
    MosaiqCodeCapture.select_patient_code_summary()

# Verify the code view selection and code capture summary.
def verify_code_view_selection():
    MosaiqCodeCapture.verify_code_view_selection()

# Select a charge and perform actions related to tagged charges.
def verify_code_capture_summary():
    MosaiqCodeCapture.verify_code_capture_summary()

# Main function to run the smoke test.
def select_charge():
    MosaiqCodeCapture.select_charge()

# Open and interact with the edit tagged charges window.
def open_edit_tagged_charges():
    tags_to_verify = ["Edit Diagnosis 2", "Edit Facility", "Edit POS Code", "Edit Admit"]
    MosaiqCodeCapture.open_edit_tagged_charges()
    MosaiqCodeCapture.verify_edit_tagged_charges_window(tags_to_verify)

# Cancel the tagged charges operation.
def cancel_tagged_charges():
    MosaiqCodeCapture.cancel_tagged_charges()

# Verify the tagged charge marker.
def verify_tagged_charge_marker():
    MosaiqCodeCapture.verify_tagged_charge_marker()

# Click the close button in the code summary section.
def click_close_button_code_summary():
    MosaiqCodeCapture.click_close_button_code_summary()

# Log out of Mosaiq.
def logout() -> None:
    mosaiq_logout = Logout()
    mosaiq_logout.logoutUser()

# Main function to run the smoke test.
def main() -> None:
    login_mosaiq()
    try:
        select_patient()
        open_patient_code_summary()
        verify_code_view_selection()
        verify_code_capture_summary()
        select_charge()
        open_edit_tagged_charges()
        cancel_tagged_charges()
        verify_tagged_charge_marker()
        click_close_button_code_summary()
    finally:
        logout()

if __name__ == "__main__":
    main()









    







