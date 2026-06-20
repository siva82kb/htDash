import os
import logging
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
from io import StringIO

# Configuration
BUCKET_NAME = "homerclouds"

# Use absolute path based on script location
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
local_base = os.path.join(SCRIPT_DIR, "META-DATA")

PLUTO = ["WFE", "WURD", "FPS", "HOC", "FME1", "FME2"]
MARS = ["ML", "AP", "ML-AP"]
LOGINPLACE = ["ludhiana", "manipal", "ranipet"]

s3 = boto3.client("s3")

def normalize_place(place: str) -> str:
    """Normalize place name to lowercase."""
    return place.lower()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


def read_csv_skip_metadata(file_path: str):
    """
    Read CSV file, skipping metadata header lines that start with ':'.
    The actual CSV header is the first line that doesn't start with ':' and contains commas.
    """
    try:
        # Read the file as text
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into lines
        lines = content.split('\n')
        
        # Find the line that has the actual CSV headers (contains commas and doesn't start with ':')
        header_line = None
        header_idx = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line and not line.startswith(':') and ',' in line:
                header_line = line
                header_idx = i
                break
        
        if header_line is None:
            raise ValueError("Could not find CSV header line")
        
        # Collect all data lines after the header (skip any lines that start with ':')
        data_lines = []
        for i in range(header_idx + 1, len(lines)):
            line = lines[i].strip()
            if line and not line.startswith(':'):
                data_lines.append(line)
        
        # Reconstruct CSV content
        csv_content = header_line + '\n' + '\n'.join(data_lines)
        
        # Read the CSV
        df = pd.read_csv(StringIO(csv_content))
        
        logger.info(f"Successfully read {file_path} with {len(df)} rows")
        logger.info(f"Columns: {df.columns.tolist()[:5]}...")  # Show first 5 columns
        return df
        
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return pd.DataFrame()


def process_user(user_id: str, place: str, devices: List[str]) -> None:
    """Process one user's devices — writes extdata.csv and Dates/ CSVs locally."""
    for device in devices:
        device_dir = "Pluto" if device == "PLUTO" else "Mars"
        config_local = os.path.join(local_base, place, "patients", user_id, device_dir, "configdata.csv")
        session_local = os.path.join(local_base, place, "patients", user_id, device_dir, "sessions", "sessions.csv")
        extdata_file = os.path.join(local_base, place, "patients", user_id, device_dir, "sessions", "extdata.csv")
        date_folder = os.path.join(local_base, place, "patients", user_id, device_dir, "Dates")

        if not os.path.exists(config_local) or not os.path.exists(session_local):
            logger.info(f"Skipping processing for {place}/patients/{user_id}/{device_dir} because required files missing.")
            continue

        try:
            config_df = pd.read_csv(config_local)
            if config_df.empty:
                logger.info(f"Config file empty for {place}/patients/{user_id}/{device_dir}. Skipping.")
                continue

            mechanism_key = "Mechanism" if device == "PLUTO" else "Movement"

            # Read session data with metadata skipping
            session_df = read_csv_skip_metadata(session_local)
            
            if session_df.empty:
                logger.warning(f"Session data is empty for {user_id}")
                continue
            
            logger.info(f"Processing {len(session_df)} session records for {user_id}")
            logger.info(f"Session columns: {session_df.columns.tolist()}")
            
            # Compute session durations
            session_durations = compute_session_durations(session_df, mechanism_key)
            
            # Process and write output files
            process_and_write_outputs(session_df, date_folder, extdata_file, mechanism_key, session_durations)

        except Exception as e:
            logger.exception(f"Failed processing for user {user_id} / device {device}: {e}")


