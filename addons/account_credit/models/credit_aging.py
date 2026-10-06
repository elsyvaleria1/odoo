AGING_BUCKETS = (
    ("current", "Not due", None, 0),
    ("b1_30", "1-30 days", 1, 30),
    ("b31_60", "31-60 days", 31, 60),
    ("b61_90", "61-90 days", 61, 90),
    ("b91_180", "91-180 days", 91, 180),
    ("b180_plus", "Over 180 days", 181, None),
)
AGING_SELECTION = [(code, label) for code, label, _lo, _hi in AGING_BUCKETS]
AGING_CODES = tuple(code for code, *_ in AGING_BUCKETS)


def aging_bucket(days_past_due):
    for code, _label, low, high in AGING_BUCKETS:
        if low is None and days_past_due <= (high or 0):
            return code
        if (
            low is not None
            and days_past_due >= low
            and (high is None or days_past_due <= high)
        ):
            return code
    return AGING_CODES[-1]


def aging_case_sql(days_expression) -> str:
    parts = ["CASE"]
    for code, _label, low, high in AGING_BUCKETS:
        if low is None:
            parts.append(f"WHEN {days_expression} <= {high or 0} THEN '{code}'")
        elif high is None:
            parts.append(f"WHEN {days_expression} >= {low} THEN '{code}'")
        else:
            parts.append(
                f"WHEN {days_expression} BETWEEN {low} AND {high} THEN '{code}'"
            )
    parts.append(f"ELSE '{AGING_CODES[-1]}' END")
    return " ".join(parts)
