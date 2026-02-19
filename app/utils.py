import os
from datetime import datetime
from flask_mail import Message

from . import mail
from .models import VehicleRequestForm


# -------------------------
# Jinja template filters
# -------------------------
def register_template_filters(app):
    @app.template_filter("mmddyy")
    def mmddyy(value):
        if not value:
            return ""
        try:
            # date/datetime object
            return value.strftime("%m-%d-%Y")
        except AttributeError:
            # string -> try parse
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.strftime("%m-%d-%y")
                except ValueError:
                    continue
            return value

    @app.template_filter("comma")
    def comma_format(value):
        if value is None or value == "":
            return ""
        try:
            return f"{int(value):,}"
        except (ValueError, TypeError):
            try:
                return f"{float(value):,.0f}"
            except (ValueError, TypeError):
                return value


# -------------------------
# Form helpers
# -------------------------
def parse_date_or_none(s):
    s = (s or "").strip()
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


# -------------------------
# Mileage audit + alerting
# -------------------------
def _get_alert_email() -> str:
    # Read at call time (so env var changes take effect without restart)
    return os.environ.get("ALERT_EMAIL", "yuhuitestict@gmail.com").strip()


def parse_mileage_or_none(v):
    """
    Accepts strings like "12,345" or "12345".
    Returns int or None.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    s = s.replace(",", "")
    try:
        return int(s)
    except ValueError:
        return None


def send_mileage_error_alert(subject: str, body: str):
    """
    Best-effort email. Failure should not block submission.
    """
    alert_email = _get_alert_email()
    if not alert_email:
        print("[MileageAudit] ALERT_EMAIL not set; skipping email.")
        return

    try:
        msg = Message(subject=subject, sender=alert_email, recipients=[alert_email])
        msg.body = body
        mail.send(msg)
    except Exception as e:
        # do not block user; log for server debugging
        print("[MileageAudit] Email send failed:", repr(e))


def audit_vehicle_mileage_and_alert(record_id: int):
    """
    Runs after a record is submitted.
    Checks overlap + gap (>5 miles) for the same vehicle across other submitted records.
    Sends an email to ALERT_EMAIL if issues are found.
    """
    rec = VehicleRequestForm.query.get(record_id)
    if not rec or rec.status != "submitted":
        return

    vehicle = (rec.vehicle or "").strip()
    if not vehicle:
        return

    s0 = parse_mileage_or_none(rec.start_mileage)
    e0 = parse_mileage_or_none(rec.end_mileage)

    issues = []
    if s0 is None or e0 is None:
        issues.append("Invalid or missing mileage on submitted record.")
    elif e0 < s0:
        issues.append(f"End mileage < start mileage ({s0} -> {e0}).")

    # Other submitted records for same vehicle
    others = (
        VehicleRequestForm.query
        .filter_by(vehicle=vehicle, status="submitted")
        .filter(VehicleRequestForm.id != rec.id)
        .all()
    )

    parsed = []
    for r in others:
        s = parse_mileage_or_none(r.start_mileage)
        e = parse_mileage_or_none(r.end_mileage)
        if s is None or e is None:
            continue
        parsed.append((r, s, e))

    # 1) Overlap check: positive-length intersection
    overlaps = []
    if s0 is not None and e0 is not None:
        for r, s, e in parsed:
            if (s0 < e) and (e0 > s):
                overlaps.append((r, s, e))
        if overlaps:
            issues.append(f"Overlapping mileage range detected with {len(overlaps)} other record(s).")

    # 2) Gap check to "previous" record (by ID descending)
    prev = (
        VehicleRequestForm.query
        .filter_by(vehicle=vehicle, status="submitted")
        .filter(VehicleRequestForm.id != rec.id)
        .order_by(VehicleRequestForm.id.desc())
        .first()
    )
    if prev and s0 is not None:
        prev_e = parse_mileage_or_none(prev.end_mileage)
        if prev_e is not None:
            gap = s0 - prev_e
            if gap > 5:
                issues.append("Gap > 5 miles detected to the previous record.")

    if not issues:
        return

    subject = f"[Vehicle Mileage Check] {vehicle} - Submitted Record #{rec.id}"

    body = []
    body.append("Mileage audit detected potential issues.\n\n")
    body.append("Submitted record:\n")
    body.append(f"  - Record ID: {rec.id}\n")
    body.append(f"    Name: {rec.name}\n")
    body.append(f"    User Email: {rec.email}\n")
    body.append(f"    Vehicle: {rec.vehicle}\n")
    body.append(f"    Departure date: {rec.dep_date}\n")
    body.append(f"    Return date: {rec.ret_date}\n")
    body.append(f"    Start mileage: {s0}\n")
    body.append(f"    End mileage: {e0}\n")
    body.append(f"    Submitted Time: {rec.submitted_time}\n\n")

    body.append("Findings:\n")
    for it in issues:
        body.append(f"  - {it}\n")

    if overlaps:
        body.append("\nOverlapping record(s):\n")
        for r, s, e in overlaps:
            body.append(f"  - Record ID: {r.id}, Name: {r.name}, Start mileage: {s}, End mileage: {e}\n")

    send_mileage_error_alert(subject, "".join(body))
