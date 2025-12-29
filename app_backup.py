#pip install flask requests python-dotenv
#pip install flask-cors

from flask import Flask, jsonify, Response, abort, request
from flask_cors import CORS
import json
from main import main_with_logger, sendEmail

from logger import configure_logging, log_info, log_queue
import logging


# ADD THIS PART (UI streaming) for print in HTML Page in response
#Add a global log queue
# ADD HERE (top-level)
import queue
log_queue = queue.Queue()
#Add a Queue logging handler
#import logging


import os
from datetime import datetime
import threading
app = Flask(__name__)
CORS(app, supports_credentials=True)
'''
## For production:
CORS(
    app,
    origins=["https://your-dhis2.org"],
    supports_credentials=True
)
'''
# --- GET endpoint ---
LOG_DIR = "logs"
JSON_PATH = "pi-sql-mapping.json"


def safe_runner():
    configure_logging()
    try:
        log_info("Job started")
        main_with_logger()
        log_info("JOB_COMPLETED")
        sendEmail()
    except Exception as e:
        log_info(f"Job failed: {e}")
        log_info("JOB_COMPLETED")

@app.route("/run")
def run():
    threading.Thread(target=safe_runner, daemon=True).start()
    return {"status": "started"}


#from flask import Response

'''
@app.route("/logs")
def stream_logs():
    def generate():
        while True:
            msg = log_queue.get()  # waits for next log
            yield f"data: {msg}\n\n"

    return Response(generate(), mimetype="text/event-stream")
'''

from flask import Response, stream_with_context

@app.route("/logs")
def stream_logs():
    print("SSE client connected")

    def generate():
        try:
            # initial comment keeps connection open
            yield ": connected\n\n"

            while True:
                msg = log_queue.get()
                yield f"data: {msg}\n\n"
        except GeneratorExit:
            print("SSE client disconnected")

    return Response(
        stream_with_context(generate()),
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/test-sse")
def test_sse():
    def generate():
        import time
        for i in range(5):
            yield f"data: TEST MESSAGE {i}\n\n"
            time.sleep(1)

    return Response(generate(), mimetype="text/event-stream")


'''
@app.get("/run")
def run_main():
    thread = threading.Thread(target=main_with_logger)
    thread.daemon = True
    thread.start()
    return "run", 200

def extract_timestamp(filename: str):
    """
    Convert filename 'log_yyyy-mm-dd_hh-mm-ss.log' -> datetime object
    """
    try:
        # Example: log_2025-02-11_10-11-21.log
        base = filename.replace("log_", "").replace(".log", "")

        date_part, time_part = base.split("_")
        time_part = time_part.replace("-", ":")

        return datetime.fromisoformat(f"{date_part} {time_part}")
    except:
        return None


@app.get("/history")
def get_history():
    try:
        # Read directory
        files = os.listdir(LOG_DIR)

        # Collect valid log files
        log_files = []
        for f in files:
            ts = extract_timestamp(f)

            if ts:
                log_files.append((f, ts))

        if not log_files:
            return jsonify({"message": "No log files found"}), 404

        # Sort newest first
        log_files.sort(key=lambda x: x[1], reverse=True)

        results = []

        for filename, ts in log_files:
            file_path = os.path.join(LOG_DIR, filename)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except:
                content = "(Could not read file)"

            results.append({
                "createdAt": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "content": content
            })

        return jsonify(results)

    except Exception as e:
        print("Error:", e)
        return jsonify({"message": "Internal server error"}), 500


@app.get("/process")
def get_process():
    try:
        # Read directory
        files = os.listdir(LOG_DIR)
        # Keep only valid log files
        log_files = []
        for f in files:
            ts = extract_timestamp(f)

            if ts:
                log_files.append((f, ts))

        if not log_files:
            return jsonify({"message": "No log files found"}), 404

        # Sort newest first
        log_files.sort(key=lambda x: x[1], reverse=True)
        newest_file = log_files[0][0]
        timestamp = log_files[0][1]

        file_path = os.path.join(LOG_DIR, newest_file)

        # Read and return content
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content, mimetype="text/plain")
        return jsonify({
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "message": content
        })

    except Exception as e:
        print("Error:", e)
        return jsonify({"message": "Internal server error"}), 500


def load_json():
    if not os.path.exists(JSON_PATH):
        return {}
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data):
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# -------------------- GET ALL --------------------
@app.get("/pi-queries")
def get_all_queries():
    data = load_json()
    # Trả về dạng: [{id, value}]
    result = [
        {"id": key.strip("[]"), "value": value}
        for key, value in data.items()
    ]
    return jsonify(data)


# -------------------- GET ONE --------------------
@app.get("/pi-queries/<id>")
def get_query(id):
    data = load_json()
    key = f"{id}"

    if key not in data:
        abort(404, f"Key '{id}' not found")

    return jsonify({
        "id": id,
        "value": data[key]
    })


# -------------------- UPDATE (TEXT) --------------------
@app.post("/")
def update_query():
    data = load_json()

    body = request.get_json()

    if not body or "id" not in body or "value" not in body:
        abort(
            400, "Body must be JSON: {\"id\": \"your_id\", \"value\": \"text\"}")

    key = str(body["id"])
    new_value = str(body["value"])  # always save as string

    if key not in data:
        abort(404, f"Key '{key}' not found")

    data[key] = new_value
    save_json(data)

    return jsonify({
        "message": "Updated successfully",
        "id": key,
        "value": new_value
    })

'''
if __name__ == "__main__":
    #app.run(host="0.0.0.0", port=8000, debug=True)
    #configure_logging()
    app.run(debug=True)
