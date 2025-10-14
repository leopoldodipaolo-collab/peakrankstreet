# app/__init__.py

import os
from flask import Flask, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

# --- Estensioni globali ---
db = SQLAlchemy()
login_manager = LoginManager()
jwt = JWTManager()
migrate = Migrate()
scheduler = BackgroundScheduler()

# --- Configurazione Flask-Login ---
login_manager.login_view = 'auth.login'
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"

# --- Gestione Admin ---
from .admin import admin, setup_admin_views

# --- Factory function ---
def create_app():
    app = Flask(__name__)

    # --- Configurazioni ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret-key-change-in-prod')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-key-change-in-prod')

    # --- DATABASE POSTGRESQL ---
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql://peakrankstreet_db_user:2Ih7mXJUYaaVwKUeMFpOgqQbgRosQGE3@dpg-d3jper6mcj7s73fbkbr0-a.frankfurt-postgres.render.com/peakrankstreet_db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --- Percorsi upload locali (opzionali) ---
    app.config['UPLOAD_FOLDER'] = None
    app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'] = None

    # --- Disabilita cache Jinja2 (debug) ---
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.cache = None
    app.jinja_env.add_extension('jinja2.ext.do')

    # --- Inizializza estensioni ---
    db.init_app(app)
    login_manager.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    # --- Importa modelli e definisci user_loader ---
    from .models import User, Notification

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- Context processor globale ---
    @app.context_processor
    def inject_global_variables():
        unread_notifications_count = 0
        if current_user.is_authenticated:
            unread_notifications_count = Notification.query.filter_by(
                recipient_id=current_user.id, read=False
            ).count()
        return dict(
            now=datetime.utcnow(),
            user_city=current_user.city if current_user.is_authenticated else None,
            unread_notifications_count=unread_notifications_count
        )

    # --- Blueprints ---
    from .main.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .auth.routes import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .api.routes import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    from .mobile.routes import mobile as mobile_blueprint
    app.register_blueprint(mobile_blueprint, url_prefix='/api/mobile')

    # --- Admin setup ---
    admin.init_app(app)
    with app.app_context():
        setup_admin_views(admin, db)
        print("✅ Admin panel configurato e inizializzato.")

    # --- Scheduler per chiusura sfide scadute ---
    from .models import close_expired_challenges

    try:
        if not scheduler.running:
            @scheduler.scheduled_job('cron', hour=0, minute=0)  # ogni mezzanotte
            def close_daily_expired_challenges_job():
                with app.app_context():
                    closed_count = close_expired_challenges()
                    if closed_count > 0:
                        print(f"⏰ Scheduler: chiuse {closed_count} sfide scadute.")
                    else:
                        print("⏰ Scheduler: nessuna sfida da chiudere.")
            scheduler.start()
            print("✅ Scheduler avviato - chiusura automatica sfide attiva.")
    except Exception as e:
        print(f"⚠️ Errore nell'avvio dello scheduler: {e}")

    # --- Jinja globals ---
    app.jinja_env.globals.update(
        datetime=datetime,
        timedelta=timedelta,
        today_minus_1day=datetime.utcnow() - timedelta(days=1)
    )

    return app

# --- Funzione di stop scheduler ---
def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        print("⏹️ Scheduler fermato.")
