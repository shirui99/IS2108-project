# Graph Report - IS2108-project  (2026-11-15)

## Corpus Check
- 99 files · ~42,963 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 17 file(s) not represented in the graph (top: .sqlite3 9, (none) 3, .css 3)

## Summary
- 967 nodes · 2375 edges · 65 communities (35 shown, 30 thin omitted)
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 386 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `1eb593d1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- store/views.py
- adminpanel/views.py
- CustomerManagementTests
- Project Runtime
- Admin Panel Pages
- Application Routing
- Site Layout and Setup
- django_db
- Storefront Pages
- App Configuration
- Customer
- ReceiptTests
- Product
- restock.py
- Graphify Instructions
- Admin Form Components
- CategoryTests
- CancellationTests
- restock_metadata.json
- train_restock.py
- StockAdviceTests
- SubscriptionCycle
- django_db_models_deletion
- AdjustmentTests
- CustomerEdgeCaseTests
- CustomerStoryTests
- Subscription
- GroupPurchase
- get_restock_suggestions
- ProductPhotoTests
- process_due_subscriptions
- account_views.py
- test_order_inspection.py
- StoreMutationTests
- FinalVerificationTests
- .render
- Review
- subscription_processing.py
- prediction_records.py
- MoreCustomerStoryTests
- test_integration_audit.py
- FulfilmentTests
- SubscriptionSafetyTests
- generate_purchases.py
- PredictionCaptureTests
- ReviewModerationTests
- AuditJourneys
- Product
- AGENTS.md - FruitBasket pair project
- SupportResponseTests
- StaffAuthenticationTests
- ArtifactLoadingTests
- CategoryMigrationTests
- DeactivateProductTests
- PersonalHistoryTests
- CancellationMigrationTests
- ReviewModeration
- CancelPrepareRaceTests
- CategoryMLTests
- PredictionMigrationTests

## God Nodes (most connected - your core abstractions)
1. `Product` - 89 edges
2. `Customer` - 88 edges
3. `Item` - 84 edges
4. `Orders` - 76 edges
5. `Subscription` - 43 edges
6. `process_due_subscriptions()` - 36 edges
7. `SubscriptionCycle` - 32 edges
8. `CustomerEdgeCaseTests` - 32 edges
9. `CustomerStoryTests` - 30 edges
10. `Category` - 26 edges

## Surprising Connections (you probably didn't know these)
- `ProductForm` --uses--> `Product`  [INFERRED]
  fruitbasket/fruitbasketproj/adminpanel/forms.py → fruitbasket/fruitbasketproj/adminpanel/models.py
- `ProductView` --uses--> `ProductForm`  [INFERRED]
  fruitbasket/fruitbasketproj/adminpanel/views.py → fruitbasket/fruitbasketproj/adminpanel/forms.py
- `ItemBatchForm` --uses--> `InventoryBatch`  [INFERRED]
  fruitbasket/fruitbasketproj/adminpanel/forms.py → fruitbasket/fruitbasketproj/adminpanel/models.py
- `ItemBatchForm` --uses--> `Product`  [INFERRED]
  fruitbasket/fruitbasketproj/adminpanel/forms.py → fruitbasket/fruitbasketproj/adminpanel/models.py
- `ItemView` --uses--> `ItemBatchForm`  [INFERRED]
  fruitbasket/fruitbasketproj/adminpanel/views.py → fruitbasket/fruitbasketproj/adminpanel/forms.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Admin Management Workflow** — fruitbasket_fruitbasketproj_adminpanel_templates_adminpanel_customer_new_customer_management, fruitbasket_fruitbasketproj_adminpanel_templates_adminpanel_item_new_stock_management, fruitbasket_fruitbasketproj_adminpanel_templates_adminpanel_order_new_order_management, fruitbasket_fruitbasketproj_adminpanel_templates_adminpanel_product_new_product_management [INFERRED 0.95]

## Communities (65 total, 30 thin omitted)

### Community 0 - "store/views.py"
Cohesion: 0.19
Nodes (11): sellable_stock_filter(), stock_cutoff(), ProfileForm, ReviewForm, cart(), index(), logout(), orders() (+3 more)

### Community 1 - "adminpanel/views.py"
Cohesion: 0.17
Nodes (7): ItemBatchForm, OrderCancellationForm, OrderForm, Meta, category_code(), staff_cancel_order(), StockChanged

### Community 2 - "CustomerManagementTests"
Cohesion: 0.06
Nodes (14): CustomerForm, Meta, StockAdjustmentForm, CustomerManagementTests, request(), run(), CustomerView, fulfil_order() (+6 more)

### Community 4 - "Admin Panel Pages"
Cohesion: 0.24
Nodes (12): Admin Panel Base Template, Admin Panel Header Template, Admin Panel Navigation Template, Customer Management Page, Customer Records, Staff Home Page, Inventory Batches, Stock Management Page (+4 more)

### Community 6 - "Site Layout and Setup"
Cohesion: 0.18
Nodes (11): Fruit Basket Site Base Template, Django Online Grocery Store, Fruit Basket Landing Page, Fruit Basket Site Header, Online Store Navigation Destination, Fruit Basket Site Navigation, Django Development Server, Fruit Basket Development Setup Instructions (+3 more)

### Community 7 - "django_db"
Cohesion: 0.08
Nodes (10): Migration, Migration, Migration, Migration, Migration, Migration, Migration, Migration (+2 more)

### Community 8 - "Storefront Pages"
Cohesion: 0.36
Nodes (10): Shopping Cart Page, Checkout Page, Product Catalog Page, Login Page, Orders Page, Pantry Page, Sign Up Page, Store Base Layout (+2 more)

### Community 10 - "Customer"
Cohesion: 0.15
Nodes (7): Customer, Meta, Orders, FulfilmentConcurrencyTests, Command, Command, login_middleware()

### Community 12 - "Product"
Cohesion: 0.25
Nodes (4): Item, Meta, Product, Meta

### Community 13 - "restock.py"
Cohesion: 0.19
Nodes (4): load_restock_artifacts(), predict_restock(), fallback(), _prediction_result()

### Community 18 - "CategoryTests"
Cohesion: 0.08
Nodes (7): CategoryForm, Meta, ProductForm, Meta, CategoryTests, ProductStoryTests, CategoryView

### Community 19 - "CancellationTests"
Cohesion: 0.10
Nodes (7): CancelledAllocation, InventoryBatch, Meta, OrderCancellation, cancel_order(), AD20Tests, CancellationTests

### Community 20 - "restock_metadata.json"
Cohesion: 0.07
Nodes (33): counts, cross_boundary_excluded, eligible_examples, test_examples, training_examples, cutoff, dependencies, joblib@1.6.0 (+25 more)

### Community 21 - "train_restock.py"
Cohesion: 0.11
Nodes (8): build_pipeline(), load_and_prepare_data(), prepare_training_data(), run_training(), run_worked_assertion(), save_model_and_metadata(), split_by_cutoff(), train_and_evaluate()

### Community 22 - "StockAdviceTests"
Cohesion: 0.14
Nodes (3): get_stock_advice(), StockAdviceTests, SellabilityTests

### Community 23 - "SubscriptionCycle"
Cohesion: 0.14
Nodes (7): Category, Meta, SubscriptionCycle, Meta, DueRetryConcurrencyTests, SubscriptionHoldMigrationTests, SubscriptionProcessingRaceTests

### Community 24 - "django_db_models_deletion"
Cohesion: 0.10
Nodes (10): Migration, Migration, Migration, Migration, Migration, Migration, Migration, Migration (+2 more)

### Community 28 - "Subscription"
Cohesion: 0.20
Nodes (11): Subscription, Meta, check_future_date(), ResumeForm, SubscriptionEditForm, SubscriptionForm, subscription_action(), subscription_edit() (+3 more)

### Community 29 - "GroupPurchase"
Cohesion: 0.20
Nodes (13): GroupPurchase, Meta, GroupForm, group_detail(), group_join(), groups(), pooled_lines(), generate_order_id() (+5 more)

### Community 30 - "get_restock_suggestions"
Cohesion: 0.22
Nodes (4): get_customer_purchase_history(), get_restock_suggestions(), RestockFeatureTests, restock()

### Community 32 - "process_due_subscriptions"
Cohesion: 0.16
Nodes (4): DueSubscriptionTests, process_due_subscriptions(), ProcessingResults, run()

### Community 33 - "account_views.py"
Cohesion: 0.14
Nodes (10): SavedItem, Meta, StockNotice, Meta, change_password(), saved_item(), saved_list(), stock_notice() (+2 more)

### Community 34 - "test_order_inspection.py"
Cohesion: 0.15
Nodes (8): GroupLine, Meta, GroupMember, Meta, OrderInspectionTests, order_inspection_detail(), order_inspection_list(), _order_origin()

### Community 35 - "StoreMutationTests"
Cohesion: 0.12
Nodes (3): CatalogueAndCartLoginTests, CustomerAuthenticationMiddlewareTests, StoreMutationTests

### Community 36 - "FinalVerificationTests"
Cohesion: 0.16
Nodes (8): StockAdjustment, Meta, buyer_client(), FinalVerificationTests, fail(), writeoff_data(), WriteoffCheckoutRaceTests, run()

### Community 37 - ".render"
Cohesion: 0.14
Nodes (9): index(), login(), ProductView, stock_advice(), SignupForm, generate_customer_id(), login(), pantry() (+1 more)

### Community 38 - "Review"
Cohesion: 0.25
Nodes (8): Review, Meta, ModerationForm, page(), review_action(), review_detail(), review_list(), staff_access()

### Community 39 - "subscription_processing.py"
Cohesion: 0.17
Nodes (5): process_subscriptions(), staff_access(), subscription_processing(), Command, ScheduledCycleConflict

### Community 40 - "prediction_records.py"
Cohesion: 0.28
Nodes (10): RestockCapture, Meta, capture_current(), CaptureFilters, CaptureSelection, prediction_capture(), prediction_detail(), prediction_list() (+2 more)

### Community 42 - "test_integration_audit.py"
Cohesion: 0.19
Nodes (3): SupportTicket, Meta, SupportResponseConcurrencyTests

### Community 45 - "generate_purchases.py"
Cohesion: 0.24
Nodes (4): generate_events(), main(), validate_events(), write_events()

### Community 48 - "AuditJourneys"
Cohesion: 0.22
Nodes (3): AuditFailureProbes, AuditJourneys, AuditMethodTests

### Community 49 - "Product"
Cohesion: 0.18
Nodes (10): Brand Commitments, Capabilities and Constraints, Evidence on Hand, Operating Context, Platform, Positioning, Product, Product Principles (+2 more)

### Community 50 - "AGENTS.md - FruitBasket pair project"
Cohesion: 0.20
Nodes (9): AGENTS.md - FruitBasket pair project, Architecture and changes, FruitBasket stock policy, Graphify navigation, Machine learning, Requests, security and data, Scope and authority, Templates and UI (+1 more)

### Community 58 - "ReviewModeration"
Cohesion: 0.33
Nodes (3): ReviewModeration, Meta, ReviewModerationMigrationTests

## Knowledge Gaps
- **16 isolated node(s):** `Graphify CLI`, `Graphify Wiki Index`, `Reusable Form Field Rows`, `Admin Panel Header Template`, `Customer Records` (+11 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 388 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **30 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Customer` connect `Customer` to `store/views.py`, `adminpanel/views.py`, `CustomerManagementTests`, `django_db`, `Product`, `restock.py`, `CategoryTests`, `CancellationTests`, `StockAdviceTests`, `SubscriptionCycle`, `AdjustmentTests`, `CustomerEdgeCaseTests`, `CustomerStoryTests`, `Subscription`, `GroupPurchase`, `get_restock_suggestions`, `ProductPhotoTests`, `process_due_subscriptions`, `account_views.py`, `test_order_inspection.py`, `StoreMutationTests`, `FinalVerificationTests`, `.render`, `prediction_records.py`, `MoreCustomerStoryTests`, `test_integration_audit.py`, `FulfilmentTests`, `SubscriptionSafetyTests`, `PredictionCaptureTests`, `ReviewModerationTests`, `AuditJourneys`, `SupportResponseTests`, `StaffAuthenticationTests`, `DeactivateProductTests`, `PersonalHistoryTests`, `CancelPrepareRaceTests`?**
  _High betweenness centrality (0.137) - this node is a cross-community bridge._
