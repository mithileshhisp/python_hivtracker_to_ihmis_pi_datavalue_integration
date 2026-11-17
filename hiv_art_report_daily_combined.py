"""Daily DHIS2 HIV ART report.

Creates ONE combined CSV (ART fields + current client treatment status).
Each run refreshes the file for the current Nepali reporting month.
Uses nepali-datetime for BS/Gregorian conversion and month boundaries.

Configure credentials and DHIS2_API / ORG_UNIT_UID as environment variables.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from requests.adapters import HTTPAdapter
import time

import csv
import logging
#import os
from datetime import date, datetime, timedelta
from pathlib import Path

from urllib.request import urlopen

import nepali_datetime
import requests
from requests.auth import HTTPBasicAuth

import glob
import smtplib
from email.mime.multipart import MIMEMultipart 
from email.mime.text import MIMEText 
from email.mime.base import MIMEBase 
from email import encoders

from dotenv import load_dotenv
import os
load_dotenv()
# ------------------------------- Configuration -------------------------------
#DHIS2_API = os.getenv("DHIS2_GET_API_URL", "").rstrip("/")
DHIS2_API = os.getenv("DHIS2_GET_API_URL")
DHIS2_USERNAME = os.getenv("DHIS2_GET_USER")
DHIS2_PASSWORD = os.getenv("DHIS2_GET_PASSWORD")
ORG_UNIT_UID = os.getenv("ART_REPORT_ORG_UNIT_UID")

FROM_EMAIL_ADDR = os.getenv("FROM_EMAIL_ADDR")
FROM_EMAIL_PASSWORD = os.getenv("FROM_EMAIL_PASSWORD")

PROGRAM_UID = os.getenv("PROGRAM_UID")
SQL_VIEW_UID = os.getenv("SQL_VIEW_UID")
STATUS_OPTION_SET_UID = os.getenv("STATUS_OPTION_SET_UID")

ORG_UNIT_GROUP_UID = os.getenv("ART_REPORT_ORG_UNIT_GROUP_UID")

#print(f"DHIS2_API: {DHIS2_API}")
#print(f"DHIS2_USERNAME: {DHIS2_USERNAME}")
#print(f"DHIS2_PASSWORD: {DHIS2_PASSWORD}")
#print(f"ORG_UNIT_UID: {ORG_UNIT_UID}")

# This output is deliberately a single, stable monthly file. Daily runs overwrite
# the same file with the latest results for the current reporting month.
#OUTPUT_DIR = Path(__file__).resolve().parent / "HIV_ART_Reports"
#OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_OUTPUT_DIR = "HIV_ART_Reports"
os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)

#LOG_DIR = REPORT_OUTPUT_DIR / "logs"
#LOG_DIR.mkdir(parents=True, exist_ok=True)

from constants import LOG_FILE_ART_REPORT_GENERATION

LOG_DIR = os.path.join(REPORT_OUTPUT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

assert REPORT_OUTPUT_DIR != "/" and REPORT_OUTPUT_DIR != "" #### Never delete outside log folder.

logging.basicConfig(
    filename=os.path.join(LOG_DIR, LOG_FILE_ART_REPORT_GENERATION),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

DATA_ELEMENTS = [
    ("drKkLxaGFwv", "Client Code"),
    ("trackedEntityInstance", "Tracked Entity Id"),
    ("ouId", "Service Site Id"),
    ("ouName", "Service Site Name"),
    ("Fu4LhjNsJZL", "Service Number"),
    ("U9uQVlPfT8G", "Age At Registration (Years)"),
    ("enrollmentDate", "Enrollment Date"),
    ("TN7r3ws7IG9", "Gender"),
    ("Usl9OzVV46v", "Risk Group"),
    ("UHoTGT1dtjj", "Finger Print ID"),
    ("Xidou6gOttS", "Enrolled in Insurance"),
    ("zTwMKXGt0xF", "Age at Visited (Years)"),
    ("rQnmYAF1899-gPHLt0PQq1b", "ART Initiation Date"),
    ("qzj6QVLG5IA", "HIV positive identification date at this site"),
    ("bVDIGJi6YqQ", "Regimen before by Another Site"),
    ("bllr47JqYI6", "Regimen at this Site"),
    ("TULSRUan4HK", "Regimen Substituted?"),
    ("hmHVlzgtZ0w", "Substituted Regimen"),
    ("vne8TzbU8R8", "Regimen Switched?"),
    ("Bk9I9PWKHbE", "Switched Regimen"),
    ("p4iEE1Z50ck", "Reason of Switching"),
    ("currentRegimen", "Current Regimen"),
    ("VLFKV5JmWQM", "Other ART regimen"),
    ("SztYMNdiCoq", "ART treatment adherence"),
    ("status", "Treatment Status (ART follow up)"),
    ("statusDate", "Status Date"),
    ("pueiw33HjzI", "Months ARV regimen provided"),
    ("age-category", "Age (in category)"),
    ("age-sex-group", "Age and Sex Group"),
    ("teiActiveStatus", "TEI Active/Inactive Status"),  # NEW LAST COLUMN
]

STATUS_DE_UID = "WpBa1L6xxPC"  # ART follow-up status data element
TRANSFER_IN_DE_UID = "bj6JwQ2TxZm"
DEATH_DE_UID = "HNpcuv51Vsq"
STATUS_STAGES = {"AcmSTzlFRAG", "YRSdePjzzfs"}
REGIMEN_DE_UIDS = {
    "bVDIGJi6YqQ", "bllr47JqYI6", "hmHVlzgtZ0w", "Bk9I9PWKHbE"
}

'''
session = requests.Session()
session.auth = HTTPBasicAuth(DHIS2_USERNAME, DHIS2_PASSWORD)
session.headers.update({"Accept": "application/json"})
'''

session = requests.Session()
session.auth = HTTPBasicAuth(DHIS2_USERNAME, DHIS2_PASSWORD)
session.headers.update({"Accept": "application/json"})


# Reuse HTTP connections.
adapter = HTTPAdapter(
    pool_connections=10,
    pool_maxsize=10,
    max_retries=2,
)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Each worker gets its own Session.
_thread_local = local()


def get_worker_session():
    if not hasattr(_thread_local, "session"):
        worker_session = requests.Session()
        worker_session.auth = HTTPBasicAuth(
            DHIS2_USERNAME,
            DHIS2_PASSWORD,
        )
        worker_session.headers.update({"Accept": "application/json"})
        worker_session.mount(
            "http://", HTTPAdapter(pool_connections=2, pool_maxsize=2)
        )
        worker_session.mount(
            "https://", HTTPAdapter(pool_connections=2, pool_maxsize=2)
        )
        _thread_local.session = worker_session

    return _thread_local.session


def get_json(path, params=None):
    url = f"{DHIS2_API.rstrip('/')}/{path.lstrip('/')}"

    # Use a thread-local session when processing TEIs concurrently.
    active_session = (
        _thread_local.session
        if hasattr(_thread_local, "session")
        else session
    )

    response = active_session.get(
        url,
        params=params,
        timeout=(10, 120),
    )
    response.raise_for_status()
    return response.json()

'''
def get_json(path, params=None):
    
    response = session.get(f"{DHIS2_API}{path.lstrip('/')}", params=params, timeout=120)

    print("Request URL : %s", response.url)

    print("Response URL : %s", response.geturl())
    
    response.raise_for_status()
    return response.json()

'''
'''
def get_json(path, params=None):
    
    url = f"{DHIS2_API}{path.lstrip('/')}"

    response = session.get(url, params=params, timeout=120)
    #print("Request URL :", url)
    #print("Response URL:", response.url)
    #print("HTTP Status :", response.status_code)
    response.raise_for_status()
    return response.json()

'''

from datetime import date, timedelta
#import nepali_datetime
import logging


def previous_nepali_month(today=None):
    """Return the previous Nepali month and its ISO/Gregorian date range.

    Calendar conversion and month lengths come from nepali-datetime.
    The ISO end date is the final day of the previous Nepali month
    (inclusive).
    """
    today = today or date.today()

    # Convert today's Gregorian date to Nepali date
    #bs_today = nepali_datetime.date.from_datetime_date(today)
    bs_today = nepali_datetime.datetime.now()

    # First day of the current Nepali month
    bs_current_month_start = nepali_datetime.date(
        bs_today.year, bs_today.month, 1
    )

    # Previous Nepali month: one day before current month's start
    iso_current_month_start = bs_current_month_start.to_datetime_date()
    iso_previous_month_end = iso_current_month_start - timedelta(days=1)

    # Convert the previous month's last ISO date back to Nepali date
    bs_previous_month_end = nepali_datetime.date.from_datetime_date(
        iso_previous_month_end
    )

    # First day of the previous Nepali month
    bs_previous_month_start = nepali_datetime.date(
        bs_previous_month_end.year,
        bs_previous_month_end.month,
        1
    )

    # Convert Nepali month boundaries to ISO/Gregorian dates
    iso_start = bs_previous_month_start.to_datetime_date()
    iso_end = iso_previous_month_end

    month_name = bs_previous_month_start.strftime("%B")

    print(
        f"Previous Nepali month: {month_name}, "
        f"Nepali year: {bs_previous_month_start.year}"
    )
    logging.info(
        "Previous Nepali month: %s, year: %s",
        month_name,
        bs_previous_month_start.year
    )
    print(
        f"Previous ISO Start Date: {iso_start.isoformat()} "
        f"Previous ISO End Date: {iso_end.isoformat()}"
    )

    return (
        str(bs_previous_month_start.year),
        str(bs_previous_month_start.month),
        month_name,
        iso_start.isoformat(),
        iso_end.isoformat(),
        iso_end.isoformat(),  # as_of: previous month is fully completed
    )


def get_bs_month_start_end(bs_year, bs_month):
    # Start of Nepali month
    start_date = nepali_datetime.date(bs_year, bs_month, 1)

    # Start of next month
    if bs_month == 12:
        next_month = nepali_datetime.date(bs_year + 1, 1, 1)
    else:
        next_month = nepali_datetime.date(bs_year, bs_month + 1, 1)

    # End of month
    end_date = next_month - timedelta(days=1)

    return start_date, end_date

def current_nepali_month(today=None):
    """Return the Nepali month containing an ISO/Gregorian date.

    Calendar conversion and month lengths come from the nepali-datetime
    package. No year-by-year Nepali-to-ISO date table is maintained here.
    The ISO end date is the final day of the Nepali month (inclusive).
    """

    today = today or date.today()

    bs_today = nepali_datetime.date.from_datetime_date(today)
    bs_month_start = nepali_datetime.date(bs_today.year, bs_today.month, 1)

    if bs_today.month == 12:
        bs_next_month_start = nepali_datetime.date(bs_today.year + 1, 1, 1)
    else:
        bs_next_month_start = nepali_datetime.date(bs_today.year, bs_today.month + 1, 1)

    iso_start = bs_month_start.to_datetime_date()
    iso_next_month_start = bs_next_month_start.to_datetime_date()
    iso_end = iso_next_month_start - timedelta(days=1)

    '''
    current_nepali_datetime = nepali_datetime.datetime.now()
    # Extract the month number
    nepali_current_month_number = current_nepali_datetime.month

    # Extract the Nepali Year
    nepali_current_year = current_nepali_datetime.year

    # Example: current nelai month to month startdate and enddate
    start, end = get_bs_month_start_end(nepali_current_year, nepali_current_month_number)

    iso_start = start.to_datetime_date()
    iso_end = end.to_datetime_date()

    #print("Start AD:", start.to_datetime_date())
    #print("End AD:", end.to_datetime_date())
    '''

    # Since the task runs daily, report the data available up to today,
    # without querying future events later in the current Nepali month.
    as_of = min(today, iso_end)

    month_name = bs_today.strftime("%B")

    print(f"Nepali month_number: {str(bs_today.month)}  Nepali month_name: {month_name} Nepali year_name: {str(bs_today.year)} ")
    logging.info(f"Nepali month_name: {month_name} Nepali year: {str(bs_today.year)} ")
    print(f"ISO Start Date : {iso_start.isoformat()} ISO end Date: {iso_end.isoformat()} ")
    logging.info(f"ISO Start Date : {iso_start.isoformat()} ISO end Date: {iso_end.isoformat()} ")

    return (
        str(bs_today.year),
        str(bs_today.month),
        month_name,
        iso_start.isoformat(),
        iso_end.isoformat(),
        as_of.isoformat(),
    )


def get_status_queries():
    """Return status value/dataElement pairs represented by the original UI."""
    result = get_json(
        f"optionSets/{STATUS_OPTION_SET_UID}.json",
        {"fields": "id,name,options[name,code]"},
    )
    queries = set()
    for option in result.get("options", []):
        code = (option.get("code") or "").strip()
        if not code or code.casefold() == "death":
            continue
        queries.add((STATUS_DE_UID, code))
        if code == "on_treatment":
            queries.add((STATUS_DE_UID, "treatment_restarted"))

    # Special options constructed in the original JavaScript UI.
    queries.add((TRANSFER_IN_DE_UID, "true"))
    queries.add((DEATH_DE_UID, "death"))
    return sorted(queries)


def get_orgunit_group_members():
    """Fetch organisation units belonging to the configured DHIS2 group."""
    #https://tracker.hivaids.gov.np/save-child-2.27/api/organisationUnitGroups/frpkpIavdbP.json?fields=id,name,organisationUnits[id,name]
    if not ORG_UNIT_GROUP_UID:
        raise RuntimeError(
            "Set ART_REPORT_ORG_UNIT_GROUP_UID in the .env file."
        )

    result = get_json(
        f"organisationUnitGroups/{ORG_UNIT_GROUP_UID}.json",
        {
            "fields": "id,name,organisationUnits[id,name]",
        },
    )

    group_name = result.get("name", "")
    members = result.get("organisationUnits", [])

    if not members:
        raise RuntimeError(
            f"No organisation units found in group: {group_name}"
        )

    logging.info(
        "Organisation unit group Name: %s; members count: %d",
        group_name,
        len(members),
    )
    print(f"Organisation unit group Name : {group_name}; "f"members count: {len(members)}")
    
    return group_name, members



def get_candidates(end_date, status_de_uid, status_value, orgunit_uid):
    """Read TEI IDs from the SQL view for a specific organisation unit."""

    params = [
        ("paging", "false"),
        ("var", f"orgunit:{orgunit_uid}"),
        ("var", f"deid:{status_de_uid}"),
        ("var", f"devalue:{status_value}"),
        ("var", f"enddate:{end_date}"),
    ]

    payload = get_json(
        f"sqlViews/{SQL_VIEW_UID}/data.json",
        params,
    )
    
    rows = payload.get("listGrid", {}).get("rows", [])

    return {
        str(row[0])
        for row in rows
        if row and row[0]
    }

'''
def get_candidates(end_date, status_de_uid, status_value):
    """Read TEI IDs from the SQL view using the original four variables."""
    params = [
        ("paging", "false"),
        ("var", f"orgunit:{ORG_UNIT_UID}"),
        ("var", f"deid:{status_de_uid}"),
        ("var", f"devalue:{status_value}"),
        ("var", f"enddate:{end_date}"),
    ]
    payload = get_json(f"sqlViews/{SQL_VIEW_UID}/data.json", params)
    rows = payload.get("listGrid", {}).get("rows", [])
    return {str(row[0]) for row in rows if row and row[0]}
'''

def get_tei_data(tei_uid, as_of_date):
    """Fetch one TEI, collect its enrollment attributes and event data.

    Events are sorted chronologically so a later qualifying status supersedes
    an earlier one. Only events on or before the daily as-of date are included.
    """

    """
    params = {
        "program": PROGRAM_UID,
        "fields": (
            "trackedEntityInstance,attributes[attribute,value],"
            "enrollments[program,orgUnit,orgUnitName,enrollmentDate,"
            "events[programStage,orgUnit,eventDate,dueDate,dataValues[dataElement,value]]]"
        ),
    }
    """
    #https://tracker.hivaids.gov.np/save-child-2.27/api/trackedEntityInstances/A1oZZ3LfIYg.json?fields=trackedEntityInstance,inactive
    params = {
        "program": PROGRAM_UID,
        "fields": (
            "trackedEntityInstance,inactive,attributes[attribute,value],"
            "enrollments[program,orgUnit,orgUnitName,enrollmentDate,"
            "events[programStage,orgUnit,eventDate,dueDate,"
            "dataValues[dataElement,value]]]"
        ),
    }


    tei = get_json(f"trackedEntityInstances/{tei_uid}.json", params)

    # Capture the TEI's active/inactive status from DHIS2.
    inactive_value = tei.get("inactive")

    if inactive_value is True:
        tei_active_status = "Inactive"
    elif inactive_value is False:
        tei_active_status = "Active"
    else:
        # Leave blank if DHIS2 does not return the property.
        tei_active_status = ""

    """
    attrs = {
        item.get("attribute"): item.get("value", "")
        for item in tei.get("attributes", []) if item.get("attribute")
    }
    attrs["trackedEntityInstance"] = tei.get("trackedEntityInstance", tei_uid)
    """

    attrs = {
        item.get("attribute"): item.get("value", "")
        for item in tei.get("attributes", [])
        if item.get("attribute")
    }

    attrs["trackedEntityInstance"] = tei.get(
        "trackedEntityInstance", tei_uid
    )

    # Store TEI active/inactive status for the CSV export.
    attrs["teiActiveStatus"] = tei_active_status


    events_out = {}
    status_candidates = []
    regimen_candidates = []

    for enrollment in tei.get("enrollments", []):
        if enrollment.get("program") != PROGRAM_UID:
            continue
        # Preserve the original report's site and enrollment fields.
        attrs["ouId"] = enrollment.get("orgUnit", "")
        attrs["ouName"] = enrollment.get("orgUnitName", "")
        attrs["enrollmentDate"] = (enrollment.get("enrollmentDate") or "").split("T")[0]

        dated_events = []
        for event in enrollment.get("events", []):
            event_date = (event.get("eventDate") or "").split("T")[0]
            if not event_date or event_date > as_of_date:
                continue
            dated_events.append((event_date, event))

        for event_date, event in sorted(dated_events, key=lambda x: x[0]):
            stage = event.get("programStage")
            for dv in event.get("dataValues", []):
                de_uid = dv.get("dataElement")
                value = dv.get("value", "")
                if not de_uid:
                    continue

                # Use status values only from the follow-up/status stages.
                if stage in STATUS_STAGES:
                    if de_uid == TRANSFER_IN_DE_UID:
                        status_candidates.append((event_date, "transfer_in"))
                    elif de_uid == DEATH_DE_UID:
                        status_candidates.append((event_date, "death"))
                    elif de_uid == STATUS_DE_UID and value:
                        status_candidates.append((event_date, value))

                # The original UI uses these regimen D.E.s to derive currentRegimen.
                if de_uid in REGIMEN_DE_UIDS:
                    regimen_candidates.append((event_date, value))

                events_out[de_uid] = value

    if status_candidates:
        status_candidates.sort(key=lambda item: item[0])
        events_out["statusDate"], events_out["status"] = (
            status_candidates[-1][0], status_candidates[-1][1]
        )
    else:
        events_out["status"] = ""
        events_out["statusDate"] = ""

    if regimen_candidates:
        regimen_candidates.sort(key=lambda item: item[0])
        events_out["currentRegimen"] = regimen_candidates[-1][1]
    else:
        events_out["currentRegimen"] = ""

    # Retain the original special display convention.
    if events_out.get("status") == "on_treatment":
        if any(value == "treatment_restarted" for _, value in status_candidates):
            events_out["status"] = "on_treatment/treatment_restarted"

    return attrs, events_out


def make_report_row(attrs, ev):
    row = {}
    for field, _label in DATA_ELEMENTS:
        if field == "age-category":
            try:
                age = float(ev.get("zTwMKXGt0xF") or "")
                row[field] = "0-14" if age <= 14 else "14+"
            except (TypeError, ValueError):
                row[field] = ""
        elif field == "age-sex-group":
            try:
                age = float(ev.get("zTwMKXGt0xF") or "")
            except (TypeError, ValueError):
                age = None
            gender = attrs.get("TN7r3ws7IG9", "")
            if gender == "Other":
                value = "TG"
            elif age is None:
                value = ""
            elif age <= 14 and gender == "Male":
                value = "CM"
            elif age <= 14 and gender == "Female":
                value = "CF"
            elif age > 14 and gender == "Male":
                value = "AM"
            elif age > 14 and gender == "Female":
                value = "AF"
            else:
                value = ""
            row[field] = value
        elif field in attrs:
            row[field] = attrs.get(field, "")
        elif field == "rQnmYAF1899-gPHLt0PQq1b":
            row[field] = ev.get("rQnmYAF1899") or ev.get("gPHLt0PQq1b") or ""
        else:
            row[field] = ev.get(field, "")
    return row

'''
def write_combined_csv(path, rows):
    """One combined export: all ART columns plus treatment status/date."""
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([label for _, label in DATA_ELEMENTS])
        for row in rows:
            writer.writerow([row.get(field, "") for field, _ in DATA_ELEMENTS])

'''
#import csv
#import os

def write_combined_csv(path, rows):
    """One combined export: all ART columns plus treatment status/date."""

    # Ensure the output directory exists
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        # Write column headers
        writer.writerow([label for _, label in DATA_ELEMENTS])

        # Write report rows
        for row in rows:
            writer.writerow([
                row.get(field, "") for field, _ in DATA_ELEMENTS
            ])

    logging.info(
        "CSV report generated successfully: %s; rows=%d",
        path,
        len(rows)
    )
    print(f"CSV report generated successfully: {path}; "f"rows: {len(rows)}")


def sendEmail_art_report(generated_csv_files, current_time_start, 
        start_clock, group_name, nepali_month_name, nepali_year, iso_month_start,
        iso_month_end, total_rows, all_tei_uids, active_tei_count,inactive_tei_count, 
        unknown_tei_status_count
    ):
    """
    Send one email with all generated CSV reports attached.
    output_files: list of CSV file paths.
    """
    output_files = [Path(file) for file in generated_csv_files]

    # Attach only files that actually exist.
    valid_files = [file for file in output_files if file.is_file()]

    if not valid_files:
        logging.warning("No valid CSV attachments found. Email not sent.")
        print("No valid CSV attachments found. Email not sent.")
        return

    if not FROM_EMAIL_ADDR or not FROM_EMAIL_PASSWORD:
        raise RuntimeError(
            "Set FROM_EMAIL_ADDR and FROM_EMAIL_PASSWORD in the .env file."
        )

    recipients = ["mithilesh.thakur@hispindia.org"]
    #recipients = ["mithilesh.thakur@hispindia.org","sumit.tripathi@hispindia.org"]
    #recipients = ["mithilesh.thakur@hispindia.org","sumit.tripathi@hispindia.org","RKonda@fhi360.org"]

    msg = MIMEMultipart()
    msg["From"] = FROM_EMAIL_ADDR
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = "Auto Generate Monthly HIV ART Reports"

    today_date = datetime.now().strftime("%Y-%m-%d")
    today_date_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    
    # Capture finish time dynamically
    #end_datetime = datetime.now()
    end_datetime = datetime.now().strftime(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    elapsed_seconds = int(time.perf_counter() - start_clock)

    hours = elapsed_seconds // 3600
    minutes = (elapsed_seconds % 3600) // 60
    seconds = elapsed_seconds % 60

    #print(f"ART Report Generation Process finished: {end_datetime:%Y-%m-%d %H:%M:%S}")
    #print(f"Total Report Generation Time: {hours} hours, {minutes} minutes, {seconds} seconds")

    body = (
        f"Please find attached the HIV ART reports generated on \n\n"
        f"HIV ART Report Generation Process Start Time {current_time_start}.\n"
        f"HIV ART Report Generation Process finished Time {end_datetime}.\n"
        f"Total Report Generation Time: {hours} hours, {minutes} minutes, {seconds} seconds \n\n"
        f"Automated HIV ART Report  for Organisation unit group: {group_name}. \n"
        f"Total CSV reports attached: {len(valid_files)}\n\n"
        f"Automated HIV ART Report Details. \n"
        f"Nepali reporting month: {nepali_month_name} {nepali_year} \n"
        f"ISO Start Date of reporting month: {iso_month_start} and ISO End Date of reporting month: {iso_month_end} \n\n"
        f"Total Clients/ TEIs/ rows exported: {len(all_tei_uids)} \n"
        f"Total Active Clients/ TEIs/ rows exported: {active_tei_count} \n"
        f"Total Inactive Clients/ TEIs/ rows exported: {inactive_tei_count} \n"
        f"Total Unknow Status Clients/ TEIs/ rows exported: {unknown_tei_status_count} \n\n"
        f"Regards,\n"
        f"Mithilesh Kumar Thakur"
    )

    msg.attach(MIMEText(body, "plain"))

    # Attach every generated CSV to this one email.
    for output_file in valid_files:
        with output_file.open("rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())

        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=output_file.name,
        )
        msg.attach(part)

        logging.info("Attached CSV: %s", output_file)
        print(f"Attached: {output_file.name}")

    try:
        # Uses the SMTP server configuration from your existing script.
        with smtplib.SMTP("192.178.211.109", 587, timeout=300) as smtp:
            smtp.starttls()
            smtp.login(FROM_EMAIL_ADDR, FROM_EMAIL_PASSWORD)
            smtp.sendmail(
                FROM_EMAIL_ADDR,
                recipients,
                msg.as_string(),
            )

        logging.info(
            f"ART report email sent successfully. to { recipients } with Attachments, "
            f"{len(valid_files)}",
        )
        print(
            f"ART report email sent successfully. to { recipients } with Attachments, "
            f"{len(valid_files)}",
        )

    except Exception:
        logging.exception("Failed to send ART report email.")
        raise


'''
def sendEmail_art_report( output_file ):

    output_file = Path(output_file)
    logging.error("sending email with Attachment: %s", output_file)
    print("sending email with Attachment: %s", output_file)
    if not output_file.exists():
        logging.error("Attachment file not found: %s", output_file)
        print(f"Attachment file not found: , {output_file}")
        return
    
    #fromaddr = "dss.nipi@hispindia.org"
    fromaddr = FROM_EMAIL_ADDR
    # list of email_id to send the mail
    #li = ["mithilesh.thakur@hispindia.org", "saurabh.leekha@hispindia.org","dpatankar@nipi-cure.org","mohinder.singh@hispindia.org"]
    #li = ["mithilesh.thakur@hispindia.org","sumit.tripathi@hispindia.org","RKonda@fhi360.org"]
    li = ["mithilesh.thakur@hispindia.org"]

    for toaddr in li:

        #toaddr = "mithilesh.thakur@hispindia.org"
        
        # instance of MIMEMultipart 
        msg = MIMEMultipart() 
        
        # storing the senders email address   
        msg['From'] = fromaddr 
        
        # storing the receivers email address  
        msg['To'] = toaddr 
        
        # storing the subject  
        msg['Subject'] = "Auto Generate Monthly ART Report"
        
        # string to store the body of the mail 
        #body = "Python Script test of the Mail"

        today_date = datetime.now().strftime("%Y-%m-%d")
        #updated_odk_api_url = f"{ODK_API_URL}?$filter=__system/submissionDate ge {today_date}"
        updated_odk_api_url = f"{today_date}"

        body = f"Auto Sync ART data from hivtracker to ihmis"
        
        # attach the body with the msg instance 
        msg.attach(MIMEText(body, 'plain')) 
        
        attachment = open(output_file, "rb") 
        
        # instance of MIMEBase and named as p 
        p = MIMEBase('application', 'octet-stream') 
        
        # To change the payload into encoded form 
        p.set_payload((attachment).read()) 
        
        # encode into base64 
        encoders.encode_base64(p) 
        
        #p.add_header('Content-Disposition', "attachment; filename= %s" % output_file) 
        p.add_header(
            "Content-Disposition",
            "attachment",
            filename=output_file.name,
        )
        # attach the instance 'p' to instance 'msg' 
        msg.attach(p) 
        try:
            # creates SMTP session 
            #s = smtplib.SMTP('smtp.gmail.com', 587)
            s = smtplib.SMTP("192.178.211.109", 587, timeout=30)
            
            # start TLS for security 
            s.starttls() 
            
            # Authentication 
            #s.login(fromaddr, "NIPIODKHispIndia@123")
            #s.login(fromaddr, "dztnzuvhbxlauwxy") ## set app password App Name Mail as on 22/12/2025
            s.login(fromaddr, FROM_EMAIL_PASSWORD)
            

            # Converts the Multipart msg into a string 
            text = msg.as_string() 
            
            # sending the mail 
            s.sendmail(fromaddr, toaddr, text) 
            print(f"mail send to: {toaddr}")
            logging.info(f"mail send to: {toaddr}")
            # terminating the session 
            s.quit()
        except Exception as exception:
            print("Error: %s!\n\n" % exception)

'''

def generate_report( current_time_start, start_clock):
    if not DHIS2_API:
        raise RuntimeError("Set DHIS2_GET_API_URL in the .env file.")

    if not DHIS2_USERNAME or not DHIS2_PASSWORD:
        raise RuntimeError(
            "Set DHIS2_GET_USER and DHIS2_GET_PASSWORD."
        )

    start_time = time.perf_counter()

    (
        year,
        month_number,
        month_name,
        month_start,
        month_end,
        as_of_date,
    ) = previous_nepali_month()

    group_name, orgunit_members = get_orgunit_group_members()

    # Load status options only once.
    status_queries = get_status_queries()
    print(f"Status queries loaded: {len(status_queries)}")
    logging.info(f"Status queries loaded: {len(status_queries)}")

    print(
        f"Starting ART report. Group={group_name}; "
        f"BS month={month_name} {year}; Report Generate as-of = {as_of_date}"
    )
    logging.info(
        f"Starting ART report. Group={group_name}; "
        f"BS month={month_name} {year}; Report Generate as-of = {as_of_date}"
    )

    # Phase 1: Collect candidates for every organisation unit.
    candidates_by_ou = {}
    all_tei_uids = set()

    for member in orgunit_members:
        ou_uid = member.get("id")
        ou_name = member.get("name", ou_uid or "unknown")

        if not ou_uid:
            continue

        print(f"Collecting candidates for {ou_name} ({ou_uid})")
        logging.info(f"Collecting candidates for {ou_name} ({ou_uid})")

        ou_candidates = set()

        for de_uid, value in status_queries:
            try:
                ids = get_candidates(
                    as_of_date,
                    de_uid,
                    value,
                    ou_uid,
                )
                ou_candidates.update(ids)

            except requests.RequestException:
                logging.exception(
                    "Candidate query failed: OU=%s, DE=%s, value=%s",
                    ou_uid,
                    de_uid,
                    value,
                )

        candidates_by_ou[ou_uid] = {
            "name": ou_name,
            "teis": ou_candidates,
        }

        all_tei_uids.update(ou_candidates)

        print(
            f"OU={ou_uid}; unique candidates={len(ou_candidates)}"
        )
        logging.info(
            f"OU={ou_uid}; unique candidates={len(ou_candidates)}"
        )
    print(f"Total unique TEIs to fetch: {len(all_tei_uids)}")
    logging.info(f"Total unique TEIs to fetch: {len(all_tei_uids)}")

    # Phase 2: Fetch each unique TEI concurrently, only once.
    tei_cache = {}
    failed_teis = set()

    # TEI active/inactive counters
    active_tei_count = 0
    inactive_tei_count = 0
    unknown_tei_status_count = 0

    max_workers = 8  # Start with 8; tune based on DHIS2 capacity.

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_uid = {
            executor.submit(get_tei_data, uid, as_of_date): uid
            for uid in all_tei_uids
        }

        completed = 0
        total = len(future_to_uid)

        for future in as_completed(future_to_uid):
            uid = future_to_uid[future]
            completed += 1

            try:
                attrs, ev = future.result()
                tei_cache[uid] = (attrs, ev)

            except Exception:
                failed_teis.add(uid)
                logging.exception("Failed to fetch TEI %s", uid)

            if completed % 100 == 0 or completed == total:
                print(
                    f"Fetched TEIs: {completed}/{total}; "
                    f"successful={len(tei_cache)}; "
                    f"failed={len(failed_teis)}"
                )
                logging.info(
                    f"Fetched TEIs: {completed}/{total}; "
                    f"successful={len(tei_cache)}; "
                    f"failed={len(failed_teis)}"
                )
    
        # Count active/inactive TEIs from successfully fetched TEI records.
        for attrs, ev in tei_cache.values():
            status = attrs.get("teiActiveStatus", "")

            if status == "Active":
                active_tei_count += 1
            elif status == "Inactive":
                inactive_tei_count += 1
            else:
                unknown_tei_status_count += 1

        # Print counts to console.
        print(
            f"TEI Active Count: {active_tei_count}; "
            f"TEI Inactive Count: {inactive_tei_count}; "
            f"Unknown Status Count: {unknown_tei_status_count}"
        )

        # Write counts to the log file.
        logging.info(
            "TEI status counts: Active=%d; Inactive=%d; Unknown=%d",
            active_tei_count,
            inactive_tei_count,
            unknown_tei_status_count,
        )
            
    # Phase 3: Build and write one CSV for each group member.
    generated_files = 0
    total_rows = 0
    generated_csv_files = []

    for ou_uid, info in candidates_by_ou.items():
        ou_name = info["name"]
        ou_candidates = info["teis"]

        report_rows = []

        for uid in sorted(ou_candidates):
            cached = tei_cache.get(uid)

            if cached is None:
                continue

            attrs, ev = cached
            report_rows.append(make_report_row(attrs, ev))

        safe_name = "".join(
            "_" if char in '<>:"/\\|?*' or ord(char) < 32 else char
            for char in ou_name
        ).strip(" .")

        if not safe_name:
            safe_name = ou_uid
        '''
        filename = (
            f"HIV_ART_Treatment_Status_"
            f"{year}_{month_number.zfill(2)}_{month_name}_"
            f"{safe_name}.csv"
        )
        '''
        
        filename = (
            f"HIV_ART_Treatment_Status_"
            f"{year}_{month_number.zfill(2)}_{month_name}_"
            f"{safe_name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        )

        output_files = []
        output_file = os.path.join(REPORT_OUTPUT_DIR, filename)

        write_combined_csv(output_file, report_rows)

        generated_csv_files.append(output_file)
        generated_files += 1
        total_rows += len(report_rows)

        print(f"Generated: {output_file} "f"({len(report_rows)} rows)")   
        logging.info(f"Generated: {output_file} "f"({len(report_rows)} rows)")     

        # Collect only files generated in this run
        output_files.append(output_file)

        print(
            f"Generated: {output_file}; rows={len(report_rows)}"
        )
        logging.info(
            f"Generated: {output_file}; rows={len(report_rows)}"
        )

        # Uncomment if you want one email per organisation unit.
        # sendEmail_art_report(output_file)


    if generated_csv_files:
        sendEmail_art_report(generated_csv_files, current_time_start, 
            start_clock,group_name, month_name, year, month_start,
            month_end, total_rows, all_tei_uids, active_tei_count,
            inactive_tei_count, unknown_tei_status_count

        )
        print(
            f"Email sent with {len(generated_csv_files)} CSV files "
            "for the latest generated month."
        )   
        logging.info(
            f"Email sent with {len(generated_csv_files)} CSV files "
            "for the latest generated month."
        )             
    else:
        print("No CSV files were generated. Email not sent.")
        logging.info("No CSV files were generated. Email not sent.")
    
    elapsed = time.perf_counter() - start_time

    print(
        f"Finished ART report. Group={group_name}; "
        f"files={generated_files}; rows={total_rows}; "
        f"unique TEIs={len(all_tei_uids)}; "
        f"failed TEIs={len(failed_teis)}; "
        f"elapsed={elapsed:.1f} seconds"
    )

    logging.info(
        "Finished ART report. Group=%s; files=%d; rows=%d; "
        "unique TEIs=%d; failed TEIs=%d; elapsed=%.1f seconds",
        group_name,
        generated_files,
        total_rows,
        len(all_tei_uids),
        len(failed_teis),
        elapsed,
    )

    print(f"Organisation unit group: {group_name}")
    logging.info(f"Organisation unit group: {group_name}")
    print(f"Nepali reporting month: {month_name} {year}")
    logging.info(f"Nepali reporting month: {month_name} {year}")
    print(f"Data as of ISO date: {as_of_date}")
    logging.info(f"Data as of ISO date: {as_of_date}")
    print(f"CSV files generated: {generated_files}")
    logging.info(f"CSV files generated: {generated_files}")
    print(f"Total rows exported: {total_rows}")
    logging.info(f"Total rows exported: {total_rows}")

    print(f"Total Active TEIs: {active_tei_count}")
    logging.info("Total Active TEIs: %d", active_tei_count)

    print(f"Total Inactive TEIs: {inactive_tei_count}")
    logging.info("Total Inactive TEIs: %d", inactive_tei_count)

    print(f"Total TEIs with Unknown Status: {unknown_tei_status_count}")
    logging.info(
        "Total TEIs with Unknown Status: %d",
        unknown_tei_status_count,
    )

'''
def generate_report():

    if not DHIS2_API:
        raise RuntimeError(
            "Set DHIS2_GET_API_URL in the .env file."
        )

    if not DHIS2_USERNAME or not DHIS2_PASSWORD:
        raise RuntimeError(
            "Set DHIS2_GET_USER and DHIS2_GET_PASSWORD."
        )

    # Determine the current Nepali reporting month.
    (
        year,
        month_number,
        month_name,
        month_start,
        month_end,
        as_of_date,
    ) = current_nepali_month()

    # Fetch all organisation units in the configured group.
    group_name, orgunit_members = get_orgunit_group_members()

    logging.info(
        "Starting ART report. Group=%s; BS month=%s %s; "
        "ISO month=%s to %s; as-of=%s",
        group_name,
        month_name,
        year,
        month_start,
        month_end,
        as_of_date,
    )
    print(
        f"Starting ART report. Group={group_name}; "
        f"BS month={month_name} {year}; "
        f"ISO month={month_start} to {month_end}; "
        f"as-of={as_of_date}"
    )
    total_rows = 0
    generated_files = 0

    for member in orgunit_members:

        orgunit_uid = member.get("id")
        orgunit_name = member.get("name", orgunit_uid or "unknown")

        if not orgunit_uid:
            logging.warning(
                "Skipping group member without an organisation unit UID."
            )
            continue

        logging.info(
            "Generating report for organisation unit: %s (%s)",
            orgunit_name,
            orgunit_uid,
        )
        print(
            f"Generating report for organisation unit: "
            f"{orgunit_name} ({orgunit_uid})"
        )
        # Collect unique TEIs for this organisation unit.
        candidate_teis = set()
        status_queries = get_status_queries()

        for de_uid, value in status_queries:
            try:
                ids = get_candidates(
                    as_of_date,
                    de_uid,
                    value,
                    orgunit_uid,
                )
                candidate_teis.update(ids)

                logging.info(
                    "OU=%s; query %s=%s; returned %d TEIs",
                    orgunit_uid,
                    de_uid,
                    value,
                    len(ids),
                )
                print(
                    f"OU={orgunit_uid}; query {de_uid}={value}; "
                    f"returned {len(ids)} TEIs"
                )
            except requests.RequestException:
                logging.exception(
                    "Candidate query failed for OU=%s, DE=%s, value=%s",
                    orgunit_uid,
                    de_uid,
                    value,
                )

        logging.info(
            "OU=%s; unique candidate TEIs=%d",
            orgunit_uid,
            len(candidate_teis),
        )
        print(f"OU={orgunit_uid}; unique candidate TEIs {len(candidate_teis)} ")
        
        report_rows = []

        for index, tei_uid in enumerate(
            sorted(candidate_teis),
            start=1,
        ):
            try:
                attrs, ev = get_tei_data(tei_uid, as_of_date)

                # Keep this report limited to the current organisation unit.
                # Use the enrollment organisation unit returned by DHIS2.
                
                if attrs.get("ouId") != orgunit_uid:
                    logging.info(
                        "Skipping TEI %s: enrollment OU=%s, report OU=%s",
                        tei_uid,
                        attrs.get("ouId"),
                        orgunit_uid,
                    )
                    continue
                       
                report_rows.append(make_report_row(attrs, ev))

                if index % 100 == 0:
                    logging.info(
                        "OU=%s; processed %d/%d TEIs",
                        orgunit_uid,
                        index,
                        len(candidate_teis),
                    )
                    print(
                        f"OU={orgunit_uid}; processed "
                        f"{index}/{len(candidate_teis)} TEIs"
                    )

            except requests.RequestException:
                logging.exception(
                    "DHIS2 request failed for TEI %s, OU=%s",
                    tei_uid,
                    orgunit_uid,
                )

            except (KeyError, TypeError, ValueError):
                logging.exception(
                    "Could not process TEI %s, OU=%s",
                    tei_uid,
                    orgunit_uid,
                )

        # Make the organisation unit name safe for a Windows filename.
        safe_name = "".join(
            "_" if char in '<>:"/\\\\|?*' or ord(char) < 32 else char
            for char in orgunit_name
        ).strip(" .")

        if not safe_name:
            safe_name = orgunit_uid

        # Generate one CSV per organisation unit group member.
        report_file_name = (
            f"HIV_ART_Treatment_Status_"
            f"{year}_{month_number.zfill(2)}_{month_name}_"
            f"{safe_name}.csv"
        )

        output_file = os.path.join(
            REPORT_OUTPUT_DIR,
            report_file_name,
        )

        write_combined_csv(output_file, report_rows)

        generated_files += 1
        total_rows += len(report_rows)

        logging.info(
            "Generated OU report: %s; rows=%d",
            output_file,
            len(report_rows),
        )

        print(f"Organisation unit Name : {orgunit_name} uid :  ({orgunit_uid})")
        logging.info(
            f"Organisation unit Name : {orgunit_name} uid : ({orgunit_uid})"
        )
        print(f"Rows exported: {len(report_rows)}")
        logging.info(f"Rows exported: {len(report_rows)}")
        print(f"CSV file: {output_file}")
        logging.info(f"CSV file: {output_file}")

        # Email this organisation unit's CSV.
        #sendEmail_art_report(output_file)

    logging.info(
        "Finished multi-CSV ART report. Group=%s; files=%d; rows=%d",
        group_name,
        generated_files,
        total_rows,
    )
    print(
        f"Finished multi-CSV ART report. Group={group_name}; "
        f"files={generated_files}; rows={total_rows}"
    )

    print(f"Organisation unit group: {group_name}")
    logging.info(f"Organisation unit group: {group_name}")
    print(f"Nepali reporting month: {month_name} {year}")
    logging.info(f"Nepali reporting month: {month_name} {year}")
    print(f"Data as of ISO date: {as_of_date}")
    logging.info(f"Data as of ISO date: {as_of_date}")
    print(f"CSV files generated: {generated_files}")
    logging.info(f"CSV files generated: {generated_files}")
    print(f"Total rows exported: {total_rows}")
    logging.info(f"Total rows exported: {total_rows}")

'''

'''
def generate_report():
    
    if not DHIS2_USERNAME or not DHIS2_PASSWORD:
        raise RuntimeError("Set DHIS2_USERNAME and DHIS2_PASSWORD environment variables.")
    if not ORG_UNIT_UID or ORG_UNIT_UID == "YOUR_ORG_UNIT_UID":
        raise RuntimeError("Set ORG_UNIT_UID to the intended DHIS2 organisation unit UID.")
    if "YOUR-DHIS2-SERVER" in DHIS2_API:
        raise RuntimeError("Set DHIS2_API to your actual DHIS2 API base URL.")

    year, month_number, month_name, month_start, month_end, as_of_date = current_nepali_month()
    logging.info(
        "Starting report. Nepali month=%s %s; ISO month=%s to %s; as-of=%s; OU=%s",
        month_name, year, month_start, month_end, as_of_date, ORG_UNIT_UID,
    )

    # Merge candidate TEIs from every status option into one unique set.
    
    
    candidate_teis = set()
    
    status_queries = get_status_queries()
    for de_uid, value in status_queries:
        ids = get_candidates(as_of_date, de_uid, value)
        candidate_teis.update(ids)
        logging.info("Status query %s=%s returned %d TEIs", de_uid, value, len(ids))
    
    logging.info("Unique candidate TEIs across all statuses: %d", len(candidate_teis))
    report_rows = []
    
    for index, tei_uid in enumerate(sorted(candidate_teis), start=1):
        try:
            attrs, ev = get_tei_data(tei_uid, as_of_date)
            # Include all clients returned by the status queries, with status in
            # the same ART CSV; don't create a second client-status file.
            report_rows.append(make_report_row(attrs, ev))
            if index % 100 == 0:
                logging.info("Processed %d/%d TEIs", index, len(candidate_teis))
                print("Processed %d/%d TEIs", index, len(candidate_teis))
        except requests.RequestException:
            logging.exception("DHIS2 request failed for TEI %s", tei_uid)
        except (KeyError, TypeError, ValueError):
            logging.exception("Could not process TEI %s", tei_uid)
    
    # Stable filename means the daily task refreshes this month's combined report.
    #output_file = OUTPUT_DIR / f"HIV_ART_Treatment_Status_{year}_{month_number.zfill(2)}_{month_name}.csv"

    report_file_name = f"HIV_ART_Treatment_Status_{year}_{month_number.zfill(2)}_{month_name}.csv"
    f"HIV_ART_Treatment_Status_{year}_{month_number.zfill(2)}_{month_name}.csv"
    output_file = os.path.join(REPORT_OUTPUT_DIR, report_file_name)

    output_file_attach = os.path.join(REPORT_OUTPUT_DIR, report_file_name)
    
    write_combined_csv(output_file, report_rows)

    logging.info("Finished report: %s; rows=%d", output_file, len(report_rows))

    sendEmail_art_report( output_file_attach )

    print(f"Nepali reporting month: {month_name} {year}")
    print(f"Data as of ISO date: {as_of_date}")
    print(f"Unique candidate clients: {len(candidate_teis)}")
    print(f"Rows exported: {len(report_rows)}")
    print(f"Combined CSV: {output_file}")

'''

if __name__ == "__main__":
    try:

        current_time_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_clock = time.perf_counter()
        print( f"Monthly ART Report Generation Process Start . { current_time_start }" )
        logging.info(f"Monthly ART Report Generation Process Start  . { current_time_start }")
        
        generate_report( current_time_start, start_clock )

        current_time_end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Capture finish time dynamically
        end_datetime = datetime.now()
        elapsed_seconds = int(time.perf_counter() - start_clock)

        hours = elapsed_seconds // 3600
        minutes = (elapsed_seconds % 3600) // 60
        seconds = elapsed_seconds % 60

        print( f"Monthly ART Report Generation Process finished . { current_time_end }" )
        logging.info(f"Monthly ART Report Generation Process finished . { current_time_end }")
        #print(f"ART Report Generation Process finished: {end_datetime:%Y-%m-%d %H:%M:%S}")
        print(f"Total Report Generation Time: {hours} hours, {minutes} minutes, {seconds} seconds")
        logging.info(f"Total Report Generation Time: {hours} hours, {minutes} minutes, {seconds} seconds")


    except Exception:
        logging.exception("HIV ART report generation failed")
        raise



'''
import time
from datetime import datetime

# Capture start time dynamically
start_datetime = datetime.now()
start_clock = time.perf_counter()

print(f"Report Generation Process Start: {start_datetime:%Y-%m-%d %H:%M:%S}")

# Your report generation process
generate_report()

# Capture finish time dynamically
end_datetime = datetime.now()
elapsed_seconds = int(time.perf_counter() - start_clock)

hours = elapsed_seconds // 3600
minutes = (elapsed_seconds % 3600) // 60
seconds = elapsed_seconds % 60

print(f"ART Report Generation Process finished: {end_datetime:%Y-%m-%d %H:%M:%S}")
print(f"Total Report Generation Time: {hours} hours, {minutes} minutes, {seconds} seconds")

'''