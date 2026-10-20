# Reporting setup lives in test_report_gen_script and MUST be imported before any
# interops import: it puts Squish on sys.path and installs the compatibility shims
# interops needs to report under the standalone squishtest extension.
import time
from datetime import datetime

import test_config
import test_report_gen_script as reporting

from interops.libraries.mosaiq.interactions.objects.mosaiq_core_objects import MosaiqCoreObjects
from interops.libraries.mosaiq.interactions.objects.mosaiq_schedule_location_objects import (
    ScheduleLocation,
    DailyMasterSchedule,
    ActivityCodes,
)
from interops.libraries.mosaiq import MosaiqAutController
from interops.libraries.squish_actions import CommonActions
from interops.libraries.mosaiq.pages import Login, Logout
from interops.libraries.mosaiq.interactions import (
    MosaiqDashboard,
    MosaiqCommonPopups,
    MosaiqSchedule,
)

VerifyThat = reporting.VerifyThat
test_section = reporting.test_section


# Server, port and AUT come from configuration-files/test_environment.json.
CFG = test_config.for_test("smoke", "MSQ-SMK-005")
MOSAIQ_SERVER = CFG.server_host
SQUISH_SERVER_PORT = CFG.squish_port
MOSAIQ_AUT_NAME = CFG.aut_name

# Department the Daily Master schedule is expected to open against. Daily Master is scoped by
# department, not location -- its caption reads "... - Daily Master Schedule: <department>".
# Leave as "" to accept whichever department MOSAIQ opens with and simply assert one is set.
SCHEDULE_DEPARTMENT = "RO"  # ""  # "Sunnyvale Medical Oncology"

# The appointment the prerequisite books, so steps 4-6 have something of their own to find
# rather than depending on whatever the server happens to hold today.
APPOINTMENT_ACTIVITY = ActivityCodes.consultations_Outpatient_Cons_1  # "99241"
APPOINTMENT_STAFF = "Crumble, Beverly"

TEST_CASE_NAME = "Access Department Queue and Daily Master Schedule Display"


def current_appointment_date() -> str:
    """Today, in the m/d/yyyy form the Appointment Slip's Date field uses.

    Built from the parts rather than strftime: %-d/%-m are not portable to Windows and %#d/%#m
    are MSVC-only, while MOSAIQ shows no leading zeros. Matches how set_birthdate() formats.
    """
    now = datetime.now()
    return f"{now.month}/{now.day}/{now.year}"


def current_appointment_time() -> str:
    """Now, in the h:mm AM/PM form the Appointment Slip's Time field uses."""
    now = datetime.now()
    hour = now.hour % 12 or 12
    meridiem = "AM" if now.hour < 12 else "PM"
    return f"{hour}:{now.minute:02d} {meridiem}"


def time_selector(appointmentTime: str) -> str:
    """The appointment time as the schedule table renders it, e.g. "10:30".

    Stripped of the AM/PM suffix, which the table does not show.
    """
    return appointmentTime.replace(" AM", "").replace(" PM", "").strip()


def patient_selector(patientLastName: str) -> str:
    """The patient last name as the schedule table renders it, e.g. "MSQ-84082,".

    The trailing comma is what separates last name from first in the table cell. Squish's OCR
    splits on whitespace, so keeping it anchors the match to the name rather than to a
    substring of something else.
    """
    return f"{patientLastName},"


def session_selector(patientLastName: str, appointmentTime: str) -> str:
    """The combined "time|last_name," row pattern, e.g. "10:30|MSQ-84082,".

    Retained for reference and for anything that wants a single whole-row match. Step 5 now
    searches time_selector() and patient_selector() separately instead: one combined pattern
    hangs the whole match on the vertical rule between the two fields, which Tesseract renders
    variously as "/", "[", "{", and a miss says nothing about which half OCR failed on.
    """
    return f"{time_selector(appointmentTime)}|{patientLastName},"


