
Student Leave Management System (SLMS)
-------------------------------------
Tech: HTML, CSS, Bootstrap, Flask, SQLite3

Quick start (local dev):
1. Create a virtualenv: python -m venv venv
2. Activate it: source venv/bin/activate  (Windows: venv\Scripts\activate)
3. Install requirements: pip install -r requirements.txt
4. Update MAIL_USERNAME and MAIL_PASSWORD in app.py (or set env vars)
5. Run: python app.py
6. Open: http://127.0.0.1:5000

Notes:
- The project includes placeholder email sending. In dev the verification link will be printed to console if email fails.
- Reminder job runs every 30 minutes (BackgroundScheduler) and prints a placeholder message.
- This is a minimal skeleton. You asked for a zip you can implement directly: expand features as needed.
