"""
Patient notes — two kinds, same shape and mechanics:

1. Free notes (Notes tab)            → stored in notes.json, role-keyed buckets.
2. Retrospective event notes (Timeline) → stored on the event entry in
   protocol_events.json under `event_notes`, role-keyed buckets.

Both are immutable, role-keyed (each role sees only its own bucket; admin sees
all), rich text (Quill HTML, DOMPurify-sanitised on render), with gap-anchored
created_at/committed_at and one optional PDF. One optional PDF per note lives at
note_attachments/<note_id>.pdf, downloadable by the note's author (any role) or
admin. See docs/data_schemas.md and docs/pages.md.
"""

from flask import Blueprint, request, jsonify, session as flask_session, send_file
from datetime import datetime, timedelta
import uuid

from config import Config
from utils.data_access import (
    find_patient_folder, get_patients_path,
    read_patient_notes, write_patient_notes, write_patient_log,
)
from utils.protocol_events import read_protocol_events, write_protocol_events

bp = Blueprint('notes', __name__)

# privilege → alias role letter (also the bucket key)
_ROLE_LETTER = {'admin': 'A', 'therapist': 'T', 'engineer': 'E'}


def _bucket_for(privilege: str):
    """Return the notes bucket name for a privilege, or None if the role can't take notes."""
    return privilege if privilege in _ROLE_LETTER else None


# ── Shared note building / file serving ────────────────────────────────────────

def _save_note_pdf(folder: str, homer_id: str, attachment_rel: str, pdf_file) -> None:
    """Persist an uploaded PDF (S3 or local) at <patient>/<attachment_rel>."""
    if Config.USE_S3:
        from utils.s3_store import s3_upload_file
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            pdf_file.save(tmp.name)
            tmp_path = tmp.name
        try:
            s3_upload_file(tmp_path, f"{folder}/patients/{homer_id}/{attachment_rel}",
                           content_type='application/pdf')
        finally:
            _os.unlink(tmp_path)
    else:
        dest = get_patients_path(folder) / homer_id / attachment_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        pdf_file.save(str(dest))


def _build_note(folder: str, homer_id: str, author: str, alias: str):
    """Read+validate the current multipart request, save any PDF, build a note dict.

    Returns (note, None) on success, or (None, (message, status)) on failure.
    """
    title        = (request.form.get('title') or '').strip()
    content_html = (request.form.get('content_html') or '').strip()
    caption      = (request.form.get('caption') or '').strip()
    gap_raw      = request.form.get('gap_seconds')
    pdf_file     = request.files.get('file')

    if not title:
        return None, ('Title is required.', 400)
    if not content_html or content_html in ('<p><br></p>', '<p></p>'):
        return None, ('Note body is required.', 400)
    if pdf_file and pdf_file.filename:
        if not pdf_file.filename.lower().endswith('.pdf'):
            return None, ('Attachment must be a PDF file.', 400)
        if not caption:
            return None, ('Caption is required when a file is attached.', 400)

    # committed_at is server-authoritative; created_at = committed_at − gap (gap
    # measured client-side from modal-open to save) → created ≤ committed, skew-immune.
    committed_dt = datetime.now()
    try:
        gap = max(0.0, float(gap_raw)) if gap_raw is not None else 0.0
    except (TypeError, ValueError):
        gap = 0.0
    created_dt = committed_dt - timedelta(seconds=gap)

    note_id = str(uuid.uuid4())
    note = {
        'id':                 note_id,
        'alias':              alias,
        'author':             author,
        'title':              title,
        'content_html':       content_html,
        'created_at':         created_dt.strftime('%Y-%m-%dT%H:%M:%S'),
        'committed_at':       committed_dt.strftime('%Y-%m-%dT%H:%M:%S'),
        'attachment':         None,
        'attachment_caption': None,
    }
    if pdf_file and pdf_file.filename:
        attachment_rel = f'note_attachments/{note_id}.pdf'
        _save_note_pdf(folder, homer_id, attachment_rel, pdf_file)
        note['attachment']         = attachment_rel
        note['attachment_caption'] = caption
    return note, None


