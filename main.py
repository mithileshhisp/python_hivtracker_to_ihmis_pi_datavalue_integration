## install
#pip install python-dotenv
#pip install psycopg2-binary
#pip install clickhouse-connect

# main.py
from dotenv import load_dotenv
import os

load_dotenv()
from concurrent.futures import ThreadPoolExecutor
import requests
import json
from datetime import datetime,date
import nepali_datetime
from logger import configure_logging,log_info,log_error
from utils import (
    get_dataValueSets_org_group,get_org_unit_list,
    get_aggregated_de_from_indicators,get_orgunit_grp_member,
    get_program_indicators_data_values, push_dataValueSet_in_dhis2,
    get_bs_month_start_end,get_between_dates_iso,sendEmail
)



DHIS2_GET_API_URL = os.getenv("DHIS2_GET_API_URL")
DHIS2_GET_USER = os.getenv("DHIS2_GET_USER")
DHIS2_GET_PASSWORD = os.getenv("DHIS2_GET_PASSWORD")

DHIS2_POST_API_URL = os.getenv("DHIS2_POST_API_URL")
DHIS2_POST_USER = os.getenv("DHIS2_POST_USER")
DHIS2_POST_PASSWORD = os.getenv("DHIS2_POST_PASSWORD")


ORG_UNIT_GROUP_ART_CENTERS = os.getenv("ORG_UNIT_GROUP_ART_CENTERS")
DATA_SET_HIV_AIDS_ART_CENTERS = os.getenv("DATA_SET_HIV_AIDS_ART_CENTERS")


dataValueSet_endPoint = f"{DHIS2_POST_API_URL}dataValueSets" 

#DHIS2_AUTH_POST = ("hispdev", "Devhisp@1")
#session_post = requests.Session()
#session_post.auth = DHIS2_AUTH_POST

# Create a session object for persistent connection
#session_get = requests.Session()
#session_get.auth = DHIS2_AUTH_GET

raw_auth = os.getenv("DHIS2_AUTH")

if raw_auth is None:
    raise ValueError("DHIS2_AUTH is missing in .env")

if ":" not in raw_auth:
    raise ValueError("DHIS2_AUTH must be in user:password format")

user, pwd = raw_auth.split(":", 1)

session_get = requests.Session()
#session_get.auth = (user, pwd)
session_get.auth = (DHIS2_GET_USER, DHIS2_GET_PASSWORD)

session_post = requests.Session()
#session_get.auth = (user, pwd)
session_post.auth = (DHIS2_POST_USER, DHIS2_POST_PASSWORD)

#session_get.verify = False


def main_with_logger():

    configure_logging()
    ## current nepali date/month/period
    # Get the current Nepali date and time
    current_nepali_datetime = nepali_datetime.datetime.now()
    # Extract the month number
    nepali_current_month_number = current_nepali_datetime.month

    # Extract the Nepali Year
    nepali_current_year = current_nepali_datetime.year

    # Get the month name (optional, if you need the name instead of the number)
    nepali_current_month_name = current_nepali_datetime.strftime("%B")

    print(f"Current Nepali Year: {nepali_current_year}")
    print(f"Current Nepali month number: {nepali_current_month_number}")
    print(f"Current Nepali month name: {nepali_current_month_name}")

    # Example: current nelai month to month startdate and enddate
    start, end = get_bs_month_start_end(nepali_current_year, nepali_current_month_number)
    #start, end = get_bs_month_start_end(2081, 1)

    print("Start BS:", start)
    print("End BS:", end)
    print("Start AD:", start.to_datetime_date())
    print("End AD:", end.to_datetime_date())

    # Convert date objects to string

    current_nepali_monthly_period = start.strftime("%Y-%m-%d").split("-")[0] + "" + start.strftime("%Y-%m-%d").split("-")[1]
    
    print(f"current_nepali_monthly_period {current_nepali_monthly_period}")
    log_info(f"current_nepali_monthly_period {current_nepali_monthly_period}")


    current_time_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print( f"pushing to IHMIS Aggregated Data Value process start . { current_time_start }" )
    log_info(f"pushing to IHMIS Aggregated Data Value process start  . { current_time_start }")
    
    aggregated_data_values = get_dataValueSets_org_group( dataValueSet_endPoint, session_get, DATA_SET_HIV_AIDS_ART_CENTERS, ORG_UNIT_GROUP_ART_CENTERS, current_nepali_monthly_period )

    log_info(f"aggregated_data_values {len(aggregated_data_values)}")
    print(f"aggregated_data_values {len(aggregated_data_values)}")

    #tempDataValues = list()
    dataValueSet_payload = {}
    if aggregated_data_values:
        dataValueSet_payload = {
            "dataValues":aggregated_data_values
        }

        #print( f"dataValueSet_payload . { dataValueSet_payload }" )
        push_dataValueSet_in_dhis2( dataValueSet_endPoint, session_post, dataValueSet_payload )

if __name__ == "__main__":

    event_push_count = 0
    null_patient_id_count = 0
    total_patient_count = 0

    #main()
    main_with_logger()
    current_time_end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print( f"pushing to IHMIS Aggregated Data Value process finished . { current_time_end }" )
    log_info(f"pushing Tracker event data in DHIS finished . { current_time_end }")
    sendEmail()
    #print(f"total_patient_count. {total_patient_count}, null_patient_id_count. {null_patient_id_count}, event_push_count {event_push_count}")
    #log_info(f"total_patient_count. {total_patient_count}, null_patient_id_count. {null_patient_id_count}, event_push_count {event_push_count}")
    