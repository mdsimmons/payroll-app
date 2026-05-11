import os
import sys
import json
import csv
import re
from datetime import datetime, timedelta
from io import StringIO
from flask import Flask, render_template, request, jsonify, Response, session, redirect
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from payroll import load_employees, calculate_payroll

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

USER_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")


def load_users():
    if not os.path.exists(USER_DATA_FILE):
        return {ADMIN_USER: ADMIN_PASS}
    with open(USER_DATA_FILE, "r") as f:
        return json.load(f)


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            if request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


EMPLOYEES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "employees.json")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payroll_history.json")
TAX_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tax_settings.json")
APP_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_settings.json")
SCHEDULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedules.json")
TIMECLOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timeclock.json")
TIMEOFF_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "time_off.json")
SHIFT_SWAPS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shift_swaps.json")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def load_tax_settings():
    if not os.path.exists(TAX_SETTINGS_FILE):
        return None
    with open(TAX_SETTINGS_FILE, "r") as f:
        return json.load(f)


def load_app_settings():
    if not os.path.exists(APP_SETTINGS_FILE):
        return {"week_start_day": 6}
    with open(APP_SETTINGS_FILE, "r") as f:
        return json.load(f)


def save_app_settings(settings):
    with open(APP_SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def get_week_range(date_str, week_start_day=0):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    diff = (dt.weekday() - week_start_day + 7) % 7
    start = dt - timedelta(days=diff)
    end = start + timedelta(days=6)
    return {
        "week_start": start.strftime("%Y-%m-%d"),
        "week_end": end.strftime("%Y-%m-%d"),
        "week_label": f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}",
    }


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    users = load_users()
    if users.get(data.get("username")) == data.get("password"):
        session["user"] = data["username"]
        session.permanent = True
        if data.get("remember"):
            app.permanent_session_lifetime = timedelta(days=30)
        else:
            app.permanent_session_lifetime = timedelta(hours=2)
        return jsonify({"ok": True})
    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/session")
def check_session():
    return jsonify({"user": session.get("user")})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/employees", methods=["GET"])
@require_login
def get_employees():
    try:
        employees = load_employees(EMPLOYEES_FILE)
        return jsonify(employees)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/employees", methods=["POST"])
@require_login
def add_employee():
    try:
        with open(EMPLOYEES_FILE, "r") as f:
            data = json.load(f)

        new_emp = request.json
        existing_ids = [e["id"] for e in data["employees"]]
        emp_num = len(data["employees"]) + 1
        new_emp["id"] = f"EMP{emp_num:03d}"

        while new_emp["id"] in existing_ids:
            emp_num += 1
            new_emp["id"] = f"EMP{emp_num:03d}"

        new_emp["pay_type"] = new_emp.get("pay_type", "hourly")
        new_emp["hourly_rate"] = float(new_emp["hourly_rate"])
        new_emp["salary_amount"] = float(new_emp.get("salary_amount", 0))
        new_emp["federal_allowances"] = int(new_emp.get("federal_allowances", 0))
        new_emp["state_allowances"] = int(new_emp.get("state_allowances", 0))
        new_emp["step2_checked"] = bool(new_emp.get("step2_checked", False))
        new_emp["overtime_rate"] = float(new_emp.get("overtime_rate", 0))
        new_emp["tipped"] = bool(new_emp.get("tipped", False))
        new_emp["fed_add_withholding_type"] = new_emp.get("fed_add_withholding_type", "amount")
        new_emp["fed_add_withholding_value"] = float(new_emp.get("fed_add_withholding_value", 0))
        new_emp["state_add_withholding_type"] = new_emp.get("state_add_withholding_type", "amount")
        new_emp["state_add_withholding_value"] = float(new_emp.get("state_add_withholding_value", 0))

        # Auto-generate unique 4-digit PIN
        import random
        existing_pins = {e.get("pin") for e in data["employees"]}
        while True:
            pin = f"{random.randint(0,9999):04d}"
            if pin not in existing_pins:
                break
        new_emp["pin"] = pin

        # Auto-generate username from name (lowercase, no spaces)
        base_username = re.sub(r'[^a-zA-Z0-9]', '', new_emp["name"]).lower()
        username = base_username
        existing_usernames = {e.get("username") for e in data["employees"] if e.get("username")}
        suffix = 1
        while username in existing_usernames:
            username = f"{base_username}{suffix}"
            suffix += 1
        new_emp["username"] = username

        data["employees"].append(new_emp)

        with open(EMPLOYEES_FILE, "w") as f:
            json.dump(data, f, indent=2)

        return jsonify(new_emp), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/employees/<emp_id>", methods=["PUT"])
