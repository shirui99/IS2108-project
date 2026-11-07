import csv
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


SEED = 2108
HOUSEHOLD_COUNT = 120
PRODUCTS_PER_HOUSEHOLD = 6
PURCHASES_PER_HISTORY = 8
OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "purchases.csv"
FIELDNAMES = (
    "customer_id",
    "product_id",
    "category",
    "household_size",
    "purchased_quantity",
    "purchased_at",
)

# Category values match Product.CATEGORY; pack definitions guide quantity ranges.
PRODUCTS = (
    ("P001", "dairy", "1 L carton", 9, 3),
    ("P002", "dairy", "12-egg carton", 12, 2),
    ("P003", "fruit", "1 kg bag", 7, 4),
    ("P004", "fruit", "500 g pack", 10, 4),
    ("P005", "meat", "500 g pack", 14, 3),
    ("P006", "meat", "1 kg pack", 18, 2),
    ("P007", "bakery", "1 loaf", 5, 3),
    ("P008", "rice", "5 kg bag", 35, 1),
    ("P009", "snacks", "200 g pack", 11, 5),
    ("P010", "frozen", "500 g pack", 21, 3),
    ("P011", "household", "1 L bottle", 30, 2),
    ("P012", "rice", "1 kg bag", 24, 2),
)
CATEGORIES = {
    "dairy",
    "fruit",
    "meat",
    "bakery",
    "rice",
    "snacks",
    "frozen",
    "household",
}


def generate_events(seed=SEED):
    """Generate reproducible household-product events; return rows without targets.

    Args:
        seed: Seed for the local random generator.

    Returns:
        CSV-ready event dictionaries with one row per distinct purchase date.
    """
    rng = random.Random(seed)
    rows = []
    first_possible_date = date(2024, 1, 1)

    for household_number in range(1, HOUSEHOLD_COUNT + 1):
        household_id = f"H{household_number:03d}"
        household_size = rng.randint(1, 6)
        selected_products = sorted(rng.sample(PRODUCTS, PRODUCTS_PER_HOUSEHOLD))

        for product_id, category, _pack_definition, typical_interval, max_quantity in selected_products:
            purchase_date = first_possible_date + timedelta(days=rng.randint(0, 90))
            household_cadence = rng.uniform(0.8, 1.2)

            for purchase_number in range(PURCHASES_PER_HISTORY):
                if purchase_number:
                    interval = max(
                        3,
                        round(typical_interval * household_cadence + rng.randint(-4, 4)),
                    )
                    # A small share of periods are longer, reflecting occasional stock-up gaps.
                    if rng.random() < 0.12:
                        interval += rng.randint(8, 24)
                    purchase_date += timedelta(days=interval)

                rows.append(
                    {
                        "customer_id": household_id,
                        "product_id": product_id,
                        "category": category,
                        "household_size": household_size,
                        "purchased_quantity": rng.randint(1, max_quantity)
                        + (household_size - 1) // 3,
                        "purchased_at": purchase_date.isoformat(),
                    }
                )

    return rows


def validate_events(rows):
    """Check row counts, feature values, and strictly increasing histories.

    Args:
        rows: Event dictionaries returned by `generate_events`.

    Returns:
        A mapping of check names to pass/fail booleans.
    """
    histories = defaultdict(list)
    household_sizes = defaultdict(set)
    product_definitions = defaultdict(set)
    household_products = defaultdict(set)
    for row in rows:
        key = (row["customer_id"], row["product_id"])
        histories[key].append(row)
        household_sizes[row["customer_id"]].add(row["household_size"])
        household_products[row["customer_id"]].add(row["product_id"])
        product_definitions[row["product_id"]].add(row["category"])

    expected_rows = HOUSEHOLD_COUNT * PRODUCTS_PER_HOUSEHOLD * PURCHASES_PER_HISTORY
    valid_histories = len(histories) == HOUSEHOLD_COUNT * PRODUCTS_PER_HOUSEHOLD
    for events in histories.values():
        dates = [date.fromisoformat(row["purchased_at"]) for row in events]
        if len(dates) != PURCHASES_PER_HISTORY or any(
            current <= previous for previous, current in zip(dates, dates[1:])
        ):
            valid_histories = False
            break
    return {
        "row_count": len(rows) == expected_rows,
        "household_count": len(household_sizes) == HOUSEHOLD_COUNT,
        "six_products_per_household": all(
            len(products) == PRODUCTS_PER_HOUSEHOLD
            for products in household_products.values()
        ),
        "eight_strictly_increasing_dates_per_history": valid_histories,
        "stable_household_size": all(len(sizes) == 1 for sizes in household_sizes.values()),
        "positive_whole_quantities": all(
            isinstance(row["purchased_quantity"], int)
            and row["purchased_quantity"] > 0
            for row in rows
        ),
        "valid_categories": all(row["category"] in CATEGORIES for row in rows),
        "consistent_product_definitions": len({product[0] for product in PRODUCTS})
        == len(PRODUCTS)
        and all(product[2] for product in PRODUCTS)
        and all(
            product_id in product_definitions
            and product_definitions[product_id] == {category}
            for product_id, category, _pack, _interval, _quantity in PRODUCTS
        ),
        "raw_contract_columns": all(set(row) == set(FIELDNAMES) for row in rows),
        "derived_features_excluded": all(
            "previous_interval_days" not in row
            and "target_days" not in row
            and "pack_definition" not in row
            for row in rows
        ),
    }


def write_events(rows, output_path=OUTPUT_PATH):
    """Write event rows to CSV and return the resolved output path.

    Args:
        rows: Event dictionaries returned by `generate_events`.
        output_path: Destination CSV path.

    Returns:
        The resolved path of the written CSV.

    Side effects:
        Creates the destination directory if needed and overwrites the CSV.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return output_path.resolve()


def main():
    """Generate, validate, and save the synthetic event CSV."""
    rows = generate_events()
    checks = validate_events(rows)
    checks["reproducible_fixed_seed"] = rows == generate_events()
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise ValueError(f"Generated data failed checks: {', '.join(failed_checks)}")

    output_path = write_events(rows)
    print(f"Rows written: {len(rows)}")
    print(f"Output: {output_path}")
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")


if __name__ == "__main__":
    main()