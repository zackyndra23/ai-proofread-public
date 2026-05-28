# wsgi.py
"""
WSGI entrypoint for production servers (Gunicorn/uWSGI/mod_wsgi) and local runs.
- Gunicorn:  gunicorn wsgi:app
- uWSGI:     uwsgi --http :5000 --wsgi-file wsgi.py --callable application
"""

import os
from app import app 
try:
  from dotenv import load_dotenv
  load_dotenv()
except Exception:
  pass

from app import create_app

app = create_app()
if __name__ == "__main__":
    port = int(os.getenv("PORT", "2302"))
    app.run(host="0.0.0.0", port=port)