## Restock Timing Model
##Function: Predict the interval until a customer next purchases the same product, then automatically display products approaching their estimated repurchase date.

# Restock data contract

This prototype estimates when a customer may next purchase a product. It uses
the existing Django `Customer`, `Product`, `Orders`, and `Item` records; no
additional database fields are assumed.

## Raw CSV contract

The generated synthetic CSV has exactly these columns:

`customer_id, product_id, category, household_size, purchased_quantity, purchased_at`

`customer_id` is a synthetic customer identifier, not a Django primary key.
`purchased_at` is the purchase date. The generator keeps product pack
definitions internally to guide quantity ranges; they are not model inputs and
are not included in the CSV.

When preparing real events from Django, include **delivered personal orders**
(`Orders.Ostatus == "delivered"`), using `Orders.Odate` as `purchased_at`.
Identify customers through `Orders.Ocustomer_id`, products through
`Item.Iproduct_id`, and include Items attached through `Item.Iorder_id`.
Count every attached Item regardless of `Item.Istatus`; used or discarded Items
still count toward the original purchase. Exclude cancelled orders.

Aggregate by customer, product, and purchase date. Combine same-day orders into
one event and sum their Items into `purchased_quantity`.

## Features and target

| Contract name | Existing field or definition |
| --- | --- |
| `household_size` | `Customer.Chouseholdsize` |
| `category` | `Product.Pcategory` |
| `purchased_quantity` | Count of qualifying Items in the aggregated event |
| `purchased_at` | Synthetic event date; `Orders.Odate` for real events |
| `previous_interval_days` | Derived during training data preparation: days since the preceding distinct purchase date for the same customer and product |
| `target_days` | Training label derived from the next distinct purchase date for the same customer and product |

`previous_interval_days` and `target_days` are not raw CSV columns. Compute them
after ordering events by customer, product, and `purchased_at`; `target_days`
is only available for historical events with a later distinct purchase date.

Use the customer’s current household size for historical events and assume it
was stable over the prototype’s history. Do not infer changes from order data.

## History requirements

- **Two or more distinct purchase dates** for the same customer-product provide
  a prior interval and permit ML inference using the latest event. For synthetic
  data, eight purchase dates are generated for each selected customer-product.
- **One distinct purchase date** permits only a labelled initial estimate; it
  does not provide a learned prior interval.
- **No qualifying history** produces no personalised suggestion.
- `target_days` is available only for historical events with a later distinct
  purchase date. Same-day purchases are combined before intervals and targets
  are calculated.

## Personal-order scope and current status mismatch

Today, `Orders.Ocustomer` identifies one customer, but there is no field that
marks an order as personal versus subscription- or group-generated. If those
order types are added, add an explicit order source/type or ownership
relationship and qualify personal orders by that marker; do not assume that
having an `Ocustomer` alone proves the order was personal.

There is a current delivery-status inconsistency: `store.views.checkout`
creates an order without setting `Ostatus`, so it keeps the model default
`"placed"`, while it immediately changes the attached Items to
`Istatus == "delivered"`. Under this contract, that checkout order is not yet a
qualifying delivered order. This README records the mismatch; checkout behavior
is intentionally unchanged.

## End-to-end flow

1. Checkout creates an `Orders` row, assigns the selected warehouse `Item`
   rows to it, and marks those Items as delivered. The current checkout code
   leaves the order itself as `"placed"`.
2. The restock history query follows `Item.Iorder` to `Orders`, filters the
   session customer's `Ocustomer_id`, and accepts only orders with
   `Ostatus == "delivered"`. It groups attached Items by product and
   `Odate`, so two same-day orders become one quantity. Later `used` or
   `expired` statuses do not remove the original purchase from history.
3. For each active product with an unexpired or undated available warehouse
   Item, the helper uses the latest two distinct purchase dates and the latest
   quantity to build the four named model features.
4. The saved pipeline predicts an interval. With only one purchase date, or
   when the pipeline is unavailable or returns an invalid value, the helper
   uses the training-only category median and then the training-only overall
   median, labelling the result `INITIAL`. With no usable artifact or fallback,
   it returns `UNAVAILABLE`.
5. The helper keeps overdue products and products due through today plus three
   days, sorting by estimated date. The view adds the human-readable due status
   and estimate label, then renders `store/restock.html`, where the existing
   cart URL is used for “Add to Cart”.

Therefore, with the current checkout implementation, a real purchase does not
reach step 2 until another part of the application changes its order status to
`"delivered"`. The order status must be authoritative for delivery; an Item's
`Istatus == "delivered"` alone is not sufficient.

## Training commands and artifacts

Run these commands from `fruitbasket/fruitbasketproj`:

```powershell
python ml/generate_purchases.py
python ml/train_restock.py
python manage.py check
python manage.py test store
```

The generator writes the raw synthetic events to
`ml/data/purchases.csv`. Training reads that CSV and writes:

- `ml_models/restock_model.joblib` — fitted preprocessing and random-forest
  pipeline.
- `ml_models/restock_metadata.json` — feature names, training-only fallback
  medians, cutoff, dependency versions, counts, and evaluation results.

The current saved run used Python 3.13.5, pandas 3.1.1, scikit-learn 1.9.1,
and joblib 1.6.0. It prepared 4,320 eligible examples, trained on 4,092,
tested on 107, and excluded 121 anchors crossing the cutoff
`2024-09-01`. Test MAE was 5.374 days for the previous-interval baseline,
7.159 days for the category-median baseline, and 5.071 days for the random
forest. Reloaded pipeline predictions matched the original predictions.

These are synthetic-data measurements, not evidence of real customer
accuracy. The generated histories use fixed product selections and stable
household size, and the model has not been validated against populated
production-like FruitBasket purchase histories.

## Operational assumptions and limitations

- The saved artifacts must be present below Django `BASE_DIR / "ml_models"`.
  Metadata is loaded independently, so a missing or unloadable pipeline can
  still support `INITIAL` fallback estimates when metadata is valid.
- Training and serving must continue to use exactly
  `household_size`, `category`, `purchased_quantity`, and
  `previous_interval_days`; identifiers and dates are grouping/evaluation
  fields, not model inputs.
- The prototype assumes household size is stable and uses the customer's
  current `Chouseholdsize` for every historical event.
- The order schema has no personal/subscription/group origin marker. If those
  origins are introduced, add an explicit order type or ownership relation and
  filter for personal orders before training or serving.
- `Orders.Odate` is treated as the purchase/delivery date. The feature does
  not infer consumption from `Ifinished`, `Istatus`, or expiry dates.
- Available stock is screened for `Istatus == "available"` and
  `Iexpiry IS NULL` or `Iexpiry > today`; checkout remains responsible for
  delivery-date eligibility.
- The view obtains `Customer.Cid` from the project's `request.session["Cid"]`
  login convention. The restock URL is `/store/restock/`, and the URL is not
  protected by the existing middleware list; the view itself redirects when
  that session value is absent.