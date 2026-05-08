import json
import os
from tax_tables import (
    FEDERAL_WITHHOLDING_STANDARD,
    WITHHOLDING_DEDUCTION as FEDERAL_DEDUCTION,
    SOCIAL_SECURITY_RATE,
    SOCIAL_SECURITY_WAGE_BASE,
    MEDICARE_RATE,
    ADDITIONAL_MEDICARE_RATE,
    ADDITIONAL_MEDICARE_THRESHOLD_SINGLE,
    STATE_TAXES as DEFAULT_STATE_TAXES,
)


def load_tax_settings():
    settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tax_settings.json")
    if not os.path.exists(settings_file):
        return None
    with open(settings_file, "r") as f:
        return json.load(f)


def load_employees(filepath="employees.json"):
    with open(filepath, "r") as f:
        data = json.load(f)
    return data["employees"]


def calculate_gross_pay(hours, hourly_rate, overtime_rate=0):
    if overtime_rate and hours > 40:
        regular = 40 * hourly_rate
        overtime = (hours - 40) * hourly_rate * overtime_rate
        return round(regular + overtime, 2)
    return round(hours * hourly_rate, 2)


def _get_federal_col(filing_status, step2_checked):
    col_map = {
        "married": (2, 3),
        "head_of_household": (4, 5),
        "single": (6, 7),
    }
    std_col, step2_col = col_map.get(filing_status, (6, 7))
    return step2_col if step2_checked else std_col


def calc_federal_from_settings(gross_pay, filing_status, settings, step2_checked=False):
    brackets = settings.get("federal", {}).get("brackets", [])
    col = _get_federal_col(filing_status, step2_checked)
    for row in brackets:
        lower, upper = row[0], row[1]
        upper_val = upper if upper > 0 else float("inf")
        if lower <= gross_pay < upper_val:
            return round(row[col], 2)
    return 0.0


def calc_state_from_settings(gross_pay, state, filing_status, settings, allowances=0):
    state_data = settings.get("state", {}).get(state)
    if not state_data:
        return 0.0
    
    brackets = state_data.get("brackets", [])
    if not brackets:
        return 0.0
    
    for row in brackets:
        lower, upper = row[0], row[1]
        upper_val = upper if upper > 0 else float("inf")
        if lower <= gross_pay < upper_val:
            allow_idx = 2 + allowances
            if allow_idx >= len(row):
                allow_idx = len(row) - 1
            return round(row[allow_idx], 2)
    
    return 0.0


def get_fica_settings(settings):
    fica = settings.get("fica", {}) if settings else {}
    return {
        "ss_rate": fica.get("social_security_rate", 6.2) / 100,
        "medicare_rate": fica.get("medicare_rate", 1.45) / 100,
    }


def calculate_federal_tax(adjusted_annual_wage, filing_status, settings=None):
    if settings:
        return calc_federal_from_settings(adjusted_annual_wage, filing_status, settings)
    brackets = FEDERAL_WITHHOLDING_STANDARD[filing_status]
    for low, high, base, rate, over in brackets:
        if low <= adjusted_annual_wage < high:
            tax = base + rate * (adjusted_annual_wage - over)
            return round(max(0, tax), 2)
    return 0.0


def calculate_state_tax(taxable_income, state, filing_status, settings=None, gross_pay=None, allowances=0):
    if settings:
        return calc_state_from_settings(taxable_income, state, filing_status, settings, gross_pay, allowances)
    state_info = DEFAULT_STATE_TAXES.get(state, {})
    bracket_key = f"brackets_{filing_status}"
    if bracket_key in state_info:
        brackets = state_info[bracket_key]
    elif "brackets" in state_info:
        brackets = state_info["brackets"]
    else:
        return 0.0
    
    tax = 0.0
    for row in brackets:
        lower, upper = row[0], row[1]
        allow_idx = 2 + min(1, allowances)
        rate = row[allow_idx] if len(row) > allow_idx else row[2]
        if taxable_income <= lower:
            break
        taxable_in_bracket = min(taxable_income, upper) - lower
        tax += taxable_in_bracket * rate
    return round(tax, 2)


def calculate_fica(gross_pay, fica=None):
    if fica is None:
        fica = get_fica_settings(None)
    social_security = round(gross_pay * fica["ss_rate"], 2)
    medicare = round(gross_pay * fica["medicare_rate"], 2)
    return social_security, medicare


DEFAULT_MINIMUM_WAGE = {
    "CA": 16.50, "NY": 15.00, "NC": 7.25, "TX": 7.25, "FL": 12.00, "WA": 16.28,
}


def get_state_minimum_wage(state, settings):
    if settings and settings.get("state"):
        state_data = settings["state"].get(state, {})
        mw = state_data.get("minimum_wage", 0)
        if mw:
            return mw
    return DEFAULT_MINIMUM_WAGE.get(state, 7.25)


