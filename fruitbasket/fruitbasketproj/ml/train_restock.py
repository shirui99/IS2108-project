from pathlib import Path

import pandas as pd


INPUT_PATH = Path(__file__).resolve().parent / "data" / "purchases.csv"
PREDICTOR_COLUMNS = [
    "household_size",
    "category",
    "purchased_quantity",
    "previous_interval_days",
]
IDENTIFIER_COLUMNS = ["customer_id", "product_id", "purchased_at"]
TARGET_COLUMN = "target_days"
RAW_COLUMNS = [
    "customer_id",
    "product_id",
    "category",
    "household_size",
    "purchased_quantity",
    "purchased_at",
]


def prepare_training_data(purchases):
    """Prepare eligible historical anchors and return predictors and target.

    Args:
        purchases: Raw purchase events as a pandas DataFrame.

    Returns:
        A tuple of `(prepared, predictors, target)`. `prepared` retains
        identifiers and derived dates for grouping and evaluation; `predictors`
        contains exactly the model input columns; `target` contains
        `target_days`.

    Raises:
        ValueError: If required columns are missing or an interval is invalid.
    """
    missing_columns = sorted(set(RAW_COLUMNS) - set(purchases.columns))
    if missing_columns:
        raise ValueError(f"Missing raw purchase columns: {', '.join(missing_columns)}")

    events = purchases[RAW_COLUMNS].copy()
    events["purchased_at"] = pd.to_datetime(events["purchased_at"], errors="raise")

    # Same-day rows represent one purchase event; quantity is the sum of Items.
    events = (
        events.groupby(
            ["customer_id", "product_id", "purchased_at"],
            as_index=False,
            sort=False,
        )
        .agg(
            household_size=("household_size", "first"),
            category=("category", "first"),
            purchased_quantity=("purchased_quantity", "sum"),
        )
    )
    events = events.sort_values(
        ["customer_id", "product_id", "purchased_at"]
    ).reset_index(drop=True)
    history = events.groupby(["customer_id", "product_id"], sort=False)

    # shift(1) and shift(-1) inspect the previous and following event in each history.
    events["previous_purchase_at"] = history["purchased_at"].shift(1)
    events["next_purchase_at"] = history["purchased_at"].shift(-1)
    events["previous_interval_days"] = (
        events["purchased_at"] - events["previous_purchase_at"]
    ).dt.days
    events["target_days"] = (
        events["next_purchase_at"] - events["purchased_at"]
    ).dt.days

    interval_columns = ["previous_interval_days", "target_days"]
    invalid_intervals = events[interval_columns].dropna().le(0).any(axis=1)
    if invalid_intervals.any():
        raise ValueError("Purchase histories contain non-positive intervals.")

    # The first and last event have no complete previous-to-next training anchor.
    eligible = events.dropna(subset=interval_columns).copy()
    prepared_columns = IDENTIFIER_COLUMNS + [
        "household_size",
        "category",
        "purchased_quantity",
        "previous_interval_days",
        "next_purchase_at",
        TARGET_COLUMN,
    ]
    prepared = eligible[prepared_columns]
    predictors = prepared[PREDICTOR_COLUMNS]
    target = prepared[TARGET_COLUMN]
    return prepared, predictors, target


def load_and_prepare_data(input_path=INPUT_PATH):
    """Read the raw purchase CSV and prepare eligible training examples.

    Args:
        input_path: CSV path; defaults to the data file beside this script.

    Returns:
        The `(prepared, predictors, target)` tuple from `prepare_training_data`.
    """
    purchases = pd.read_csv(input_path)
    return prepare_training_data(purchases)


def run_worked_assertion():
    """Check shift-derived intervals on a three-event example.

    Returns:
        None after confirming intervals of 7 and 10 days.
    """
    example = pd.DataFrame(
        {
            "customer_id": ["C001", "C001", "C001"],
            "product_id": ["P001", "P001", "P001"],
            "category": ["fruit", "fruit", "fruit"],
            "household_size": [3, 3, 3],
            "purchased_quantity": [2, 2, 2],
            "purchased_at": ["2024-01-01", "2024-01-08", "2024-01-18"],
        }
    )
    prepared, predictors, target = prepare_training_data(example)
    assert len(prepared) == 1
    assert predictors.columns.tolist() == PREDICTOR_COLUMNS
    assert target.name == TARGET_COLUMN
    assert prepared.iloc[0]["previous_interval_days"] == 7
    assert prepared.iloc[0]["target_days"] == 10


if __name__ == "__main__":
    run_worked_assertion()
    prepared, _, _ = load_and_prepare_data()
    print(f"Eligible examples: {len(prepared)}")