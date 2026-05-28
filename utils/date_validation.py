"""Date Rule Framework — server side.

Single source of truth for clinical-date bounds on event modals. Spec lives in
`config/date_rules.json`; mirrored on the client by `_applyDateBounds` /
`_resolveDateBounds` in patient_detail.js. See CLAUDE.md → "Date Rule Framework"
for the full spec.

Phase 1: universal default rule (not before activation/enrollment, not after today).
Phase 2: per-event overrides + a small DSL (`<field>`, `<field> ± Nd`,
`event:<id>`, `today`) + optional `experimental`/`control` group selector.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Tuple

_RULES_PATH = Path(__file__).resolve().parent.parent / 'config' / 'date_rules.json'
_RULES_CACHE: Optional[dict] = None

# Comparisons are at datetime precision. A floor like "enrollDate" resolves to
# enrollDate at 00:00; a ceiling like "today" resolves to *now*. This way the
# user can pick any minute in the allowed window without HTML5 datetime-local
# rejecting an otherwise-valid same-day choice.
_DSL_OFFSET_RE = re.compile(r'^([A-Za-z_]\w*)\s*([+-])\s*(\d+)d$')


def _load_rules() -> dict:
    global _RULES_CACHE
    if _RULES_CACHE is None:
        with _RULES_PATH.open() as f:
            _RULES_CACHE = json.load(f)
    return _RULES_CACHE


def get_date_rules() -> dict:
    """Public read-only accessor — for the route that renders patient_detail.html
    to embed the spec as `window.DATE_RULES`, so the client resolver stays in
    lock-step with the server. Callers must NOT mutate the returned dict."""
    return _load_rules()


def _parse_dt(value: str) -> Optional[datetime]:
    """Parse an ISO datetime or date string. Returns datetime at 00:00 for
    date-only inputs."""
    if not value:
        return None
    try:
        # Strip seconds if present
        v = value.replace(' ', 'T')
        if 'T' in v:
            return datetime.strptime(v[:16], '%Y-%m-%dT%H:%M')
        return datetime.strptime(v[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def _fmt_display(dt: datetime, with_time: bool = True) -> str:
    """User-facing error format. With `with_time=True` (default) always shows
    'DD Mon YYYY HH:MM' — even at midnight — so datetime-precision bounds are
    unambiguous to the user (e.g. "after device setup at 14:30")."""
    return dt.strftime('%d %b %Y %H:%M') if with_time else dt.strftime('%d %b %Y')


def _latest_completion(events_data: dict, event_id: str) -> Optional[str]:
    """Most recent `completion_date` among completed entries with the given
    `protocol_event_id`. Looks in both `complete[]` and `free.<event_id>[]`."""
    if not events_data:
        return None
    candidates = []
    for entry in events_data.get('complete', []) or []:
        if entry.get('protocol_event_id') == event_id and entry.get('completion_date'):
            candidates.append(entry['completion_date'])
    for entry in events_data.get('free', {}).get(event_id, []) or []:
        if entry.get('completion_date'):
            candidates.append(entry['completion_date'])
    return max(candidates) if candidates else None


def _resolve_token(token: str, patient: dict, events_data: Optional[dict],
                   role: str) -> Optional[datetime]:
    """Resolve a single DSL token to a datetime. `role` is 'floor' or 'ceiling'
    (controls how `today` is interpreted)."""
    t = token.strip()

    # today sentinel
    if t == 'today':
        now = datetime.now()
        if role == 'ceiling':
            return now.replace(second=0, microsecond=0)
        return datetime.combine(now.date(), datetime.min.time())

    # event:<id> reference
    if t.startswith('event:'):
        eid = t[len('event:'):].strip()
        if not events_data:
            return None
        comp = _latest_completion(events_data, eid)
        return _parse_dt(comp) if comp else None

    # field + Nd / field - Nd
    m = _DSL_OFFSET_RE.match(t)
    if m:
        field, sign, n = m.group(1), m.group(2), int(m.group(3))
        base = _parse_dt((patient or {}).get(field))
        if base is None:
            return None
        delta = timedelta(days=n if sign == '+' else -n)
        # For a ceiling offset like "enrollDate + 5d" → end of that day (23:59),
        # so the user can pick any time up to that day's last minute.
        result = base + delta
        if role == 'ceiling':
            return result.replace(hour=23, minute=59, second=0, microsecond=0)
        return datetime.combine(result.date(), datetime.min.time())

    # bare field — normalized to start/end of day so that, e.g., a patient
    # activated at 11:00 still allows other events earlier on activation day.
    # (Event refs stay at full datetime precision — that's their whole point.)
    base = _parse_dt((patient or {}).get(t))
    if base is None:
        return None
    if role == 'ceiling':
        return base.replace(hour=23, minute=59, second=0, microsecond=0)
    return datetime.combine(base.date(), datetime.min.time())


def _rule_for_event(event_id: Optional[str], group: Optional[str]) -> Optional[dict]:
    """Look up the per-event rule, applying the experimental/control group
    selector when present. Returns None when the event has no override."""
    if not event_id:
        return None
    spec = _load_rules().get('events', {}).get(event_id)
    if not isinstance(spec, dict):
        return None
    if 'experimental' in spec or 'control' in spec:
        return spec.get(group) if group else None
    return spec


def resolve_bounds(patient: dict,
                   event_id: Optional[str] = None,
                   events_data: Optional[dict] = None,
                   rule_kind: str = 'completion'
                   ) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Return (min_dt, max_dt) for the given event (or the default rule when
    `event_id` is None or has no override). References that resolve to None are
    dropped; bounds reduce to the strictest defined values.

    `rule_kind`:
      - `'completion'` (default): falls back to `default_completion_rule` for
        clinical-event date inputs (the universal "between activation and
        today" floor/ceiling).
      - `'scheduling'`: falls back to `default_scheduling_rule` for future-date
        inputs (the `not_before: today` floor that keeps therapists from
        picking a past date when scheduling a visit/appointment).
    """
    rules = _load_rules()
    group = (patient or {}).get('group')
    default_key = 'default_scheduling_rule' if rule_kind == 'scheduling' else 'default_completion_rule'
    rule = _rule_for_event(event_id, group) or rules.get(default_key) or {}

    nb_tokens = rule.get('not_before') or []
    na_tokens = rule.get('not_after')  or []

    nb_vals = [v for v in (_resolve_token(t, patient, events_data, 'floor')   for t in nb_tokens) if v]
    na_vals = [v for v in (_resolve_token(t, patient, events_data, 'ceiling') for t in na_tokens) if v]

    min_dt = max(nb_vals) if nb_vals else None
    max_dt = min(na_vals) if na_vals else None
    return (min_dt, max_dt)


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_default_bounds(patient: dict) -> Tuple[Optional[date], date]:
    """Date-precision (min_date, max_date) for the default rule. Kept for
    backwards compatibility with the Phase 1 callers; new code should use
    `resolve_bounds`."""
    min_dt, max_dt = resolve_bounds(patient, event_id=None, events_data=None)
    return (min_dt.date() if min_dt else None,
            max_dt.date() if max_dt else date.today())


def validate_event_date(patient: dict, value: str,
                        event_id: Optional[str] = None,
                        events_data: Optional[dict] = None) -> Optional[str]:
    """Validate a clinical-event date against either the per-event rule (if
    one exists for `event_id`) or the default rule. Returns an error string
    when out of bounds, else None. Empty values return None — the route owns
    its required-field check."""
    if not value:
        return None
    dt = _parse_dt(value)
    if dt is None:
        return 'Date is not in a recognised format.'
    min_dt, max_dt = resolve_bounds(patient, event_id, events_data)
    if min_dt and dt < min_dt:
        return f'Date cannot be before {_fmt_display(min_dt)}.'
    if max_dt and dt > max_dt:
        return f'Date cannot be after {_fmt_display(max_dt)}.'
    return None


def validate_completion_date(patient: dict, value: str) -> Optional[str]:
    """Phase 1 wrapper — validates against the default rule only. New routes
    should use `validate_event_date` directly so per-event rules apply."""
    return validate_event_date(patient, value, event_id=None, events_data=None)
