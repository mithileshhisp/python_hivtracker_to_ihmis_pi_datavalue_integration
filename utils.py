# utils.py

import requests
import logging

import certifi  ## for post data in hmis production certificate issue


import json
import smtplib
from email.mime.multipart import MIMEMultipart 
from email.mime.text import MIMEText 
from email.mime.base import MIMEBase 
from email import encoders
from urllib.parse import quote

## for nepali date
import nepali_datetime
from datetime import datetime, timedelta, date

#from datetime import timedelta

from dotenv import load_dotenv
import os
import glob
load_dotenv()

FROM_EMAIL_ADDR = os.getenv("FROM_EMAIL_ADDR")
FROM_EMAIL_PASSWORD = os.getenv("FROM_EMAIL_PASSWORD")

from constants import LOG_FILE
#from app import QueueLogHandler

DHIS2_API_URL = os.getenv("DHIS2_API_URL")


# ADD THIS PART (UI streaming) for print in HTML Page in response
#Add a global log queue
import queue
log_queue = queue.Queue()
#Add a Queue logging handler
#import logging

'''
class QueueLogHandler(logging.Handler):
    def emit(self, record):
        log_queue.put(self.format(record))
'''

import logging
import queue

log_queue = queue.Queue()

class QueueHandler(logging.Handler):
    def emit(self, record):
        log_queue.put(self.format(record))


def configure_logging_for_app(log_file=None):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 🔴 REMOVE OLD HANDLERS (THIS IS KEY)
    for h in list(logger.handlers):
        logger.removeHandler(h)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    # Console
    console  = logging.StreamHandler()
    console .setFormatter(formatter)
    logger.addHandler(console)

    # Queue (for UI)
    qh = QueueHandler()
    qh.setFormatter(formatter)
    logger.addHandler(qh)

    # File (ONLY if provided)
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file, mode="w")
        fh.setFormatter(formatter)
        logger.addHandler(fh)



'''
def configure_logging_for_app():

    
    import os
    from constants import LOG_FILE

    LOG_DIR = "logs"
    os.makedirs(LOG_DIR, exist_ok=True)
    assert LOG_DIR != "/" and LOG_DIR != "" #### Never delete outside log folder.

    log_path = os.path.join(LOG_DIR, LOG_FILE)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)

    queue_handler = QueueLogHandler()
    queue_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 🔴 CRITICAL: remove old handlers
    root.handlers.clear()

    root.addHandler(file_handler)
    root.addHandler(queue_handler)

    logging.info("Logging initialized for Flask app")

'''




