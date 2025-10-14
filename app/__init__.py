# app/__init__.py

import os
from flask import Flask, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import sys
import traceback
from flask_migrate import Migrate

# --- Estensioni globali ---
db = SQLAlchemy()
login_manager = LoginManager()
jwt = JWTManager()
scheduler = BackgroundScheduler()
migrate = Migrate()

# --- Flask-Login ---
login_manager.login_view = 'auth.login'
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"

# --- Admin ---
from .admin import admin, setup_admin_views


def create_app():
    """Factory function per creare e configurare l'app Flask."""
    app_dir = os.path.abspath(os.path.dirname(__file__))

    app = Flask(
        __name__,
        static_folder=os.path.join(app_dir, 'static'),
        static_url_path='/static'
    )

    # --- Debug ---
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.cache = None
    app.jinja_env.add_extension('jinja2.ext.do')

    # --- Chiavi segrete ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'jwt-secret')

    # --- Database & upload path ---
    base_data_path = '/data'
    db_path = os.path.join(base_data_path, 'site.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(base_data_path, 'profile_pics')
    app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'] = os.path.join(base_data_path, 'featured_routes')

    # --- Creazione directory solo se il filesystem lo permette ---
    for path in [base_data_path, app.config['UPLOAD_FOLDER'], app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER']]:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            print(f"⚠️ Impossibile creare {path} (probabilmente filesystem di sola lettura): {e}")

    # --- Inizializzazione estensioni ---
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(app_dir, 'migrations'))
    jwt.init_app(app)
    CORS(app)

    # --- Import modelli ---
    from .models import User, Notification, close_expired_challenges

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- Context processor ---
    @app.context_processor
    def inject_globals():
        unread = 0
        if current_user.is_authenticated:
            unread = Notification.query.filter_by(recipient_id=current_user.id, read=False).count()
        return dict(
            now=datetime.utcnow(),
            user_city=current_user.city if current_user.is_authenticated else None,
            unread_notifications_count=unread
        )

    # --- Blueprint ---
    from .main.routes import main as main_blueprint
    from .auth.routes import auth as auth_blueprint
    from .api.routes import api as api_blueprint
    from .mobile.routes import mobile as mobile_blueprint

    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')
    app.register_blueprint(mobile_blueprint, url_prefix='/api/mobile')

    # --- Admin ---
    admin.init_app(app)
    with app.app_context():
        setup_admin_views(admin, db)
    print("✅ Admin panel configurato e inizializzato.")

    # --- Database setup ---
    with app.app_context():
        try:
            db.create_all()
            print("✅ Tabelle database create/verificate con successo.")
        except Exception as e:
            print(f"⚠️ Errore durante la creazione delle tabelle: {e}")

    # --- Chiudi sfide scadute all'avvio ---
    with app.app_context():
        try:
            closed = close_expired_challenges()
            if closed > 0:
                print(f"🚀 All'avvio: chiuse {closed} sfide scadute.")
        except Exception as e:
            print(f"⚠️ Errore chiusura sfide all'avvio: {e}")

    # --- Scheduler ---
    try:
        if not scheduler.running:
            @scheduler.scheduled_job('cron', hour=0, minute=0)
            def close_daily_expired_challenges():
                with app.app_context():
                    try:
                        closed = close_expired_challenges()
                        if closed > 0:
                            print(f"⏰ Scheduler: chiuse {closed} sfide scadute.")
                        else:
                            print("⏰ Scheduler: nessuna sfida da chiudere.")
                    except Exception as e:
                        print(f"❌ Errore scheduler: {e}")

            scheduler.start()
            print("✅ Scheduler avviato.")
        else:
            print("✅ Scheduler già attivo.")
    except Exception as e:
        print(f"⚠️ Errore nell'avvio dello scheduler: {e}")

    # --- Variabili globali Jinja ---
    app.jinja_env.globals.update(
        datetime=datetime,
        timedelta=timedelta,
        today_minus_1day=datetime.utcnow() - timedelta(days=1)
    )

    return app


def stop_scheduler():
    """Ferma lo scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        print("⏹️ Scheduler fermato.")