def _serve_note_attachment(folder: str, homer_id: str, note: dict, download_name: str):
    """Serve a note's PDF after the caller has been authorised."""
    attachment_rel = note.get('attachment')
    if not attachment_rel:
        return jsonify({'error': 'Attachment not found'}), 404
    if Config.USE_S3:
        from utils.s3_store import s3_get_bytes
        import io
        data = s3_get_bytes(f"{folder}/patients/{homer_id}/{attachment_rel}")
        if data is None:
            return jsonify({'error': 'Attachment not found'}), 404
        return send_file(io.BytesIO(data), mimetype='application/pdf',
                         as_attachment=False, download_name=download_name)
    path = get_patients_path(folder) / homer_id / attachment_rel
    if not path.exists():
        return jsonify({'error': 'Attachment not found'}), 404
    return send_file(str(path), mimetype='application/pdf',
                     as_attachment=False, download_name=download_name)


def _can_download(note: dict, privilege: str) -> bool:
    """Note attachments: author (any role) or admin."""
    return privilege == 'admin' or note.get('author') == flask_session.get('loginid')


# ── Free notes (Notes tab) ─────────────────────────────────────────────────────

def _next_alias(bucket_list: list, role_letter: str) -> str:
    """Next per-bucket free-note alias: Notes-<R>-NNNN (oldest = 0001)."""
    return f"Notes-{role_letter}-{len(bucket_list) + 1:04d}"


@bp.route('/api/patients/<homer_id>/notes', methods=['GET'])
def api_list_notes(homer_id):
    """Free notes visible to the caller, newest first. admin → all buckets; else own."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    privilege = flask_session.get('privilege', '')
    if _bucket_for(privilege) is None:
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    notes_data = read_patient_notes(folder, homer_id)
    is_admin = privilege == 'admin'
    notes = ([n for bucket in notes_data.values() for n in bucket] if is_admin
             else list(notes_data.get(privilege, [])))
    notes.sort(key=lambda n: n.get('created_at') or '', reverse=True)
    return jsonify({'notes': notes, 'is_admin': is_admin})


@bp.route('/api/patients/<homer_id>/notes', methods=['POST'])
def api_create_note(homer_id):
    """Create an immutable free note in the caller's role bucket (multipart form)."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    privilege = flask_session.get('privilege', '')
    bucket = _bucket_for(privilege)
    if bucket is None:
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    notes_data = read_patient_notes(folder, homer_id)
    notes_data.setdefault(bucket, [])
    alias = _next_alias(notes_data[bucket], _ROLE_LETTER[bucket])

    note, err = _build_note(folder, homer_id, flask_session.get('loginid', 'unknown'), alias)
    if err:
        return jsonify({'error': err[0]}), err[1]

    notes_data[bucket].append(note)
    write_patient_notes(folder, homer_id, notes_data)
    write_patient_log(folder, homer_id, flask_session.get('loginid', 'unknown'),
                      flask_session.get('session_id', 0), f"Note created — {note['alias']}")
    return jsonify({'ok': True, 'note': note})


