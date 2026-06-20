from flask import Blueprint, request, jsonify
import pandas as pd
from datetime import datetime, timedelta
import os
from config import Config
from models.user import current_session
from utils.data_processors import DataProcessor
 
bp = Blueprint("charts", __name__)
 
 
@bp.route("/get_hospital_details/<hospital_id>", methods=["GET"])
def get_hospital_details(hospital_id):
    if not hospital_id:
        return jsonify({"error": "Hospital ID required"}), 400
 
    # Determine place
    if current_session.is_admin():
        place = current_session.place_info.get(hospital_id, current_session.login_place)
    else:
        place = current_session.login_place
 
    details = DataProcessor.get_hospital_details(
        hospital_id, current_session.device_name, place
    )
 
    if details:
        return jsonify(details)
    else:
        return jsonify({"error": "Data not found for the given Hospital ID"}), 404
 
 
@bp.route("/chart-data/<hospital_id>/<device_name>", methods=["GET"])
def get_chart_data(hospital_id, device_name):
    print(device_name)
    

    print("Current working dir:", os.getcwd())
    try:
        # Determine place
        if current_session.is_admin():
            place = current_session.place_info.get(
                hospital_id, current_session.login_place
            )
        else:
            place = current_session.login_place
 
        config_file = os.path.join(
            Config.META_DATA_PATH, place, hospital_id, device_name, Config.CONFIG_DATA
        )
        ext_file = os.path.join(
            Config.META_DATA_PATH,
            place,
            hospital_id,
            device_name,
            "sessions/extdata.csv",
        )
 
        if not os.path.exists(config_file) or not os.path.exists(ext_file):
            print(f"Missing files - Config: {config_file}, Ext: {ext_file}")
            return jsonify({"error": "Data files not found"}), 404
 
        ext_data = pd.read_csv(ext_file)
        config_data = pd.read_csv(config_file)
 
        # Parse dates — study is always 30 days from StartDate
        # Parse StartDate safely
        start_date = pd.to_datetime(
            config_data["StartDate"].iloc[0],
            dayfirst=True,
            errors="coerce"
        )
 
        if pd.isna(start_date):
            return jsonify({"error": "Invalid StartDate format"}), 400
 
        end_date = start_date + timedelta(days=29)
        current_date = datetime.now().date()
 
        # Generate date range
        date_range = [
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]
 
        # Parse ext_data safely
        ext_data["DateTime"] = pd.to_datetime(
            ext_data["DateTime"],
            dayfirst=True,
            errors="coerce"
        )
 
        ext_data = ext_data.dropna(subset=["DateTime"])
        ext_data["Date"] = ext_data["DateTime"].dt.date
 
        # Aggregate session durations
        session_duration_by_date = ext_data.groupby("Date")["MoveTime"].sum() / 60
 
        # Prepare data — line_data must align 1-to-1 with labels (full date_range)
        # Use None for future dates so Chart.js shows gaps, not zeros
        labels = [date.strftime("%Y-%m-%d") for date in date_range]
        line_data = [
            round(float(session_duration_by_date.get(date.date(), 0)), 2)
            if date.date() <= current_date else None
            for date in date_range
        ]
 
        bubble_data = [
            {
                "x": date.strftime("%Y-%m-%d"),
                "y": session_duration_by_date.get(date.date(), 0),
                "r": 10,
            }
            for date in date_range
        ]
 
        # Get target time
        horizontal_line_y = (
            int(config_data["TotalTime"].iloc[-1])
            if current_session.device_name in ["Pluto", "Mars"]
            else 60
        )
 
        horizontal_line_data = [
            {"x": label, "y": horizontal_line_y} for label in labels
        ]
 
        chart_data = {
            "labels": labels,
            "datasets": [
                {
                    "label": "Session Duration",
                    "data": line_data,
                    "borderColor": "navy",
                    "backgroundColor": None,
                    "type": "line",
                    "fill": True,
                },
                {
                    "label": "Session Bubble",
                    "data": bubble_data,
                    "backgroundColor": "rgba(46, 139, 87, 0.6)",
                    "hoverBackgroundColor": "rgba(46, 139, 87, 0.8)",
                    "type": "bubble",
                },
                {
                    "label": "Target Line",
                    "data": horizontal_line_data,
                    "borderColor": "red",
                    "borderDash": [10, 5],
                    "type": "line",
                    "fill": False,
                },
            ],
        }
 
        return jsonify(chart_data)
 
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500
 
 
@bp.route(
    "/fetch-mechanism-data/<hospital_id>/<selected_date>/<device_name>", methods=["GET"]
)
def fetch_mechanism_data(hospital_id, selected_date, device_name):
    """Fetch mechanism data for a specific date"""
    try:
        # Normalize device name to handle lowercase from frontend
        device_name_normalized = (
            device_name.lower().capitalize()
            if device_name.lower() in ["pluto", "mars"]
            else device_name
        )
 
        # Determine place
        if current_session.is_admin():
            place = current_session.place_info.get(
                hospital_id, current_session.login_place
            )
        else:
            place = current_session.login_place
 
        # Construct file path - use original name for file path
        date_file = os.path.join(
            Config.META_DATA_PATH,
            place,
            hospital_id,
            device_name,
            Config.DATES_FOLDER,
            f"{selected_date}.csv",
        )
 
        if not os.path.exists(date_file):
            return jsonify({"error": f"Date file not found: {date_file}"}), 404
 
        date_data = pd.read_csv(date_file)
 
        # Determine mechanism column name - use normalized name for config check
        if device_name_normalized == Config.PLUTO_LABEL:
            mechanism_col = "Mechanism"
            static_mechanisms = Config.PLUTO_MECHANISMS
        elif device_name_normalized == Config.MARS_LABEL:
            mechanism_col = "Movement"
            static_mechanisms = Config.MARS_MECHANISMS
        else:
            return jsonify(
                {
                    "error": f"Invalid device type: {device_name} (normalized: {device_name_normalized})"
                }
            ), 400
 
        # Group by mechanism
        mechanism_duration = (
            date_data.groupby(mechanism_col)["GameDuration"].sum().reset_index()
        )
 
        mechanisms = mechanism_duration[mechanism_col].tolist()
        durations = mechanism_duration["GameDuration"].tolist()
 
        # Ensure all mechanisms are present
        final_durations = []
        for mechanism in static_mechanisms:
            if mechanism in mechanisms:
                final_durations.append(durations[mechanisms.index(mechanism)])
            else:
                final_durations.append(0)
 
        # Get prescribed times from config
        config_file = os.path.join(
            Config.META_DATA_PATH, place, hospital_id, device_name, Config.CONFIG_DATA
        )
 
        lines = []
        if os.path.exists(config_file):
            config_data = pd.read_csv(config_file)
            for mechanism in static_mechanisms:
                if mechanism in config_data.columns:
                    lines.append(int(config_data[mechanism].iloc[-1]))
                else:
                    lines.append(0)
        else:
            lines = [0] * len(static_mechanisms)
 
        chart_data = {
            "mechanisms": static_mechanisms,
            "durations": final_durations,
            "lines": lines,
        }
 
        return jsonify(chart_data)
 
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500
 
 
@bp.route("/get-patient-mechanisms/<hospital_id>", methods=["GET"])
def get_patient_mechanisms(hospital_id):
    """Get all mechanisms used by a patient from their config files"""
    try:
        from models.user import current_session
        import pandas as pd
        from datetime import datetime
 
        if not current_session.login_place:
            return jsonify({"error": "Not logged in"}), 401
 
        login_place = current_session.login_place
        # Correct path: META_DATA_PATH / place / hospital_id / Device / configdata.csv
        base_path = os.path.join(Config.META_DATA_PATH, login_place)
 
        mechanisms = []
        last_updated = None
 
        # Check Pluto config (capital P to match Config.PLUTO_LABEL)
        pluto_config = os.path.join(base_path, hospital_id, Config.PLUTO_LABEL, "configdata.csv")
        if os.path.exists(pluto_config):
            # Get file modification time
            file_mtime = os.path.getmtime(pluto_config)
            file_date = datetime.fromtimestamp(file_mtime)
            if last_updated is None or file_date > last_updated:
                last_updated = file_date
            try:
                df = pd.read_csv(pluto_config)
                pluto_mechs = Config.PLUTO_MECHANISMS  # ["WFE", "WURD", "FPS", "HOC", "FME1", "FME2"]
                for mech in pluto_mechs:
                    if mech in df.columns:
                        total = df[mech].sum()
                        if total > 0:
                            mechanisms.append(
                                {
                                    "name": mech,
                                    "device": "PLUTO",
                                    "totalDuration": float(total),
                                }
                            )
            except Exception as e:
                print(f"Error reading Pluto config: {e}")
 
        # Check Mars config (capital M to match Config.MARS_LABEL)
        mars_config = os.path.join(base_path, hospital_id, Config.MARS_LABEL, "configdata.csv")
        if os.path.exists(mars_config):
            # Get file modification time
            file_mtime = os.path.getmtime(mars_config)
            file_date = datetime.fromtimestamp(file_mtime)
            if last_updated is None or file_date > last_updated:
                last_updated = file_date
            try:
                df = pd.read_csv(mars_config)
                mars_mechs = ["ML", "AP", "MLAP"]
                for mech in mars_mechs:
                    if mech in df.columns:
                        total = df[mech].sum()
                        if total > 0:
                            mechanisms.append(
                                {
                                    "name": mech,
                                    "device": "MARS",
                                    "totalDuration": float(total),
                                }
                            )
            except Exception as e:
                print(f"Error reading Mars config: {e}")
 
        return jsonify(
            {
                "mechanisms": mechanisms,
                "hospital_id": hospital_id,
                "last_updated": last_updated.strftime("%Y-%m-%dT%H:%M:%S")
                if last_updated
                else None,
            }
        )
 
    except Exception as e:
        print(f"Error getting patient mechanisms: {e}")
        return jsonify({"error": str(e)}), 500
 
 