@require_login
def update_employee(emp_id):
    try:
        with open(EMPLOYEES_FILE, "r") as f:
            data = json.load(f)

        updated = request.json
        found = False
        for i, emp in enumerate(data["employees"]):
            if emp["id"] == emp_id:
                data["employees"][i] = updated
                data["employees"][i]["id"] = emp_id
                data["employees"][i]["pay_type"] = updated.get("pay_type", "hourly")
                data["employees"][i]["hourly_rate"] = float(updated["hourly_rate"])
                data["employees"][i]["salary_amount"] = float(updated.get("salary_amount", 0))
                data["employees"][i]["federal_allowances"] = int(updated.get("federal_allowances", 0))
                data["employees"][i]["state_allowances"] = int(updated.get("state_allowances", 0))
                data["employees"][i]["step2_checked"] = bool(updated.get("step2_checked", False))
                data["employees"][i]["overtime_rate"] = float(updated.get("overtime_rate", 0))
                data["employees"][i]["tipped"] = bool(updated.get("tipped", False))
                data["employees"][i]["fed_add_withholding_type"] = updated.get("fed_add_withholding_type", "amount")
                data["employees"][i]["fed_add_withholding_value"] = float(updated.get("fed_add_withholding_value", 0))
                data["employees"][i]["state_add_withholding_type"] = updated.get("state_add_withholding_type", "amount")
                data["employees"][i]["state_add_withholding_value"] = float(updated.get("state_add_withholding_value", 0))
                # Auto-generate username from name
                base_username = re.sub(r'[^a-zA-Z0-9]', '', data["employees"][i]["name"]).lower()
                username = base_username
                existing_usernames = {e.get("username") for e in data["employees"] if e.get("username") and e["id"] != emp_id}
                suffix = 1
                while username in existing_usernames:
                    username = f"{base_username}{suffix}"
                    suffix += 1
                data["employees"][i]["username"] = username

                found = True
                break

        if not found:
            return jsonify({"error": "Employee not found"}), 404

        with open(EMPLOYEES_FILE, "w") as f:
            json.dump(data, f, indent=2)

        return jsonify(data["employees"][i])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/employees/<emp_id>", methods=["DELETE"])
