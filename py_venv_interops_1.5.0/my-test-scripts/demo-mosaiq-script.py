# Reporting setup lives in test_report_gen_script and MUST be imported before any
# interops import: it puts Squish on sys.path and installs the compatibility shims
# interops needs to report under the standalone squishtest extension.
import test_report_gen_script as reporting

from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.pages import Login
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

PATIENT_MR = "84082"
PATIENT_CHART = "MSQ-84082"

TEST_CASE_NAME = "demo_mosaiq_open_patient_and_diagnoses"
MOSAIQ_AUT_NAME = "accwin"  # matches MosaiqAutController._aut_name


def open_patient() -> None:
    with test_section(f"Open patient MR# {PATIENT_MR}"):
        MosaiqDashboard.open_select_patient()
        MosaiqOpenPatient.typeText_in_patient_mr_number(PATIENT_MR)
        MosaiqOpenPatient.click_apply_filters_button()

        # greaterThan: the filter must actually match something before we click a row.
        results = MosaiqOpenPatient.get_search_results()
        VerifyThat(len(results)) \
            .greaterThan(0) \
            .andReportCritical(f"Filtering on MR# {PATIENT_MR} should return at least one row")

        # notEquals(None): the grid must actually hold a row for this MR number.
        # Uses the same lookup click_specific_result_using_mr_number() uses, so it
        # asserts the thing the next line depends on. Do NOT assert on
        # getattr(row, "text", "") -- these grid objects expose no `text`, so the
        # fallback silently yields [''] and the verification fails for no reason.
        matching_row = CommonActions.get_child_object_by_value(results, PATIENT_MR)
        VerifyThat(matching_row) \
            .notEquals(None) \
            .andReport(f"Search grid should contain a row for MR# {PATIENT_MR}")

        MosaiqOpenPatient.click_specific_result_using_mr_number(PATIENT_MR)

        # andReportCritical: a failure here aborts the test instead of cascading.
        # A screenshot is attached to the report for this step.
        VerifyThat(MosaiqDashboard.wait_for_patient_to_open(15), screenshot=True) \
            .equals(True) \
            .andReportCritical(f"Patient MR# {PATIENT_MR} should open in the dashboard")

        VerifyThat(MosaiqDashboard.is_patient_chart_open()) \
            .equals(True) \
            .andReport("Open Patient toolbar label should confirm a chart is open")


def open_diagnoses_from_chart() -> None:
    with test_section("Diagnoses and problems via patient chart"):
        MosaiqDashboard.open_patient_chart(PATIENT_CHART)
        MosaiqChart.__find_chart_diagnoses_and_problems_window()
        MosaiqChart.click_diagnosis_and_problems_tab_item()

        # matches: assert the chart identifier has the expected MSQ-<digits> shape.
        VerifyThat(PATIENT_CHART) \
            .matches(r"MSQ-\d+") \
            .andReport("Chart identifier should match the MSQ-<digits> pattern")


def open_diagnoses_from_d_and_i() -> None:
    with test_section("Diagnoses and problems via D&I"):
        MosaiqDashboard.open_patient_d_and_i(PATIENT_CHART)

        VerifyThat(MosaiqDandI.open_diagnoses_and_problems_window(30000)) \
            .notEquals(False) \
            .andReport("Diagnoses and Problems window should open from D&I")


def main() -> None:
    sq = reporting.start_reporting(TEST_CASE_NAME, aut_name=MOSAIQ_AUT_NAME)

    MosaiqAutController.mosaiq_aut(
        serverAddress=MOSAIQ_SERVER,
        serverPort=SQUISH_SERVER_PORT,
    ).start_aut()

    with test_section("Login"):
        Login().loginUser("impac", "impac")
        VerifyThat(MosaiqDashboard.wait_for_main_workspace_area(20)) \
            .equals(True) \
            .andReportCritical("Mosaiq workspace should load after login")

    open_patient()
    open_diagnoses_from_chart()
    open_diagnoses_from_d_and_i()

    reporting.finish_reporting(sq)


if __name__ == "__main__":
    main()
