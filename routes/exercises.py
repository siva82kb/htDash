# routes/exercises.py
from flask import Blueprint, request, jsonify
from config import Config
from models.user import current_session
from utils.file_handlers import FileHandler  # Add this import
import os
import json
from datetime import datetime
import subprocess
import shutil


def resolve_login_place(data=None):
    """Return login_place from session if live; restore from login_id in
    request body if Flask session was wiped (server restart)."""
    if current_session.login_place:
        return current_session.login_place
    login_id = (data or {}).get("login_id", "")
    if login_id:
        user_data = Config.LOGIN_CREDENTIALS.get(login_id)
        if user_data:
            current_session.login_place = user_data.get("place")
            current_session.privilege = user_data.get("privilege", "user")
            return current_session.login_place
    return None

bp = Blueprint("exercises", __name__)


@bp.route("/get_vcg_options", methods=["GET"])
def get_vcg_options():
    """Get available VCG types."""
    return jsonify(
        {"status": "success", "vcg_options": list(Config.EXERCISE_LIBRARY.keys())}
    )




def _normalise_vcg_type(raw):
    """Normalise any VCG type variant to the canonical EXERCISE_LIBRARY key.
    Handles: vcg4_5, VCG4_5, vcg4&5, VCG4&5, vcg4,5 → VCG4,5
             vcg2, VCG2 → VCG2  etc.
    """
    if not raw:
        return None
    s = str(raw).upper().strip()
    # All flavours of the combined 4&5 type
    if s in ("VCG4_5", "VCG4&5", "VCG4,5", "VCG45", "VCG4/5"):
        return "VCG4,5"
    if s in ("VCG2",):
        return "VCG2"
    if s in ("VCG3",):
        return "VCG3"
    return s  # pass through for any future types

@bp.route("/get_exercise_programs/<vcg_type>", methods=["GET"])
def get_exercise_programs(vcg_type):
    """Get exercise programs for a specific VCG type."""
    vcg_type = _normalise_vcg_type(vcg_type)
    if vcg_type not in Config.EXERCISE_LIBRARY:
        return jsonify({"status": "error", "message": f"Invalid VCG type: {vcg_type}"}), 400

    programs = Config.EXERCISE_LIBRARY[vcg_type]["programs"]
    simplified_programs = [
        {"id": key, "name": value["name"], "exercise_count": len(value["exercises"])}
        for key, value in programs.items()
    ]

    return jsonify(
        {
            "status": "success",
            "vcg_type": vcg_type,
            "vcg_name": Config.EXERCISE_LIBRARY[vcg_type]["name"],
            "programs": simplified_programs,
        }
    )


@bp.route("/get_exercise_details/<vcg_type>/<program_id>", methods=["GET"])
def get_exercise_details(vcg_type, program_id):
    """Get detailed exercises for a specific program."""
    vcg_type = _normalise_vcg_type(vcg_type)
    if vcg_type not in Config.EXERCISE_LIBRARY:
        return jsonify({"status": "error", "message": f"Invalid VCG type: {vcg_type}"}), 400

    if program_id not in Config.EXERCISE_LIBRARY[vcg_type]["programs"]:
        return jsonify({"status": "error", "message": "Invalid program"}), 400

    exercises = Config.EXERCISE_LIBRARY[vcg_type]["programs"][program_id]["exercises"]

    return jsonify({"status": "success", "exercises": exercises})


