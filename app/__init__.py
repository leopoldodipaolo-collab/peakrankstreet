# app/__init__.py

import os
from flask import Flask, redirect, url_for, request # Importa Flask e alcune funzioni utili
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_cors import CORS # Necessario se esponi API
from flask_jwt_extended import JWTManager # Necessario per JWT
from datetime import datetime, timedelta
from dotenv import load_dotenv # Per caricare le variabili d'ambiente
from apscheduler.schedulers.background import BackgroundScheduler # Per lo scheduler
import sys # Per stampare messaggi di debug su stderr
import traceback # Per stampare traceback
from flask_migrate import Migrate

# --- Inizializza le estensioni globalmente ---
# Queste verranno poi inizializzate con l'app nella factory create_app()
db = SQLAlchemy()
login_manager = LoginManager()
jwt = JWTManager()
scheduler = BackgroundScheduler()

# --- Configurazione Flask-Login ---
login_manager.login_view = 'auth.login' # Route di login quando l'utente non è autenticato
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"
migrate = Migrate() # <-- INIZIALIZZA MIGRATE QUI (fuori da create_app)

# --- Gestione Admin (Flask-Admin) ---
# Importa l'istanza admin e la funzione di setup dal modulo admin
# Assicurati che questi file esistano in app/admin/ e siano importabili
from .admin import admin, setup_admin_views

# --- Factory Function dell'Applicazione ---
def create_app():
    """
    Factory function per creare e configurare l'istanza dell'applicazione Flask.
    """
    app_dir = os.path.abspath(os.path.dirname(__file__))

    app = Flask(__name__,
                static_folder=os.path.join(app_dir, 'static'),
                static_url_path='/static')

    # --- AGGIUNGI QUESTE RIGHE PER DISABILITARE LA CACHE DI JINJA2 (PER DEBUG) ---
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.cache = None
    # --- FINE AGGIUNTA ---

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'un-valore-di-default-molto-sicuro-da-cambiare-in-produzione'
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'

    db_path = os.path.join(app_dir, 'site.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/profile_pics')
    app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/featured_routes')

    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    if not os.path.exists(app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER']):
        os.makedirs(app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'])

    app.jinja_env.add_extension('jinja2.ext.do')

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(app_dir, 'migrations'))
    jwt.init_app(app)
    CORS(app)

    from .models import User, Notification

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

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

    from .main.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .auth.routes import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .api.routes import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    from .mobile.routes import mobile as mobile_blueprint
    app.register_blueprint(mobile_blueprint, url_prefix='/api/mobile')

    from .admin import admin, setup_admin_views

    admin.init_app(app)

    with app.app_context():
        setup_admin_views(admin, db)
    print("✅ Admin panel configurato e inizializzato.")

    with app.app_context():
        try:
            db.create_all()
            print("✅ Tabelle database verificate/create con successo.")
        except Exception as e:
            print(f"⚠️ Errore durante la creazione delle tabelle: {e}")

    with app.app_context():
        try:
            from .models import close_expired_challenges
            closed_count = close_expired_challenges()
            if closed_count > 0:
                print(f"🚀 All'avvio: chiuse {closed_count} sfide scadute.")
        except Exception as e:
            print(f"⚠️ Errore chiusura sfide all'avvio: {e}")

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