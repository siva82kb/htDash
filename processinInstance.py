import os
import logging
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# Configuration 
BUCKET_NAME = "homerclouds"
local_base = "./META-DATA"
# local_base = "/home/admin/dashboard/META-DATA"

PLUTO = ["WFE", "WURD", "FPS", "HOC", "FME1", "FME2"]
MARS = ["ML", "AP", "ML-AP"]
LOGINPLACE = ["Ludhiana", "Manipal", "Ranipet"]


# boto3 client
s3 = boto3.client("s3")

# ---------------- Logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)




def process_user(user_id: str, place: str, devices: List[str]) -> None:
    """Process one user's devices — writes extdata.csv and Dates/ CSVs locally."""
    for device in devices:
        device_dir = "Pluto" if device == "PLUTO" else "Mars"
        config_local = os.path.join(local_base, place, user_id, device_dir, "configdata.csv")
        session_local = os.path.join(local_base, place, user_id, device_dir, "sessions", "sessions.csv")
        extdata_file = os.path.join(local_base, place, user_id, device_dir, "sessions", "extdata.csv")
        date_folder = os.path.join(local_base, place, user_id, device_dir, "Dates")

        if not os.path.exists(config_local) or not os.path.exists(session_local):
            logger.info(f"Skipping processing for {place}/{user_id}/{device_dir} because required files missing.")
            continue

        try:
            config_df = pd.read_csv(config_local)
            if config_df.empty:
                logger.info(f"Config file empty for {place}/{user_id}/{device_dir}. Skipping.")
                continue

            # Mechanism key differs based on device type
            mechanism_key = "Mechanism" if device == "PLUTO" else "Movement"

            # First pass: compute session durations aggregated per Date and SessionNumber
            session_durations = compute_session_durations(session_local, mechanism_key)

            # Second pass: process chunks, write extdata and per-date files
            process_sessions_and_write(session_local, date_folder, extdata_file, mechanism_key, session_durations)

        except Exception as e:
            logger.exception(f"Failed processing for user {user_id} / device {device}: {e}")

def get_user_devices(user_id: str, place: str) -> List[str]:
    """
    Quick check for device prefixes under a user. Returns list containing "PLUTO" and/or "MARS".
    """
    devices = []
    prefixes = {
        "PLUTO": f"{place}/{user_id}/Pluto/",
        "MARS": f"{place}/{user_id}/Mars/"
    }
    for dev, prefix in prefixes.items():
        try:
            resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, MaxKeys=1)
            if resp.get("Contents"):
                devices.append(dev)
        except Exception as e:
            logger.warning(f"Error checking {dev} for {user_id} at {place}: {e}")
    return devices

def download_required_files(place: str, user: str, device: str) -> bool:
    """
    Ensure configdata.csv and sessions/sessions.csv are downloaded locally if newer on S3.
    Returns True if any file was downloaded/updated, False otherwise.
    """
    device_dir = "Pluto" if device == "PLUTO" else "Mars"
    prefix = f"{place}/{user}/{device_dir}/"
    files = [f"{prefix}configdata.csv", f"{prefix}sessions/sessions.csv"]
    updated = False

    for key in files:
        local_path = os.path.join(local_base, key)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        # Head object to get S3 last modified
        try:
            s3_obj = s3.head_object(Bucket=BUCKET_NAME, Key=key)
            s3_lastmodified = s3_obj["LastModified"].timestamp()  # float seconds since epoch (UTC)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                logger.info(f"Skipping {key}: Not found in S3")
                continue
            else:
                logger.exception(f"Error in head_object for {key}")
                continue

        # If local exists and is up-to-date, skip
        if os.path.exists(local_path):
            local_mtime = os.path.getmtime(local_path)  # seconds since epoch (local)
            # Compare numeric timestamps (both seconds since epoch), more robust across tz
            if local_mtime >= s3_lastmodified:
                # Local file is already up-to-date
                continue

        # Download atomically to temp then replace
        tmp_path = local_path + ".tmp"
        try:
            logger.info(f"Downloading {key} -> {local_path}")
            s3.download_file(BUCKET_NAME, key, tmp_path)
            os.replace(tmp_path, local_path)
            updated = True
        except Exception as e:
            logger.exception(f"Error downloading {key}: {e}")
            # cleanup tmp if exists
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    return updated

# ------------------- Listing users with boto3 -------------------
def list_user_ids(place: str) -> List[str]:
    """
    List the top-level user IDs under a place. Uses Delimiter='/' to get CommonPrefixes.
    """
    prefix = f"{place}/"
    continuation_token = None
    user_ids = []
    try:
        while True:
            if continuation_token:
                resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, Delimiter='/', ContinuationToken=continuation_token)
            else:
                resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, Delimiter='/')
            for cp in resp.get("CommonPrefixes", []):
                # CommonPrefix like 'Ludhiana/USERID/'
                p = cp.get("Prefix", "")
                parts = p.split("/")
                if len(parts) >= 2 and parts[1]:
                    user_ids.append(parts[1])
            if resp.get("IsTruncated"):
                continuation_token = resp.get("NextContinuationToken")
            else:
                break
    except Exception as e:
        logger.exception(f"Failed to list user ids for place {place}: {e}")
    return user_ids

