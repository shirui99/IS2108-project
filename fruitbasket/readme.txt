Step 1. Change to the fruitbasket folder

Step 2. Create virtual environment:

python -m venv venv

Step 3. Activate virtual environment:

.\venv\Scripts\activate.bat

Step 4. Restore Python packages:

pip install -r requirements.txt

Step 5. Run the project on the development server:

cd fruitbasketproj
python manage.py runserver

Optional: add the sample grocery catalogue from the folder containing manage.py:

python manage.py seed_catalog

This adds missing products and sample warehouse stock. Existing products and
order relationships are retained. The old sample customer username
restock_demo is renamed to alex.tan; its password remains unchanged.

Subscriptions: orders for due subscriptions are created by running this from the folder containing manage.py
(run it once a day, or by hand for a demo):

python manage.py process_subscriptions
