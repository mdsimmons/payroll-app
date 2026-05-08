# 2026 Federal Withholding Rate Schedules
# Source: IRS Publication 15-T (2026), Percentage Method for Automated Payroll Systems
# Format: (min, max, base_tax, rate, over)
# tax = base_tax + rate * (adjusted_annual_wage - over)

# STANDARD tables: W-4 from 2019 or earlier, OR W-4 2020+ without Step 2 checked
FEDERAL_WITHHOLDING_STANDARD = {
    "single": [
        (0, 7500, 0.00, 0.00, 0),
        (7500, 19900, 0.00, 0.10, 7500),
        (19900, 57900, 1240.00, 0.12, 19900),
        (57900, 113200, 5800.00, 0.22, 57900),
        (113200, 209275, 17966.00, 0.24, 113200),
        (209275, 263725, 41024.00, 0.32, 209275),
        (263725, 648100, 58448.00, 0.35, 263725),
        (648100, float("inf"), 192979.50, 0.37, 648100),
    ],
    "married": [
        (0, 19300, 0.00, 0.00, 0),
        (19300, 44100, 0.00, 0.10, 19300),
        (44100, 120100, 2480.00, 0.12, 44100),
        (120100, 230700, 11600.00, 0.22, 120100),
        (230700, 422850, 35932.00, 0.24, 230700),
        (422850, 531750, 82048.00, 0.32, 422850),
        (531750, 788000, 116896.00, 0.35, 531750),
        (788000, float("inf"), 206583.50, 0.37, 788000),
    ],
    "head_of_household": [
        (0, 0, 0.00, 0.00, 0),
        (0, 10400, 0.00, 0.10, 0),
        (10400, 48800, 1040.00, 0.12, 10400),
        (48800, 104800, 5648.00, 0.22, 48800),
        (104800, 200875, 17968.00, 0.24, 104800),
        (200875, 255325, 41026.00, 0.32, 200875),
        (255325, 639700, 58450.00, 0.35, 255325),
        (639700, float("inf"), 192985.00, 0.37, 639700),
    ],
}

# Amount to subtract from annualized wages to get "Adjusted Annual Wage Amount"
# These represent the standard deduction equivalent baked into the Pub 15-T tables
WITHHOLDING_DEDUCTION = {
    "single": 7500,
    "married": 16100,
    "head_of_household": 10400,
}

# FICA rates 2026
# Source: SSA.gov, IRS Topic 751
SOCIAL_SECURITY_RATE = 0.062
SOCIAL_SECURITY_WAGE_BASE = 184500
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ADDITIONAL_MEDICARE_THRESHOLD_SINGLE = 200000
ADDITIONAL_MEDICARE_THRESHOLD_MARRIED = 250000

# State tax brackets (2026)
STATE_TAXES = {
    "CA": {
        "brackets_single": [
            (0, 11079, 0.01, 0.01),
            (11079, 26264, 0.02, 0.02),
            (26264, 41452, 0.04, 0.04),
            (41452, 57542, 0.06, 0.06),
            (57542, 72724, 0.08, 0.08),
            (72724, 371479, 0.093, 0.093),
            (371479, 445771, 0.103, 0.103),
            (445771, 742953, 0.113, 0.113),
            (742953, float("inf"), 0.123, 0.123),
        ],
        "brackets_married": [
            (0, 22158, 0.01, 0.01),
            (22158, 52528, 0.02, 0.02),
            (52528, 82904, 0.04, 0.04),
            (82904, 115084, 0.06, 0.06),
            (115084, 145448, 0.08, 0.08),
            (145448, 742958, 0.093, 0.093),
            (742958, 891542, 0.103, 0.103),
            (891542, 1485906, 0.113, 0.113),
            (1485906, float("inf"), 0.123, 0.123),
        ],
        "brackets_head_of_household": [
            (0, 22173, 0.01, 0.01),
            (22173, 52530, 0.02, 0.02),
            (52530, 67716, 0.04, 0.04),
            (67716, 83805, 0.06, 0.06),
            (83805, 98990, 0.08, 0.08),
            (98990, 505208, 0.093, 0.093),
            (505208, 606251, 0.103, 0.103),
            (606251, 1010417, 0.113, 0.113),
            (1010417, float("inf"), 0.123, 0.123),
        ],
        "standard_deduction": {"single": 5706, "married": 11412, "head_of_household": 11412},
        "allowance_value": 0,
    },
    "NY": {
        "brackets_single": [
            (0, 8500, 0.04, 0.04),
            (8500, 11700, 0.045, 0.045),
            (11700, 13900, 0.0525, 0.0525),
            (13900, 80650, 0.055, 0.055),
            (80650, 215400, 0.06, 0.06),
            (215400, 1077550, 0.0685, 0.0685),
            (1077550, 5000000, 0.0965, 0.0965),
            (5000000, 25000000, 0.103, 0.103),
            (25000000, float("inf"), 0.109, 0.109),
        ],
        "brackets_married": [
            (0, 17150, 0.04, 0.04),
            (17150, 23600, 0.045, 0.045),
            (23600, 27900, 0.0525, 0.0525),
            (27900, 161550, 0.055, 0.055),
            (161550, 323200, 0.06, 0.06),
            (323200, 2155350, 0.0685, 0.0685),
            (2155350, 5000000, 0.0965, 0.0965),
            (5000000, 25000000, 0.103, 0.103),
            (25000000, float("inf"), 0.109, 0.109),
        ],
        "brackets_head_of_household": [
            (0, 12800, 0.04, 0.04),
            (12800, 17650, 0.045, 0.045),
            (17650, 20900, 0.0525, 0.0525),
            (20900, 107650, 0.055, 0.055),
            (107650, 269300, 0.06, 0.06),
            (269300, 1616450, 0.0685, 0.0685),
            (1616450, 5000000, 0.0965, 0.0965),
            (5000000, 25000000, 0.103, 0.103),
            (25000000, float("inf"), 0.109, 0.109),
        ],
        "standard_deduction": {"single": 8000, "married": 16050, "head_of_household": 11200},
        "allowance_value": 1000,
    },
    "TX": {
        "brackets": [(0, float("inf"), 0.0, 0.0)],
        "standard_deduction": {"single": 0, "married": 0, "head_of_household": 0},
        "allowance_value": 0,
    },
    "FL": {
        "brackets": [(0, float("inf"), 0.0, 0.0)],
        "standard_deduction": {"single": 0, "married": 0, "head_of_household": 0},
        "allowance_value": 0,
    },
    "WA": {
        "brackets": [(0, float("inf"), 0.0, 0.0)],
        "standard_deduction": {"single": 0, "married": 0, "head_of_household": 0},
        "allowance_value": 0,
    },
    "NC": {
        "brackets_single": [(0, float("inf"), 0.0399, 0.0399)],
        "brackets_married": [(0, float("inf"), 0.0399, 0.0399)],
        "brackets_head_of_household": [(0, float("inf"), 0.0399, 0.0399)],
        "standard_deduction": {"single": 12750, "married": 25500, "head_of_household": 19125},
        "allowance_value": 0,
    },
}
