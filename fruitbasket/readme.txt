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