# Restock data contract

This prototype estimates when a customer may next purchase a product. It uses
the existing Django `Customer`, `Product`, `Orders`, and `Item` records; no
additional database fields are assumed.

## Qualifying purchase events

- Include **delivered personal orders** (`Orders.Ostatus == "delivered"`).
  `Orders.Odate` is the purchase date.
- Identify the customer through `Orders.Ocustomer_id`, the product through
  `Item.Iproduct_id`, and include each `Item` attached to the order through
  `Item.Iorder_id`.
- Count all attached Items, regardless of `Item.Istatus`. An Item remains part
  of the purchase after it is used or discarded; do not filter on its current
  status.
- Exclude cancelled orders (`Orders.Ostatus == "cancelled"`). Filtering for
  delivered orders already excludes them.
- Aggregate by customer, product, and `Odate`. Multiple orders or Items for the
  same customer-product on the same date form one event; sum their Items into
  one `purchased_quantity`.

## Features and target

| Contract name | Existing field or definition |
| --- | --- |
| `household_size` | `Customer.Chouseholdsize` |
| `category` | `Product.Pcategory` |
| `purchased_quantity` | Count of qualifying Items in the aggregated event |
| `previous_interval_days` | Days between this event date and the preceding distinct purchase date for the same customer and product |
| `target_days` | Days from this event date to the next distinct purchase date for the same customer and product |

Use the customer’s current household size for historical events and assume it
was stable over the prototype’s history. Do not infer changes from order data.

## History requirements

- **Two or more distinct purchase dates** for the same customer-product provide
  a prior interval and permit ML inference using the latest event.
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