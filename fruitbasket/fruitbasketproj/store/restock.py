import json
import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

try:
    import joblib
except ImportError:  # Keep the store module importable before ML dependencies are installed.
    joblib = None

from django.conf import settings


EXPECTED_FEATURES = [
    "household_size",
    "category",
    "purchased_quantity",
    "previous_interval_days",
]


@lru_cache(maxsize=1)
def load_restock_artifacts():
    """Load the saved pipeline and metadata once for this Python process.

    Returns:
        A dictionary containing `pipeline`, `metadata`, and an optional
        diagnostic `error`. Missing or invalid artifacts produce `None` values
        rather than preventing Django from importing the store module.

    Side effects:
        Reads `ml_models/restock_model.joblib` and
        `ml_models/restock_metadata.json` below Django's `settings.BASE_DIR`.
    """
    try:
        artifact_dir = Path(settings.BASE_DIR) / "ml_models"
        model_path = artifact_dir / "restock_model.joblib"
        metadata_path = artifact_dir / "restock_metadata.json"

        if joblib is None:
            raise RuntimeError("joblib is not installed")
        if not model_path.is_file():
            raise FileNotFoundError(f"Missing restock pipeline: {model_path}")
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Missing restock metadata: {metadata_path}")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        feature_names = metadata.get("feature_names")
        if feature_names != EXPECTED_FEATURES:
            raise ValueError(
                f"Unexpected restock feature names: {feature_names!r}"
            )
        pipeline = joblib.load(model_path)
        return {"pipeline": pipeline, "metadata": metadata, "error": None}
    except (
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
        EOFError,
        ImportError,
        AttributeError,
        ModuleNotFoundError,
        json.JSONDecodeError,
    ) as error:
        return {"pipeline": None, "metadata": None, "error": str(error)}


def _prediction_result(status, latest_purchase_at, interval_days=None, reason=None):
    """Build the public result shape from a validated interval.

    Args:
        status: Result label such as `MODEL`, `INITIAL`, or `UNAVAILABLE`.
        latest_purchase_at: Date of the latest observed purchase.
        interval_days: Positive whole-day interval, if one is available.
        reason: Optional diagnostic explanation for the result.

    Returns:
        A dictionary containing `status`, `interval_days`, `restock_date`, and
        `reason`; unavailable results have null interval/date values.
    """
    result = {
        "status": status,
        "interval_days": None,
        "restock_date": None,
        "reason": reason,
    }
    if interval_days is None:
        return result

    try:
        latest_date = pd.Timestamp(latest_purchase_at).date()
        result["interval_days"] = interval_days
        result["restock_date"] = (
            latest_date + pd.Timedelta(days=interval_days)
        ).isoformat()
    except (TypeError, ValueError, OverflowError) as error:
        result["status"] = "UNAVAILABLE"
        result["reason"] = f"Invalid latest purchase date: {error}"
        result["interval_days"] = None
    return result


def predict_restock(
    latest_purchase_at,
    household_size,
    category,
    purchased_quantity,
    previous_interval_days,
    history_count=2,
):
    """Predict the next restock date from one prepared customer-product history.

    Args:
        latest_purchase_at: Latest observed purchase date.
        household_size: Stable household size used by the training data.
        category: Product category.
        purchased_quantity: Quantity in the latest aggregated purchase.
        previous_interval_days: Days since the preceding distinct purchase.
        history_count: Number of distinct purchase dates available.

    Returns:
        A dictionary with `status`, `interval_days`, `restock_date`, and
        `reason`. `status` is `MODEL` for a valid model prediction, `INITIAL`
        for a training-median fallback, or `UNAVAILABLE` when neither a valid
        model result nor fallback interval exists.

    Notes:
        This function accepts already prepared values and does not query Django
        models. Model output and fallback medians are rounded upward to at
        least one whole day before calculating `restock_date`.
    """
    artifacts = load_restock_artifacts()
    metadata = artifacts["metadata"] or {}
    category_medians = metadata.get("training_only_category_medians", {})
    overall_median = metadata.get("training_only_overall_median")
    if not isinstance(category_medians, dict):
        category_medians = {}

    try:
        latest_date = pd.Timestamp(latest_purchase_at)
        if pd.isna(latest_date):
            raise ValueError("latest purchase date is missing")
    except (TypeError, ValueError) as error:
        return _prediction_result(
            "UNAVAILABLE",
            latest_purchase_at,
            reason=f"Invalid latest purchase date: {error}",
        )

    def fallback(reason):
        """Return the training-derived category or global median fallback."""
        interval = category_medians.get(category, overall_median)
        try:
            interval = float(interval)
            if not math.isfinite(interval) or interval <= 0:
                raise ValueError("fallback interval is not positive and finite")
            return _prediction_result(
                "INITIAL",
                latest_date,
                max(1, math.ceil(interval)),
                reason=reason,
            )
        except (TypeError, ValueError, OverflowError):
            return _prediction_result(
                "UNAVAILABLE",
                latest_date,
                reason=f"{reason}; no usable training-derived fallback",
            )

    if history_count < 2 or previous_interval_days is None:
        return fallback("Insufficient purchase history for model inference")

    try:
        row = pd.DataFrame(
            [
                {
                    "household_size": household_size,
                    "category": category,
                    "purchased_quantity": purchased_quantity,
                    "previous_interval_days": previous_interval_days,
                }
            ],
            columns=EXPECTED_FEATURES,
        )
        pipeline = artifacts["pipeline"]
        if pipeline is None:
            return fallback(
                f"Restock model unavailable: {artifacts['error'] or 'unknown error'}"
            )
        prediction = float(pipeline.predict(row)[0])
        if not math.isfinite(prediction) or prediction <= 0:
            return fallback("Restock model returned an invalid interval")
        return _prediction_result(
            "MODEL",
            latest_date,
            max(1, math.ceil(prediction)),
            reason="Random Forest prediction",
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
        KeyError,
        IndexError,
        RuntimeError,
    ) as error:
        return fallback(f"Restock model prediction failed: {error}")