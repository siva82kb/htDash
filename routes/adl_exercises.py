# routes/adl_exercises.py
from flask import Blueprint, request, jsonify, send_file
from config import Config
from models.user import current_session
import os
import json
from datetime import datetime
import subprocess
import tempfile


def resolve_login_place(data=None):
    """Return login_place from session if live; restore it from login_id in
    request body if the Flask session was wiped (e.g. server restart) while
    the user's browser still has localStorage credentials."""
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
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import qrcode
from io import BytesIO

bp = Blueprint("adl", __name__)


@bp.route("/get_adl_options", methods=["GET"])
def get_adl_options():
    """Get available ADL categories."""
    return jsonify(
        {
            "status": "success",
            "adl_categories": list(Config.ADL_EXERCISE_LIBRARY.keys()),
        }
    )


@bp.route("/get_adl_exercises/<category>", methods=["GET"])
def get_adl_exercises(category):
    """Get exercises for a specific ADL category."""
    if category not in Config.ADL_EXERCISE_LIBRARY:
        return jsonify({"status": "error", "message": "Invalid category"}), 400

    exercises = Config.ADL_EXERCISE_LIBRARY[category]["exercises"]

    return jsonify(
        {
            "status": "success",
            "category_name": Config.ADL_EXERCISE_LIBRARY[category]["name"],
            "exercises": exercises,
        }
    )


@bp.route("/get_all_adl_exercises", methods=["GET"])
def get_all_adl_exercises():
    """Get all ADL exercises from all categories at once - optimized for performance."""
    all_exercises = []
    for category, category_data in Config.ADL_EXERCISE_LIBRARY.items():
        for ex in category_data.get("exercises", []):
            all_exercises.append({**ex, "category": category})

    return jsonify({"status": "success", "exercises": all_exercises})


@bp.route("/print_adl_exercises/<user_id>", methods=["GET"])
def print_adl_exercises(user_id):
    """Generate PDF with ADL exercises for printing."""
    try:
        # Get ADL prescription — canonical path is adl_prescriptions/latest.json
        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
        else:
            place = current_session.login_place

        if Config.USE_S3:
            from utils.s3_store import s3_read_json
            prescription = s3_read_json(f"{place}/{user_id}/adl_prescriptions/latest.json")
            if not prescription:
                return jsonify({"error": "No ADL prescription found"}), 404
        else:
            file_path = os.path.join(
                Config.META_DATA_PATH, place, user_id, "adl_prescriptions", "latest.json"
            )
            if not os.path.exists(file_path):
                return jsonify({"error": "No ADL prescription found"}), 404
            with open(file_path, "r") as f:
                prescription = json.load(f)

        # Create PDF
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, f"ADL Exercise Prescription")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 70, f"Patient ID: {user_id}")
        c.drawString(
            50,
            height - 85,
            f"Date: {prescription.get('created_at', datetime.now().strftime('%Y-%m-%d'))}",
        )

        y = height - 120

        # Exercises
        for idx, exercise in enumerate(prescription.get("selected_exercises", []), 1):
            if y < 100:  # New page
                c.showPage()
                y = height - 50
                c.setFont("Helvetica-Bold", 16)
                c.drawString(50, y, f"ADL Exercise Prescription (Continued)")
                y -= 30
                c.setFont("Helvetica", 12)

            # Exercise title
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, f"Exercise {idx}: {exercise.get('short_name', '')}")
            y -= 20

            # Dosage
            c.setFont("Helvetica", 12)
            dosage = exercise.get("dosage", {})
            c.drawString(
                70,
                y,
                f"Sets: {dosage.get('sets', 3)} | Reps: {dosage.get('reps', 10)} | Duration: {dosage.get('duration', '30 seconds')}",
            )
            y -= 20

            # Instructions
            c.drawString(
                70,
                y,
                f"Instructions: {exercise.get('instructions', 'No instructions available')[:80]}...",
            )
            y -= 30

            # QR Code for video
            if exercise.get("youtube_url"):
                qr = qrcode.QRCode(version=1, box_size=3, border=1)
                qr.add_data(exercise["youtube_url"])
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")

                # Save QR to temp file
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    qr_img.save(tmp.name)
                    c.drawImage(tmp.name, width - 150, y - 10, width=80, height=80)
                    os.unlink(tmp.name)

            y -= 50

        c.save()
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"ADL_Exercises_{user_id}.pdf",
            mimetype="application/pdf",
        )

    except Exception as e:
        print(f"Error printing ADL exercises: {e}")
        return jsonify({"error": str(e)}), 500

    # routes/adl.py - Add these endpoints