# ------------------- Processing (two-pass chunked) -------------------

def compute_session_durations(session_local: str, mechanism_key: str) -> Dict[tuple, float]:
    """
    First pass: iterate chunks and compute total GameDuration (minutes) per (Date, SessionNumber).
    Return dict keyed by (date_str_dd-mm-YYYY, sessionnumber) -> total_minutes
    """
    session_durations = {}
    if not os.path.exists(session_local):
        return session_durations

    try:
        for chunk in pd.read_csv(session_local, skiprows= 3 if mechanism_key == "Mechanism" else 3, chunksize=5000, usecols=lambda c: True, dtype=str):
            # Ensure columns exist safely, parse DateTime and MoveTime
            if "DateTime" not in chunk.columns or "MoveTime" not in chunk.columns or "SessionNumber" not in chunk.columns:
                continue
            # parse DateTime and MoveTime robustly
            chunk["DateTime"] = pd.to_datetime(chunk["DateTime"], errors="coerce")
            chunk = chunk.dropna(subset=["DateTime"])
            # MoveTime numeric
            chunk["MoveTime"] = pd.to_numeric(chunk["MoveTime"], errors="coerce").fillna(0.0)
            # GameDuration in minutes
            chunk["GameDuration"] = (chunk["MoveTime"] / 60.0).round(4)
            chunk["Date"] = chunk["DateTime"].dt.strftime("%d-%m-%Y")

            grouped = chunk.groupby(["Date", "SessionNumber"], as_index=False)["GameDuration"].sum()
            for _, r in grouped.iterrows():
                key = (r["Date"], str(r["SessionNumber"]))
                session_durations[key] = session_durations.get(key, 0.0) + float(r["GameDuration"])
    except Exception as e:
        logger.exception(f"Error in compute_session_durations for {session_local}: {e}")

    return session_durations

def process_sessions_and_write(session_local: str, date_folder: str, extdata_file: str, mechanism_key: str,
                               session_durations: Dict[tuple, float]) -> None:
    """
    Second pass: iterate chunks again, write extdata.csv and per-date grouped CSVs.
    """
    if not os.path.exists(session_local):
        return

    os.makedirs(os.path.dirname(extdata_file), exist_ok=True)
    os.makedirs(date_folder, exist_ok=True)

    # Collect all extdata and date data first, then write once
    ext_data_frames = []
    date_data_dict = {}  # {date: list_of_dataframes}

    try:
        for chunk in pd.read_csv(session_local, skiprows= 3 if mechanism_key == "Mechanism" else 3, chunksize=5000, dtype=str):
            if "DateTime" not in chunk.columns:
                continue
            chunk["DateTime"] = pd.to_datetime(chunk["DateTime"], errors="coerce")
            chunk = chunk.dropna(subset=["DateTime"])
            # Columns used: DateTime, SessionNumber, GameName, MoveTime, (Mechanism or Movement)
            # Ensure presence
            if "SessionNumber" not in chunk.columns or "GameName" not in chunk.columns or "MoveTime" not in chunk.columns:
                continue
            mech_present = mechanism_key in chunk.columns
            if not mech_present:
                chunk[mechanism_key] = ""  # fill missing mechanism column

            # Numeric conversions
            chunk["MoveTime"] = pd.to_numeric(chunk["MoveTime"], errors="coerce").fillna(0.0)
            chunk["GameDuration"] = (chunk["MoveTime"] / 60.0).round(4)
            chunk["Date"] = chunk["DateTime"].dt.strftime("%d-%m-%Y")
            # Format DateTime text for extdata per your original: dd-mm-YYYY HH:MM:SS
            chunk["DateTime_str"] = chunk["DateTime"].dt.strftime("%d-%m-%Y %H:%M:%S")

            # Build extdata rows: DateTime, SessionNumber, SessionDuration, GameName, GameDuration, Mechanism, MoveTime
            ext_rows = []
            for _, row in chunk.iterrows():
                date_str = row["Date"]
                sess_num = str(row["SessionNumber"])
                session_duration = session_durations.get((date_str, sess_num), 0.0)
                ext_rows.append({
                    "DateTime": row["DateTime_str"],
                    "SessionNumber": sess_num,
                    "SessionDuration": round(float(session_duration), 4),
                    "GameName": row.get("GameName", ""),
                    "GameDuration": round(float(row.get("GameDuration", 0.0)), 4),
                    mechanism_key: row.get(mechanism_key, ""),
                    "MoveTime": float(row.get("MoveTime", 0.0))
                })

            # Collect extdata
            ext_df = pd.DataFrame(ext_rows)
            if not ext_df.empty:
                ext_data_frames.append(ext_df)

            # Per-date grouped summaries: group by Date, SessionNumber, mechanism_key, GameName and sum GameDuration
            grouped = chunk.groupby(["Date", "SessionNumber", mechanism_key, "GameName"], as_index=False)["GameDuration"].sum()

            # Collect date data
            for date, date_group in grouped.groupby("Date"):
                if date not in date_data_dict:
                    date_data_dict[date] = []
                date_data_dict[date].append(date_group[["SessionNumber", mechanism_key, "GameName", "GameDuration"]])

    except Exception as e:
        logger.exception(f"Error in process_sessions_and_write for {session_local}: {e}")

    # Write extdata.csv once with all data
    if ext_data_frames:
        final_ext_df = pd.concat(ext_data_frames, ignore_index=True)
        final_ext_df.to_csv(extdata_file, index=False)
        logger.info(f"Created extdata.csv: {extdata_file} (rows={len(final_ext_df)})")

    # Write date files once with all data (replace existing files)
    for date, date_frames in date_data_dict.items():
        if date_frames:
            out_path = os.path.join(date_folder, f"{date}.csv")
            combined_date_df = pd.concat(date_frames, ignore_index=True)
            # Remove duplicates based on key columns
            combined_date_df = combined_date_df.drop_duplicates(
                subset=["SessionNumber", mechanism_key, "GameName"], 
                keep="last"
            )
            combined_date_df.to_csv(out_path, index=False)
            logger.info(f"Created date file: {out_path} (rows={len(combined_date_df)})")