def compute_session_durations(session_df: pd.DataFrame, mechanism_key: str) -> Dict[tuple, float]:
    """Compute total GameDuration (minutes) per (Date, SessionNumber)."""
    session_durations = {}
    try:
        # Check if required columns exist
        if "DateTime" not in session_df.columns:
            logger.error(f"DateTime column not found. Available columns: {session_df.columns.tolist()}")
            return session_durations
            
        # Convert DateTime
        session_df["DateTime"] = pd.to_datetime(session_df["DateTime"], errors="coerce")
        session_df = session_df.dropna(subset=["DateTime"])
        
        # Convert MoveTime to numeric
        if "MoveTime" not in session_df.columns:
            logger.error(f"MoveTime column not found. Available columns: {session_df.columns.tolist()}")
            return session_durations
            
        session_df["MoveTime"] = pd.to_numeric(session_df["MoveTime"], errors="coerce").fillna(0.0)
        session_df["GameDuration"] = (session_df["MoveTime"] / 60.0).round(4)
        session_df["Date"] = session_df["DateTime"].dt.strftime("%d-%m-%Y")

        # Group by Date and SessionNumber
        if "SessionNumber" not in session_df.columns:
            logger.error(f"SessionNumber column not found. Available columns: {session_df.columns.tolist()}")
            return session_durations
            
        grouped = session_df.groupby(["Date", "SessionNumber"], as_index=False)["GameDuration"].sum()
        for _, row in grouped.iterrows():
            key = (row["Date"], str(row["SessionNumber"]))
            session_durations[key] = float(row["GameDuration"])
            
        logger.info(f"Computed {len(session_durations)} session durations")
    except Exception as e:
        logger.exception(f"Error in compute_session_durations: {e}")

    return session_durations


def process_and_write_outputs(session_df: pd.DataFrame, date_folder: str, extdata_file: str, 
                             mechanism_key: str, session_durations: Dict[tuple, float]) -> None:
    """Process the session dataframe and write output files."""
    
    os.makedirs(os.path.dirname(extdata_file), exist_ok=True)
    os.makedirs(date_folder, exist_ok=True)

    try:
        # Create extdata dataframe
        extdata_rows = []
        for idx, row in session_df.iterrows():
            try:
                # Parse datetime
                dt = pd.to_datetime(row["DateTime"])
                date_str = dt.strftime("%d-%m-%Y")
                sess_num = str(row["SessionNumber"])
                session_duration = session_durations.get((date_str, sess_num), 0.0)
                
                extdata_rows.append({
                    "DateTime": dt.strftime("%d-%m-%Y %H:%M:%S"),
                    "SessionNumber": sess_num,
                    "SessionDuration": round(session_duration, 4),
                    "GameName": str(row.get("GameName", "")),
                    "GameDuration": round(float(row.get("MoveTime", 0.0)) / 60.0, 4),
                    mechanism_key: str(row.get(mechanism_key, "")),
                    "MoveTime": float(row.get("MoveTime", 0.0))
                })
            except Exception as e:
                logger.warning(f"Error processing row {idx}: {e}")
                continue
        
        # Save extdata.csv
        if extdata_rows:
            extdata_df = pd.DataFrame(extdata_rows)
            extdata_df.to_csv(extdata_file, index=False)
            logger.info(f"Created extdata.csv: {extdata_file} (rows={len(extdata_df)})")
        else:
            logger.warning(f"No extdata rows generated for {extdata_file}")
        
        # Create per-date summaries
        if "DateTime" in session_df.columns:
            session_df["Date"] = pd.to_datetime(session_df["DateTime"]).dt.strftime("%d-%m-%Y")
            session_df["GameDuration"] = session_df["MoveTime"] / 60.0
            
            grouped = session_df.groupby(["Date", "SessionNumber", mechanism_key, "GameName"], as_index=False)["GameDuration"].sum()
            
            # Write a file for each date
            for date in grouped["Date"].unique():
                date_df = grouped[grouped["Date"] == date].copy()
                # Remove duplicates if any
                date_df = date_df.drop_duplicates(subset=["SessionNumber", mechanism_key, "GameName"], keep="last")
                date_df = date_df[["SessionNumber", mechanism_key, "GameName", "GameDuration"]]
                
                out_path = os.path.join(date_folder, f"{date}.csv")
                date_df.to_csv(out_path, index=False)
                logger.info(f"Created date file: {out_path} (rows={len(date_df)})")

    except Exception as e:
        logger.exception(f"Error in process_and_write_outputs: {e}")


def get_user_devices(user_id: str, place: str) -> List[str]:
    """Check for device prefixes under a user."""
    place = normalize_place(place)
    devices = []
    prefixes = {
        "PLUTO": f"{place}/patients/{user_id}/Pluto/",
        "MARS": f"{place}/patients/{user_id}/Mars/"
    }
    for dev, prefix in prefixes.items():
        try:
            resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, MaxKeys=1)
            if resp.get("Contents"):
                devices.append(dev)
                logger.info(f"Found {dev} device for user {user_id} at {place}")
        except Exception as e:
            logger.warning(f"Error checking {dev} for {user_id} at {place}: {e}")
    return devices


