## install
#pip install python-dotenv
#pip install psycopg2-binary
#pip install clickhouse-connect

# pip install nepali-date_converter
# pip install npdatetime
# pip install datetime

#https://pypi.org/project/nepali-calendar-utils/
#pip install nepali-calendar-utils
#pip install nepali
#pip install nepali-datetime

# main.py
from dotenv import load_dotenv
import os

load_dotenv()
from concurrent.futures import ThreadPoolExecutor
import requests
import json
from datetime import datetime,date
import nepali_datetime
from utils import (
    configure_logging,
    log_info,log_error,get_program_indicator_list,get_org_unit_list,
    get_aggregated_de_from_indicators,get_orgunit_grp_member,
    get_program_indicators_data_values, push_dataValueSet_in_dhis2,
    get_bs_month_start_end,get_between_dates_iso
   
)


DHIS2_GET_API_URL = os.getenv("DHIS2_GET_API_URL")
DHIS2_GET_USER = os.getenv("DHIS2_GET_USER")
DHIS2_GET_PASSWORD = os.getenv("DHIS2_GET_PASSWORD")

DHIS2_POST_API_URL = os.getenv("DHIS2_POST_API_URL")
DHIS2_POST_USER = os.getenv("DHIS2_POST_USER")
DHIS2_POST_PASSWORD = os.getenv("DHIS2_POST_PASSWORD")

META_ATTRIBUTE_PI_TO_AGGREGATE_DE = os.getenv("META_ATTRIBUTE_PI_TO_AGGREGATE_DE")
META_ATTRIBUTE_HMIS_ORG_UNIT_CODE = os.getenv("META_ATTRIBUTE_HMIS_ORG_UNIT_CODE")
IHMIS_DEFAULT_ATTRIBUTE_OPTION_COMBO = os.getenv("IHMIS_DEFAULT_ATTRIBUTE_OPTION_COMBO")

ORG_UNIT_GROUP_ART_CENTERS = os.getenv("ORG_UNIT_GROUP_ART_CENTERS")
PI_GROUP_ART_REPORT = os.getenv("PI_GROUP_ART_REPORT")
HIV_PROGRAM_ID = os.getenv("HIV_PROGRAM_ID")

program_indicators_api_url = f"{DHIS2_GET_API_URL}programIndicators"
org_unit_api_url = f"{DHIS2_GET_API_URL}organisationUnits"
orgunit_grp_api_url = f"{DHIS2_GET_API_URL}organisationUnitGroups"
program_indicators_data_value_url = f"{DHIS2_GET_API_URL}analytics.json"

dataValueSet_endPoint = f"{DHIS2_POST_API_URL}dataValueSets" 


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


