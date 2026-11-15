# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Household shoppers who buy groceries, keep track of perishables and check when to restock.
- Employees who manage the product catalogue, warehouse stock, customers, orders and support through a separate staff panel.

## Product Purpose

FruitBasket is a business-to-consumer grocery website that brings shopping and pantry tracking together. It helps shoppers see what they have, notice approaching expiry dates and make more informed restocking decisions.

## Positioning

FruitBasket connects the grocery purchase journey to a personal pantry and restock suggestions based on purchase history. Customers can act on those suggestions by adding products to their cart.

## Operating Context

- Customers can browse products, create an account, sign in, manage a cart, place orders and review order details.
- The pantry shows purchased items and expiry information. Customers can record whether an item was used or thrown away, and can rate an item.
- Restock suggestions use purchase history and identify whether an estimate came from the trained model or the initial fallback.
- Staff use custom views to manage products, stock, customers, orders and support tickets.
- This is a pair project for the IS2108 course. Team members need to understand and explain the application and disclose material AI assistance.

## Capabilities and Constraints

- The existing application uses Python, Django, the Django ORM and server-rendered templates. Follow the project instructions in `AGENTS.md` and preserve existing workflows and data contracts.
- The project uses a trained model persisted as a joblib artifact for restock suggestions, with an initial fallback when a model estimate is unavailable or unsuitable. Do not describe the fallback as a trained prediction or claim real-world effectiveness from synthetic evaluation.
- The adopted restock pipeline uses `HistGradientBoostingRegressor` with household size, product category, latest purchase quantity and previous purchase interval as inputs. Its recorded chronological test MAE is 3.776 days on synthetic data; serving labels model predictions `MODEL`, median fallbacks `INITIAL`, and unusable estimates `UNAVAILABLE`. See `docs/ml/restock-model.md` for the training data, feature and evaluation details.
- Preserve customer ownership and staff authorization. Customer and staff workflows have distinct access requirements.
- Keep the interface usable with a keyboard, provide readable labels and textual status information, and support small screens without relying on a JavaScript navigation menu.
- The existing catalogue and sample warehouse stock include synthetic records created for development. Treat sample prices, stock and customer information as test data, not evidence of a real commercial operation.

## Brand Commitments

- The product is named FruitBasket.
- Its purpose joins grocery shopping with a more thoughtful pantry and perishable-tracking routine.

## Evidence on Hand

- Product and workflow implementation: `fruitbasket/fruitbasketproj/store/` and `fruitbasket/fruitbasketproj/adminpanel/`.
- Existing product categories and data model: `fruitbasket/fruitbasketproj/adminpanel/models.py`.
- Restock implementation and model documentation: `fruitbasket/fruitbasketproj/store/restock.py` and `docs/ml/restock-model.md`.
- Sample catalogue setup: `fruitbasket/fruitbasketproj/store/management/commands/seed_catalog.py`.
- Local setup instructions: `fruitbasket/readme.txt`.
- No verified customer testimonials, commercial performance figures or real-world model effectiveness evidence were supplied. Do not invent them.

## Product Principles

1. Make shopping and pantry information easy to understand and act on.
2. Put expiry information and the customer's existing groceries in view when they make food decisions.
3. Present restock suggestions as estimates and let the customer decide what to buy.
4. Ground product details and status messages in the application's actual records and capabilities.
5. Keep customer and staff workflows understandable, accessible and appropriate to their roles.