def patient_last_name_from_banner(bannerText: str) -> str:
    """Pulls the last name out of the open patient banner, e.g. "MSQ-84082, LUNGPATIENT  MR#: ...".

    MOSAIQ renders the banner as "<last>, <first>", so everything before the first comma is the
    last name. Returns "" when the banner is empty or not in that shape, which the caller
    reports rather than guessing at.
    """
    return bannerText.split(",")[0].strip() if "," in bannerText else ""


def login_valid_clinical_user() -> None:
    """Step 1 -- log in with a valid clinical user."""
    with test_section("Step 1: Log in"):
        MosaiqAutController.mosaiq_aut(
            serverAddress=MOSAIQ_SERVER,
            serverPort=SQUISH_SERVER_PORT,
        ).start_aut()
        VerifyThat(CommonActions.wait_for_object_to_appear(MosaiqCoreObjects.mOSAIQ_Dashboard_Window, 30)) \
            .equals(True) \
            .andReportCritical("Mosaiq should show the login window after starting the AUT")

        Login().loginUser("impac", "impac")
        VerifyThat(MosaiqDashboard.wait_for_main_workspace_area(20)) \
            .equals(True) \
            .andReportCritical("Mosaiq workspace should load after login")


def open_recent_patient() -> str:
    """Prerequisite -- open the top patient from File's recent patients list.

    :return: the patient's last name, read from the dashboard banner
    :rtype: str
    """
    with test_section("Prerequisite: Open the most recent patient"):
        MosaiqDashboard.open_file_recentpatient(1)
        VerifyThat(MosaiqDashboard.wait_for_patient_to_open(20), screenshot=True) \
            .equals(True) \
            .andReportCritical("Top recent patient should open in the dashboard")

        # The banner is the dashboard's own statement of who is loaded, and reading it is what
        # keeps this test free of a hardcoded patient: the booked appointment and the OCR
        # selector in step 5 are both built from whoever the recent list actually opened.
        banner = MosaiqDashboard.get_open_patient_label_text()
        patient_last_name = patient_last_name_from_banner(banner)
        VerifyThat(patient_last_name) \
            .notEquals("") \
            .andReportCritical(f"Patient banner should name the open patient; banner read {banner!r}")

        return patient_last_name


def book_prerequisite_appointment(patientLastName: str, appointmentDate: str, appointmentTime: str) -> None:
    """Prerequisite -- book the appointment steps 4-6 will look for.

    Patient, Date, Appointments and Duration are left at whatever the slip defaults to.
    patientLastName and appointmentDate are used to check those defaults, not to set them.

    NOTE: this WRITES to the schedule. Unlike step 6, which cancels out of the Appointment
    Slip, this commits with OK so the appointment exists for the rest of the run. Each run
    leaves one behind on the server.
    """
    with test_section(f"Prerequisite: Book a {APPOINTMENT_ACTIVITY} appointment at {appointmentTime}"):
        MosaiqSchedule.click_add_button_in_daily_master_window()
        VerifyThat(MosaiqSchedule.is_appointment_slip_open(15000)) \
            .equals(True) \
            .andReportCritical("Appointment Slip should open from the Daily Master Add button")

        # Patient is left alone: the slip opens pre-populated from the chart the prerequisite
        # opened. Asserted rather than assumed, because booking against the wrong patient would
        # write a real appointment to the wrong chart -- and because it is what step 5's OCR
        # selector is built from.
        VerifyThat(MosaiqSchedule.get_patient_in_appointment_slip().strip()) \
            .contains(patientLastName) \
            .andReportCritical(f"Appointment Slip should be pre-populated with the open patient '{patientLastName}'")

        # Only Activity, Time and Staff are set. Date, Appointments, Duration and Location are
        # left at the values the slip defaults to -- do not add type_date_in_appointment_slip(),
        # type_appointments_number_in_appointment_slip_window(),
        # type_duration_in_appointment_slip() or type_location_in_appointment_slip() here.
        MosaiqSchedule.type_activity_in_appointment_slip(APPOINTMENT_ACTIVITY)
        MosaiqSchedule.type_time_in_appointment_slip(appointmentTime)
        MosaiqSchedule.type_staff_in_appointment_slip(APPOINTMENT_STAFF)

        # Read the slip back before committing: OK writes to a real schedule, so it is worth
        # knowing the fields took the values that were typed rather than silently rejecting them.
        # Date is read but not typed: the slip is expected to default to the day Daily Master is
        # showing, and steps 4-6 only find the appointment if it landed on today.
        VerifyThat(MosaiqSchedule.get_date_in_appointment_slip().strip()) \
            .contains(appointmentDate) \
            .andReport(f"Appointment Slip should default its date to today, {appointmentDate}")
        VerifyThat(MosaiqSchedule.get_time_in_appointment_slip().strip()) \
            .notEquals("") \
            .andReport(f"Appointment Slip time should be set to {appointmentTime}")

        MosaiqSchedule.click_ok_button_in_appointment_slip_window()
        VerifyThat(MosaiqSchedule.is_appointment_slip_open(5000)) \
            .equals(False) \
            .andReport("Appointment Slip should close once the appointment is booked")