@bp.route("/api/patients/<homer_id>/sync-activity", methods=["POST"])
def sync_patient_activity(homer_id):
    """Trigger S3 download + processing for one patient. Called from the Devices tab."""
    try:
        place = current_session.login_place
        if not place:
            return jsonify({"error": "Not authenticated"}), 401
        from processinInstance import process_single_patient
        result = process_single_patient(homer_id, place)
        if result.get("ok"):
            return jsonify({"status": "ok"})
        return jsonify({"error": result.get("error", "Processing failed")}), 500
    except Exception as e:
        print(f"sync_patient_activity error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/patients/<homer_id>/activity", methods=["GET"])
def patient_activity(homer_id):
    """Return 30-day daily exercise minutes for Pluto and Mars for a patient."""
    try:
        place = current_session.login_place
        if not place:
            return jsonify({"error": "Not authenticated"}), 401

        place = place.lower()
        current_date = datetime.now().date()
        result = {}

        # Helper to read CSV from local META-DATA folder
        def read_csv_file(local_path):
            """Read CSV from local file."""
            if not os.path.exists(local_path):
                return None
            try:
                return pd.read_csv(local_path)
            except Exception as e:
                print(f"Error reading {local_path}: {e}")
                return None

        # Helper to list files in local folder
        def list_folder_files(local_folder):
            """List CSV files in a local folder."""
            files = []
            if os.path.exists(local_folder):
                try:
                    for fname in os.listdir(local_folder):
                        if fname.endswith('.csv'):
                            files.append(fname)
                except Exception as e:
                    print(f"Error listing {local_folder}: {e}")
            return files

        for device_dir, device_key in [("Pluto", "pluto"), ("Mars", "mars")]:
            # Build local paths from META-DATA folder
            config_file = os.path.join(Config.META_DATA_PATH, place, "patients", homer_id, device_dir, Config.CONFIG_DATA)
            ext_file = os.path.join(Config.META_DATA_PATH, place, "patients", homer_id, device_dir, "sessions", "extdata.csv")
            dates_folder = os.path.join(Config.META_DATA_PATH, place, "patients", homer_id, device_dir, Config.DATES_FOLDER)

            # Read config and extdata from local
            config_df = read_csv_file(config_file)
            ext_df = read_csv_file(ext_file)

            if config_df is None or ext_df is None or config_df.empty:
                continue

            try:
                start_date = pd.to_datetime(config_df["StartDate"].iloc[0], dayfirst=True, errors="coerce")
                if pd.isna(start_date):
                    continue

                target = int(config_df["TotalTime"].iloc[-1]) if "TotalTime" in config_df.columns else 60
                end_date = start_date + timedelta(days=29)

                ext_df["DateTime"] = pd.to_datetime(ext_df["DateTime"], dayfirst=True, errors="coerce")
                ext_df = ext_df.dropna(subset=["DateTime"])
                ext_df["Date"] = ext_df["DateTime"].dt.date
                daily_minutes = ext_df.groupby("Date")["MoveTime"].sum() / 60

                date_range = [start_date.date() + timedelta(days=i) for i in range(30)]
                labels = [d.strftime("%Y-%m-%d") for d in date_range]
                data = [
                    round(float(daily_minutes.get(d, 0)), 2) if d <= current_date else None
                    for d in date_range
                ]

                # Dates that have a Dates/ CSV (for click drill-down)
                dates_with_data = []
                date_files = list_folder_files(dates_folder)
                for fname in date_files:
                    if fname.endswith(".csv"):
                        try:
                            dt = datetime.strptime(fname[:-4], "%d-%m-%Y")
                            dates_with_data.append(dt.strftime("%Y-%m-%d"))
                        except ValueError:
                            pass
                print(f"[patient_activity] {homer_id}/{device_dir}: Found {len(dates_with_data)} dates with data files")

                # Config details — prescribed mechanism times
                mechanisms = Config.PLUTO_MECHANISMS if device_key == "pluto" else Config.MARS_MECHANISMS
                prescribed = {}
                for m in mechanisms:
                    if m in config_df.columns:
                        prescribed[m] = int(config_df[m].iloc[-1])

                # Mismatch check: config StartDate vs patient activationDate
                from utils.data_access import read_patient_meta
                mismatch = None
                try:
                    patient = read_patient_meta(place, homer_id)
                    activation_str = (patient or {}).get("activationDate", "")
                    if activation_str:
                        activation_date = datetime.fromisoformat(activation_str).date()
                        if start_date.date() != activation_date:
                            diff = (start_date.date() - activation_date).days
                            mismatch = {
                                "config_start": start_date.strftime("%d %b %Y"),
                                "activation":   activation_date.strftime("%d %b %Y"),
                                "diff_days":    diff,
                            }
                except Exception:
                    pass

                row = config_df.iloc[-1]
                result[device_key] = {
                    "labels":          labels,
                    "data":            data,
                    "target":          target,
                    "dates_with_data": dates_with_data,
                    "start_date":      start_date.strftime("%Y-%m-%d"),
                    "end_date":        (start_date + timedelta(days=29)).strftime("%Y-%m-%d"),
                    "training_side":   str(row.get("TrainingSide", "—")),
                    "prescribed":      prescribed,
                    "mismatch":        mismatch,
                }
            except Exception as e:
                print(f"Error processing {device_dir} for {homer_id}: {e}")
                continue

        return jsonify(result)

    except Exception as e:
        print(f"Error in patient_activity for {homer_id}: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/patients/<homer_id>/activity/<date>/<device>", methods=["GET"])
