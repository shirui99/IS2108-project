import json
from importlib.metadata import version
from pathlib import Path
from platform import python_version

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


INPUT_PATH = Path(__file__).resolve().parent / "data" / "purchases.csv"
PREDICTOR_COLUMNS = [
    "household_size",
    "category",
    "purchased_quantity",
    "previous_interval_days",
]
IDENTIFIER_COLUMNS = ["customer_id", "product_id", "purchased_at"]
TARGET_COLUMN = "target_days"
CUTOFF_DATE = pd.Timestamp("2024-09-01")
MODEL_PATH = Path(__file__).resolve().parent.parent / "ml_models" / "restock_model.joblib"
METADATA_PATH = (
    Path(__file__).resolve().parent.parent / "ml_models" / "restock_metadata.json"
)
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


def split_by_cutoff(prepared, cutoff=CUTOFF_DATE):
    """Split examples without allowing observations across the time boundary.

    Args:
        prepared: Prepared examples containing anchor and next-purchase dates.
        cutoff: Timestamp separating training and test anchors.

    Returns:
        A `(training, test)` tuple. Training targets are observed before the
        cutoff; test anchors are on or after it.
    """
    cutoff = pd.Timestamp(cutoff)
    training = prepared[prepared["next_purchase_at"] < cutoff].copy()
    test = prepared[prepared["purchased_at"] >= cutoff].copy()
    return training, test


def build_pipeline():
    """Build the unfit preprocessing and Random Forest regression pipeline.

    Returns:
        A scikit-learn Pipeline with categorical one-hot encoding, numeric
        passthrough, and a fixed-seed RandomForestRegressor.
    """
    categorical_columns = ["category"]
    numeric_columns = [
        "household_size",
        "purchased_quantity",
        "previous_interval_days",
    ]
    preprocessing = ColumnTransformer(
        [
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                categorical_columns,
            ),
            ("numeric", "passthrough", numeric_columns),
        ]
    )
    return Pipeline(
        [
            ("preprocessing", preprocessing),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=200,
                    random_state=2108,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def train_and_evaluate(prepared, cutoff=CUTOFF_DATE):
    """Train on the historical partition, evaluate baselines and the forest.

    Args:
        prepared: Eligible examples returned by `prepare_training_data`.
        cutoff: Timestamp separating training and test anchors.

    Returns:
        A dictionary containing the fitted pipeline, evaluation results,
        partition counts, and training-only category/overall medians.

    Raises:
        ValueError: If either chronological partition is empty.
    """
    training, test = split_by_cutoff(prepared, cutoff)
    if training.empty or test.empty:
        raise ValueError("Chronological cutoff must leave both train and test rows.")

    # Fit every learned value only on training examples; test rows are evaluation-only.
    pipeline = build_pipeline()
    pipeline.fit(training[PREDICTOR_COLUMNS], training[TARGET_COLUMN])

    category_medians = training.groupby("category")[TARGET_COLUMN].median()
    overall_median = float(training[TARGET_COLUMN].median())
    category_predictions = test["category"].map(category_medians).fillna(overall_median)
    previous_predictions = test["previous_interval_days"]
    forest_predictions = pipeline.predict(test[PREDICTOR_COLUMNS])

    results = {
        "previous_interval_mae_days": float(
            mean_absolute_error(test[TARGET_COLUMN], previous_predictions)
        ),
        "category_median_mae_days": float(
            mean_absolute_error(test[TARGET_COLUMN], category_predictions)
        ),
        "random_forest_mae_days": float(
            mean_absolute_error(test[TARGET_COLUMN], forest_predictions)
        ),
    }
    return {
        "pipeline": pipeline,
        "eligible_examples": len(prepared),
        "training": training,
        "test": test,
        "category_medians": {str(key): float(value) for key, value in category_medians.items()},
        "overall_median": overall_median,
        "results": results,
        "forest_predictions": forest_predictions,
    }


def save_model_and_metadata(evaluation, cutoff=CUTOFF_DATE):
    """Persist the fitted pipeline and training/evaluation metadata.

    Args:
        evaluation: Result dictionary returned by `train_and_evaluate`.
        cutoff: Timestamp used for the chronological split.

    Returns:
        None.

    Side effects:
        Writes the fitted joblib pipeline and JSON metadata beside this script.
    """
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(evaluation["pipeline"], MODEL_PATH)

    reloaded_pipeline = joblib.load(MODEL_PATH)
    original_predictions = evaluation["forest_predictions"]
    reloaded_predictions = reloaded_pipeline.predict(
        evaluation["test"][PREDICTOR_COLUMNS]
    )
    reload_matches = bool(np.allclose(original_predictions, reloaded_predictions))
    if not reload_matches:
        raise ValueError("Reloaded pipeline predictions do not match fitted predictions.")

    metadata = {
        "model_version": "restock-random-forest-v1",
        "feature_names": PREDICTOR_COLUMNS,
        "target_column": TARGET_COLUMN,
        "training_only_category_medians": evaluation["category_medians"],
        "training_only_overall_median": evaluation["overall_median"],
        "cutoff": pd.Timestamp(cutoff).date().isoformat(),
        "counts": {
            "eligible_examples": int(evaluation["eligible_examples"]),
            "training_examples": int(len(evaluation["training"])),
            "test_examples": int(len(evaluation["test"])),
            "cross_boundary_excluded": int(
                evaluation["eligible_examples"]
                - len(evaluation["training"])
                - len(evaluation["test"])
            ),
        },
        "evaluation": evaluation["results"],
        "pipeline_reload_predictions_match": reload_matches,
        "dependencies": {
            "python": python_version(),
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": version("joblib"),
        },
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def run_training():
    """Prepare data, train/evaluate the model, save artifacts, and print metrics.

    Returns:
        The evaluation dictionary from `train_and_evaluate`.
    """
    prepared, _, _ = load_and_prepare_data()
    evaluation = train_and_evaluate(prepared)
    save_model_and_metadata(evaluation)
    print(f"Prepared examples: {len(prepared)}")
    print(f"Training examples: {len(evaluation['training'])}")
    print(f"Test examples: {len(evaluation['test'])}")
    for name, mae in evaluation["results"].items():
        print(f"{name}: {mae:.3f} days")
    print(f"Saved pipeline: {MODEL_PATH.resolve()}")
    print(f"Saved metadata: {METADATA_PATH.resolve()}")
    print("Reloaded predictions match: PASS")
    return evaluation


if __name__ == "__main__":
    run_worked_assertion()
    run_training()