def calculate_overtime_pay(hours, hourly_rate, overtime_rate):
    if overtime_rate and hours > 40:
        return round((hours - 40) * hourly_rate * overtime_rate, 2)
    return 0.0


def calculate_payroll(employee, hours, year_to_date_gross=0, pay_periods_per_year=26, tips=0):
    settings = load_tax_settings()
    overtime_rate = employee.get("overtime_rate", 0) or 0
    filing_status = employee["filing_status"]
    state = employee["state"]
    is_salary = employee.get("pay_type") == "salary"

    if is_salary:
        gross_pay = round(employee["salary_amount"], 2)
        regular_pay = gross_pay
        makeup = 0
    elif employee.get("tipped"):
        regular_pay = calculate_gross_pay(hours, employee["hourly_rate"], overtime_rate)
        min_wage = get_state_minimum_wage(state, settings)
        expected_tips = max(0, round(min_wage * hours - regular_pay, 2))
        makeup = max(0, round(expected_tips - tips, 2))
        gross_pay = round(regular_pay + tips + makeup, 2)
    else:
        gross_pay = calculate_gross_pay(hours, employee["hourly_rate"], overtime_rate)

    if settings:
        step2 = employee.get("step2_checked", False)
        federal_tax = calc_federal_from_settings(gross_pay, filing_status, settings, step2_checked=step2)
    else:
        deduction = FEDERAL_DEDUCTION[filing_status]
        annual_wages = gross_pay * pay_periods_per_year
        adjusted_annual_wage = max(0, annual_wages - deduction)
        annual_federal_tax = calculate_federal_tax(adjusted_annual_wage, filing_status, None)
        federal_tax = round(annual_federal_tax / pay_periods_per_year, 2)

    emp_allowances = employee.get("state_allowances", 0)
    if settings:
        state_tax = calc_state_from_settings(gross_pay, state, filing_status, settings, allowances=emp_allowances)
    else:
        state_info = DEFAULT_STATE_TAXES.get(state, {})
        allowance_val = state_info.get("allowance_value", 0)
        state_std_ded = state_info.get("standard_deduction", {}).get(filing_status, 0)
        annual_state_income = gross_pay * pay_periods_per_year
        annual_state_allowances = emp_allowances * allowance_val
        annual_taxable_state = max(0, annual_state_income - annual_state_allowances - state_std_ded)
        annual_state_tax = calculate_state_tax(annual_taxable_state, state, filing_status, None, allowances=emp_allowances)
        state_tax = round(annual_state_tax / pay_periods_per_year, 2)

    fed_add_type = employee.get("fed_add_withholding_type")
    fed_add_val = employee.get("fed_add_withholding_value", 0) or 0
    if fed_add_type == "percentage" and fed_add_val:
        federal_tax += round(gross_pay * fed_add_val / 100, 2)
    elif fed_add_type == "amount" and fed_add_val:
        federal_tax += round(fed_add_val, 2)

    state_add_type = employee.get("state_add_withholding_type")
    state_add_val = employee.get("state_add_withholding_value", 0) or 0
    if state_add_type == "percentage" and state_add_val:
        state_tax += round(gross_pay * state_add_val / 100, 2)
    elif state_add_type == "amount" and state_add_val:
        state_tax += round(state_add_val, 2)

    fica = get_fica_settings(settings)
    social_security, medicare = calculate_fica(gross_pay, fica)
    additional_medicare = 0.0

    total_tax = round(federal_tax + state_tax + social_security + medicare, 2)
    total_deductions = total_tax

    if employee.get("tipped"):
        employer_paid = round(regular_pay + makeup, 2)
        net_pay = round(employer_paid - total_deductions, 2)
    else:
        net_pay = round(gross_pay - total_deductions, 2)

    overtime_pay = calculate_overtime_pay(hours, employee["hourly_rate"], overtime_rate) if not is_salary else 0.0

    result = {
        "employee_id": employee["id"],
        "employee_name": employee["name"],
        "hours_worked": hours,
        "hourly_rate": employee["hourly_rate"],
        "overtime_pay": overtime_pay,
        "gross_pay": gross_pay,
        "federal_tax": federal_tax,
        "state_tax": state_tax,
        "state": state,
        "social_security": social_security,
        "medicare": medicare,
        "additional_medicare": additional_medicare,
        "total_tax": total_tax,
        "total_deductions": total_deductions,
        "net_pay": net_pay,
        "employer_paid": round(regular_pay + makeup, 2) if employee.get("tipped") else gross_pay,
    }
    if employee.get("tipped"):
        result["tipped"] = True
        result["tips"] = tips
        result["expected_tips"] = expected_tips
        result["makeup"] = makeup
        result["regular_pay"] = regular_pay
    return result
