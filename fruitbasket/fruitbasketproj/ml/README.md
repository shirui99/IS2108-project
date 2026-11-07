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