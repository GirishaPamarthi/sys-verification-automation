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
from interops.libraries.mosaiq.interactions import MosaiqDashboard, MosaiqOpenPatient, MosaiqOrders
from interops.libraries.mosaiq.pages import Login, Logout

# Server and Port configurations
MOSAIQ_SERVER = "10.68.132.189"
SQUISH_SERVER_PORT = 4322
MOSAIQ_ORDERS_PATIENT_MR = "2007"

#Pre-requisites: 
# a) A patient with an MR ID of 2007 exists in the database. Or update the MOSAIQ_ORDERS_PATIENT_MR variable to match an existing patient.
# b) Observation Orders for this patient should exist in the system with comments added.

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
    #MosaiqOpenPatient.click_first_search_result()
    MosaiqOpenPatient.click_specific_result_using_mr_number(MOSAIQ_ORDERS_PATIENT_MR)


# Access eChart -> Orders menu item.
def access_echart_orders():
    MosaiqDashboard.open_eChart_orders()
    MosaiqOrders.click_all_button()
    time.sleep(2)

# To print all visible orders in the Orders window.
def print_visible_orders() -> None:
    try:
        all_orders = MosaiqOrders.read_all_orders_via_ocr()
        print(f"All visible orders: {all_orders}")
    except Exception as e:
        print(f"Warning: could not read all orders: {e}")

# To compare the comments of the first order with the observation comments.
def compare_order_comments_with_observation_comments():
    MosaiqOrders.compare_order_comments_with_observation_comments()
    print("Order comments successfully compared with observation comments.")

# To cancel the Observation Orders window.
def cancel_observation_orders():
    MosaiqOrders.click_cancel_button_observation_orders()
    print("Clicked the cancel button in the Observation Orders window.")

# Log out of Mosaiq.
def logout() -> None:
    mosaiq_logout = Logout()
    mosaiq_logout.logoutUser()

# Main function to run the smoke test.
def main() -> None:
    login_mosaiq()
    try:
        select_patient()
        access_echart_orders()
        print_visible_orders()
        compare_order_comments_with_observation_comments()
        cancel_observation_orders()
    finally:
        logout()

if __name__ == "__main__":
    main()









    