@bp.route("/save_vcg_prescription", methods=["POST"])
def save_vcg_prescription():
    """Save VCG exercise prescription."""
    try:
        data = request.get_json()
        login_place = resolve_login_place(data)
        if not login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        user_id = data.get("user_id")
        vcg_type = data.get("vcg_type")
        selected_exercises = data.get("exercises", [])

        if not all([user_id, vcg_type]):
            return jsonify(
                {"status": "error", "message": "Missing required fields"}
            ), 400

        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
        else:
            place = current_session.login_place

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prescription_data = {
            "user_id": user_id,
            "vcg_type": vcg_type,
            "selected_exercises": selected_exercises,
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "version": timestamp,
        }

        if Config.USE_S3:
            from utils.s3_store import s3_write_json
            prefix = f"{place}/{user_id}/vcg_prescriptions"
            s3_write_json(f"{prefix}/prescription_{timestamp}.json", prescription_data)
            s3_write_json(f"{prefix}/latest.json", prescription_data)
        else:
            base_path = os.path.join(Config.META_DATA_PATH, place, user_id)
            vcg_folder = os.path.join(base_path, "vcg_prescriptions")
            os.makedirs(vcg_folder, exist_ok=True)
            file_path = os.path.join(vcg_folder, f"prescription_{timestamp}.json")
            with open(file_path, "w") as f:
                json.dump(prescription_data, f, indent=2)
            shutil.copy2(file_path, os.path.join(vcg_folder, "latest.json"))
            # Legacy S3 upload via CLI
            try:
                s3_prefix = f"{place}/{user_id}/vcg_prescriptions"
                subprocess.run(["aws", "s3", "cp", file_path,
                                f"s3://{Config.BUCKET_NAME}/{s3_prefix}/prescription_{timestamp}.json"],
                               capture_output=True, text=True)
                subprocess.run(["aws", "s3", "cp", os.path.join(vcg_folder, "latest.json"),
                                f"s3://{Config.BUCKET_NAME}/{s3_prefix}/latest.json"],
                               capture_output=True, text=True)
            except Exception as s3_error:
                print(f"S3 upload error: {s3_error}")

        return jsonify(
            {
                "status": "success",
                "message": "VCG prescription saved successfully",
                "timestamp": timestamp,
            }
        )

    except Exception as e:
        print(f"Error saving VCG exercises: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/get_vcg_prescription/<user_id>", methods=["GET"])