# ------------------- ThreadPool helpers -------------------

def process_single_user(user: str, place: str, devices: List[str]):
    """
    Called in thread pool. Downloads necessary files (if newer) and processes the user.
    """
    # Always try to download updated files for devices
    for device in devices:
        try:
            download_required_files(place, user, device)
        except Exception:
            logger.exception(f"Error downloading files for {place}/{user}/{device}")

    if not devices:
        return

    # Check if we have local files to process
    any_local_present = any(
        os.path.exists(os.path.join(local_base, place, user, "Pluto" if d == "PLUTO" else "Mars", "configdata.csv")) and
        os.path.exists(os.path.join(local_base, place, user, "Pluto" if d == "PLUTO" else "Mars", "sessions", "sessions.csv"))
        for d in devices
    )

    if not any_local_present:
        logger.info(f"No local files present for {place}/{user}. Skipping.")
        return

    try:
        process_user(user, place, devices)
    except Exception as e:
        logger.exception(f"Error processing user {place}/{user}: {e}")

# ------------------- Single-patient entry point (called by Flask) -------------------

def process_single_patient(homer_id: str, place: str) -> Dict[str, Any]:
    """
    Download S3 files and process data for one patient.
    Called on-demand from the patient detail Devices tab.
    Returns {"ok": True} or {"ok": False, "error": "..."}.
    """
    try:
        devices = get_user_devices(homer_id, place)
        if not devices:
            # Patient has no devices on S3 yet — still attempt local processing
            logger.info(f"No S3 devices found for {place}/{homer_id}")
        else:
            for device in devices:
                try:
                    download_required_files(place, homer_id, device)
                except Exception:
                    logger.exception(f"Error downloading {place}/{homer_id}/{device}")

        # Process local files (extdata + Dates/) whether or not we just downloaded
        any_local = False
        for device in (devices or ["PLUTO", "MARS"]):
            device_dir = "Pluto" if device == "PLUTO" else "Mars"
            config_local  = os.path.join(local_base, place, homer_id, device_dir, "configdata.csv")
            session_local = os.path.join(local_base, place, homer_id, device_dir, "sessions", "sessions.csv")
            if os.path.exists(config_local) and os.path.exists(session_local):
                any_local = True
                mechanism_key = "Mechanism" if device == "PLUTO" else "Movement"
                extdata_file = os.path.join(local_base, place, homer_id, device_dir, "sessions", "extdata.csv")
                date_folder  = os.path.join(local_base, place, homer_id, device_dir, "Dates")
                session_durations = compute_session_durations(session_local, mechanism_key)
                process_sessions_and_write(session_local, date_folder, extdata_file, mechanism_key, session_durations)

        if not any_local:
            return {"ok": False, "error": "No device data available for this patient yet."}

        return {"ok": True}
    except Exception as e:
        logger.exception(f"process_single_patient failed for {place}/{homer_id}: {e}")
        return {"ok": False, "error": str(e)}


# ------------------- Main -------------------

def main():
    processed_users = set()  # Track processed users to avoid duplicates

    logger.info(f"Script started at: {datetime.now().isoformat()}")
    max_workers = 4

    for place in LOGINPLACE:
        users = list_user_ids(place)
        if not users:
            logger.info(f"No users found for place {place}. Continuing.")
            continue

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_user = {}
            for user in users:
                if user == "logs":
                    continue

                user_key = f"{place}/{user}"
                if user_key in processed_users:
                    logger.info(f"Skipping already processed user: {user_key}")
                    continue
                processed_users.add(user_key)

                devices = get_user_devices(user, place)
                future = executor.submit(process_single_user, user, place, devices)
                future_to_user[future] = user

            for future in as_completed(future_to_user):
                user = future_to_user[future]
                try:
                    future.result()
                except Exception as e:
                    logger.exception(f"Future for user {user} raised exception: {e}")

    logger.info("Processing completed.")

if __name__ == "__main__":
    main()