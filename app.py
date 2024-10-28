import os
from flask import Flask

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "odoo-recommender-secret-key"

# Import routes after app initialization
import routes