@bp.route('/api/patients/<homer_id>/notes/<note_id>/attachment', methods=['GET'])
def api_download_note_attachment(homer_id, note_id):
    """Serve a free note's PDF. Allowed for the note's author (any role) or admin."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    privilege = flask_session.get('privilege', '')
    if _bucket_for(privilege) is None:
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    notes_data = read_patient_notes(folder, homer_id)
    note = next((n for bucket in notes_data.values() for n in bucket if n.get('id') == note_id), None)
    if not note:
        return jsonify({'error': 'Note not found'}), 404
    if not _can_download(note, privilege):
        return jsonify({'error': 'Forbidden'}), 403
    return _serve_note_attachment(folder, homer_id, note, f"{note.get('alias', 'note')}.pdf")


# ── Retrospective event notes (Timeline) ───────────────────────────────────────

def _iter_event_entries(events_data: dict):
    """Yield every event entry that can hold event_notes (complete[] + free dicts/lists)."""
    for e in events_data.get('complete', []):
        if isinstance(e, dict):
            yield e
    for v in events_data.get('free', {}).values():
        if isinstance(v, list):
            for e in v:
                if isinstance(e, dict):
                    yield e
        elif isinstance(v, dict) and v.get('id'):
            yield v


def _find_event_entry(events_data: dict, event_id: str):
    return next((e for e in _iter_event_entries(events_data) if e.get('id') == event_id), None)


def _next_event_note_alias(events_data: dict, role: str) -> str:
    """Next event-note alias for a role: EvtNote-<R>-NNNN, sequenced patient-wide."""
    count = sum(len((e.get('event_notes') or {}).get(role, [])) for e in _iter_event_entries(events_data))
    return f"EvtNote-{_ROLE_LETTER[role]}-{count + 1:04d}"


@bp.route('/api/patients/<homer_id>/events/<event_id>/notes', methods=['GET'])
def api_list_event_notes(homer_id, event_id):
    """Retrospective notes for one event, role-filtered, newest first."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    privilege = flask_session.get('privilege', '')
    if _bucket_for(privilege) is None:
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    events_data = read_protocol_events(folder, homer_id)
    entry = _find_event_entry(events_data or {}, event_id)
    if entry is None:
        return jsonify({'error': 'Event not found'}), 404

    buckets = entry.get('event_notes') or {}
    is_admin = privilege == 'admin'
    notes = ([n for b in buckets.values() for n in b] if is_admin
             else list(buckets.get(privilege, [])))
    notes.sort(key=lambda n: n.get('created_at') or '', reverse=True)
    return jsonify({'notes': notes, 'is_admin': is_admin})


@bp.route('/api/patients/<homer_id>/events/<event_id>/notes', methods=['POST'])
def api_create_event_note(homer_id, event_id):
    """Create an immutable retrospective note on an event, in the caller's role bucket."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    privilege = flask_session.get('privilege', '')
    bucket = _bucket_for(privilege)
    if bucket is None:
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found'}), 404
    entry = _find_event_entry(events_data, event_id)
    if entry is None:
        return jsonify({'error': 'Event not found'}), 404

    alias = _next_event_note_alias(events_data, bucket)
    note, err = _build_note(folder, homer_id, flask_session.get('loginid', 'unknown'), alias)
    if err:
        return jsonify({'error': err[0]}), err[1]

    entry.setdefault('event_notes', {'admin': [], 'therapist': [], 'engineer': []})
    entry['event_notes'].setdefault(bucket, [])
    entry['event_notes'][bucket].append(note)
    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, flask_session.get('loginid', 'unknown'),
                      flask_session.get('session_id', 0), f"Event note created — {note['alias']}")
    return jsonify({'ok': True, 'note': note})


@bp.route('/api/patients/<homer_id>/event-notes/<note_id>/attachment', methods=['GET'])
def api_download_event_note_attachment(homer_id, note_id):
    """Serve an event note's PDF. Allowed for the note's author (any role) or admin."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    privilege = flask_session.get('privilege', '')
    if _bucket_for(privilege) is None:
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    events_data = read_protocol_events(folder, homer_id) or {}
    note = None
    for entry in _iter_event_entries(events_data):
        for b in (entry.get('event_notes') or {}).values():
            note = next((n for n in b if n.get('id') == note_id), None)
            if note:
                break
        if note:
            break
    if not note:
        return jsonify({'error': 'Note not found'}), 404
    if not _can_download(note, privilege):
        return jsonify({'error': 'Forbidden'}), 403
    return _serve_note_attachment(folder, homer_id, note, f"{note.get('alias', 'note')}.pdf")
