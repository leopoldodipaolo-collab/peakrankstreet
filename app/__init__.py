# app/__init__.py

import os
import sys
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv

from flask import Flask, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler

# Carica .env se presente (utile in sviluppo)
load_dotenv()

# --- Estensioni globali ---
db = SQLAlchemy()
login_manager = LoginManager()
jwt = JWTManager()
migrate = Migrate()
scheduler = BackgroundScheduler()

# --- Config Flask-Login ---
login_manager.login_view = 'auth.login'
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"

# --- Admin (assicurati che app/admin esista) ---
from .admin import admin, setup_admin_views  # import a livello modulo; devono esistere


def create_app():
    """
    Factory function per creare e configurare l'app Flask.
    Compatibile con:
      - Ambiente di sviluppo (Windows/macOS/Linux) usando SQLite come fallback
      - Deploy su Render / Docker usando una DATABASE_URL (Postgres)
    """
    app_dir = os.path.abspath(os.path.dirname(__file__))

    app = Flask(
        __name__,
        static_folder=os.path.join(app_dir, 'static'),
        static_url_path='/static'
    )

    # Disabilita cache Jinja2 in sviluppo per vedere i template aggiornati subito (rimuovere in produzione se desiderato)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.cache = None
    app.jinja_env.add_extension('jinja2.ext.do')

    # Chiavi segrete (preferibile impostare tramite variabili d'ambiente)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'un-valore-di-default-da-cambiare')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-da-cambiare')

    # ---------- CONFIGURAZIONE DATABASE ----------
    # Priorità: DATABASE_URL (Postgres) -- fallback a SQLite locale (development)
    raw_db_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')  # supporta possibili nomi diversi
    if raw_db_url:
        # Alcuni servizi forniscono URL con schema `postgres://` — SQLAlchemy richiede `postgresql://`
        database_url = raw_db_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        using_postgres = True
    else:
        # Fallback: sqlite in ./data/site.db (utile in sviluppo)
        base_local_data = os.path.join(os.path.dirname(app_dir), 'data')
        db_file = os.path.join(base_local_data, 'site.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_file}"
        using_postgres = False

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # ---------- UPLOAD FOLDERS ----------
    # Se usi Postgres in produzione (Render), /data sarà disponibile al runtime; evitare di creare /data in build.
    # Creiamo cartelle di upload solo quando possibile (evitiamo crash in build-time di Render).
    if using_postgres:
        base_data_path = '/data'  # render/runtime persistent path
    else:
        base_data_path = os.path.join(os.path.dirname(app_dir), 'data')

    app.config['UPLOAD_FOLDER'] = os.path.join(base_data_path, 'profile_pics')
    app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER'] = os.path.join(base_data_path, 'featured_routes')

    # Creazione cartelle: proviamo, ma non falliamo in caso di filesystem di sola lettura (es. build di Render)
    for path in (base_data_path, app.config['UPLOAD_FOLDER'], app.config['ADMIN_FEATURED_ROUTES_UPLOAD_FOLDER']):
        try:
            # su Linux in build-time /data può essere read-only -> catch OSError
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            # Non interrompiamo l'avvio; logghiamo per debug.
            print(f"⚠️ Impossibile creare {path} (probabilmente filesystem di sola lettura): {e}")

    # ---------- INIZIALIZZA ESTENSIONI ----------
    db.init_app(app)
    login_manager.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(app_dir, 'migrations'))
    CORS(app)

    # ---------- IMPORT MODELLI E USER_LOADER ----------
    # Import qui per risolvere dipendenze circolari
    try:
        from .models import User, Notification, close_expired_challenges
    except Exception:
        # Se l'import fallisce (es. durante alcune operazioni di build), logghiamo ma non crashiamo
        print("⚠️ Attenzione: import di modelli fallito durante create_app(); controlla trace qui sotto.")
        traceback.print_exc()
        User = None
        Notification = None
        close_expired_challenges = None

    if User is not None:
        @login_manager.user_loader
        def load_user(user_id):
            try:
                return User.query.get(int(user_id))
            except Exception:
                return None

    # ---------- CONTEXT PROCESSOR ----------
    @app.context_processor
    def inject_global_variables():
        unread_notifications_count = 0
        if current_user.is_authenticated and Notification is not None:
            try:
                unread_notifications_count = Notification.query.filter_by(
                    recipient_id=current_user.id, read=False
                ).count()
            except Exception:
                # se il DB non è raggiungibile durante la build, evitiamo crash
                unread_notifications_count = 0
        return dict(
            now=datetime.utcnow(),
            user_city=(current_user.city if current_user.is_authenticated else None),
            unread_notifications_count=unread_notifications_count
        )

    # ---------- REGISTER BLUEPRINTS ----------
    # Import blueprint all'interno della factory per evitare import circolari
    try:
        from .main.routes import main as main_blueprint
        app.register_blueprint(main_blueprint)
    except Exception:
        print("⚠️ main blueprint non registrato (forse import fallito).")
        traceback.print_exc()

    try:
        from .auth.routes import auth as auth_blueprint
        app.register_blueprint(auth_blueprint)
    except Exception:
        print("⚠️ auth blueprint non registrato (forse import fallito).")
        traceback.print_exc()

    try:
        from .api.routes import api as api_blueprint
        app.register_blueprint(api_blueprint, url_prefix='/api')
    except Exception:
        print("⚠️ api blueprint non registrato (forse import fallito).")
        traceback.print_exc()

    try:
        from .mobile.routes import mobile as mobile_blueprint
        app.register_blueprint(mobile_blueprint, url_prefix='/api/mobile')
    except Exception:
        print("⚠️ mobile blueprint non registrato (forse import fallito).")
        traceback.print_exc()

    # ---------- FLASK-ADMIN SETUP ----------
    try:
        admin.init_app(app)
        with app.app_context():
            setup_admin_views(admin, db)
        print("✅ Admin panel configurato e inizializzato.")
    except Exception:
        print("⚠️ Errore durante la configurazione di Flask-Admin:")
        traceback.print_exc()

    # ---------- DATABASE: controllo connessione / creazione tabelle quando appropriato ----------
    with app.app_context():
        try:
            # Mostra quale URI stiamo usando (utile per debug)
            print(f"📦 SQLALCHEMY_DATABASE_URI = {app.config.get('SQLALCHEMY_DATABASE_URI')}")
        except Exception:
            pass

        # Se stiamo usando Postgres, NON forziamo la creazione delle tabelle qui (preferire migrazioni).
        # Proviamo comunque a verificare la connessione al DB e loggare eventuali errori.
        if using_postgres:
            try:
                # tentativo di connessione (non eseguiamo create_all automaticamente)
                engine = db.get_engine(app)
                with engine.connect() as conn:
                    # connessione ok
                    print("✅ Connessione al database Postgres riuscita.")
            except Exception as e:
                print(f"⚠️ Impossibile connettersi al database Postgres ora: {e}")
                # non rilanciare: potrebbe essere la build-phase. Lascia che l'operazione di migrazione sia eseguita a runtime o manualmente.
        else:
            # fallback sqlite: se siamo in sviluppo, proviamo a creare le tabelle locali
            try:
                db.create_all()
                print("✅ Database SQLite (dev) creato/verificato con successo.")
            except Exception as e:
                print(f"⚠️ Errore durante db.create_all() su SQLite (dev fallback): {e}")

    # ---------- CLOSE EXPIRED CHALLENGES AT START (if available) ----------
    if close_expired_challenges is not None:
        try:
            with app.app_context():
                try:
                    closed_count = close_expired_challenges()
                    if closed_count and closed_count > 0:
                        print(f"🚀 All'avvio: chiuse {closed_count} sfide scadute.")
                except Exception as e:
                    print(f"⚠️ Errore nella chiusura automatica sfide all'avvio: {e}")
        except Exception:
            # non bloccare l'app per errori di startup di questa funzione
            traceback.print_exc()

    # ---------- SCHEDULER: job giornaliero per chiudere sfide scadute ----------
    try:
        if not scheduler.running:
            if close_expired_challenges is not None:
                @scheduler.scheduled_job('cron', hour=0, minute=0)
                def close_daily_expired_challenges_job():
                    with app.app_context():
                        try:
                            closed_count = close_expired_challenges()
                            if closed_count and closed_count > 0:
                                print(f"⏰ Scheduler: chiuse {closed_count} sfide scadute.")
                            else:
                                print("⏰ Scheduler: nessuna sfida da chiudere.")
                        except Exception as e:
                            print(f"❌ Errore scheduler durante close_expired_challenges: {e}")

                scheduler.start()
                print("✅ Scheduler avviato - chiusura automatica sfide attiva.")
            else:
                print("⚠️ close_expired_challenges non disponibile; scheduler non avviato per quel job.")
        else:
            print("✅ Scheduler già attivo.")
    except Exception:
        print("⚠️ Errore nell'avvio dello scheduler:")
        traceback.print_exc()

    # ---------- Variabili globali Jinja ----------
    app.jinja_env.globals.update(
        datetime=datetime,
        timedelta=timedelta,
        today_minus_1day=datetime.utcnow() - timedelta(days=1)
    )

    return app


def stop_scheduler():
    """Ferma lo scheduler (utile per testing o shutdown)."""
    if scheduler.running:
        scheduler.shutdown()
        print("⏹️ Scheduler fermato.")
