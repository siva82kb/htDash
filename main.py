from flask import Flask, render_template, redirect, url_for, session as flask_session
from config import Config
import os

# Import blueprints
from routes.auth import bp as auth_bp
from routes.dashboard import bp as dashboard_bp
from routes.user_management import bp as user_management_bp
from routes.device_data import bp as device_data_bp
from routes.charts import bp as charts_bp
from routes.exercises import bp as exercises_bp  
from routes.adl_exercises import bp as adl_bp  
from routes.exercise_timing import bp as timing_bp 
from routes.exit_questionnaire import bp as exit_bp  
from routes.call_logs import bp as call_logs_bp
from routes.patient_events import bp as patient_events_bp
from routes.notes import bp as notes_bp
from routes.devices import bp as devices_bp
from routes.sim_cards import bp as sim_cards_bp 
from routes.time_records import bp as time_records_bp

app = Flask(__name__)
app.config.from_object(Config)

# Cache static files for 1 hour in production; templates auto-reload only in debug
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 if Config.DEBUG else 3600
app.config['TEMPLATES_AUTO_RELOAD'] = Config.DEBUG

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(user_management_bp)
app.register_blueprint(device_data_bp)
app.register_blueprint(charts_bp)
app.register_blueprint(exercises_bp) 
app.register_blueprint(adl_bp, url_prefix='/adl') 
app.register_blueprint(timing_bp, url_prefix='/timing') 
app.register_blueprint(exit_bp, url_prefix='/exit') 
app.register_blueprint(call_logs_bp)
app.register_blueprint(patient_events_bp, url_prefix='/patient_events')
app.register_blueprint(notes_bp)
app.register_blueprint(devices_bp, url_prefix='/devices')
app.register_blueprint(sim_cards_bp, url_prefix='/sim_cards')
app.register_blueprint(time_records_bp, url_prefix='/time_records')

import time as _time
_JS_VERSION = str(int(_time.time()))  # changes on every server restart

@app.context_processor
def inject_globals():
    return dict(use_local_storage=Config.USE_LOCAL_STORAGE, js_version=_JS_VERSION)


@app.after_request
def add_header(response):
    """Disable caching only for HTML pages and API responses; allow static assets to be cached."""
    content_type = response.content_type or ''
    # Don't disable cache for static assets (JS, CSS, images, fonts)
    if 'text/html' in content_type or 'application/json' in content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
    return response

@app.route('/')
def index():
    if not flask_session.get('login_place'):
        return redirect(url_for('login'))
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/login')
def login():
    if flask_session.get('login_place'):
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return redirect(url_for('index'))

@app.route('/devices')
def devices():
    from flask import session as flask_session
    if not flask_session.get('login_place'):
        return redirect(url_for('login'))
    return render_template('devices.html', active_page='devices')

if __name__ == '__main__':
    # Ensure necessary directories exist
    os.makedirs(Config.LOG_DIR, exist_ok=True)
    os.makedirs(Config.META_DATA_PATH, exist_ok=True)
    for hospital in Config.HOSPITALS:
        os.makedirs(os.path.join(Config.DATA_ROOT, hospital, 'patients'), exist_ok=True)
        os.makedirs(os.path.join(Config.DATA_ROOT, hospital, 'dashboard'), exist_ok=True)
        for device in ['pluto', 'mars', 'actigraphs', 'modems', 'sims']:
            os.makedirs(os.path.join(Config.DATA_ROOT, hospital, 'devices', device), exist_ok=True)
    
    app.run(host="0.0.0.0", port=8080, debug=Config.DEBUG)