@require_login
def delete_employee(emp_id):
    try:
        with open(EMPLOYEES_FILE, "r") as f:
            data = json.load(f)

        data["employees"] = [e for e in data["employees"] if e["id"] != emp_id]

        with open(EMPLOYEES_FILE, "w") as f:
            json.dump(data, f, indent=2)

        return jsonify({"message": "Employee deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/weeks", methods=["GET"])
@require_login
def get_history_weeks():
    try:
        history = load_history()
        weeks = sorted(history.keys(), reverse=True)
        result = []
        for week_key in weeks:
            entry = history[week_key]
            result.append({
                "week_key": week_key,
                "week_label": entry["week_label"],
                "week_start": entry["week_start"],
                "week_end": entry["week_end"],
                "summary": entry.get("summary"),
                "has_results": "results" in entry,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<week_key>", methods=["GET"])
@require_login
def get_history_week(week_key):
    try:
        history = load_history()
        if week_key not in history:
            return jsonify({"error": "Week not found"}), 404
        return jsonify(history[week_key])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<week_key>", methods=["DELETE"])
@require_login
def delete_history_week(week_key):
    try:
        history = load_history()
        if week_key not in history:
            return jsonify({"error": "Week not found"}), 404
        del history[week_key]
        save_history(history)
        return jsonify({"message": "Week deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tax-settings", methods=["GET"])
@require_login
def get_tax_settings():
    try:
        settings = load_tax_settings()
        if settings is None:
            return jsonify({"using_defaults": True})
        return jsonify(settings)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tax-settings", methods=["PUT"])
@require_login
def save_tax_settings():
    try:
        settings = request.json
        with open(TAX_SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return jsonify({"message": "Settings saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tax-settings", methods=["DELETE"])
@require_login
def reset_tax_settings():
    try:
        if os.path.exists(TAX_SETTINGS_FILE):
            os.remove(TAX_SETTINGS_FILE)
        return jsonify({"message": "Settings reset to defaults"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/app-settings", methods=["GET"])
@require_login
def get_app_settings():
    try:
        return jsonify(load_app_settings())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/app-settings", methods=["PUT"])
@require_login
def save_app_settings_route():
    try:
        settings = request.json
        save_app_settings(settings)
        return jsonify({"message": "Settings saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/change-password", methods=["POST"])
@require_login
def change_password():
    try:
        data = request.json
        users = load_users()
        current_user = session["user"]

        if users.get(current_user) != data.get("current_password"):
            return jsonify({"error": "Current password is incorrect"}), 403

        new_password = data.get("new_password")
        new_username = (data.get("new_username") or "").strip() or current_user

        if not new_password or len(new_password) < 1:
            return jsonify({"error": "New password is required"}), 400

        del users[current_user]
        users[new_username] = new_password
        with open(USER_DATA_FILE, "w") as f:
            json.dump(users, f, indent=2)
        session["user"] = new_username

        return jsonify({"message": "Credentials updated", "username": new_username})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Scheduling ─────────────────────────────────────────────
@app.route("/api/schedules", methods=["GET"])
@require_login
def get_schedules():
    data = load_json(SCHEDULES_FILE, {"shifts": {}, "status": "draft", "open_shifts": [], "week_start": "", "week_label": ""})
    return jsonify(data)


@app.route("/api/schedules", methods=["PUT"])
@require_login
def save_schedules():
    try:
        data = request.json
        existing = load_json(SCHEDULES_FILE, {})
        existing.update(data)
        save_json(SCHEDULES_FILE, existing)
        return jsonify({"message": "Schedules saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedules/publish", methods=["POST"])
@require_login
def publish_schedule():
    data = load_json(SCHEDULES_FILE, {})
    data["status"] = "published"
    save_json(SCHEDULES_FILE, data)
    label = data.get("week_label", "this week")
    create_notification("schedule_published", f"Schedule for {label} has been published")
    return jsonify({"message": "Schedule published"})


@app.route("/api/schedules/unpublish", methods=["POST"])
@require_login
def unpublish_schedule():
    data = load_json(SCHEDULES_FILE, {})
    data["status"] = "draft"
    save_json(SCHEDULES_FILE, data)
    label = data.get("week_label", "this week")
    create_notification("schedule_unpublished", f"Schedule for {label} has been unpublished")
    return jsonify({"message": "Schedule set to draft"})


@app.route("/api/schedules/copy", methods=["POST"])
@require_login
def copy_schedule():
    data = load_json(SCHEDULES_FILE, {"shifts": {}})
    data["status"] = "draft"
    save_json(SCHEDULES_FILE, data)
    return jsonify({"message": "Schedule copied"})


# ─── Schedule Templates ─────────────────────────────────────
SCHEDULE_TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule_templates.json")
NOTIFICATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notifications.json")


def load_templates():
    return load_json(SCHEDULE_TEMPLATES_FILE, {"templates": []})


def save_templates(data):
    save_json(SCHEDULE_TEMPLATES_FILE, data)


@app.route("/api/schedule-templates", methods=["GET"])
@require_login
def get_schedule_templates():
    data = load_templates()
    # Return lightweight list (no shifts data for listing)
    result = [{"id": t["id"], "name": t["name"], "created_at": t.get("created_at", "")} for t in data["templates"]]
    return jsonify(result)


@app.route("/api/schedule-templates/<template_id>", methods=["GET"])
@require_login
def get_schedule_template(template_id):
    data = load_templates()
    for t in data["templates"]:
        if t["id"] == template_id:
            return jsonify(t)
    return jsonify({"error": "Template not found"}), 404


@app.route("/api/schedule-templates", methods=["POST"])
@require_login
def create_schedule_template():
    try:
        name = request.json.get("name", "").strip()
        if not name:
            return jsonify({"error": "Template name required"}), 400
        current = load_json(SCHEDULES_FILE, {"shifts": {}, "open_shifts": []})
        templates = load_templates()
        tid = f"T{len(templates['templates']) + 1:03d}"
        templates["templates"].append({
            "id": tid,
            "name": name,
            "shifts": current.get("shifts", {}),
            "open_shifts": current.get("open_shifts", []),
            "created_at": datetime.now().isoformat(),
        })
        save_templates(templates)
        return jsonify({"id": tid, "name": name}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule-templates/<template_id>", methods=["PUT"])
@require_login
def update_schedule_template(template_id):
    try:
        name = request.json.get("name", "").strip()
        if not name:
            return jsonify({"error": "Template name required"}), 400
        templates = load_templates()
        for t in templates["templates"]:
            if t["id"] == template_id:
                t["name"] = name
                save_templates(templates)
                return jsonify({"message": "Template updated"})
        return jsonify({"error": "Template not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule-templates/<template_id>", methods=["DELETE"])
@require_login
def delete_schedule_template(template_id):
    templates = load_templates()
    templates["templates"] = [t for t in templates["templates"] if t["id"] != template_id]
    save_templates(templates)
    return jsonify({"message": "Template deleted"})


@app.route("/api/schedule-templates/<template_id>/apply", methods=["POST"])
@require_login
def apply_schedule_template(template_id):
    try:
        templates = load_templates()
        template = None
        for t in templates["templates"]:
            if t["id"] == template_id:
                template = t
                break
        if not template:
            return jsonify({"error": "Template not found"}), 404
        current = load_json(SCHEDULES_FILE, {"shifts": {}, "status": "draft", "open_shifts": [], "week_start": "", "week_label": ""})
        current["shifts"] = {k: [dict(s) for s in v] for k, v in template.get("shifts", {}).items()}
        current["open_shifts"] = [dict(o) for o in template.get("open_shifts", [])]
        current["status"] = "draft"
        save_json(SCHEDULES_FILE, current)
        return jsonify({"message": f"Template '{template['name']}' applied"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Notifications ─────────────────────────────────────────


def load_notifications():
    return load_json(NOTIFICATIONS_FILE, {"notifications": []})


def save_notifications(data):
    save_json(NOTIFICATIONS_FILE, data)


def create_notification(ntype, message):
    data = load_notifications()
    nid = 1
    if data["notifications"]:
        nid = max(n["id"] for n in data["notifications"]) + 1
    data["notifications"].insert(0, {
        "id": nid,
        "type": ntype,
        "message": message,
        "created_at": datetime.now().isoformat(),
        "read_by": [],
    })
    save_notifications(data)
    return nid


@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    eid = session.get("employee_id")
    is_admin = session.get("user") is not None
    data = load_notifications()
    notifs = data["notifications"]
    result = []
    for n in notifs:
        n_copy = dict(n)
        if eid:
            n_copy["is_read"] = eid in n.get("read_by", [])
        elif is_admin:
            n_copy["is_read"] = "admin" in n.get("read_by", [])
        result.append(n_copy)
    return jsonify(result)


@app.route("/api/notifications/read", methods=["POST"])
def mark_notification_read():
    try:
        nid = request.json.get("id")
        if not nid:
            return jsonify({"error": "id required"}), 400
        eid = session.get("employee_id")
        is_admin = session.get("user") is not None
        data = load_notifications()
        for n in data["notifications"]:
            if n["id"] == nid:
                if is_admin:
                    if "admin" not in n.get("read_by", []):
                        n.setdefault("read_by", []).append("admin")
                elif eid:
                    if eid not in n.get("read_by", []):
                        n.setdefault("read_by", []).append(eid)
                save_notifications(data)
                return jsonify({"message": "Marked as read"})
        return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Time Clock ─────────────────────────────────────────────
@app.route("/api/timeclock/now", methods=["GET"])
def get_timeclock_now():
    """Returns current clock status for all employees. Public (used by tablet clock UI)."""
    try:
        data = load_json(TIMECLOCK_FILE, {"entries": []})
        today = datetime.now().strftime("%Y-%m-%d")
        active = [e for e in data["entries"] if e.get("clock_out") is None]
        today_entries = [e for e in data["entries"] if e.get("date") == today]
        employees = load_employees(EMPLOYEES_FILE)
        emp_map = {e["id"]: e["name"] for e in employees}
        for e in active:
            e["employee_name"] = emp_map.get(e["employee_id"], "Unknown")
        return jsonify({"active": active, "today_entries": today_entries, "date": today})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeclock/clock", methods=["POST"])
def clock_in_out():
    """Clock in or out. Body: {pin} (PIN identifies employee). Public for tablet use."""
    try:
        data = request.json
        emp_id = data.get("employee_id")
        pin = str(data.get("pin", "")).strip()
        employees = load_employees(EMPLOYEES_FILE)

        # If no employee_id, look up by PIN
        if not emp_id:
            emp = next((e for e in employees if str(e.get("pin", "")).strip() == pin), None)
            if not emp:
                return jsonify({"error": "Invalid PIN"}), 403
            emp_id = emp["id"]
        else:
            emp = next((e for e in employees if e["id"] == emp_id), None)
            if not emp:
                return jsonify({"error": "Employee not found"}), 404
            if str(emp.get("pin", "")).strip() != pin:
                if pin != "admin":  # admin bypass
                    return jsonify({"error": "Invalid PIN"}), 403

        clock = load_json(TIMECLOCK_FILE, {"entries": []})
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        active = [e for e in clock["entries"] if e.get("employee_id") == emp_id and e.get("clock_out") is None]

        if active:
            entry = active[0]
            entry["clock_out"] = now.isoformat()
            hours = (now - datetime.fromisoformat(entry["clock_in"])).total_seconds() / 3600
            entry["hours"] = round(hours, 2)
            entry["status"] = "completed"
            msg = f"Clocked out. Hours: {entry['hours']:.2f}"
        else:
            entry = {
                "employee_id": emp_id,
                "employee_name": emp["name"],
                "date": today,
                "clock_in": now.isoformat(),
                "clock_out": None,
                "hours": None,
                "status": "active",
            }
            clock["entries"].append(entry)
            msg = "Clocked in"

        save_json(TIMECLOCK_FILE, clock)
        return jsonify({"message": msg, "entry": entry})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeclock/history", methods=["GET"])
@require_login
def get_timeclock_history():
    data = load_json(TIMECLOCK_FILE, {"entries": []})
    start = request.args.get("start")
    end = request.args.get("end")
    entries = data["entries"]
    if start:
        entries = [e for e in entries if e.get("date") >= start]
    if end:
        entries = [e for e in entries if e.get("date") <= end]
    return jsonify(entries)


@app.route("/api/timeclock/delete", methods=["POST"])
@require_login
def delete_timeclock_entry():
    try:
        idx = request.json.get("index")
        data = load_json(TIMECLOCK_FILE, {"entries": []})
        if 0 <= idx < len(data["entries"]):
            data["entries"].pop(idx)
            save_json(TIMECLOCK_FILE, data)
            return jsonify({"message": "Entry deleted"})
        return jsonify({"error": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeclock/entry/<int:idx>", methods=["PUT"])
@require_login
def update_timeclock_entry(idx):
    try:
        data = load_json(TIMECLOCK_FILE, {"entries": []})
        if idx < 0 or idx >= len(data["entries"]):
            return jsonify({"error": "Invalid index"}), 400
        entry = data["entries"][idx]
        body = request.json
        if "date" in body:
            entry["date"] = body["date"]
        if "clock_in" in body:
            entry["clock_in"] = body["clock_in"]
        if "clock_out" in body:
            entry["clock_out"] = body["clock_out"]
        # Recalculate hours
        if entry.get("clock_in") and entry.get("clock_out"):
            try:
                cin = datetime.fromisoformat(entry["clock_in"])
                cout = datetime.fromisoformat(entry["clock_out"])
                entry["hours"] = round((cout - cin).total_seconds() / 3600, 2)
                entry["status"] = "completed"
            except Exception:
                pass
        elif entry.get("clock_in") and not entry.get("clock_out"):
            entry["hours"] = None
            entry["status"] = "active"
        save_json(TIMECLOCK_FILE, data)
        return jsonify({"message": "Entry updated", "entry": entry})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeclock/add", methods=["POST"])
@require_login
def add_timeclock_entry():
    try:
        body = request.json
        emp_id = body.get("employee_id")
        date = body.get("date")
        clock_in = body.get("clock_in")
        clock_out = body.get("clock_out")
        if not emp_id or not date or not clock_in:
            return jsonify({"error": "employee_id, date, and clock_in required"}), 400
        employees = load_employees(EMPLOYEES_FILE)
        emp = next((e for e in employees if e["id"] == emp_id), None)
        entry = {
            "employee_id": emp_id,
            "employee_name": emp["name"] if emp else emp_id,
            "date": date,
            "clock_in": clock_in,
            "clock_out": clock_out or None,
            "hours": None,
            "status": "completed" if clock_out else "active",
        }
        if clock_in and clock_out:
            try:
                cin = datetime.fromisoformat(clock_in)
                cout = datetime.fromisoformat(clock_out)
                entry["hours"] = round((cout - cin).total_seconds() / 3600, 2)
            except Exception:
                pass
        data = load_json(TIMECLOCK_FILE, {"entries": []})
        data["entries"].append(entry)
        save_json(TIMECLOCK_FILE, data)
        return jsonify({"message": "Entry added", "entry": entry}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Time Off Requests ──────────────────────────────────────
@app.route("/api/timeoff", methods=["GET"])
@require_login
def get_timeoff():
    data = load_json(TIMEOFF_FILE, {"requests": []})
    return jsonify(data)


@app.route("/api/timeoff/request", methods=["POST"])
def request_timeoff():
    try:
        data = request.json
        emp_id = data.get("employee_id") or session.get("employee_id")
        if not emp_id:
            return jsonify({"error": "Employee ID required"}), 400
        off = load_json(TIMEOFF_FILE, {"requests": []})
        off["requests"].append({
            "id": len(off["requests"]) + 1,
            "employee_id": emp_id,
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "reason": data.get("reason", ""),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        })
        save_json(TIMEOFF_FILE, off)
        return jsonify({"message": "Request submitted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeoff/respond", methods=["POST"])
@require_login
def respond_timeoff():
    try:
        data = request.json
        req_id = data.get("id")
        new_status = data.get("status")
        if new_status not in ("approved", "denied"):
            return jsonify({"error": "Invalid status"}), 400
        off = load_json(TIMEOFF_FILE, {"requests": []})
        for r in off["requests"]:
            if r["id"] == req_id:
                r["status"] = new_status
                save_json(TIMEOFF_FILE, off)
                return jsonify({"message": f"Request {new_status}"})
        return jsonify({"error": "Request not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Employee Portal Login ──────────────────────────────────
@app.route("/api/employee/login", methods=["POST"])
def employee_login():
    data = request.json
    username = data.get("username", "").strip().lower()
    emp_id = data.get("employee_id", "").strip().upper()
    pin = data.get("pin", "").strip()
    employees = load_employees(EMPLOYEES_FILE)
    if username:
        emp = next((e for e in employees if e.get("username", "").lower() == username), None)
    else:
        emp = next((e for e in employees if e["id"] == emp_id), None)
    if not emp or str(emp.get("pin", "")).strip() != pin:
        return jsonify({"error": "Invalid credentials"}), 401
    session["employee_id"] = emp["id"]
    session["employee_name"] = emp["name"]
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=8)
    return jsonify({"ok": True, "employee": {"id": emp["id"], "name": emp["name"]}})


@app.route("/api/employee/session")
def employee_session():
    eid = session.get("employee_id")
    if eid:
        return jsonify({"employee_id": eid, "employee_name": session.get("employee_name")})
    return jsonify({"employee_id": None})


@app.route("/api/employee/logout", methods=["POST"])
def employee_logout():
    session.pop("employee_id", None)
    session.pop("employee_name", None)
    return jsonify({"ok": True})


@app.route("/api/employee/paystubs", methods=["GET"])
def employee_paystubs():
    eid = request.args.get("employee_id") or session.get("employee_id")
    if not eid:
        return jsonify({"error": "Unauthorized"}), 401
    history = load_history()
    result = []
    for week_key, entry in history.items():
        if not entry.get("results"):
            continue
        for r in entry["results"]:
            if r.get("employee_id") == eid:
                r["week_label"] = entry["week_label"]
                r["week_start"] = entry["week_start"]
                r["week_end"] = entry["week_end"]
                result.append(r)
    return jsonify(sorted(result, key=lambda x: x.get("week_start", ""), reverse=True))


@app.route("/api/employee/schedule", methods=["GET"])
def employee_schedule():
    eid = request.args.get("employee_id") or session.get("employee_id")
    if not eid:
        return jsonify({"error": "Unauthorized"}), 401
    week_start = request.args.get("week_start")
    data = load_json(SCHEDULES_FILE, {"shifts": {}, "status": "draft"})

    if data.get("status") != "published":
        return jsonify({"shifts": [], "status": "draft", "week_start": week_start or "", "week_label": ""})

    if week_start and data.get("week_start") != week_start:
        return jsonify({"shifts": [], "status": "published", "week_start": week_start, "week_label": ""})

    shifts = data.get("shifts", {}).get(eid, [])
    return jsonify({
        "shifts": shifts,
        "status": "published",
        "week_start": data.get("week_start", ""),
        "week_label": data.get("week_label", ""),
    })




@app.route("/api/employee/timeoff", methods=["GET"])
def employee_my_timeoff():
    eid = request.args.get("employee_id") or session.get("employee_id")
    if not eid:
        return jsonify({"error": "Unauthorized"}), 401
    data = load_json(TIMEOFF_FILE, {"requests": []})
    mine = [r for r in data["requests"] if r.get("employee_id") == eid]
    return jsonify(mine)


# ─── Shift Claiming & Swapping ─────────────────────────────
@app.route("/api/employee/open-shifts", methods=["GET"])
def get_open_shifts():
    data = load_json(SCHEDULES_FILE, {"shifts": {}, "open_shifts": []})
    return jsonify(data.get("open_shifts", []))


@app.route("/api/employee/claim-shift", methods=["POST"])
def claim_open_shift():
    try:
        eid = request.json.get("employee_id") or session.get("employee_id")
        if not eid:
            return jsonify({"error": "Unauthorized"}), 401
        weekday = request.json.get("weekday")
        if weekday is None:
            return jsonify({"error": "weekday required"}), 400

        data = load_json(SCHEDULES_FILE, {"shifts": {}, "open_shifts": []})
        open_shifts = data.get("open_shifts", [])
        shift_idx = None
        for i, o in enumerate(open_shifts):
            if o.get("weekday") == weekday:
                shift_idx = i
                break
        if shift_idx is None:
            return jsonify({"error": "No open shift for that day"}), 404

        claimed = open_shifts.pop(shift_idx)
        if eid not in data["shifts"]:
            data["shifts"][eid] = [{} for _ in range(7)]
        data["shifts"][eid][weekday] = {
            "start": claimed.get("start", ""),
            "end": claimed.get("end", ""),
            "notes": claimed.get("notes", ""),
        }
        data["open_shifts"] = open_shifts
        save_json(SCHEDULES_FILE, data)
        return jsonify({"message": "Shift claimed"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/employee/swap-request", methods=["POST"])
def create_swap_request():
    try:
        from_eid = request.json.get("employee_id") or session.get("employee_id")
        if not from_eid:
            return jsonify({"error": "Unauthorized"}), 401
        to_eid = request.json.get("to_employee_id")
        weekday = request.json.get("weekday")
        if not to_eid or weekday is None:
            return jsonify({"error": "to_employee_id and weekday required"}), 400

        schedules = load_json(SCHEDULES_FILE, {"shifts": {}, "week_start": ""})
        week_start = schedules.get("week_start", "")

        swaps = load_json(SHIFT_SWAPS_FILE, {"swaps": []})
        swaps["swaps"].append({
            "id": len(swaps["swaps"]) + 1,
            "from_employee_id": from_eid,
            "to_employee_id": to_eid,
            "weekday": weekday,
            "week_start": week_start,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        })
        save_json(SHIFT_SWAPS_FILE, swaps)
        return jsonify({"message": "Swap request sent"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/employee/swap-requests", methods=["GET"])
def get_swap_requests():
    eid = request.args.get("employee_id") or session.get("employee_id")
    if not eid:
        return jsonify({"error": "Unauthorized"}), 401
    swaps = load_json(SHIFT_SWAPS_FILE, {"swaps": []})
    mine = [s for s in swaps["swaps"] if s["from_employee_id"] == eid or s["to_employee_id"] == eid]
    employees = load_employees(EMPLOYEES_FILE)
    emp_map = {e["id"]: e["name"] for e in employees}
    for s in mine:
        s["from_name"] = emp_map.get(s["from_employee_id"], s["from_employee_id"])
        s["to_name"] = emp_map.get(s["to_employee_id"], s["to_employee_id"])
    return jsonify(mine)


@app.route("/api/employee/swap-respond", methods=["POST"])
def respond_swap_request():
    try:
        eid = request.json.get("employee_id") or session.get("employee_id")
        if not eid:
            return jsonify({"error": "Unauthorized"}), 401
        swap_id = request.json.get("id")
        action = request.json.get("action")
        if action not in ("approved", "declined"):
            return jsonify({"error": "Invalid action"}), 400

        swaps = load_json(SHIFT_SWAPS_FILE, {"swaps": []})
        schedules = load_json(SCHEDULES_FILE, {"shifts": {}, "status": "draft"})
        for s in swaps["swaps"]:
            if s["id"] == swap_id and s["to_employee_id"] == eid:
                if action == "approved":
                    # Swap the shifts in schedules
                    wk = s["weekday"]
                    from_shifts = schedules["shifts"].get(s["from_employee_id"], [{} for _ in range(7)])
                    to_shifts = schedules["shifts"].get(s["to_employee_id"], [{} for _ in range(7)])
                    from_shift = dict(from_shifts[wk]) if wk < len(from_shifts) else {}
                    to_shift = dict(to_shifts[wk]) if wk < len(to_shifts) else {}
                    if s["from_employee_id"] not in schedules["shifts"]:
                        schedules["shifts"][s["from_employee_id"]] = [{} for _ in range(7)]
                    if s["to_employee_id"] not in schedules["shifts"]:
                        schedules["shifts"][s["to_employee_id"]] = [{} for _ in range(7)]
                    schedules["shifts"][s["from_employee_id"]][wk] = to_shift
                    schedules["shifts"][s["to_employee_id"]][wk] = from_shift
                    save_json(SCHEDULES_FILE, schedules)
                    s["status"] = "approved"
                else:
                    s["status"] = "declined"
                save_json(SHIFT_SWAPS_FILE, swaps)
                return jsonify({"message": f"Swap {action}"})
        return jsonify({"error": "Swap request not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/shift-swaps", methods=["GET"])
@require_login
def admin_get_swap_requests():
    swaps = load_json(SHIFT_SWAPS_FILE, {"swaps": []})
    employees = load_employees(EMPLOYEES_FILE)
    emp_map = {e["id"]: e["name"] for e in employees}
    for s in swaps["swaps"]:
        s["from_name"] = emp_map.get(s["from_employee_id"], s["from_employee_id"])
        s["to_name"] = emp_map.get(s["to_employee_id"], s["to_employee_id"])
    return jsonify(swaps["swaps"])


@app.route("/api/shift-swaps/approve", methods=["POST"])
@require_login
def admin_approve_swap():
    try:
        swap_id = request.json.get("id")
        swaps = load_json(SHIFT_SWAPS_FILE, {"swaps": []})
        schedules = load_json(SCHEDULES_FILE, {"shifts": {}, "status": "draft"})
        for s in swaps["swaps"]:
            if s["id"] == swap_id:
                wk = s["weekday"]
                from_shifts = schedules["shifts"].get(s["from_employee_id"], [{} for _ in range(7)])
                to_shifts = schedules["shifts"].get(s["to_employee_id"], [{} for _ in range(7)])
                from_shift = dict(from_shifts[wk]) if wk < len(from_shifts) else {}
                to_shift = dict(to_shifts[wk]) if wk < len(to_shifts) else {}
                if s["from_employee_id"] not in schedules["shifts"]:
                    schedules["shifts"][s["from_employee_id"]] = [{} for _ in range(7)]
                if s["to_employee_id"] not in schedules["shifts"]:
                    schedules["shifts"][s["to_employee_id"]] = [{} for _ in range(7)]
                schedules["shifts"][s["from_employee_id"]][wk] = to_shift
                schedules["shifts"][s["to_employee_id"]][wk] = from_shift
                save_json(SCHEDULES_FILE, schedules)
                s["status"] = "approved"
                save_json(SHIFT_SWAPS_FILE, swaps)
                return jsonify({"message": "Swap approved"})
        return jsonify({"error": "Swap not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/shift-swaps/delete", methods=["POST"])
@require_login
def admin_delete_swap():
    try:
        swap_id = request.json.get("id")
        swaps = load_json(SHIFT_SWAPS_FILE, {"swaps": []})
        swaps["swaps"] = [s for s in swaps["swaps"] if s["id"] != swap_id]
        save_json(SHIFT_SWAPS_FILE, swaps)
        return jsonify({"message": "Swap deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/payroll", methods=["POST"])
@require_login
def run_payroll():
    try:
        employees = load_employees(EMPLOYEES_FILE)
        hours_data = request.json["hours"]
        week_info = request.json["week_info"]

        results = []
        total_gross = 0
        total_net = 0

        for emp in employees:
            emp_id = emp["id"]
            hours = hours_data.get(emp_id, 0)
            tips = float(hours_data.get(f"{emp_id}_tips", 0)) if isinstance(hours_data, dict) else 0
            result = calculate_payroll(emp, float(hours), tips=tips)
            results.append(result)
            total_gross += result["gross_pay"]
            total_net += result["net_pay"]

        payroll_data = {
            "week_start": week_info["week_start"],
            "week_end": week_info["week_end"],
            "week_label": week_info["week_label"],
            "hours": hours_data,
            "results": results,
            "summary": {
                "total_gross": round(total_gross, 2),
                "total_net": round(total_net, 2),
            },
        }

        history = load_history()
        if week_info["week_label"] in history and "results" in history[week_info["week_label"]]:
            return jsonify({"error": "Payroll already exists for this week. Delete it from history first."}), 409
        history[week_info["week_label"]] = payroll_data
        save_history(history)

        return jsonify(payroll_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hours", methods=["POST"])
@require_login
def save_hours():
    try:
        hours_data = request.json["hours"]
        week_info = request.json["week_info"]

        history = load_history()
        if week_info["week_label"] in history:
            history[week_info["week_label"]]["hours"] = hours_data
        else:
            history[week_info["week_label"]] = {
                "week_start": week_info["week_start"],
                "week_end": week_info["week_end"],
                "week_label": week_info["week_label"],
                "hours": hours_data,
            }

        save_history(history)
        return jsonify({"message": "Hours saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reports", methods=["GET"])
@require_login
def get_reports():
    try:
        start = request.args.get("start")
        end = request.args.get("end")
        if not start or not end:
            return jsonify({"error": "start and end parameters required"}), 400

        history = load_history()
        weeks_in_range = []
        summary = {
            "total_hours": 0, "total_gross": 0, "total_federal_tax": 0,
            "total_state_tax": 0, "total_social_security": 0, "total_medicare": 0,
            "total_additional_medicare": 0, "total_tax": 0, "total_deductions": 0,
            "total_net": 0, "week_count": 0,
        }
        employees = {}

        for week_key, entry in history.items():
            if not entry.get("results"):
                continue
            ws, we = entry["week_start"], entry["week_end"]
            if ws >= start and we <= end:
                weeks_in_range.append(week_key)
                summary["week_count"] += 1

                for r in entry["results"]:
                    eid = r["employee_id"]
                    h = float(r.get("hours_worked", 0))
                    g = float(r.get("gross_pay", 0))
                    ft = float(r.get("federal_tax", 0))
                    st = float(r.get("state_tax", 0))
                    ss = float(r.get("social_security", 0))
                    mc = float(r.get("medicare", 0))
                    am = float(r.get("additional_medicare", 0))
                    tt = float(r.get("total_tax", 0))
                    td = float(r.get("total_deductions", 0))
                    nt = float(r.get("net_pay", 0))

                    summary["total_hours"] += h
                    summary["total_gross"] += g
                    summary["total_federal_tax"] += ft
                    summary["total_state_tax"] += st
                    summary["total_social_security"] += ss
                    summary["total_medicare"] += mc
                    summary["total_additional_medicare"] += am
                    summary["total_tax"] += tt
                    summary["total_deductions"] += td
                    summary["total_net"] += nt

                    if eid not in employees:
                        employees[eid] = {
                            "name": r["employee_name"],
                            "weeks": [],
                            "totals": {
                                "total_hours": 0, "total_gross": 0, "total_federal_tax": 0,
                                "total_state_tax": 0, "total_social_security": 0, "total_medicare": 0,
                                "total_additional_medicare": 0, "total_tax": 0, "total_deductions": 0, "total_net": 0,
                            },
                        }
                    employees[eid]["weeks"].append({
                        "week_label": entry["week_label"],
                        "week_start": entry["week_start"],
                        "week_end": entry["week_end"],
                        "hours_worked": h, "hourly_rate": r.get("hourly_rate"),
                        "gross_pay": g, "federal_tax": ft, "state_tax": st,
                        "social_security": ss, "medicare": mc, "additional_medicare": am,
                        "total_tax": tt, "total_deductions": td, "net_pay": nt,
                    })
                    employees[eid]["totals"]["total_hours"] += h
                    employees[eid]["totals"]["total_gross"] += g
                    employees[eid]["totals"]["total_federal_tax"] += ft
                    employees[eid]["totals"]["total_state_tax"] += st
                    employees[eid]["totals"]["total_social_security"] += ss
                    employees[eid]["totals"]["total_medicare"] += mc
                    employees[eid]["totals"]["total_additional_medicare"] += am
                    employees[eid]["totals"]["total_tax"] += tt
                    employees[eid]["totals"]["total_deductions"] += td
                    employees[eid]["totals"]["total_net"] += nt

        for k in ("total_hours", "total_gross", "total_federal_tax", "total_state_tax",
                  "total_social_security", "total_medicare", "total_additional_medicare",
                  "total_tax", "total_deductions", "total_net"):
            summary[k] = round(summary[k], 2)
        for eid in employees:
            for k in employees[eid]["totals"]:
                employees[eid]["totals"][k] = round(employees[eid]["totals"][k], 2)

        return jsonify({
            "start": start, "end": end,
            "weeks_in_range": weeks_in_range,
            "summary": summary,
            "employees": employees,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/csv", methods=["GET"])
@require_login
def download_history_csv():
    try:
        start = request.args.get("start")
        end = request.args.get("end")
        history = load_history()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Week Label", "Week Start", "Week End",
            "Employee ID", "Employee Name", "State",
            "Hours Worked", "Hourly Rate", "Gross Pay",
            "Federal Tax", "State Tax", "Social Security",
            "Medicare", "Additional Medicare", "Total Tax",
            "Total Deductions", "Net Pay",
        ])
        for entry in history.values():
            if not entry.get("results"):
                continue
            ws, we = entry["week_start"], entry["week_end"]
            if start and ws < start:
                continue
            if end and we > end:
                continue
            for r in entry["results"]:
                writer.writerow([
                    entry["week_label"], ws, we,
                    r.get("employee_id", ""), r.get("employee_name", ""), r.get("state", ""),
                    r.get("hours_worked", 0), r.get("hourly_rate", 0), r.get("gross_pay", 0),
                    r.get("federal_tax", 0), r.get("state_tax", 0), r.get("social_security", 0),
                    r.get("medicare", 0), r.get("additional_medicare", 0), r.get("total_tax", 0),
                    r.get("total_deductions", 0), r.get("net_pay", 0),
                ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=payroll_history.csv"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reports/csv", methods=["GET"])
@require_login
def download_reports_csv():
    try:
        start = request.args.get("start", "2000-01-01")
        end = request.args.get("end", "2099-12-31")
        history = load_history()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Week Label", "Week Start", "Week End",
            "Employee ID", "Employee Name", "State",
            "Hours Worked", "Hourly Rate", "Gross Pay",
            "Federal Tax", "State Tax", "Social Security",
            "Medicare", "Additional Medicare", "Total Tax",
            "Total Deductions", "Net Pay",
        ])
        for entry in history.values():
            if not entry.get("results"):
                continue
            ws, we = entry["week_start"], entry["week_end"]
            if ws < start or we > end:
                continue
            for r in entry["results"]:
                writer.writerow([
                    entry["week_label"], ws, we,
                    r.get("employee_id", ""), r.get("employee_name", ""), r.get("state", ""),
                    r.get("hours_worked", 0), r.get("hourly_rate", 0), r.get("gross_pay", 0),
                    r.get("federal_tax", 0), r.get("state_tax", 0), r.get("social_security", 0),
                    r.get("medicare", 0), r.get("additional_medicare", 0), r.get("total_tax", 0),
                    r.get("total_deductions", 0), r.get("net_pay", 0),
                ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=payroll_report.csv"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