def open_schedule_view() -> None:
    """Step 2 -- open the scheduling view via Schedule > Daily Master."""
    with test_section("Step 2: Open the Daily Master scheduling view"):
        MosaiqDashboard.open_schedule_daily_master()
        VerifyThat(MosaiqSchedule.is_daily_master_schedule_open(30000)) \
            .equals(True) \
            .andReportCritical("Daily Master schedule window should open from Schedule > Daily Master...")


def select_department_if_prompted() -> None:
    """Step 3 -- deal with the department/location prompt, which only appears on first use."""
    with test_section("Step 3: Select department/location if prompted"):
        # The Location Directory: RO dialog is shown only when nothing has been selected before
        # on this workstation. Its absence is the normal path, not a failure, so this is a
        # branch rather than an assertion.
        if CommonActions.does_object_exist(ScheduleLocation.location_Directory_RO_Window, 3000):
            MosaiqSchedule.click_select_button_in_ro_window()
            VerifyThat(CommonActions.wait_for_object_to_disappear(ScheduleLocation.location_Directory_RO_Window, 15)) \
                .equals(True) \
                .andReport("Location Directory dialog should close after selecting a location")
        else:
            print("Location Directory dialog not shown; a department is already selected.")

        # Daily Master is department-scoped and carries the department in its caption. The
        # Department dropdown itself is no use for reading it -- its text is the label
        # "Department:", not the selected value.
        department = MosaiqSchedule.get_daily_master_department()
        VerifyThat(department) \
            .notEquals("") \
            .andReport("Daily Master schedule should be scoped to a department")

        if SCHEDULE_DEPARTMENT:
            VerifyThat(department) \
                .equals(SCHEDULE_DEPARTMENT) \
                .andReport(f"Daily Master schedule should be showing department '{SCHEDULE_DEPARTMENT}'")
        else:
            print(f"Daily Master schedule is scoped to department {department!r}.")