def get_vcg_prescription(user_id):
    """Get the latest VCG prescription for a user."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
        else:
            place = current_session.login_place

        if Config.USE_S3:
            from utils.s3_store import s3_read_json, s3_list_prefix
            s3_prefix = f"{place}/{user_id}/vcg_prescriptions"
            prescription_data = s3_read_json(f"{s3_prefix}/latest.json")
            if not prescription_data:
                return jsonify({"status": "success", "has_prescription": False,
                                "message": "No VCG prescription found"})
            all_versions = []
            for key in s3_list_prefix(s3_prefix + "/"):
                fname = key.split("/")[-1]
                if fname.startswith("prescription_") and fname.endswith(".json"):
                    vdata = s3_read_json(key) or {}
                    all_versions.append({
                        "timestamp": vdata.get("version", fname.replace("prescription_","").replace(".json","")),
                        "created_at": vdata.get("created_at", ""),
                        "exercise_count": len(vdata.get("selected_exercises", [])),
                    })
        else:
            latest_path = os.path.join(Config.META_DATA_PATH, place, user_id,
                                       "vcg_prescriptions", "latest.json")
            vcg_folder  = os.path.join(Config.META_DATA_PATH, place, user_id, "vcg_prescriptions")

            if not os.path.exists(latest_path):
                return jsonify({"status": "success", "has_prescription": False,
                                "message": "No VCG prescription found"})

            with open(latest_path, "r") as f:
                prescription_data = json.load(f)

            all_versions = []
            if os.path.exists(vcg_folder):
                for file in os.listdir(vcg_folder):
                    if file.startswith("prescription_") and file.endswith(".json") and file != "latest.json":
                        try:
                            with open(os.path.join(vcg_folder, file)) as vf:
                                version_data = json.load(vf)
                            all_versions.append({
                                "timestamp": version_data.get("version", file.replace("prescription_","").replace(".json","")),
                                "created_at": version_data.get("created_at", ""),
                                "exercise_count": len(version_data.get("selected_exercises", [])),
                            })
                        except:
                            pass

        # Sort versions by timestamp (newest first)
        all_versions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Get full exercise details from library
        vcg_type = _normalise_vcg_type(prescription_data.get("vcg_type") or "")
        selected_exercises = prescription_data.get("selected_exercises", [])

        enriched_exercises = []
        if vcg_type and vcg_type in Config.EXERCISE_LIBRARY:
            # Collect all exercises from all programs for this VCG type
            all_exercises = []
            for program in Config.EXERCISE_LIBRARY[vcg_type]["programs"].values():
                all_exercises.extend(program["exercises"])

            # Enrich with full details
            for selected_ex in selected_exercises:
                for full_ex in all_exercises:
                    if full_ex["id"] == selected_ex.get("id"):
                        # Merge full exercise details with selected exercise (including dosage)
                        merged_ex = {**full_ex, **selected_ex}
                        enriched_exercises.append(merged_ex)
                        break

        return jsonify(
            {
                "status": "success",
                "has_prescription": True,
                "prescription": prescription_data,
                "enriched_exercises": enriched_exercises,
                "versions": all_versions,
            }
        )

    except Exception as e:
        print(f"Error getting VCG prescription: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/save_controller_exercises", methods=["POST"])
def save_controller_exercises():
    """Save controller's exercise prescription with versioning."""
    try:
        data = request.get_json()
        login_place = resolve_login_place(data)
        if not login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        user_id = data.get("user_id")
        exercise_type = data.get("exercise_type", "vcg")  # 'vcg' or 'adl'
        vcg_type = _normalise_vcg_type(data.get("vcg_type") or "")  # Normalize to canonical key
        selected_exercises = data.get("exercises", [])

        # Allow empty exercises (for deletion) but require user_id
        if not user_id:
            return jsonify(
                {"status": "error", "message": "Missing required fields"}
            ), 400

        # Always define place before any conditional that might use it
        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
        else:
            place = current_session.login_place

        prefix = "vcg" if exercise_type == "vcg" else "adl"
        s3_folder = f"{place}/{user_id}/{exercise_type}_prescriptions"
        latest_key = f"{s3_folder}/{prefix}_prescription_latest.json"

        # If vcg_type empty, try to load from existing latest
        if exercise_type == "vcg" and not vcg_type:
            if Config.USE_S3:
                from utils.s3_store import s3_read_json as _srj
                existing_latest_data = _srj(latest_key) or {}
                vcg_type = existing_latest_data.get("vcg_type") or ""
            else:
                existing_local = os.path.join(Config.META_DATA_PATH, place, user_id,
                                              f"{exercise_type}_prescriptions",
                                              f"{prefix}_prescription_latest.json")
                if os.path.exists(existing_local):
                    try:
                        with open(existing_local) as f:
                            vcg_type = json.load(f).get("vcg_type") or ""
                    except Exception:
                        pass
            if not vcg_type:
                try:
                    vcg_type = _get_user_vcg_type_helper(place, user_id)
                    if vcg_type:
                        vcg_type = _normalise_vcg_type(vcg_type)
                except Exception:
                    pass
            if not vcg_type:
                vcg_type = "VCG2"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_prescription_{timestamp}.json"

        prescription_data = {
            "user_id": user_id,
            "exercise_type": exercise_type,
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "exercises": selected_exercises,
        }
        if exercise_type == "vcg":
            prescription_data["vcg_type"] = vcg_type

        # Merge existing timeRecords
        if Config.USE_S3:
            from utils.s3_store import s3_read_json, s3_write_json
            existing_data = s3_read_json(latest_key) or {}
        else:
            existing_local = os.path.join(Config.META_DATA_PATH, place, user_id,
                                          f"{exercise_type}_prescriptions",
                                          f"{prefix}_prescription_latest.json")
            existing_data = {}
            if os.path.exists(existing_local):
                try:
                    with open(existing_local) as f:
                        existing_data = json.load(f)
                except Exception:
                    pass

        existing_exercises = existing_data.get("exercises", [])
        for new_ex in prescription_data.get("exercises", []):
            for existing_ex in existing_exercises:
                if new_ex.get("id") != existing_ex.get("id"):
                    continue
                file_records = existing_ex.get("timeRecords") or []
                client_records = new_ex.get("timeRecords") or []
                if not file_records:
                    break
                seen = {(r.get("date"), r.get("startTime"), r.get("endTime")) for r in client_records}
                for r in file_records:
                    k = (r.get("date"), r.get("startTime"), r.get("endTime"))
                    if k not in seen:
                        client_records.append(r)
                        seen.add(k)
                new_ex["timeRecords"] = client_records
                break

        if Config.USE_S3:
            s3_write_json(f"{s3_folder}/{filename}", prescription_data)
            s3_write_json(latest_key, prescription_data)
        else:
            folder_path = os.path.join(Config.META_DATA_PATH, place, user_id,
                                       f"{exercise_type}_prescriptions")
            os.makedirs(folder_path, exist_ok=True)
            file_path = os.path.join(folder_path, filename)
            with open(file_path, "w") as f:
                json.dump(prescription_data, f, indent=2)
            latest_file = os.path.join(folder_path, f"{prefix}_prescription_latest.json")
            with open(latest_file, "w") as f:
                json.dump(prescription_data, f, indent=2)
            try:
                subprocess.run(["aws", "s3", "cp", file_path,
                                f"s3://{Config.BUCKET_NAME}/{s3_folder}/{filename}"],
                               capture_output=True, text=True)
                subprocess.run(["aws", "s3", "cp", latest_file,
                                f"s3://{Config.BUCKET_NAME}/{s3_folder}/{prefix}_prescription_latest.json"],
                               capture_output=True, text=True)
            except Exception as s3_error:
                print(f"S3 upload error: {s3_error}")

        return jsonify(
            {
                "status": "success",
                "message": f"{exercise_type.upper()} prescription saved successfully",
                "filename": filename,
            }
        )

    except Exception as e:
        print(f"Error saving exercises: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def update_user_vcg_type(place, homer_id, vcg_type):
    """Update VCG type for a control group user in homerIdDetails.json"""
    data = FileHandler.load_homer_id_details(place)

    for user in data.get("details", []):
        if user.get("homerID") == homer_id and user.get("group") == "control":
            user["vcg_type"] = vcg_type
            user["status"] = "active"
            user["activated"] = True
            user["activation_date"] = datetime.now().strftime("%d-%m-%Y")
            FileHandler.save_homer_id_details(place, data)
            return True

    return False


def _get_user_vcg_type_helper(place, homer_id):
    """Get VCG type for a user from homerIdDetails.json"""
    data = FileHandler.load_homer_id_details(place)

    for user in data.get("details", []):
        if user.get("homerID") == homer_id:
            return user.get("vcg_type")

    return None


@bp.route("/update_user_vcg_type", methods=["POST"])
def update_user_vcg_type_route():
    """Update VCG type for a control group user."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        data = request.get_json()
        user_id = data.get("user_id")
        vcg_type = data.get("vcg_type")

        if not user_id or not vcg_type:
            return jsonify(
                {"status": "error", "message": "Missing required fields"}
            ), 400

        # Determine place
        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
        else:
            place = current_session.login_place

        # Update VCG type
        success = update_user_vcg_type(place, user_id, vcg_type)

        if success:
            return jsonify({"status": "success", "message": "VCG type updated"})
        else:
            return jsonify(
                {"status": "error", "message": "Failed to update VCG type"}
            ), 400

    except Exception as e:
        print(f"Error updating VCG type: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/get_latest_prescription/<user_id>/<exercise_type>", methods=["GET"])
def get_latest_prescription(user_id, exercise_type):
    """Get the latest prescription for a user."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        # Determine folder path
        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
            folder_path = os.path.join(
                Config.META_DATA_PATH, place, user_id, f"{exercise_type}_prescriptions"
            )
        else:
            folder_path = os.path.join(
                Config.META_DATA_PATH,
                current_session.login_place,
                user_id,
                f"{exercise_type}_prescriptions",
            )

        print(
            f"[DEBUG] get_latest_prescription: user_id={user_id}, exercise_type={exercise_type}, folder_path={folder_path}"
        )

        # First try to get the latest file
        latest_file = os.path.join(
            folder_path, f"{exercise_type}_prescription_latest.json"
        )
        print(
            f"[DEBUG] Looking for file: {latest_file}, exists={os.path.exists(latest_file)}"
        )

        if os.path.exists(latest_file):
            with open(latest_file, "r") as f:
                prescription_data = json.load(f)

            print(f"[DEBUG] Loaded prescription_data: {prescription_data}")

            # For VCG, enrich exercises with full details
            if exercise_type == "vcg" and "vcg_type" in prescription_data:
                vcg_type = _normalise_vcg_type(prescription_data["vcg_type"] or "")
                print(
                    f"[DEBUG] VCG type: {vcg_type}, in library: {vcg_type in Config.EXERCISE_LIBRARY}"
                )
                enriched_exercises = []

                # Get all exercises from the library for this VCG type
                if vcg_type and vcg_type in Config.EXERCISE_LIBRARY:
                    all_exercises = []
                    for program in Config.EXERCISE_LIBRARY[vcg_type][
                        "programs"
                    ].values():
                        all_exercises.extend(program["exercises"])

                    print(f"[DEBUG] All exercises in library: {len(all_exercises)}")
                    print(
                        f"[DEBUG] Selected exercises: {prescription_data.get('exercises', [])}"
                    )

                    for selected_ex in prescription_data.get("exercises", []):
                        for full_ex in all_exercises:
                            if full_ex["id"] == selected_ex.get("id"):
                                enriched_exercises.append({**full_ex, **selected_ex})
                                break

                print(f"[DEBUG] Enriched exercises count: {len(enriched_exercises)}")

                return jsonify(
                    {
                        "status": "success",
                        "has_prescription": True,
                        "prescription": prescription_data,
                        "enriched_exercises": enriched_exercises,
                    }
                )
            else:
                return jsonify(
                    {
                        "status": "success",
                        "has_prescription": True,
                        "prescription": prescription_data,
                        "enriched_exercises": prescription_data.get("exercises", []),
                    }
                )

        # If no latest file, try to find the most recent timestamped file
        if os.path.exists(folder_path):
            files = [
                f
                for f in os.listdir(folder_path)
                if f.startswith(f"{exercise_type}_prescription_")
                and f.endswith(".json")
            ]
            if files:
                # Sort by timestamp (descending) and take the first
                files.sort(reverse=True)
                most_recent = os.path.join(folder_path, files[0])

                with open(most_recent, "r") as f:
                    prescription_data = json.load(f)

                # Similar enrichment logic as above
                if exercise_type == "vcg" and "vcg_type" in prescription_data:
                    vcg_type = _normalise_vcg_type(prescription_data["vcg_type"] or "")
                    enriched_exercises = []

                    if vcg_type and vcg_type in Config.EXERCISE_LIBRARY:
                        all_exercises = []
                        for program in Config.EXERCISE_LIBRARY[vcg_type][
                            "programs"
                        ].values():
                            all_exercises.extend(program["exercises"])

                        for selected_ex in prescription_data.get("exercises", []):
                            for full_ex in all_exercises:
                                if full_ex["id"] == selected_ex.get("id"):
                                    enriched_exercises.append(
                                        {**full_ex, **selected_ex}
                                    )
                                    break

                    return jsonify(
                        {
                            "status": "success",
                            "has_prescription": True,
                            "prescription": prescription_data,
                            "enriched_exercises": enriched_exercises,
                        }
                    )

        return jsonify(
            {
                "status": "success",
                "has_prescription": False,
                "message": f"No {exercise_type.upper()} prescription found",
            }
        )

    except Exception as e:
        print(f"Error getting prescription: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/get_user_vcg_type/<user_id>", methods=["GET"])
def get_user_vcg_type(user_id):
    """Get VCG type from homerIdDetails.json for control group users."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        data = FileHandler.load_homer_id_details(current_session.login_place)

        for user in data.get("details", []):
            if user.get("homerID") == user_id:
                vcg_type = user.get("vcg_type")
                if vcg_type:
                    return jsonify({"status": "success", "vcg_type": vcg_type})
                else:
                    return jsonify(
                        {
                            "status": "error",
                            "message": "VCG type not found for this user",
                        }
                    ), 404

        return jsonify({"status": "error", "message": "User not found"}), 404

    except Exception as e:
        print(f"Error getting VCG type: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/get_controller_exercises/<user_id>", methods=["GET"])
def get_controller_exercises(user_id):
    """Get controller's latest exercise prescription."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        # Determine file path - look for latest version
        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
            vcg_folder = os.path.join(
                Config.META_DATA_PATH, place, user_id, "vcg_prescriptions"
            )
        else:
            place = current_session.login_place
            vcg_folder = os.path.join(
                Config.META_DATA_PATH,
                current_session.login_place,
                user_id,
                "vcg_prescriptions",
            )

        print(f"Looking for VCG prescriptions in: {vcg_folder}")

        # First try to get latest file (saved as latest.json by save_controller_exercises)
        latest_path = os.path.join(vcg_folder, "latest.json")

        if os.path.exists(latest_path):
            print(f"Found latest file: {latest_path}")
            with open(latest_path, "r") as f:
                prescription_data = json.load(f)
        else:
            # If no latest, try to find the most recent versioned file
            if not os.path.exists(vcg_folder):
                print(f"VCG folder does not exist: {vcg_folder}")
                return jsonify(
                    {
                        "status": "success",
                        "has_prescription": False,
                        "message": "No exercise prescription found",
                    }
                )

            json_files = [
                f
                for f in os.listdir(vcg_folder)
                if f.startswith("vcg_prescription_")
                and f.endswith(".json")
                and "latest" not in f
            ]
            if not json_files:
                print(f"No prescription files found in {vcg_folder}")
                return jsonify(
                    {
                        "status": "success",
                        "has_prescription": False,
                        "message": "No exercise prescription found",
                    }
                )

            # Get the most recent file (by timestamp in filename)
            latest_file = sorted(json_files, reverse=True)[0]
            latest_path = os.path.join(vcg_folder, latest_file)
            print(f"Found most recent file: {latest_path}")

            with open(latest_path, "r") as f:
                prescription_data = json.load(f)

        print(
            f"Prescription data loaded: {prescription_data.get('exercise_type')} with {len(prescription_data.get('exercises', []))} exercises"
        )

        # Get VCG type from prescription or fallback to homerIdDetails
        vcg_type = _normalise_vcg_type(prescription_data.get("vcg_type") or "")

        # If no vcg_type in prescription, try to get from homerIdDetails
        if not vcg_type:
            vcg_type = _normalise_vcg_type(FileHandler.get_user_vcg_type(place, user_id) or "")
            print(f"Got VCG type from homerIdDetails: {vcg_type}")

        selected_exercises = prescription_data.get("exercises", [])

        # For VCG exercises, we might want to enrich with additional details from library
        # But if the exercises already have all needed fields, we can use them directly
        enriched_exercises = []

        if vcg_type and vcg_type in Config.EXERCISE_LIBRARY:
            # Build a lookup dictionary of all exercises in this VCG type
            exercise_lookup = {}
            for prog_name, prog in Config.EXERCISE_LIBRARY[vcg_type][
                "programs"
            ].items():
                for ex in prog["exercises"]:
                    exercise_lookup[ex["id"]] = ex

            # Enrich each selected exercise with library data if available
            for selected_ex in selected_exercises:
                ex_id = selected_ex.get("id")
                if ex_id and ex_id in exercise_lookup:
                    # Merge library exercise with selected exercise (dosage from selected takes precedence)
                    library_ex = exercise_lookup[ex_id]
                    merged_ex = {**library_ex, **selected_ex}
                    enriched_exercises.append(merged_ex)
                else:
                    # If no library data, use the selected exercise as is
                    enriched_exercises.append(selected_ex)
        else:
            # If VCG type not found, just return the selected exercises
            enriched_exercises = selected_exercises

        print(f"Returning {len(enriched_exercises)} enriched exercises")

        return jsonify(
            {
                "status": "success",
                "has_prescription": True,
                "prescription": prescription_data,
                "enriched_exercises": enriched_exercises,
            }
        )

    except Exception as e:
        print(f"Error getting exercises: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/get_vcg_prescription_version/<user_id>/<timestamp>", methods=["GET"])
def get_vcg_prescription_version(user_id, timestamp):
    """Get a specific version of VCG prescription."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        # Determine file path
        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
            file_path = os.path.join(
                Config.META_DATA_PATH,
                place,
                user_id,
                "vcg_prescriptions",
                f"prescription_{timestamp}.json",
            )
        else:
            file_path = os.path.join(
                Config.META_DATA_PATH,
                current_session.login_place,
                user_id,
                "vcg_prescriptions",
                f"prescription_{timestamp}.json",
            )

        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "Version not found"}), 404

        with open(file_path, "r") as f:
            prescription_data = json.load(f)

        # Enrich exercises with full details
        vcg_type = _normalise_vcg_type(prescription_data.get("vcg_type") or "")
        enriched_exercises = []

        if vcg_type and vcg_type in Config.EXERCISE_LIBRARY:
            all_exercises = []
            for program in Config.EXERCISE_LIBRARY[vcg_type]["programs"].values():
                all_exercises.extend(program["exercises"])

            for selected_ex in prescription_data.get("exercises", []):
                for full_ex in all_exercises:
                    if full_ex["id"] == selected_ex.get("id"):
                        enriched_exercises.append({**full_ex, **selected_ex})
                        break

        return jsonify(
            {
                "status": "success",
                "prescription": prescription_data,
                "enriched_exercises": enriched_exercises,
            }
        )

    except Exception as e:
        print(f"Error getting prescription version: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/get_previous_prescription/<user_id>/<exercise_type>", methods=["GET"])
def get_previous_prescription(user_id, exercise_type):
    """Get the previous prescription (before latest) with full exercise details."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
        else:
            place = current_session.login_place

        folder_path = os.path.join(
            Config.META_DATA_PATH, place, user_id, f"{exercise_type}_prescriptions"
        )

        if not os.path.exists(folder_path):
            return jsonify({"status": "success", "has_prescription": False})

        # ADL files are saved as "prescription_TIMESTAMP.json" (no "adl_" prefix)
        # VCG files are saved as "vcg_prescription_TIMESTAMP.json"
        # Handle both naming conventions
        if exercise_type == "adl":
            files = [
                f for f in os.listdir(folder_path)
                if f.startswith("prescription_")
                and f.endswith(".json")
                and f != "latest.json"
            ]
        else:
            files = [
                f for f in os.listdir(folder_path)
                if f.startswith(f"{exercise_type}_prescription_")
                and f.endswith(".json")
                and "latest" not in f
            ]

        if not files:
            return jsonify({"status": "success", "has_prescription": False})

        # Sort by timestamp in filename (newest first)
        files.sort(reverse=True)

        # Need at least 2 files: latest + one previous
        if len(files) < 2:
            return jsonify({"status": "success", "has_prescription": False})

        previous_file = files[1]
        file_path = os.path.join(folder_path, previous_file)

        with open(file_path, "r") as f:
            prescription_data = json.load(f)

        enriched_exercises = []

        if exercise_type == "adl":
            # Enrich with ADL library data
            all_adl_exercises = []
            for category in Config.ADL_EXERCISE_LIBRARY.values():
                all_adl_exercises.extend(category["exercises"])

            selected = prescription_data.get("selected_exercises") or prescription_data.get("exercises", [])
            for selected_ex in selected:
                matched = next((ex for ex in all_adl_exercises if ex["id"] == selected_ex.get("id")), None)
                if matched:
                    enriched_exercises.append({**matched, **selected_ex})
                else:
                    enriched_exercises.append(selected_ex)
        else:
            # Enrich with VCG library data
            vcg_type = _normalise_vcg_type(prescription_data.get("vcg_type") or "")
            if vcg_type and vcg_type in Config.EXERCISE_LIBRARY:
                all_exercises = []
                for program in Config.EXERCISE_LIBRARY[vcg_type]["programs"].values():
                    all_exercises.extend(program["exercises"])
                for selected_ex in prescription_data.get("exercises", []):
                    for full_ex in all_exercises:
                        if full_ex["id"] == selected_ex.get("id"):
                            enriched_exercises.append({**full_ex, **selected_ex})
                            break

        return jsonify(
            {
                "status": "success",
                "has_prescription": True,
                "prescription": prescription_data,
                "enriched_exercises": enriched_exercises,
                "filename": previous_file,
            }
        )

    except Exception as e:
        print(f"Error getting previous prescription: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500