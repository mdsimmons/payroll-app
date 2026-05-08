import os
import sys
import json
import csv
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