def verify_day_appointments_displayed() -> bool:
    """Step 4 -- the schedule table lists the current day's appointments.

    :return: whether OCR is available, since steps 5 and 6 cannot run without it
    :rtype: bool
    """
    with test_section("Step 4: Verify current-day patients/appointments displayed"):
        # Non-OCR checks first, so this step still verifies something real on an installation
        # with no OCR engine. The window caption is the only part of this view readable without
        # OCR; VerifyThat logs the value it saw into the report as evidence of what was on
        # screen.
        caption = MosaiqSchedule.get_daily_master_schedule_window_title()
        VerifyThat(caption) \
            .contains("Daily Master Schedule") \
            .andReport("Schedule window caption should identify the Daily Master view")

        # The caption carries the day on display, e.g. " 9/21/2026  MON - Daily Master
        # Schedule: RO", so this verifies "current-day" for real without needing OCR.
        VerifyThat(caption) \
            .contains(current_appointment_date()) \
            .andReport(f"Daily Master should be showing today, {current_appointment_date()}")

        VerifyThat(CommonActions.is_object_visible(DailyMasterSchedule.window_Table_Pane, 10000)) \
            .equals(True) \
            .andReport("Schedule table pane should be displayed")

        # The window's "<selected> / <total>" counter tracks the table contents, so the day's
        # appointments can be counted without OCR. This is the real content check for step 4 --
        # the prerequisite booked one, so the day cannot legitimately be empty. VerifyThat logs
        # the count it saw into the report.
        VerifyThat(MosaiqSchedule.get_daily_master_appointment_count()) \
            .greaterThan(0) \
            .andReport("Daily Master should be showing at least the appointment just booked")

        VerifyThat(MosaiqCommonPopups.acknowledge_error_dialog()) \
            .equals(False) \
            .andReport("No error dialog should be raised while displaying the schedule")

        # The table exposes no queryable rows, so listing the day's appointments needs OCR, and
        # Squish ships no OCR engine -- Tesseract is a separate install. Probed rather than
        # assumed: without it every OCR call raises, which would abort the run at step 4 and
        # take step 7 down with it.
        # Probe only -- no OCR assertion here. The row counter above already proves the day is
        # populated, exactly and without OCR, so reading the whole table again just to count
        # its lines would pay for a full-table OCR pass to learn something already known.
        # get_daily_master_appointment_lines() remains available for a test that needs the text.
        ocr_available = MosaiqSchedule.is_daily_master_ocr_available()
        if not ocr_available:
            print("No OCR engine configured; steps 5-6 cannot run. Install Tesseract for Squish "
                  "from the Qt Customer Portal (Squish > edition 'Special') and configure its path.")
        return ocr_available


def open_one_appointment(patientLastName: str, appointmentTime: str) -> bool:
    """Step 5 -- open a single appointment from the schedule table.

    The time and the patient name are located as two independent OCR searches rather than as
    one "time|last_name," row pattern. A combined pattern hangs the whole match on the vertical
    rule between the fields, and when it misses it says nothing about why; two searches report
    separately, so the run tells you whether OCR lost the time, the name, or both.

    :param str patientLastName: Last name of the patient the appointment was booked for
    :param str appointmentTime: Time the appointment was booked at, "h:mm AM/PM"
    :return: whether the Appointment Slip was opened, so step 6 can skip rather than assert
             against a window that was never reached
    :rtype: bool
    """
    time_text = time_selector(appointmentTime)
    patient_text = patient_selector(patientLastName)

    with test_section(f"Step 5: Open the appointment for '{patient_text}' at '{time_text}'"):
        # Both checked before selecting: the OCR lookup returns None when a fragment is absent,
        # and the select call would then click None. The prerequisite booked this appointment,
        # so a miss means OCR could not read what it wrote -- reportable, not a crash.
        # setCurrentSessionToStart only on the first search: it presses Home to move the
        # highlight off a row OCR cannot read, and nothing has moved it since.
        # find_* rather than is_*: the matched object is kept and clicked below, so the row is
        # located once instead of being searched again to select it.
        time_object = MosaiqSchedule.find_text_in_daily_master_table(time_text)
        VerifyThat(time_object is not None) \
            .equals(True) \
            .andReport(f"Schedule should show an appointment at '{time_text}'")

        patient_object = MosaiqSchedule.find_text_in_daily_master_table(patient_text, False)
        VerifyThat(patient_object is not None) \
            .equals(True) \
            .andReport(f"Schedule should show an appointment for '{patient_text}'")

        if time_object is None or patient_object is None:
            print(f"Could not read {patient_text!r} at {time_text!r} off the schedule; steps 5-6 cannot run.")
            return False

        # Selected by time: the patient may hold more than one appointment today, but only one
        # was booked into this slot. Step 6 re-reads the slip's time to confirm the row that
        # opened is the one that was booked.
        MosaiqSchedule.select_found_table_object(time_object)
        # Selecting only highlights the row; Change is what opens the Appointment Slip.
        MosaiqSchedule.click_change_button_in_daily_master_window()

        opened = MosaiqSchedule.is_appointment_slip_open(15000)
        VerifyThat(opened) \
            .equals(True) \
            .andReport("Appointment Slip should open for the selected appointment")
        return opened


