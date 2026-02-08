import os
import datetime
import psutil
import threading
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from apscheduler.schedulers.background import BackgroundScheduler
import scraper_logic

# --- CRITICAL APP INITIALIZATION ---
app = Flask(__name__)
# Fallback key to prevent crash if env var is missing
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_12345')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///scraper.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- DATABASE MODELS ---
class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    main_site_url = db.Column(db.String(100), default='https://4khdhub.dad')
    mediator_domain = db.Column(db.String(100), default='cryptoinsights.site')
    hubdrive_domain = db.Column(db.String(100), default='hubdrive.space')
    check_interval = db.Column(db.Integer, default=30)

class BotStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    current_action = db.Column(db.String(200), default="Idle")
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    date_added = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Logs(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_error = db.Column(db.Boolean, default=False)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- HELPERS ---
def update_status(message):
    try:
        with app.app_context():
            status = BotStatus.query.first()
            if not status: 
                db.session.add(BotStatus())
                db.session.commit()
                status = BotStatus.query.first()
            status.current_action = message
            status.last_updated = datetime.datetime.utcnow()
            db.session.commit()
            print(f"[STATUS] {message}")
    except: pass

def log_message(message, is_error=False):
    try:
        with app.app_context():
            db.session.add(Logs(message=message, is_error=is_error))
            db.session.commit()
    except: pass

def background_job():
    with app.app_context():
        try:
            settings = Settings.query.first()
            bot_token = os.environ.get('BOT_TOKEN')
            chat_id = os.environ.get('AUTH_CHANNEL')
            
            if not bot_token or not chat_id:
                log_message("Missing BOT_TOKEN or AUTH_CHANNEL env vars", True)
                return

            update_status("🚀 Scheduler Running...")
            history = [h.title for h in History.query.all()]
            
            # Pass our helper functions to the scraper
            new_items = scraper_logic.run_scraper(
                settings.main_site_url, settings.mediator_domain, settings.hubdrive_domain,
                bot_token, chat_id, history, update_status, log_message
            )
            for item in new_items: db.session.add(History(title=item))
            db.session.commit()
            update_status("✅ Sleeping (Idle)")
        except Exception as e:
            log_message(f"Job Failed: {e}", True)
            update_status("❌ Error")

# Start Scheduler
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=background_job, trigger="interval", minutes=30, id='scraper_job')
    scheduler.start()

# --- ROUTES ---
@app.route('/')
@login_required
def dashboard():
    try:
        settings = Settings.query.first()
        # Auto-create settings if missing to prevent crash
        if not settings: 
            settings = Settings()
            db.session.add(settings)
            db.session.commit()
            
        status = BotStatus.query.first()
        if not status:
            status = BotStatus()
            db.session.add(status)
            db.session.commit()

        logs = Logs.query.order_by(Logs.timestamp.desc()).limit(50).all()
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        total = History.query.count()
        errors = Logs.query.filter_by(is_error=True).count()
        
        return render_template('dashboard.html', settings=settings, status=status, logs=logs, cpu=cpu, ram=ram, total=total, errors=errors)
    except Exception as e:
        return f"CRITICAL DASHBOARD ERROR: {str(e)}", 500

@app.route('/settings', methods=['POST'])
@login_required
def update_settings():
    settings = Settings.query.first()
    settings.main_site_url = request.form.get('main_site_url')
    settings.mediator_domain = request.form.get('mediator_domain')
    settings.hubdrive_domain = request.form.get('hubdrive_domain')
    new_interval = int(request.form.get('check_interval'))
    settings.check_interval = new_interval
    try: scheduler.reschedule_job(job_id='scraper_job', trigger='interval', minutes=new_interval)
    except: pass
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/manual-resolve', methods=['POST'])
@login_required
def manual_resolve():
    url = request.form.get('test_url')
    settings = Settings.query.first()
    manual_result = []
    
    if url:
        try:
            # Capture trace logs for the dashboard
            def trace_callback(msg): manual_result.append(msg)
            
            # Call the verbose resolver
            data, trace = scraper_logic.resolve_page_data(
                url, settings.mediator_domain, settings.hubdrive_domain, trace_callback
            )
            
            manual_result.append("=== TRACE LOG ===")
            manual_result.extend(trace)
            
            if data.get('links'):
                manual_result.append("\n=== SUCCESS: LINKS FOUND ===")
                for l in data['links']:
                    manual_result.append(f"{l['name']}: {l['url']}")
            elif "error" in data:
                manual_result.append(f"\n=== ERROR ===\n{data['error']}")
            else:
                manual_result.append("\n=== NO LINKS FOUND ===")
                
        except Exception as e:
            manual_result.append(f"CRITICAL ERROR: {str(e)}")
            
    # Re-render dashboard manually to pass manual_result
    status = BotStatus.query.first()
    logs = Logs.query.order_by(Logs.timestamp.desc()).limit(50).all()
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    total = History.query.count()
    return render_template('dashboard.html', settings=settings, status=status, logs=logs, cpu=cpu, ram=ram, total=total, manual_result=manual_result)

@app.route('/run-now')
@login_required
def run_now():
    threading.Thread(target=background_job).start()
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid Login')
    return render_template('login.html')

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        # --- NUCLEAR FIX: RESET DB ON STARTUP ---
        # Deletes old corrupt DB file and creates fresh one
        db.drop_all()
        db.create_all()
        
        # Create Default Admin
        u = os.environ.get('ADMIN_USERNAME', 'admin')
        p = os.environ.get('ADMIN_PASSWORD', 'admin')
        db.session.add(User(username=u, password=p))
        db.session.add(Settings())
        db.session.add(BotStatus())
        db.session.commit()
        print("DATABASE RESET AND INITIALIZED SUCCESSFULLY")
            
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
