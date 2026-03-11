import sys
import os

# Add your project directory to the sys.path
project_home = '/home/pymarket/pymarket'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['FLASK_ENV'] = 'production'

from app import app, init_db
init_db()
application = app