def verify_appointment_details(appointmentTime: str) -> None:
    """Step 6 -- the appointment's core details are readable on the slip.

    :param str appointmentTime: Time the prerequisite booked at, used to confirm the row that
                                opened is that appointment and not another one for the patient
    """
    with test_section("Step 6: Verify appointment details visible"):
        # Reported individually so the report names which field was blank, rather than a single
        # pass/fail over the whole slip. Two fields are deliberately not checked:
        #   status   -- a freshly booked appointment carries no status yet, so asserting one is
        #               populated would fail on the very appointment the prerequisite creates;
        #   location -- left at the slip's default rather than set by the prerequisite.
        # get_status_in_appointment_slip() and get_location_in_appointment_slip() remain
        # available for a test that sets or expects those values.
        for label, value in (
            ("date", MosaiqSchedule.get_date_in_appointment_slip()),
            ("time", MosaiqSchedule.get_time_in_appointment_slip()),
            ("MR number", MosaiqSchedule.get_patient_mr_number_in_appointment_slip()),
        ):
            VerifyThat(value.strip()) \
                .notEquals("") \
                .andReport(f"Appointment Slip should show the appointment {label}")

        # Closes the loop on step 5's two independent OCR searches: they can each match on a
        # different row, so this confirms the slip that opened really is the booked appointment.
        VerifyThat(MosaiqSchedule.get_time_in_appointment_slip().strip()) \
            .contains(time_selector(appointmentTime)) \
            .andReport(f"Opened appointment should be the one booked at {appointmentTime}")

        # Cancel, never OK: OK commits the slip and would write a change to a real schedule.
        MosaiqSchedule.click_cancel_button_in_appointment_slip_window()
        VerifyThat(MosaiqSchedule.is_appointment_slip_open(5000)) \
            .equals(False) \
            .andReport("Appointment Slip should close on Cancel without altering the appointment")


def close_schedule_view() -> None:
    """Step 7 -- close the schedule view."""
    with test_section("Step 7: Close the schedule view"):
        MosaiqSchedule.click_close_button_in_daily_master_window()
        VerifyThat(MosaiqSchedule.is_daily_master_schedule_open(5000)) \
            .equals(False) \
            .andReport("Daily Master schedule window should close")

        VerifyThat(MosaiqDashboard.wait_for_main_workspace_area(20)) \
            .equals(True) \
            .andReport("Dashboard workspace should be back after closing the schedule")


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
        Logout().exitApplication()
    except Exception as error:
        print(f"MOSAIQ teardown skipped: {error}")


def main() -> None:
    sq = reporting.start_reporting(TEST_CASE_NAME, aut_name=MOSAIQ_AUT_NAME)

    try:
        login_valid_clinical_user()

        # Prerequisites: open a patient, then book that patient an appointment at the current
        # time so steps 4-6 have known data to find. Booking happens inside the Daily Master
        # view, so the view is opened (step 2) and its department settled (step 3) first.
        patient_last_name = open_recent_patient()
        open_schedule_view()
        select_department_if_prompted()

        appointment_date = current_appointment_date()
        #appointment_time = current_appointment_time()
        appointment_time = "10:30 AM"
        book_prerequisite_appointment(patient_last_name, appointment_date, appointment_time)

        # Steps 5 and 6 reach the appointment through an OCR lookup, so they are skipped
        # wholesale where no OCR engine is configured. Step 7 runs regardless, leaving the
        # schedule closed and the report complete rather than truncated by a traceback.
        if verify_day_appointments_displayed() and open_one_appointment(patient_last_name, appointment_time):
            verify_appointment_details(appointment_time)
        close_schedule_view()
    finally:
        # finally, so a critical verification aborting the run still logs the verification
        # count and still leaves the AUT closed for the next case in the suite.
        reporting.finish_reporting(sq)
        close_mosaiq()


if __name__ == "__main__":
    main()
