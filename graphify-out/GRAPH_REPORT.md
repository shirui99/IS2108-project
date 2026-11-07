# Graph Report - IS2108-project  (2026-11-07)

## Corpus Check
- Corpus is ~5,830 words - fits in a single context window. You may not need a graph.

## Summary
- 144 nodes · 205 edges · 18 communities (7 shown, 11 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 22 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Store Operations
- Product and Inventory
- Customer Accounts
- Project Runtime
- Admin Panel Pages
- Site Layout and Setup
- Database Migrations
- Storefront Pages
- App Configuration
- Login Access Control
- Item Management
- Graphify Instructions
- Admin Form Components

## God Nodes (most connected - your core abstractions)
1. `Product` - 14 edges
2. `Customer` - 13 edges
3. `Orders` - 12 edges
4. `Item` - 11 edges
5. `ItemView` - 7 edges
6. `Admin Panel Base Template` - 7 edges
7. `Store Base Layout` - 7 edges
8. `Store Navigation Menu` - 7 edges
9. `ProductView` - 6 edges
10. `CustomerView` - 6 edges

## Surprising Connections (you probably didn't know these)
- `cart()` --uses--> `Product`  [INFERRED]
  fruitbasket/fruitbasketproj/store/views.py → fruitbasket/fruitbasketproj/adminpanel/models.py
- `index()` --uses--> `Product`  [INFERRED]
  fruitbasket/fruitbasketproj/store/views.py → fruitbasket/fruitbasketproj/adminpanel/models.py
- `ItemView` --uses--> `ItemBatchForm`  [INFERRED]
  fruitbasket/fruitbasketproj/adminpanel/views.py → fruitbasket/fruitbasketproj/adminpanel/forms.py
- `OrderForm` --uses--> `Orders`  [INFERRED]
  fruitbasket/fruitbasketproj/adminpanel/forms.py → fruitbasket/fruitbasketproj/adminpanel/models.py
- `OrderView` --uses--> `OrderForm`  [INFERRED]
  fruitbasket/fruitbasketproj/adminpanel/views.py → fruitbasket/fruitbasketproj/adminpanel/forms.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Admin Management Workflow** — fruitbasket_fruitbasketproj_adminpanel_templates_adminpanel_customer_new_customer_management, fruitbasket_fruitbasketproj_adminpanel_templates_adminpanel_item_new_stock_management, fruitbasket_fruitbasketproj_adminpanel_templates_adminpanel_order_new_order_management, fruitbasket_fruitbasketproj_adminpanel_templates_adminpanel_product_new_product_management [INFERRED 0.95]

## Communities (18 total, 11 thin omitted)

### Community 0 - "Store Operations"
Cohesion: 0.16
Nodes (9): Item, Meta, Orders, cart(), checkout(), generate_order_id(), index(), orders() (+1 more)

### Community 1 - "Product and Inventory"
Cohesion: 0.17
Nodes (8): ItemBatchForm, OrderForm, Meta, ProductForm, Meta, Product, Meta, ProductView

### Community 2 - "Customer Accounts"
Cohesion: 0.18
Nodes (8): CustomerForm, Meta, Customer, Meta, CustomerView, OrderView, generate_customer_id(), signup()

### Community 4 - "Admin Panel Pages"
Cohesion: 0.24
Nodes (12): Admin Panel Base Template, Admin Panel Header Template, Admin Panel Navigation Template, Customer Management Page, Customer Records, Staff Home Page, Inventory Batches, Stock Management Page (+4 more)

### Community 6 - "Site Layout and Setup"
Cohesion: 0.18
Nodes (11): Fruit Basket Site Base Template, Django Online Grocery Store, Fruit Basket Landing Page, Fruit Basket Site Header, Online Store Navigation Destination, Fruit Basket Site Navigation, Django Development Server, Fruit Basket Development Setup Instructions (+3 more)

### Community 7 - "Database Migrations"
Cohesion: 0.20
Nodes (3): Migration, Migration, Migration

### Community 8 - "Storefront Pages"
Cohesion: 0.36
Nodes (10): Shopping Cart Page, Checkout Page, Product Catalog Page, Login Page, Orders Page, Pantry Page, Sign Up Page, Store Base Layout (+2 more)

## Knowledge Gaps
- **16 isolated node(s):** `Admin Panel Header Template`, `Reusable Form Field Rows`, `Fruit Basket Site Header`, `Customer Records`, `Inventory Batches` (+11 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 64 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Product` connect `Product and Inventory` to `Store Operations`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `Product` (e.g. with `ItemBatchForm` and `ProductForm`) actually correct?**
  _`Product` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Admin Panel Header Template`, `Reusable Form Field Rows`, `Fruit Basket Site Header` to the rest of the system?**
  _16 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Why does `Customer` connect `Customer Accounts` to `Store Operations`, `Product and Inventory`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Customer` (e.g. with `CustomerForm` and `CustomerView`) actually correct?**
  _`Customer` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Why does `Item` connect `Store Operations` to `Product and Inventory`, `Item Management`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Orders` (e.g. with `OrderForm` and `OrderView`) actually correct?**
  _`Orders` has 4 INFERRED edges - model-reasoned connections that need verification._