def patient_activity_date(homer_id, date, device):
    """Return mechanism breakdown for a patient on a specific date and device."""
    try:
        place = current_session.login_place
        if not place:
            return jsonify({"error": "Not authenticated"}), 401

        place = place.lower()
        device_lower = device.lower()
        if device_lower not in ("pluto", "mars"):
            return jsonify({"error": "Invalid device"}), 400

        device_cap = "Pluto" if device_lower == "pluto" else "Mars"
        mechanism_col = "Mechanism" if device_lower == "pluto" else "Movement"
        static_mechs  = Config.PLUTO_MECHANISMS if device_lower == "pluto" else Config.MARS_MECHANISMS

        # Convert YYYY-MM-DD → dd-mm-YYYY for filename
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            filename = dt.strftime("%d-%m-%Y") + ".csv"
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400

        # Build local path
        date_file = os.path.join(Config.META_DATA_PATH, place, "patients", homer_id, device_cap, Config.DATES_FOLDER, filename)

        # Read date file from local
        df = None
        if os.path.exists(date_file):
            try:
                df = pd.read_csv(date_file)
            except Exception as e:
                print(f"Error reading {date_file}: {e}")

        if df is None:
            return jsonify({"error": "No data for this date"}), 404

        if mechanism_col not in df.columns or "GameDuration" not in df.columns:
            return jsonify({"error": "Unexpected file format"}), 500

        grouped = df.groupby(mechanism_col)["GameDuration"].sum()
        durations = [round(float(grouped.get(m, 0)), 2) for m in static_mechs]

        # Target from config
        config_file = os.path.join(Config.META_DATA_PATH, place, "patients", homer_id, device_cap, Config.CONFIG_DATA)

        cfg = None
        if os.path.exists(config_file):
            try:
                cfg = pd.read_csv(config_file)
            except Exception as e:
                print(f"Error reading {config_file}: {e}")

        targets = []
        if cfg is not None:
            for m in static_mechs:
                targets.append(int(cfg[m].iloc[-1]) if m in cfg.columns else 0)
        else:
            targets = [0] * len(static_mechs)

        return jsonify({"mechanisms": static_mechs, "durations": durations, "target": targets})

    except Exception as e:
        print(f"Error in patient_activity_date for {homer_id} {date} {device}: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/device-usage-overview", methods=["GET"])