def download_required_files(place: str, user: str, device: str) -> bool:
    """Download configdata.csv and sessions.csv if newer on S3."""
    place = normalize_place(place)
    device_dir = "Pluto" if device == "PLUTO" else "Mars"
    prefix = f"{place}/patients/{user}/{device_dir}/"
    files = [f"{prefix}configdata.csv", f"{prefix}sessions/sessions.csv"]
    updated = False

    for key in files:
        local_path = os.path.join(local_base, key)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        try:
            s3_obj = s3.head_object(Bucket=BUCKET_NAME, Key=key)
            s3_lastmodified = s3_obj["LastModified"].timestamp()
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                continue
            else:
                logger.exception(f"Error in head_object for {key}")
                continue

        if os.path.exists(local_path):
            local_mtime = os.path.getmtime(local_path)
            if local_mtime >= s3_lastmodified:
                continue

        tmp_path = local_path + ".tmp"
        try:
            logger.info(f"Downloading {key} -> {local_path}")
            s3.download_file(BUCKET_NAME, key, tmp_path)
            os.replace(tmp_path, local_path)
            updated = True
        except Exception as e:
            logger.exception(f"Error downloading {key}: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    return updated


def list_user_ids(place: str) -> List[str]:
    """List user IDs under a place."""
    place = normalize_place(place)
    prefix = f"{place}/patients/"
    logger.info(f"Listing users with prefix: {prefix}")
    continuation_token = None
    user_ids = []
    
    try:
        while True:
            if continuation_token:
                resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, Delimiter='/', 
                                         ContinuationToken=continuation_token)
            else:
                resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, Delimiter='/')
            
            for cp in resp.get("CommonPrefixes", []):
                p = cp.get("Prefix", "")
                parts = p.split("/")
                if len(parts) >= 3 and parts[-2]:
                    user_id = parts[-2]
                    if user_id != "patients":
                        user_ids.append(user_id)
            
            if resp.get("IsTruncated"):
                continuation_token = resp.get("NextContinuationToken")
            else:
                break
    except Exception as e:
        logger.exception(f"Failed to list user ids for place {place}: {e}")
    
    logger.info(f"Found {len(user_ids)} user(s) for place {place}")
    return user_ids


def process_single_user(user: str, place: str, devices: List[str]):
    """Process a single user."""
    place = normalize_place(place)
    logger.info(f"Processing user {user} at {place} with devices: {devices}")

    for device in devices:
        try:
            download_required_files(place, user, device)
        except Exception:
            logger.exception(f"Error downloading files for {place}/{user}/{device}")

    if not devices:
        return

    try:
        process_user(user, place, devices)
        logger.info(f"Successfully processed user {user} at {place}")
    except Exception as e:
        logger.exception(f"Error processing user {place}/{user}: {e}")


def process_single_patient(homer_id: str, place: str) -> Dict[str, Any]:
    """
    Process one patient on-demand.
    Called from Flask when user clicks "Sync Activity" button.
    Returns {"ok": True} or {"ok": False, "error": "..."}.
    """
    try:
        place = normalize_place(place)
        logger.info(f"Processing single patient: {place}/{homer_id}")
        devices = get_user_devices(homer_id, place)
        if not devices:
            return {"ok": False, "error": "No devices found for this patient"}

        # Download files from S3
        for device in devices:
            try:
                download_required_files(place, homer_id, device)
            except Exception as e:
                logger.exception(f"Error downloading {place}/{homer_id}/{device}: {e}")

        # Process the downloaded files
        process_user(homer_id, place, devices)
        logger.info(f"Successfully processed {place}/{homer_id}")
        return {"ok": True}
    except Exception as e:
        logger.exception(f"Error processing {place}/{homer_id}: {e}")
        return {"ok": False, "error": str(e)}


def main():
    processed_users = set()
    
    logger.info(f"Script started at: {datetime.now().isoformat()}")
    logger.info(f"Processing places: {LOGINPLACE}")
    max_workers = 4

    for place in LOGINPLACE:
        place = normalize_place(place)
        logger.info(f"=== Starting to process place: {place} ===")
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
                    continue
                processed_users.add(user_key)

                devices = get_user_devices(user, place)
                if not devices:
                    logger.info(f"No devices found for user {user} at {place}, skipping")
                    continue
                    
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