@bp.route("/save_adl_prescription", methods=["POST"])
def save_adl_prescription():
    """Save ADL exercise prescription with versioning."""
    try:
        data = request.get_json()
        login_place = resolve_login_place(data)
        if not login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        user_id = data.get("user_id")
        selected_exercises = data.get("exercises", [])

        if not user_id:
            return jsonify({"status": "error", "message": "Missing user ID"}), 400

        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
        else:
            place = current_session.login_place

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Merge existing timeRecords before overwriting
        if Config.USE_S3:
            from utils.s3_store import s3_read_json, s3_write_json
            existing_data = s3_read_json(f"{place}/{user_id}/adl_prescriptions/latest.json") or {}
        else:
            latest_path = os.path.join(Config.META_DATA_PATH, place, user_id,
                                       "adl_prescriptions", "latest.json")
            existing_data = {}
            if os.path.exists(latest_path):
                try:
                    with open(latest_path) as f:
                        existing_data = json.load(f)
                except Exception:
                    pass

        existing_exercises = existing_data.get("exercises", existing_data.get("selected_exercises", []))
        for new_ex in selected_exercises:
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

        prescription_data = {
            "user_id": user_id,
            "exercises": selected_exercises,
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "version": timestamp,
        }

        if Config.USE_S3:
            s3_prefix = f"{place}/{user_id}/adl_prescriptions"
            s3_write_json(f"{s3_prefix}/prescription_{timestamp}.json", prescription_data)
            s3_write_json(f"{s3_prefix}/latest.json", prescription_data)
        else:
            import shutil
            base_path = os.path.join(Config.META_DATA_PATH, place, user_id)
            adl_folder = os.path.join(base_path, "adl_prescriptions")
            os.makedirs(adl_folder, exist_ok=True)
            file_path = os.path.join(adl_folder, f"prescription_{timestamp}.json")
            with open(file_path, "w") as f:
                json.dump(prescription_data, f, indent=2)
            shutil.copy2(file_path, os.path.join(adl_folder, "latest.json"))
            try:
                s3_prefix = f"{place}/{user_id}/adl_prescriptions"
                subprocess.run(["aws", "s3", "cp", file_path,
                                f"s3://{Config.BUCKET_NAME}/{s3_prefix}/prescription_{timestamp}.json"],
                               capture_output=True, text=True)
                subprocess.run(["aws", "s3", "cp", os.path.join(adl_folder, "latest.json"),
                                f"s3://{Config.BUCKET_NAME}/{s3_prefix}/latest.json"],
                               capture_output=True, text=True)
            except Exception as s3_error:
                print(f"S3 upload error: {s3_error}")

        return jsonify(
            {
                "status": "success",
                "message": "ADL prescription saved successfully",
                "timestamp": timestamp,
            }
        )

    except Exception as e:
        print(f"Error saving ADL exercises: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# @bp.route("/get_adl_prescription/<user_id>", methods=["GET"])
# def get_adl_prescription(user_id):
#     """Get the latest ADL prescription for a user."""
#     try:
#         if not current_session.login_place:
#             return jsonify({"status": "error", "message": "Not logged in"}), 401

#         # Determine file path
#         if current_session.is_admin():
#             place = current_session.place_info.get(user_id, current_session.login_place)
#             latest_path = os.path.join(
#                 Config.META_DATA_PATH,
#                 place,
#                 user_id,
#                 "adl_prescriptions",
#                 "latest.json",
#             )
#             adl_folder = os.path.join(
#                 Config.META_DATA_PATH, place, user_id, "adl_prescriptions"
#             )
#         else:
#             latest_path = os.path.join(
#                 Config.META_DATA_PATH,
#                 current_session.login_place,
#                 user_id,
#                 "adl_prescriptions",
#                 "latest.json",
#             )
#             adl_folder = os.path.join(
#                 Config.META_DATA_PATH,
#                 current_session.login_place,
#                 user_id,
#                 "adl_prescriptions",
#             )

#         if not os.path.exists(latest_path):
#             return jsonify({"status": "success", "has_prescription": False})

#         with open(latest_path, "r") as f:
#             prescription_data = json.load(f)

#         # Get all versions for history
#         all_versions = []
#         if os.path.exists(adl_folder):
#             for file in os.listdir(adl_folder):
#                 if (
#                     file.startswith("prescription_")
#                     and file.endswith(".json")
#                     and file != "latest.json"
#                 ):
#                     version_path = os.path.join(adl_folder, file)
#                     with open(version_path, "r") as vf:
#                         try:
#                             version_data = json.load(vf)
#                             all_versions.append(
#                                 {
#                                     "timestamp": version_data.get(
#                                         "version",
#                                         file.replace("prescription_", "").replace(
#                                             ".json", ""
#                                         ),
#                                     ),
#                                     "created_at": version_data.get("created_at", ""),
#                                     "exercise_count": len(
#                                         version_data.get("selected_exercises", [])
#                                     ),
#                                 }
#                             )
#                         except:
#                             pass

#         # Sort versions by timestamp (newest first)
#         all_versions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

#         # Enrich exercises with full details from library
#         enriched_exercises = []
#         all_exercises = []
#         for category in Config.ADL_EXERCISE_LIBRARY.values():
#             all_exercises.extend(category["exercises"])

#         for selected_ex in prescription_data.get("selected_exercises", []):
#             for full_ex in all_exercises:
#                 if full_ex["id"] == selected_ex.get("id"):
#                     # Merge full exercise details with selected exercise (including dosage)
#                     merged_ex = {**full_ex, **selected_ex}
#                     enriched_exercises.append(merged_ex)
#                     break

#         return jsonify(
#             {
#                 "status": "success",
#                 "has_prescription": True,
#                 "prescription": prescription_data,
#                 "enriched_exercises": enriched_exercises,
#                 "versions": all_versions,
#             }
#         )

#     except Exception as e:
#         print(f"Error getting ADL prescription: {e}")
#         return jsonify({"status": "error", "message": str(e)}), 500

@bp.route("/get_adl_prescription/<user_id>", methods=["GET"])
def get_adl_prescription(user_id):
    """Get the latest ADL prescription for a user."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
        else:
            place = current_session.login_place

        if Config.USE_S3:
            from utils.s3_store import s3_read_json, s3_list_prefix
            s3_prefix = f"{place}/{user_id}/adl_prescriptions"
            prescription_data = s3_read_json(f"{s3_prefix}/latest.json")
            if not prescription_data:
                return jsonify({"status": "success", "has_prescription": False})
            all_versions = []
            for key in s3_list_prefix(s3_prefix + "/"):
                fname = key.split("/")[-1]
                if fname.startswith("prescription_") and fname.endswith(".json"):
                    vdata = s3_read_json(key) or {}
                    vexercises = vdata.get("selected_exercises") or vdata.get("exercises", [])
                    all_versions.append({
                        "timestamp": vdata.get("version", fname.replace("prescription_","").replace(".json","")),
                        "created_at": vdata.get("created_at", ""),
                        "exercise_count": len(vexercises),
                    })
        else:
            adl_folder  = os.path.join(Config.META_DATA_PATH, place, user_id, "adl_prescriptions")
            latest_path = os.path.join(adl_folder, "latest.json")

            if not os.path.exists(latest_path):
                return jsonify({"status": "success", "has_prescription": False})

            with open(latest_path, "r") as f:
                prescription_data = json.load(f)

            all_versions = []
            if os.path.exists(adl_folder):
                for file in os.listdir(adl_folder):
                    if file.startswith("prescription_") and file.endswith(".json") and file != "latest.json":
                        try:
                            with open(os.path.join(adl_folder, file)) as vf:
                                version_data = json.load(vf)
                            vexercises = version_data.get("selected_exercises") or version_data.get("exercises", [])
                            all_versions.append({
                                "timestamp": version_data.get("version", file.replace("prescription_","").replace(".json","")),
                                "created_at": version_data.get("created_at", ""),
                                "exercise_count": len(vexercises),
                            })
                        except Exception:
                            pass

        # Handle both possible keys
        exercises = prescription_data.get("selected_exercises") or prescription_data.get("exercises", [])

        # Sort newest first
        all_versions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # --------------------------
        # Enrich exercises
        # --------------------------
        enriched_exercises = []

        all_exercises = []
        for category in Config.ADL_EXERCISE_LIBRARY.values():
            all_exercises.extend(category["exercises"])

        for selected_ex in exercises:
            for full_ex in all_exercises:
                if full_ex["id"] == selected_ex.get("id"):
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
        print(f"Error getting ADL prescription: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route("/get_exercise_by_id/<exercise_id>", methods=["GET"])
def get_exercise_by_id(exercise_id):
    """Get full exercise details by ID."""
    try:
        # Search through all categories
        for category in Config.ADL_EXERCISE_LIBRARY.values():
            for exercise in category["exercises"]:
                if exercise["id"] == exercise_id:
                    return jsonify({"status": "success", "exercise": exercise})

        return jsonify({"status": "error", "message": "Exercise not found"}), 404

    except Exception as e:
        print(f"Error getting exercise: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500