import os
import time
import json
import datetime
import requests
import processor

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
PRODUCT_ID = os.environ.get("PRODUCT_ID", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()


def rest_headers():
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }


def download_file(bucket, file_path):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY})
    resp.raise_for_status()
    return resp.content


def upload_result(bucket, file_path, content):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.post(
        url,
        data=content,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
    return file_path


def send_notification(job, success):
    customer_id = job.get("customer_id", "")
    if success:
        title = "Processing complete"
        body = "Your upload has been processed successfully."
        ntype = "success"
    else:
        title = "Processing failed"
        body = "There was an error processing your upload."
        ntype = "error"
    payload = {
        "product_id": PRODUCT_ID,
        "customer_id": customer_id,
        "title": title,
        "body": body,
        "type": ntype,
        "read": False,
    }
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/notifications",
            json=payload,
            headers=rest_headers(),
            timeout=30,
        )
    except Exception:
        pass


def update_job(job_id, body):
    url = f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{job_id}"
    resp = requests.patch(url, json=body, headers=rest_headers(), timeout=30)
    resp.raise_for_status()


def process_job(job):
    job_id = job.get("id")
    customer_id = job.get("customer_id", "")
    file_path = job.get("input_file_path", "")
    if not file_path:
        raise ValueError("input_file_path is missing on job")

    file_bytes = download_file("uploads", file_path)
    processed = processor.process_file(file_bytes)

    records = []
    for rec in processed:
        details = dict(rec.get("details") or {})
        records.append(
            {
                "product_id": PRODUCT_ID,
                "customer_id": customer_id,
                "title": rec.get("title") or "Unnamed Product",
                "status": rec.get("status") or "Missing:critical",
                "details": details,
                "source_file_path": file_path,
                "due_date": rec.get("due_date"),
            }
        )

    result_payload = json.dumps({"records": records}, default=str).encode("utf-8")
    object_name = f"{job_id}_{int(time.time())}.json"
    uploaded_path = upload_result("results", object_name, result_payload)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    summary = f"Processed {len(records)} record(s)."
    update_job(
        job_id,
        {
            "status": "completed",
            "output_file_path": uploaded_path,
            "result_summary": summary,
            "completed_at": now,
        },
    )
    send_notification(job, True)
    print(f"Job {job_id} completed: {summary}")


def poll():
    while True:
        try:
            url = (
                f"{SUPABASE_URL}/rest/v1/jobs"
                f"?status=eq.pending&job_type=eq.process_upload&product_id=eq.{PRODUCT_ID}&select=*"
            )
            resp = requests.get(url, headers=rest_headers(), timeout=30)
            resp.raise_for_status()
            jobs = resp.json()
            if not isinstance(jobs, list):
                jobs = []

            for job in jobs:
                try:
                    process_job(job)
                except Exception as exc:
                    print(f"Job {job.get('id')} failed: {exc}")
                    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    try:
                        update_job(
                            job.get("id"),
                            {
                                "status": "failed",
                                "result_summary": f"Error: {exc}",
                                "completed_at": now,
                            },
                        )
                    except Exception as update_exc:
                        print(f"Failed to update job {job.get('id')}: {update_exc}")
                    send_notification(job, False)
        except Exception as exc:
            print(f"Poll error: {exc}")

        time.sleep(60)


if __name__ == "__main__":
    print("Poller started")
    poll()
