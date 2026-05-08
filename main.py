import os
import sys
from payroll import load_employees, calculate_payroll


def print_header():
    print("=" * 60)
    print("PAYROLL APP")
    print("=" * 60)


def list_employees(employees):
    print("\n--- Employees ---")
    for emp in employees:
        print(f"  {emp['id']}: {emp['name']} - ${emp['hourly_rate']}/hr ({emp['state']})")
    print()


def input_hours(employees):
    hours_worked = {}
    for emp in employees:
        while True:
            try:
                hours = input(f"Enter hours for {emp['name']} ({emp['id']}): ")
                hours = float(hours)
                if hours < 0:
                    print("Hours cannot be negative.")
                    continue
                if hours > 168:
                    print("Hours cannot exceed 168 (hours in a week).")
                    continue
                hours_worked[emp["id"]] = hours
                break
            except ValueError:
                print("Please enter a valid number.")
    return hours_worked


def print_paystub(result):
    print("\n" + "-" * 40)
    print(f"PAYSTUB: {result['employee_name']} ({result['employee_id']})")
    print("-" * 40)
    print(f"  Hours Worked:      {result['hours_worked']:>8.2f}")
    print(f"  Hourly Rate:       ${result['hourly_rate']:>8.2f}")
    print(f"  Gross Pay:         ${result['gross_pay']:>8.2f}")
    print()
    print("  DEDUCTIONS:")
    print(f"    Federal Tax:     ${result['federal_tax']:>8.2f}")
    print(f"    State Tax ({result['state']}):  ${result['state_tax']:>8.2f}")
    print(f"    Social Security: ${result['social_security']:>8.2f}")
    print(f"    Medicare:        ${result['medicare']:>8.2f}")
    if result["additional_medicare"] > 0:
        print(f"    Add'l Medicare:  ${result['additional_medicare']:>8.2f}")
    print(f"    Total Tax:       ${result['total_tax']:>8.2f}")
    print(f"    Total Deductions:${result['total_deductions']:>8.2f}")
    print()
    print(f"  >>> NET PAY:       ${result['net_pay']:>8.2f}")
    print("-" * 40)


def run_payroll():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    employees_file = os.path.join(script_dir, "employees.json")

    if not os.path.exists(employees_file):
        print(f"Error: {employees_file} not found.")
        sys.exit(1)

    employees = load_employees(employees_file)

    print_header()
    list_employees(employees)

    hours_worked = input_hours(employees)

    print("\n" + "=" * 60)
    print("PAYROLL RESULTS")
    print("=" * 60)

    total_gross = 0
    total_net = 0
    for emp in employees:
        result = calculate_payroll(emp, hours_worked[emp["id"]])
        print_paystub(result)
        total_gross += result["gross_pay"]
        total_net += result["net_pay"]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total Gross Payroll: ${total_gross:,.2f}")
    print(f"  Total Net Payroll:   ${total_net:,.2f}")
    print("=" * 60)


if __name__ == "__main__":
    run_payroll()