- **Are the 50 inferred relationships involving `Product` (e.g. with `ItemBatchForm` and `ProductForm`) actually correct?**
  _`Product` has 50 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Graphify CLI`, `Graphify Wiki Index`, `Reusable Form Field Rows` to the rest of the system?**
  _16 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `CustomerManagementTests` be split into smaller, more focused modules?**
  _Cohesion score 0.0613107822410148 - nodes in this community are weakly interconnected._
- **Why does `Product` connect `Product` to `store/views.py`, `adminpanel/views.py`, `CustomerManagementTests`, `django_db`, `Customer`, `ReceiptTests`, `restock.py`, `CategoryTests`, `CancellationTests`, `StockAdviceTests`, `SubscriptionCycle`, `AdjustmentTests`, `CustomerEdgeCaseTests`, `CustomerStoryTests`, `Subscription`, `GroupPurchase`, `get_restock_suggestions`, `ProductPhotoTests`, `process_due_subscriptions`, `account_views.py`, `test_order_inspection.py`, `StoreMutationTests`, `.render`, `prediction_records.py`, `MoreCustomerStoryTests`, `test_integration_audit.py`, `FulfilmentTests`, `SubscriptionSafetyTests`, `PredictionCaptureTests`, `ReviewModerationTests`, `StaffAuthenticationTests`, `DeactivateProductTests`, `PersonalHistoryTests`, `CancelPrepareRaceTests`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._
- **Are the 47 inferred relationships involving `Customer` (e.g. with `CustomerForm` and `CaptureSelection`) actually correct?**
  _`Customer` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Should `Application Routing` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._