def get_device_usage_overview():
    """
    Return daily session minutes for PLUTO and MARS across all assigned patients
    for the current site. Returns last 60 days of data aggregated by date.
    """
    try:
        place = current_session.login_place
        if current_session.is_admin():
            # Admin: pick a specific place from query param or default
            place = request.args.get("place", current_session.login_place)
 
        site_dir = os.path.join(Config.META_DATA_PATH, place)
        if not os.path.exists(site_dir):
            return jsonify({"pluto": [], "mars": [], "labels": []})
 
        from collections import defaultdict
        pluto_by_date = defaultdict(float)
        mars_by_date = defaultdict(float)
 
        # Walk every patient folder in this site
        for patient_id in os.listdir(site_dir):
            patient_dir = os.path.join(site_dir, patient_id)
            if not os.path.isdir(patient_dir):
                continue
 
            for device, store in [("Pluto", pluto_by_date), ("Mars", mars_by_date)]:
                ext_file = os.path.join(patient_dir, device, "sessions", "extdata.csv")
                if not os.path.exists(ext_file):
                    continue
                try:
                    df = pd.read_csv(ext_file)
                    if df.empty or "DateTime" not in df.columns or "MoveTime" not in df.columns:
                        continue
                    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%d-%m-%Y %H:%M:%S", errors="coerce")
                    df = df.dropna(subset=["DateTime"])
                    df["Date"] = df["DateTime"].dt.date
                    daily = df.groupby("Date")["MoveTime"].sum() / 60
                    for date, minutes in daily.items():
                        store[date] += minutes
                except Exception:
                    continue
 
        # Build a unified date range covering all data (last 60 days max)
        from datetime import date, timedelta
        today = date.today()
        cutoff = today - timedelta(days=59)
 
        all_dates = set()
        for d in pluto_by_date:
            if d >= cutoff:
                all_dates.add(d)
        for d in mars_by_date:
            if d >= cutoff:
                all_dates.add(d)
 
        if not all_dates:
            return jsonify({"pluto": [], "mars": [], "labels": []})
 
        sorted_dates = sorted(all_dates)
        labels = [d.strftime("%d %b") for d in sorted_dates]
        pluto_vals = [round(pluto_by_date.get(d, 0), 1) for d in sorted_dates]
        mars_vals  = [round(mars_by_date.get(d, 0), 1) for d in sorted_dates]
 
        return jsonify({
            "labels": labels,
            "pluto": pluto_vals,
            "mars": mars_vals
        })
 
    except Exception as e:
        print(f"Error in device_usage_overview: {e}")
        return jsonify({"error": str(e)}), 500
 