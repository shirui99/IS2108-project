import json
import math
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
from django.db.models import Count, Q
from django.utils import timezone

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


def get_customer_purchase_history(customer_id):
    """Aggregate qualifying purchase history by product and order date.

    Args:
        customer_id: `Customer.Cid` identifying the personal customer history.

    Returns:
        A dictionary keyed by product ID. Each value is a chronologically
        ordered list of dictionaries containing `purchased_at` and
        `purchased_quantity`. Products with no qualifying history are absent.

    Notes:
        The ownership filter uses `Orders.Ocustomer_id` and delivered status.
        There is no separate personal-order marker in the current schema, so
        future subscription/group orders will need an explicit type or
        ownership field before they can be excluded here.
    """
    from adminpanel.models import Item

    events = (
        Item.objects.filter(
            Iorder__Ocustomer_id=customer_id,
            Iorder__Ostatus="delivered",
        )
        .values("Iproduct_id", "Iorder__Odate")
        .annotate(purchased_quantity=Count("id"))
        .order_by("Iproduct_id", "Iorder__Odate")
    )
    history = {}
    for event in events:
        history.setdefault(event["Iproduct_id"], []).append(
            {
                "purchased_at": event["Iorder__Odate"],
                "purchased_quantity": event["purchased_quantity"],
            }
        )
    return history


def get_restock_suggestions(customer_id, today=None, due_within_days=3):
    """Return due restock suggestions for one customer.

    Args:
        customer_id: `Customer.Cid` whose personal purchase history is used.
        today: Date used for due/stock screening; defaults to local Django date.
        due_within_days: Inclusive number of future days to show.

    Returns:
        A list of dictionaries sorted by `restock_date`. Each result contains
        `product_id`, `product_name`, `category`, `available_stock`,
        `purchased_quantity`, `latest_purchase_at`, `interval_days`,
        `restock_date`, `status`, and `reason`. Products with no history,
        inactive products, unavailable stock, or dates beyond the due window
        are not returned.
    """
    from adminpanel.models import Customer, Product

    today = today or timezone.localdate()
    due_until = today + timedelta(days=due_within_days)
    history = get_customer_purchase_history(customer_id)
    if not history:
        return []
    household_size = (
        Customer.objects.filter(pk=customer_id)
        .values_list("Chouseholdsize", flat=True)
        .first()
    )
    if household_size is None:
        return []

    available_filter = Q(product_items__Istatus="available") & (
        Q(product_items__Iexpiry__isnull=True)
        | Q(product_items__Iexpiry__gt=today)
    )
    products = (
        Product.objects.filter(Pactive=True, Pid__in=history)
        .annotate(available_stock=Count("product_items", filter=available_filter))
    )

    suggestions = []
    for product in products:
        events = history[product.Pid]
        latest = events[-1]
        previous = events[-2] if len(events) >= 2 else None
        previous_interval_days = (
            (latest["purchased_at"] - previous["purchased_at"]).days
            if previous
            else None
        )
        prediction = predict_restock(
            latest_purchase_at=latest["purchased_at"],
            household_size=household_size,
            category=product.Pcategory,
            purchased_quantity=latest["purchased_quantity"],
            previous_interval_days=previous_interval_days,
            history_count=len(events),
        )
        restock_date = prediction["restock_date"]
        if not product.available_stock or not restock_date:
            continue
        restock_date = pd.Timestamp(restock_date).date()
        if restock_date > due_until:
            continue
        suggestions.append(
            {
                "product_id": product.Pid,
                "product_name": product.Pname,
                "category": product.Pcategory,
                "available_stock": product.available_stock,
                "purchased_quantity": latest["purchased_quantity"],
                "latest_purchase_at": latest["purchased_at"],
                **prediction,
            }
        )

    return sorted(suggestions, key=lambda suggestion: suggestion["restock_date"])


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