def main():

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

    # get all dates between startdate,enddate
    #dates = get_between_dates("2023-01-28", "2023-02-03")
    isoDatePeriods = get_between_dates_iso(start.to_datetime_date(), end.to_datetime_date())
    print("dates:" ,isoDatePeriods)
    #print(f"isoDatePeriods {len(isoDatePeriods)}")
    #log_info(f"isoDatePeriods {len(isoDatePeriods)}")

    current_time_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print( f"pushing to IHMIS Aggregated Data Value process start . { current_time_start }" )
    log_info(f"pushing to IHMIS Aggregated Data Value process start  . { current_time_start }")
    
    program_indicator_list = get_program_indicator_list( program_indicators_api_url,session_get,META_ATTRIBUTE_PI_TO_AGGREGATE_DE )
    log_info(f"program_indicator_size {len(program_indicator_list)}")
    print(f"program_indicator_size {len(program_indicator_list)}")

    orgunit_grp_members = get_orgunit_grp_member( orgunit_grp_api_url,session_get, ORG_UNIT_GROUP_ART_CENTERS )
    #log_info(f"orgunit_grp_members_size {len(orgunit_grp_members)}")
    #print(f"orgunit_grp_members_size {len(orgunit_grp_members)}")

    orgUnit_code_uid_dict = get_org_unit_list( org_unit_api_url,session_get,META_ATTRIBUTE_HMIS_ORG_UNIT_CODE )
    log_info(f"orgUnit_code_uid_dict_size {len(orgUnit_code_uid_dict)}")
    print(f"orgUnit_code_uid_dict_size {len(orgUnit_code_uid_dict)}")
    print(f"HMIS code --  {orgUnit_code_uid_dict['aXquUzlrYYv']}, HMIS code --  {orgUnit_code_uid_dict['BiBfVGxLkLE']} ")

    aggregated_de_dict = get_aggregated_de_from_indicators( program_indicators_api_url,session_get,META_ATTRIBUTE_PI_TO_AGGREGATE_DE )
    print(f"aggregated dataElement_coc size {len(aggregated_de_dict)}")
    log_info(f"aggregated dataElement_coc size {len(aggregated_de_dict)}")
    print(f"DE coc --  {aggregated_de_dict['UjYFHNozrnW']}, DE coc --  {aggregated_de_dict['ht5UD6UweLi']} ")

    #program_indicator = "vcFk6C2BZCx;UjYFHNozrnW;AM2UlJTIv3T;h6UU7fJNkez;YKKQmj4ENTy;YTyfolsnUhh;xPbkfVnHnAb;VaYBFHfr5vB;OIUpE0k1Fzz;jAyHNleIeUF;ht5UD6UweLi"
    #program_indicators_data_values = get_program_indicators_data_values(program_indicators_data_value_url,session_get, program_indicator, ORG_UNIT_GROUP_ART_CENTERS)

    tempDataValues = list()
    if aggregated_de_dict:
        if program_indicator_list:
            for program_indicator in program_indicator_list:
                print(f"program_indicator_name { program_indicator['name']} , program_indicator_id { program_indicator['id']}")
                log_info(f"program_indicator_name { program_indicator['name'] },  program_indicator_id { program_indicator['id']}")
                
                program_indicators_data_values = get_program_indicators_data_values(program_indicators_data_value_url,session_get, program_indicator['id'], ORG_UNIT_GROUP_ART_CENTERS)
                print(f"program_indicators_data_values size {len(aggregated_de_dict)}")
                log_info(f"program_indicators_data_values size {len(aggregated_de_dict)}")
                tempDataValues = list()
                dataValueSet_payload = {}
                if program_indicators_data_values:
                    for pi_dataValue in program_indicators_data_values:
                        #print( f"pi_de . { pi_dataValue[0] } , pi_ou . { pi_dataValue[1] }, pi_value . { pi_dataValue[2] } " )
                        if aggregated_de_dict.get(pi_dataValue[0]) is not None and orgUnit_code_uid_dict.get(pi_dataValue[1]) is not None:
                            #print( f"hmis_de . { aggregated_de_dict[pi_dataValue[0]] } , hmis_ou . { orgUnit_code_uid_dict[pi_dataValue[1]] }, hmis_value . { pi_dataValue[2] } " )
                            dataValue = {
                                "dataElement": aggregated_de_dict[pi_dataValue[0]].split("-")[0],
                                "categoryOptionCombo": aggregated_de_dict[pi_dataValue[0]].split("-")[1],
                                "attributeOptionCombo":IHMIS_DEFAULT_ATTRIBUTE_OPTION_COMBO,
                                "value": int(float(pi_dataValue[2])),
                                "period": current_nepali_monthly_period,
                                "orgUnit": orgUnit_code_uid_dict[pi_dataValue[1]]
                                #"orgUnit": pi_dataValue[1]
                            }
                            tempDataValues.append(dataValue)

                    dataValueSet_payload = {
                            "orgUnitIdScheme": "code",
                            #"dataSet": "vEURWncI7uL",
                            "dataValues":tempDataValues
                        }
                    #print( f"dataValueSet_payload . { dataValueSet_payload }" )
                    push_dataValueSet_in_dhis2( dataValueSet_endPoint, session_post, dataValueSet_payload )

        #print( f"dataValueSet_payload . { dataValueSet_payload }" )
        #print( f" dataValueSet_payload size . { len(dataValueSet_payload) }" )
        #push_dataValueSet_in_dhis2( dataValueSet_payload)

if __name__ == "__main__":

    event_push_count = 0
    null_patient_id_count = 0
    total_patient_count = 0

    main()
    current_time_end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print( f"pushing to IHMIS Aggregated Data Value process finished . { current_time_end }" )
    log_info(f"pushing Tracker event data in DHIS finished . { current_time_end }")

    #print(f"total_patient_count. {total_patient_count}, null_patient_id_count. {null_patient_id_count}, event_push_count {event_push_count}")
    #log_info(f"total_patient_count. {total_patient_count}, null_patient_id_count. {null_patient_id_count}, event_push_count {event_push_count}")
    