from flask import Flask, jsonify
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor
from main_with_app import run_job
from utils import log_queue, configure_logging_for_app

import os
import glob
from flask import send_file, jsonify

import time

LOG_DIR = "logs"
LOG_PATTERN = "*_dataValueSet_post.log"

LOG_DIR = "logs"
LOG_PATTERN = "*_dataValueSet_post.log"
LOG_RETENTION_DAYS = 7   # change as needed

app = Flask(__name__)
CORS(app)
configure_logging_for_app()

import logging
from datetime import datetime
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.setLevel(logging.WARNING)   # or ERROR
werkzeug_logger.propagate = False           # 🔴 THIS IS THE KEY


executor = ThreadPoolExecutor(max_workers=1)

job_status = {
    "running": False,
    "lastRunStart": None,
    "message": "",
    "lastRunEnd": None,
}



@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "UP",
        "service": "IHMIS Aggregation Service"
    })


@app.route("/run", methods=["POST"])
def run():
    if job_status["running"]:
        return jsonify({
            "status": "RUNNING",
            "message": "Job already in progress"
        }), 409

    # 🔹 Create new log file per run
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(LOG_DIR, f"{timestamp}_dataValueSet_post.log")

    # 🔹 Reconfigure logging for this run
    configure_logging_for_app(log_file)

    # 🔹 Clear old UI logs
    while not log_queue.empty():
        log_queue.get()

    job_status["running"] = True
    job_status["message"] = "Job started"
    job_status["lastRunStart"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def background_job():
        success, msg = run_job()

        cleanup_old_logs()
        cleanup_old_logs_keep_last_n(10)

        job_status["running"] = False
        job_status["message"] = msg
        job_status["lastRunEnd"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    executor.submit(background_job)

    return jsonify({
        "status": "STARTED",
        "message": "Aggregation job started"
    })

'''
@app.route("/run", methods=["POST"])
def run():
    if job_status["running"]:
        return jsonify({
            "status": "RUNNING",
            "message": "Job already in progress"
        }), 409

    job_status["running"] = True
    job_status["message"] = "Job started"
    job_status["lastRunStart"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def background_job():
        success, msg = run_job()
        deleted_logs = cleanup_old_logs()

         #  1. Delete logs older than X days
        deleted_by_age = cleanup_old_logs()

        #  2. Keep only last 10 logs
        cleanup_old_logs_keep_last_n(10)

        job_status["running"] = False
        job_status["message"] = msg
        job_status["lastRunEnd"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if deleted_logs:
            print("Deleted old logs:", deleted_logs)

        #while not log_queue.empty():
            #log_queue.get()

    executor.submit(background_job)

    return jsonify({
        "status": "STARTED",
        "message": "Aggregation job started"
    })
'''

@app.route("/status", methods=["GET"])
def status():
    return jsonify(job_status)


@app.route("/logs", methods=["GET"])
def get_logs():
    logs = []
    while not log_queue.empty():
        logs.append(log_queue.get())
    return jsonify(logs)


@app.route("/test-log", methods=["GET"])
def test_log():
    import logging
    logging.info("Test log from Flask route")
    return jsonify({"ok": True})


#Download latest log file (Flask)
@app.route("/logs/latest", methods=["GET"])
def download_latest_log():
    log_files = glob.glob(os.path.join(LOG_DIR, LOG_PATTERN))

    if not log_files:
        return jsonify({
            "error": "No log files found"
        }), 404

    latest_log = max(log_files, key=os.path.getmtime)

    return send_file(
        latest_log,
        as_attachment=True,
        download_name=os.path.basename(latest_log),
        mimetype="text/plain"
    )


# log history
@app.route("/logs/<filename>", methods=["GET"])
def download_log(filename):
    filepath = os.path.join(LOG_DIR, filename)

    if not os.path.isfile(filepath):
        return jsonify({"error": "Log file not found"}), 404

    return send_file(
        filepath,
        as_attachment=True,
        mimetype="text/plain"
    )



@app.route("/logs/list", methods=["GET"])
def list_logs():
    files = glob.glob(os.path.join(LOG_DIR, LOG_PATTERN))
    files.sort(key=os.path.getmtime, reverse=True)

    #return jsonify([os.path.basename(f) for f in files]) return only filenames from backend
    return jsonify([
        {
            "name": os.path.basename(f),
            "modified": os.path.getmtime(f)
        } for f in files
    ])



def cleanup_old_logs():
    now = time.time()
    cutoff = now - (LOG_RETENTION_DAYS * 24 * 60 * 60)

    deleted = []

    for file in glob.glob(os.path.join(LOG_DIR, LOG_PATTERN)):
        if os.path.getmtime(file) < cutoff:
            os.remove(file)
            deleted.append(os.path.basename(file))

    return deleted


def cleanup_old_logs_keep_last_n(keep_last=10):
    files = glob.glob(os.path.join(LOG_DIR, LOG_PATTERN))
    files.sort(key=os.path.getmtime, reverse=True)

    for file in files[keep_last:]:
        os.remove(file)


@app.route("/logs/cleanup", methods=["POST"])
def cleanup_logs_api():
    deleted = cleanup_old_logs()
    return jsonify({
        "deleted": deleted,
        "count": len(deleted)
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