def configure_logging():

    #Optional (Advanced, but useful)
    '''
    import sys
    sys.stdout.write = lambda msg: logging.info(msg)
    logging.info(f"[job:{job_id}] step 1")
    '''

    LOG_DIR = "logs"
    #os.makedirs(LOG_DIR, exist_ok=True)

    os.makedirs(LOG_DIR, exist_ok=True)
    assert LOG_DIR != "/" and LOG_DIR != "" #### Never delete outside log folder.

    # Create unique log filename
    #log_filename = f"log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    log_filename = LOG_FILE
    #log_filename = f"{LOG_FILE}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    log_path = os.path.join(LOG_DIR, log_filename)

    #logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    logging.basicConfig(filename=log_path, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    '''
    logging.basicConfig(filename=log_path,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path),
            QueueLogHandler()   # 👈 THIS is the key
        ]
    )
    '''
    # ✅ ADD THIS (UI streaming)
    '''
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Prevent duplicate handlers
    if not any(isinstance(h, QueueLogHandler) for h in root_logger.handlers):
        queue_handler = QueueLogHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        queue_handler.setFormatter(formatter)
        root_logger.addHandler(queue_handler)
    '''

def log_info(message):
    logging.info(message)

def log_error(message):
    logging.error(message)

#################################
## for HIV-TRACKER ######

def get_program_indicator_list( program_indicators_api_url,session_get,META_ATTRIBUTE_PI_TO_AGGREGATE_DE ):
    
    program_indicators = list()
    filters = [
        f"attributeValues.attribute.id:eq:{META_ATTRIBUTE_PI_TO_AGGREGATE_DE}&paging=false"
    ]

    #https://tracker.hivaids.gov.np/save-child-2.27/api/programIndicators?fields=id,name,attributeValues&filter=attributeValues.attribute.id:eq:tjqWoZ59saL&paging=false
    
    url_with_filters = f"{program_indicators_api_url}?fields=id,name,attributeValues&filter={'&filter='.join(filters)}"
    response_program_indicators = session_get.get (url_with_filters )
   
    #print(f"url_with_filters : {url_with_filters}")


    if response_program_indicators.status_code == 200:
        response_data_program_indicators_grp = response_program_indicators.json()
        
        program_indicators_grp_data = response_data_program_indicators_grp.get('programIndicators', [])
        
        if program_indicators_grp_data:
            
            return program_indicators_grp_data
    
        else:
            return []
    else:
        print(f"Failed to retrieve program_indicators units. Status code: {response_program_indicators.status_code}")

    return program_indicators


def get_org_unit_list( org_unit_api_url,session_get,META_ATTRIBUTE_HMIS_ORG_UNIT_CODE ):

    orgUnit_code_uid_dict = {}

    filters = [
        f"attributeValues.attribute.id:eq:{META_ATTRIBUTE_HMIS_ORG_UNIT_CODE}&paging=false"
    ]


    #https://tracker.hivaids.gov.np/save-child-2.27/api/organisationUnits?fields=id,name,attributeValues&filter=attributeValues.attribute.id:eq:nEIktLQW451&paging=false
    org_unit_url_with_filters = f"{org_unit_api_url}?fields=id,name,attributeValues&filter={'&filter='.join(filters)}"

    #print(f"org_unit_url_with_filters : {org_unit_url_with_filters}")

    response_org_units = session_get.get( org_unit_url_with_filters )


    if response_org_units.status_code == 200:
        response_data_org_units = response_org_units.json()
        
        org_units_data = response_data_org_units.get('organisationUnits', [])
        
        if org_units_data:
            for org_unit in org_units_data:
                org_units_attributeValues = org_unit.get('attributeValues', [])
                
                if org_units_attributeValues:
                    for org_units_attributeValue in org_units_attributeValues:

                        org_unit_uid = org_unit['id']
                        org_unit_code_hmis = org_units_attributeValue['value']

                        if org_unit_uid not in orgUnit_code_uid_dict:
                                orgUnit_code_uid_dict[org_unit_uid] = org_unit_code_hmis
                        else:
                            if org_unit_code_hmis not in orgUnit_code_uid_dict[org_unit_uid]:
                                #option_dict[code].append(value)
                                orgUnit_code_uid_dict[org_unit_uid] = org_unit_code_hmis                     
        
        else:
            error_message = f"No ORG UNIT HMIS CODE found"
            print(error_message)

    else:
        print(f"Failed to retrieve org units. Status code: {response_org_units.status_code}")

    return orgUnit_code_uid_dict




def get_aggregated_de_from_indicators( program_indicators_api_url,session_get, META_ATTRIBUTE_PI_TO_AGGREGATE_DE ):
    aggregated_de_dict = {}
    filters = [
        f"attributeValues.attribute.id:eq:{META_ATTRIBUTE_PI_TO_AGGREGATE_DE}&paging=false"
    ]

    #https://ln4.hispindia.org/timor_dev/api/programIndicators.json?fields=id,name,attributeValues&filter=attributeValues.attribute.id:eq:o8ilsRi1p8b&paging=false
    # https://links.hispindia.org/timor/api/programIndicators?fields=id,name,attributeValues&filter=attributeValues.attribute.id:eq:LmGZvNosfuS&paging=false
    url_with_filters = f"{program_indicators_api_url}?fields=id,name,attributeValues&filter={'&filter='.join(filters)}"

    #print(f"url_with_filters : {url_with_filters}")

    response_program_indicators = session_get.get( url_with_filters )


    if response_program_indicators.status_code == 200:
        response_data_program_indicators = response_program_indicators.json()
        
        program_indicators_data = response_data_program_indicators.get('programIndicators', [])
        
        if program_indicators_data:
            for program_indicator in program_indicators_data:
                program_indicators_attributeValues = program_indicator.get('attributeValues', [])
                
                if program_indicators_attributeValues:
                    for program_indicators_attributeValue in program_indicators_attributeValues:

                        program_indicator = program_indicator['id']
                        dataElement_coc = program_indicators_attributeValue['value']

                        if program_indicator not in aggregated_de_dict:
                                aggregated_de_dict[program_indicator] = dataElement_coc
                        else:
                            if dataElement_coc not in aggregated_de_dict[program_indicator]:
                                #option_dict[code].append(value)
                                aggregated_de_dict[program_indicator] = dataElement_coc                     
        
        else:
            error_message = f"No aggregated dataElement_coc found"
            print(error_message)

    else:
        print(f"Failed to retrieve program_indicators units. Status code: {response_program_indicators.status_code}")

    return aggregated_de_dict

def get_orgunit_grp_member( orgunit_grp_api_url,session_get, ORG_UNIT_GROUP_ART_CENTERS ):
    
    orgunits = list()
   
    url_with_filters = f"{orgunit_grp_api_url}/{ORG_UNIT_GROUP_ART_CENTERS}.json?fields=id,name,organisationUnits[id,name]&paging=false"

    #print(f"url_with_filters : {url_with_filters}")

    response_orgunit_grp_member = session_get.get( url_with_filters )

    if response_orgunit_grp_member.status_code == 200:
        response_data_orgunit_grp = response_orgunit_grp_member.json()
        
        orgunit_grp_data = response_data_orgunit_grp.get('organisationUnits', [])
        
        if orgunit_grp_data:
            
            for orgunit in orgunit_grp_data:
                
                if orgunit:
                    org_unit = orgunit['id']
                    orgunits.append(org_unit)
                                       
            print(f"orgunit_grp_member size {len(orgunits)}")
            logging.info(f"orgunit_grp_members size {len(orgunits)}")
            orgunit_grp_member_list = ";".join(orgunits)
        else:
            error_message = f" No orgunits found"
            print(error_message)

    else:
        print(f" Failed to retrieve org_unit. Status code: {response_orgunit_grp_member.status_code}")

    '''
    return {
        "list": orgunits,
        "string": ";".join(orgunits)
    }  
    '''  
    return orgunit_grp_member_list


def get_program_indicators_data_values( program_indicators_data_value_url, session_get, program_indicator, ORG_UNIT_GROUP_ART_CENTERS, isoDatePeriods, ART_CENTER ):
    
   
    period_list_daily = "20230514;20230513;20230512;20230511;20230510;20230509;20230508;20230507;20230506;20230505;20230504;20230503;20230502;20230501;20230430;20230429;20230428;20230427;20230426;20230425;20230424;20230423;20230422;20230421;20230420;20230419;20230418;20230417;20230416;20230415;20230414"
    #period_list_2025 = "202501;202502;202503;202504;202505;202506;202507;202508;202509;202510;202511;202512"
    org_list = "op6sM00UM5R;NdWZGvjX3BN;op6sM00UM5R"
    pi_indicators_list = "K8VVrMcSAUD;K81oZQ4b5Vl;QwOHKYNmdN9;Tak313dv0CT;IfECSBYqrqV;eu9RAPEMXhb;BfoLPFMyQzkB;ragjEZ11Bti;FDxVW7nURcD;doyR9jQvv92;GkgzaLmrg5S;MzPenhNCmy2;ck9AtliGzns;KjbIihlYc5D;v6mPHFvH2Ho;npDd2ehR91M"
    
    periods = quote(isoDatePeriods)

    
    artCenter = "sTpP9XtNNIq"
    program_indicator_data_value_url = (
        f"{program_indicators_data_value_url}"
        f"?dimension=ou:{ART_CENTER}"
        f"&dimension=dx:{program_indicator}"
        f"&filter=pe:{periods}"
        f"&displayProperty=NAME&outputIdScheme=UID"
    )
    
    ### for ou GROUP
    '''
    program_indicator_data_value_url = (
        f"{program_indicators_data_value_url}"
        f"?dimension=ou:OU_GROUP-{ORG_UNIT_GROUP_ART_CENTERS}"
        f"&dimension=dx:{program_indicator}"
        f"&filter=pe:{periods}"
        f"&displayProperty=NAME&outputIdScheme=UID"
    )
    '''
    #https://tracker.hivaids.gov.np/save-child-2.27/api/analytics.json?dimension=ou:OU_GROUP-pW6owR4oRKb&dimension=dx:vcFk6C2BZCx&filter=pe:20230514;20230513;20230512;20230511;20230510;20230509;20230508;20230507;20230506;20230505;20230504;20230503;20230502;20230501;20230430;20230429;20230428;20230427;20230426;20230425;20230424;20230423;20230422;20230421;20230420;20230419;20230418;20230417;20230416;20230415;20230414&displayProperty=NAME&outputIdScheme=UID
    
    #program_indicator_data_value_url = f"{program_indicators_data_value_url}?dimension=ou:OU_GROUP-{ORG_UNIT_GROUP_ART_CENTERS}&dimension=dx:{program_indicator}&filter=pe:{isoDatePeriods}&displayProperty=NAME&outputIdScheme=UID"

    #print(program_indicator_data_value_url)
    #print(f"program_indicator_data_value_url : {program_indicator_data_value_url}" )

    
    response_pi_datavalues = session_get.get( program_indicator_data_value_url )
    if response_pi_datavalues.status_code == 200:
        response_pi_data = response_pi_datavalues.json()
        pi_dataValues = response_pi_data.get('rows', [])
        return pi_dataValues 
    else:
        return []

def push_dataValueSet_in_dhis2( dataValueSet_endPoint, session_post, dataValueSet_payload ):
    #print(f"dataValueSet_payload : {json.dumps(dataValueSet_payload)}")
    #logging.info(f"dataValueSet_payload : {json.dumps(dataValueSet_payload)}")

    #session_post = requests.Session()
    #session_post.verify = certifi.where()
    #verify=False,
    response = session_post.post(
        dataValueSet_endPoint,
        data=json.dumps(dataValueSet_payload), verify=False,
        headers={"Content-Type": "application/json"}
    )
    conflictsDetails = ""
    if response.status_code == 200:
        #print(f"DataValue created successfully.  Row No : {row_no} . orgUnit : {orgUnit} . response . {response.status_code}")
        #print(f"DataValue created successfully.  Row No : {row_no} . orgUnit : {orgUnit} . response . {response.json()}")

        #print(f" DataValue created successfully : response . {response.json()} : response . {response.status_code}")

        #conflictsDetails   = response.json().get("response", {}).get("conflicts")
        description   = response.json().get("response", {}).get("description")
        impCount = response.json().get("response", {}).get("importCount").get("imported")
        updateCount = response.json().get("response", {}).get("importCount").get("updated")
        ignoreCount = response.json().get("response", {}).get("importCount").get("ignored")

        #conflictsDetails   = response.json().get("conflicts",[])
        #description   = response.json().get("description", {})
        #print(f"DataValue created successfully description : {description}")
        #impCount = response.json().get("importCount", {}).get("imported")
        #updateCount = response.json().get("importCount", {}).get("updated")
        #ignoreCount = response.json().get("importCount", {}).get("ignored")

        print(f"DataValue created successfully. importCount : {impCount}. updateCount : {updateCount}. ignoreCount : {ignoreCount}. description : {description}")
        logging.info(f"DataValue created successfully. importCount : {impCount}. updateCount : {updateCount}. ignoreCount: {ignoreCount}. description : {description}")
        #logging.info(f"conflictsDetails : {conflictsDetails}")
        #print(f"conflictsDetails : {conflictsDetails}")
        #logging.info(f"DataValue created successfully : {response.text}")
        #print(f"DataValue created successfully : {response.text}")
    else:
        #print(f"Failed to create dataValueSet. Error: {response.text}")
        conflictsDetails   = response.json().get("response", {}).get("conflicts")
        description   = response.json().get("response", {}).get("description")
        impCount = response.json().get("response", {}).get("importCount").get("imported")
        updateCount = response.json().get("response", {}).get("importCount").get("updated")
        ignoreCount = response.json().get("response", {}).get("importCount").get("ignored")
        
        print(f"DataValue created successfully. impCount : {impCount}. updateCount : {updateCount}. ignoreCount : {ignoreCount}. description : {description}")
        logging.info(f"DataValue created successfully. impCount : {impCount}. updateCount : {updateCount}. ignoreCount: {ignoreCount}. description : {description}")
        
        print(f"Failed to create dataValueSet. conflictsDetails: {conflictsDetails}")
        logging.info(f"conflictsDetails : {conflictsDetails}")
        logging.error(f"Failed to dataValueSet events . conflictsDetails : {conflictsDetails} . error details: {response.json()} .Error: {response.text}")


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

def get_between_dates_iso(start_date, end_date):
    """
    start_date, end_date format: YYYY-MM-DD
    returns list of dates in YYYYMMDD format
    """

    # Convert date objects to string
    if isinstance(start_date, date):
        start_date = start_date.strftime("%Y-%m-%d")
    if isinstance(end_date, date):
        end_date = end_date.strftime("%Y-%m-%d")

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    arr = []
    current = start

    while current <= end:
        arr.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)

    print(f"iso_periods_date size {len(arr)}")
    logging.info(f"iso_periods_date size {len(arr)}")
    date_iso_periods_list = ";".join(arr)

    return date_iso_periods_list


#######################################
def get_relationship_tei_list(session_post):
    
    '''
    print(type(session_get))
    print(type(session_get.get))
    test = session_get.get("https://www.google.com")
    print(test.status_code)
    print("session_get:", session_get)
    print("type(session_get):", type(session_get))
    print("dir(session_get):", dir(session_get))
    print("session_get.get:", session_get.get)
    print("type(session_get.get):", type(session_get.get))
    '''



    sql_view_url = f"{DHIS2_API_URL}/sqlViews/AV3lm7tXQ3x/data.json?paging=false"
    print(f"sql_view_url : {sql_view_url}")


    response_sql_view = session_post.get(sql_view_url)
    #print(f"response_sql_view : {response_sql_view}")
    if response_sql_view.status_code == 200:
        #print(f"response_sql_view : {response_sql_view.status_code}")
        response_sql_view_data = response_sql_view.json()
        #print(f"response_sql_view_data : {response_sql_view_data}")

        tempListGrid   = response_sql_view.json().get('listGrid', {})
        #print(f"tempListGrid : {tempListGrid}")
        #print(f"title : {tempListGrid.get('title')}")
        tempRows = tempListGrid.get('rows',[])

    else:
        print(f"Failed to retrieve sqlview data. Status code: {response_sql_view.status_code}")

    return tempRows


def get_event_details_desc(session_get, teiId,orgUnitId, programId, prgStageId, row):
    
    #https://ln4.hispindia.org/timor_dev/api/events.json?orgUnit=Fn51zf6ifbm&ouMode=SELECTED&program=RUqNUsv6WBp&status=ACTIVE&skipPaging=true&filter=alV2b3AtVLw:eq:897
    
    #../api/events.json?trackedEntityInstance=DJ9Ktm7y0kE&program=B8MqLS47pW6&programStage=hHdZDPXykTP&orgUnit=D8NyqT0sKpI&order=eventDate:DESC&skipPaging=true

    #event_search_url = f"{event_push_endpoint}?orgUnit={orgUnitID}&ouMode=SELECTED&program={programID}&status=ACTIVE&skipPaging=true&filter={event_search_dataElement_uid}:eq:{BenCallID}"
    event_get_url = f"{DHIS2_API_URL}/events.json?trackedEntityInstance={teiId}&program={programId}&programStage={prgStageId}&orgUnit={orgUnitId}&Status=COMPLETED&order=eventDate:DESC&skipPaging=true"

    #print(event_search_url)
    #print(f" event_search_url : {event_get_url}" )
    #response = requests.get(event_search_url, auth=HTTPBasicAuth(dhis2_username, dhis2_password))
    response = session_get.get(event_get_url)
    
    if response.status_code == 200:
        event_response_data = response.json()
       
        # Get events list safely
        events = event_response_data.get("events", [])
        if not events:
            print(f"Events Not found for Row No : {row}. in Child Profile Program for TEI. { teiId }")
            log_info(f"Events Not found for Row No : {row}. in Child Profile Program for TEI. { teiId }")
        else:
            #event_response_data = response.json()
            #events = event_response_data["events"]   # because your JSON has "events" key
            latest_event = events[0] if events else None
            #print(response)
            #print(event_response_data)
            #latest_event = event_response_data[0]
            #print(f"event_response_data trackedEntityInstance : {event_response_data.get('trackedEntityInstance')}" )
            dataValues = event_response_data.get('dataValues',[])
            #events = event_response_data.get('response', {})
            #print(f" dataValues : {dataValues}" )
            #print(f" latest_event : {latest_event}" )
            return latest_event 
    else:
        return []


def get_event_details_asc(session_get, teiId,orgUnitId, programId, prgStageId, row):
    
    #https://ln4.hispindia.org/timor_dev/api/events.json?orgUnit=Fn51zf6ifbm&ouMode=SELECTED&program=RUqNUsv6WBp&status=ACTIVE&skipPaging=true&filter=alV2b3AtVLw:eq:897
    
    #../api/events.json?trackedEntityInstance=liDk8H9TiHk&program=ifSz8dMpEez&programStage=ONmKYoLQW95&orgUnit=D8NyqT0sKpI&order=eventDate:ASC&skipPaging=true

    #event_search_url = f"{event_push_endpoint}?orgUnit={orgUnitID}&ouMode=SELECTED&program={programID}&status=ACTIVE&skipPaging=true&filter={event_search_dataElement_uid}:eq:{BenCallID}"
    event_get_url = f"{DHIS2_API_URL}/events.json?trackedEntityInstance={teiId}&program={programId}&programStage={prgStageId}&orgUnit={orgUnitId}&order=eventDate:ASC&skipPaging=true"

    #print(event_search_url)
    #print(f" event_search_url : {event_get_url}" )
    #response = requests.get(event_search_url, auth=HTTPBasicAuth(dhis2_username, dhis2_password))
    response = session_get.get(event_get_url)

    
    if response.status_code == 200:
        event_response_data = response.json()

        #events = event_response_data["events"]   # because your JSON has "events" key
        events = event_response_data.get("events", [])
        if not events:
            print(f"Events Not found for Row No : {row}. in Child Profile Program for TEI. { teiId }")
            log_info(f"Events Not found for Row No : {row}. in Child Profile Program for TEI. { teiId }")
        else:
        
            first_event = events[0] if events else None

            #print(response)
            #print(event_response_data)
            #first_event = event_response_data.get[0]
            #print(f"event_response_data trackedEntityInstance : {event_response_data.get('trackedEntityInstance')}" )
            dataValues = event_response_data.get('dataValues',[])
            #events = event_response_data.get('response', {})
            #print(f" dataValues : {dataValues}" )
            return first_event 
    else:
        return []


def update_eventDataValue_in_dhis2(session, updateEventDataValue, eventUID, sl_no):

    #print( f" updateEventDataValue . { updateEventDataValue }" )
    event_update_url = f"{DHIS2_API_URL}/events/{eventUID}"
    #print( f"event_update_url . { event_update_url }" )
    response = session.put(event_update_url, json=updateEventDataValue, headers={"Content-Type": "application/json"})
    
    if response.status_code == 200:
        conflictsDetails   = response.json().get("response", {}).get("conflicts")
        #description   = response.json().get("response", {}).get("description")
        impCount = response.json().get("response", {}).get("importCount").get("imported")
        updateCount = response.json().get("response", {}).get("importCount").get("updated")
        ignoreCount = response.json().get("response", {}).get("importCount").get("ignored")
        #event_uid = response.json().get("response", {}).get("importSummaries", [])[0].get("reference")
        #event_ids = [item.get("event") for item in response.json().get("response", {}).get("importSummaries", [])[0].get("importCount",{}).get("imported")]
        #print(f"Events created successfully. Event IDs: {response.json()}")
        #event_count = response.json().get("response", {}).get("importSummaries", [])[0].get("importCount",{}).get("imported")
        print(f"Events updated successfully. Row No : {sl_no}. updated event : {eventUID}. impCount : {impCount} .updateCount : {updateCount} .ignoreCount : {ignoreCount}")
        logging.info(f"Events updated successfully. Row No : {sl_no}. updated event : {eventUID}. impCount : {impCount} .updateCount : {updateCount} .ignoreCount : {ignoreCount}")
        #logging.info(f"Event created successfully . BenVisitID : {BenVisitID} . BeneficiaryRegID : {BeneficiaryRegID}. Event count: {event_count}. Event uid: {event_uid}" )
        #logging.info("MySQL connection closed")

    else:
        print(f"Failed to update events. Error: {response.text}")
        logging.error(f"Failed to update events. Row No : {sl_no} .conflictsDetails : {conflictsDetails} .Status code: {response.status_code} .error details: {response.json()} .Error: {response.text}")


def get_dhis2_orgunit_uid_by_block_district(session_post,block, district,facility):
    params = {
        "filter": f"displayName:like:{facility}",
        "fields": "id,name,parent[id,name]",
    }
    #response = requests.get(f"{DHIS2_API_URL}/organisationUnits", params=params, auth=DHIS2_AUTH)
    response = session_post.get(f"{DHIS2_API_URL}/organisationUnits", params=params )

    if response.status_code == 200:
        orgunits = response.json()["organisationUnits"]
        for orgunit in orgunits:
            parent_name = orgunit["parent"]["name"]
            if parent_name.lower() == block.lower():
                return orgunit["id"]
    return None









def get_dhis2_orgunit_uid_by_nin(session_post,dhis2_get_url,facility_nin):
    # api_url = "http://172.105.253.84:8665/odk_nipi/api/organisationUnits.json"
    params = {
        'fields': 'id,name,code',
        #'level': 5,
        'filter': f'code:eq:{facility_nin}'
    }
    #print(f"dhis2_get_url : {dhis2_get_url}")
    try:
        #response = requests.get(f"{DHIS2_API_URL}/organisationUnits", params=params, auth=DHIS2_AUTH)
        #http://49.50.97.167:8665/odk_nipi/api/organisationUnits.json?fields=id,name,code,level,parent[id,name]&filter=code:eq:1131532820&level=5&paging=false
        #http://49.50.97.167:8665/odk_nipi/api/organisationUnits.json?fields=id,name,code,level&filter=name:eq:Ratlam&level=4&paging=false
        
        #print("dhis2_get_url:", {dhis2_get_url}/"organisationUnits", params=params )
        
        response = session_post.get(f"{dhis2_get_url}/organisationUnits", params=params)

        if response.status_code == 200:
            orgunits = response.json().get('organisationUnits', [])

            if orgunits:
                return orgunits[0]['id']  # Assuming only one orgunit is expected in the response
            else:
                print(f"No orgunit found for code: {facility_nin}")
                return None
        else:
            print(f"Error: Unable to fetch data. Status Code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None
    
def data_value_exists_in_dhis2(session_post,dhis2_get_url,event_id,orgunit_uid):
    try:
        #http://172.105.253.84:8665/odk_nipi/api/trackedEntityInstances.json?ou=cXOfSxAY71d&program=eXm5MqSJmkc&filter=vJ5V1IQXZjP:EQ:784347329
        # response = requests.get(f"{DHIS2_API_URL}/events?dataElement=zkhndIoBYH7&filter=zkhndIoBYH7:like:{event_id}", auth=DHIS2_AUTH)
        
        #tei_search_url = f"{enrollment_endpoint}?ou={orgUnitID}&ouMode=SELECTED&program=vyQPQ07JB9M&filter=HKw3ToP2354:eq:{beneficiary_mapping_reg_id}"
        #response = requests.get(f"{DHIS2_API_URL}/trackedEntityInstances?ou={orgunit_uid}&ouMode=SELECTED&program=Tt9ILP7v4Fd", params={"filter": f"vJ5V1IQXZjP:EQ:{event_id}"}, auth=DHIS2_AUTH)
        #DESCENDANTS
        response = session_post.get(f"{dhis2_get_url}/trackedEntityInstances?ou={orgunit_uid}&ouMode=SELECTED&program=Tt9ILP7v4Fd", params={"filter": f"vJ5V1IQXZjP:EQ:{event_id}"})
        

        if response.status_code == 200:
            events = response.json()["trackedEntityInstances"]
            #print("length events--",len(events))
            #print(f"Event with ID {event_id} not exists in DHIS2. Adding.")
            #log_info(f"Event with ID {event_id} not exists in DHIS2. Adding.")
            if len(events) > 0:
                #print("matching uuid--", response.url)
                return True
            return False
    except Exception as e:
        log_error("An error occurred while checking data value in DHIS2.", e)
        return False
    

def sendEmail():
    # creates SMTP session
    #s = smtplib.SMTP('smtp.gmail.com', 587)
    # start TLS for security
    #s.starttls()
    # Authentication
    #s.login("ipamis@hispindia.org", "IPAMIS@12345")
    # message to be sent
    
    # message to be sent
    #message = "Message_you_need_to_send"

    # sending the mail
    #s.sendmail("ipamis@hispindia.org", "mithilesh.thakur@hispindia.org",message)
    #print(f"Email send to mithilesh.thakur@hispindia.org")
    # terminating the session
    #s.quit()
    


    #fromaddr = "dss.nipi@hispindia.org"
    fromaddr = FROM_EMAIL_ADDR
    # list of email_id to send the mail
    #li = ["mithilesh.thakur@hispindia.org", "saurabh.leekha@hispindia.org","dpatankar@nipi-cure.org","mohinder.singh@hispindia.org"]
    li = ["mithilesh.thakur@hispindia.org","sumit.tripathi@hispindia.org","RKonda@fhi360.org"]
    #li = ["mithilesh.thakur@hispindia.org"]

    for toaddr in li:

        #toaddr = "mithilesh.thakur@hispindia.org"
        
        # instance of MIMEMultipart 
        msg = MIMEMultipart() 
        
        # storing the senders email address   
        msg['From'] = fromaddr 
        
        # storing the receivers email address  
        msg['To'] = toaddr 
        
        # storing the subject  
        msg['Subject'] = "Auto Sync ART data from hivtracker to ihmis log file"
        
        # string to store the body of the mail 
        #body = "Python Script test of the Mail"

        today_date = datetime.now().strftime("%Y-%m-%d")
        #updated_odk_api_url = f"{ODK_API_URL}?$filter=__system/submissionDate ge {today_date}"
        updated_odk_api_url = f"{today_date}"

        body = f"Auto Sync ART data from hivtracker to ihmis"
        
        # attach the body with the msg instance 
        msg.attach(MIMEText(body, 'plain')) 
        
        
        # open the file to be sent  

        LOG_DIR = "logs"
        PATTERN = "*_dataValueSet_post.log"

        # Find latest matching log file
        log_files = glob.glob(os.path.join(LOG_DIR, PATTERN))
        if not log_files:
            raise FileNotFoundError("No log files found")

        latest_log = max(log_files, key=os.path.getmtime)

        filename = LOG_FILE
        #attachment = open(filename, "rb") 
        attachment = open(latest_log, "rb") 
        
        # instance of MIMEBase and named as p 
        p = MIMEBase('application', 'octet-stream') 
        
        # To change the payload into encoded form 
        p.set_payload((attachment).read()) 
        
        # encode into base64 
        encoders.encode_base64(p) 
        
        p.add_header('Content-Disposition', "attachment; filename= %s" % filename) 
        
        # attach the instance 'p' to instance 'msg' 
        msg.attach(p) 
        try:
            # creates SMTP session 
            s = smtplib.SMTP('smtp.gmail.com', 587) 
            
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
            log_info(f"mail send to: {toaddr}")
            # terminating the session 
            s.quit()
        except Exception as exception:
            print("Error: %s!\n\n" % exception)
