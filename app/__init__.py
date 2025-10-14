# app/__init__.py

import os
import sys
import traceback
from datetime import datetime, timedelta
from flask import Flask, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# --- Inizializza le estensioni globali ---
db = SQLAlchemy()
login_manager = LoginManager()
jwt = JWTManager()
scheduler = BackgroundScheduler()
migrate = Migrate()

# --- Configurazione Flask-Login ---
login_manager.login_view = 'auth.login'
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"

# --- Gestione Admin ---
from .admin import admin, setup_admin_views


def create_app():
    """
    Factory function per creare e configurare l'app Flask.
    """
    # Directory base del progetto
    app_dir = os.path.abspath(os.path.dirname(__file__))

    # --- Inizializzazione Flask ---
    app = Flask(
        __name__,
        static_folder=os.path.join(app_dir, 'static'),
        static_url_path='/static'
    )

    # Debug Jinja2 (disabilita cache durante lo sviluppo)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.cache = None

    # --- Chiavi di sicurezza ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'un-valore-di-default-molto-sicuro-da-cambiare-in-produzione'
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'

    # --- CONFIGURAZIONE DATABASE E CARTELLE PERSISTENTI ---
    # Usa /data in Linux/Render, oppure ./data in Windows
    if os.name == "nt":  # Windows
        base_data_path = os.path.join(os.path.dirname(app_dir), 'data')
    else:
        base_data_path = '/data'

    # Crea le cartelle solo se possibile (evita errori su Render build)
    try:
        os.makedirs(base_data_path, exist_ok=True)
    except OSError as e:
        print(f"⚠️ Impossibile creare {base_data_path} (probabilmente filesystem di sola lettura): {e}")


    # Percorso database
    db_path = os.path.join(base_data_path, 'site.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Cartelle di upload
    app.config['UPLOAD_FOLDER'] = os.path.join(base_data_path, 'profile_pics')
    app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'] = os.path.join(base_data_path, 'featured_routes')

    # Crea anche le cartelle di upload in locale
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'], exist_ok=True)
    except OSError as e:
        print(f"⚠️ Impossibile creare directory upload: {e}")
    os.makedirs(app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'], exist_ok=True)

    # --- Estensioni Flask ---
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(app_dir, 'migrations'))
    jwt.init_app(app)
    CORS(app)

    # --- Importa modelli ---
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
    from .auth.routes import auth as auth_blueprint
    from .api.routes import api as api_blueprint
    from .mobile.routes import mobile as mobile_blueprint

    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')
    app.register_blueprint(mobile_blueprint, url_prefix='/api/mobile')

    # --- Flask-Admin ---
    admin.init_app(app)
    with app.app_context():
        setup_admin_views(admin, db)
    print("✅ Admin panel configurato e inizializzato.")

    # --- Creazione tabelle DB ---
    with app.app_context():
        try:
            db.create_all()
            print("✅ Tabelle database verificate/create con successo.")
        except Exception as e:
            print(f"⚠️ Errore durante la creazione delle tabelle: {e}")

    # --- Chiusura sfide scadute all'avvio ---
    with app.app_context():
        try:
            from .models import close_expired_challenges
            closed_count = close_expired_challenges()
            if closed_count > 0:
                print(f"🚀 All'avvio: chiuse {closed_count} sfide scadute.")
        except Exception as e:
            print(f"⚠️ Errore chiusura sfide all'avvio: {e}")

    # --- Scheduler per chiusura giornaliera ---
    try:
        if not scheduler.running:
            from .models import close_expired_challenges

            @scheduler.scheduled_job('cron', hour=0, minute=0)
            def close_daily_expired_challenges_job():
                with app.app_context():
                    try:
                        closed_count = close_expired_challenges()
                        if closed_count > 0:
                            print(f"⏰ Scheduler: chiuse {closed_count} sfide scadute.")
                        else:
                            print("⏰ Scheduler: nessuna sfida da chiudere.")
                    except Exception as e:
                        print(f"❌ Errore scheduler: {e}")

            scheduler.start()
            print("✅ Scheduler avviato - chiusura automatica sfide attiva.")
        else:
            print("✅ Scheduler già attivo.")
    except Exception as e:
        print(f"⚠️ Errore nell'avvio dello scheduler: {e}")

    # --- Aggiunge funzioni globali a Jinja2 ---
    app.jinja_env.add_extension('jinja2.ext.do')
    app.jinja_env.globals.update(
        datetime=datetime,
        timedelta=timedelta,
        today_minus_1day=datetime.utcnow() - timedelta(days=1)
    )

    return app


# --- Ferma lo scheduler ---
def stop_scheduler():
    """Ferma lo scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        print("⏹️  Scheduler fermato.")
