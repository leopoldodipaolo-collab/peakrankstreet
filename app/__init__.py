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
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

# --- Carica variabili d'ambiente ---
load_dotenv()

# --- Inizializza estensioni globali ---
db = SQLAlchemy()
login_manager = LoginManager()
jwt = JWTManager()
scheduler = BackgroundScheduler()
csrf = CSRFProtect()
migrate = Migrate()

# --- Admin ---
from .admin import admin, setup_admin_views


def create_app():
    """
    Factory function per creare e configurare l'istanza dell'applicazione Flask.
    """
    app_dir = os.path.abspath(os.path.dirname(__file__))

    # --- Creazione app Flask ---
    app = Flask(
        __name__,
        static_folder=os.path.join(app_dir, 'static'),
        static_url_path='/static'
    )

    # --- Configurazioni base ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'un-valore-di-default-molto-sicuro-da-cambiare-in-produzione'
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # --- Configurazione Database ---
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        print("✅ Utilizzo database PostgreSQL da DATABASE_URL")
    else:
        db_path = os.path.join(app_dir, 'site.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        print("⚠️  Utilizzo SQLite per sviluppo locale (DATABASE_URL non trovato)")

    # --- Configurazione cartelle Upload ---
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'posts_images')
    app.config['PROFILE_PICS_FOLDER'] = os.path.join(app.root_path, 'static', 'profile_pics')
    app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'featured_routes')

    # Crea le directory se non esistono
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PROFILE_PICS_FOLDER'], exist_ok=True)
    os.makedirs(app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'], exist_ok=True)

    # --- Estensioni Jinja ---
    app.jinja_env.add_extension('jinja2.ext.do')

    # --- Inizializzazione estensioni ---
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(app_dir, 'migrations'))
    jwt.init_app(app)
    CORS(app)
    csrf.init_app(app)
    from flask_wtf.csrf import generate_csrf

    @app.context_processor
    def inject_csrf_token():
        from flask_wtf.csrf import generate_csrf
        return dict(csrf_token=generate_csrf)

    # --- Configura Login Manager ---
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))

    # --- Context Processor Globale ---
    @app.context_processor
    def inject_global_variables():
        unread_notifications_count = 0
        if current_user.is_authenticated:
            from .models import Notification
            unread_notifications_count = Notification.query.filter_by(
                recipient_id=current_user.id, read=False
            ).count()
        return dict(
            now=datetime.utcnow(),
            user_city=current_user.city if current_user.is_authenticated else None,
            unread_notifications_count=unread_notifications_count
        )

    # --- Registrazione Blueprint ---
    from .main.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .auth.routes import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .api.routes import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    from .mobile.routes import mobile as mobile_blueprint
    app.register_blueprint(mobile_blueprint, url_prefix='/api/mobile')

    # --- Configura Admin ---
    admin.init_app(app)
    with app.app_context():
        setup_admin_views(admin, db)
    print("✅ Admin panel configurato e inizializzato.")

    # --- Crea Tabelle Database ---
    with app.app_context():
        try:
            db.create_all()
            print("✅ Tabelle database verificate/create con successo.")
        except Exception as e:
            print(f"⚠️ Errore durante la creazione delle tabelle: {e}")

    # --- Gestione Sfide Scadute (All'avvio) ---
    with app.app_context():
        try:
            from .main.gamification import close_expired_challenges
            closed_count = close_expired_challenges()
            if closed_count > 0:
                print(f"🚀 All'avvio: chiuse {closed_count} sfide scadute.")
        except Exception as e:
            print(f"⚠️ Errore chiusura sfide all'avvio: {e}")

    # --- Scheduler per attività periodiche ---
    try:
        if not scheduler.running:
            from .main.gamification import close_expired_challenges
            
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

    # --- Globals per Jinja ---
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
        print("⏹️  Scheduler fermato.")
