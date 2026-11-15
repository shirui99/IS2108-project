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

Recipe ideas (optional): the Recipe ideas page asks a generative AI service (Anthropic Claude API) for recipes
that use pantry items expiring soon. It needs an API key in an environment variable before runserver is started.
Without a key the page still opens and says recipe ideas are not set up. Never put the key in the code.

PowerShell:  $env:ANTHROPIC_API_KEY = "your key"
Optional:    $env:FRUITBASKET_AI_MODEL = "claude-haiku-5-5"
