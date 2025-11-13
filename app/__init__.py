# app/__init__.py

import os
from flask import Flask
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
    app = Flask(__name__, static_folder='static', static_url_path='/static')

    # --- Configurazioni base ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret-key-change-me')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'default-jwt-key-change-me')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # --- Configurazione Database ---
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or f"sqlite:///{os.path.join(app_dir, 'site.db')}"
    print(f"✅ Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

    # =====================================================================
    # --- NUOVA GESTIONE DINAMICA DELLE CARTELLE DI UPLOAD ---
    # =====================================================================
    if 'RENDER' in os.environ:
        # Su Render, il disco è montato in /var/data/uploads. Questa cartella ESISTE GIÀ.
        upload_base_path = '/var/data/uploads'
        print(f"✅ Ambiente Render rilevato. Path upload: {upload_base_path}")
    else:
        # In locale, creiamo la cartella se non esiste.
        upload_base_path = os.path.join(app.root_path, 'static', 'uploads')
        print(f"⚠️  Ambiente locale rilevato. Path upload: {upload_base_path}")
        os.makedirs(upload_base_path, exist_ok=True)

    # Definiamo i percorsi completi nella configurazione dell'app
    app.config['UPLOADS_BASE_PATH'] = upload_base_path
    app.config['PROFILE_PICS_FOLDER'] = os.path.join(upload_base_path, 'profile_pics')
    app.config['POSTS_IMAGES_FOLDER'] = os.path.join(upload_base_path, 'posts_images')
    
    # Ora crea le sottocartelle. Questa operazione è permessa perché 'upload_base_path' è scrivibile.
    os.makedirs(app.config['PROFILE_PICS_FOLDER'], exist_ok=True)
    os.makedirs(app.config['POSTS_IMAGES_FOLDER'], exist_ok=True)
    # =====================================================================

    # --- Estensioni e Inizializzazioni ---
    app.jinja_env.add_extension('jinja2.ext.do')
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(app_dir, 'migrations'))
    jwt.init_app(app)
    CORS(app)
    csrf.init_app(app)

    # --- Configura Login Manager ---
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))

    # --- Context Processors ---
    @app.context_processor
    def inject_global_variables():
        unread_count = 0
        if current_user.is_authenticated:
            from .models import Notification
            unread_count = Notification.query.filter_by(
                recipient_id=current_user.id, read=False
            ).count()
            
        return dict(
            now=datetime.utcnow(), today_minus_1day=datetime.utcnow() - timedelta(days=1),
            unread_notifications_count=unread_count
        )
    # --- Registrazione Blueprint ---
    with app.app_context():
        from .main.routes import main as main_blueprint
        app.register_blueprint(main_blueprint)

        from .auth.routes import auth as auth_blueprint
        app.register_blueprint(auth_blueprint, url_prefix='/auth')

        from .api.routes import api as api_blueprint
        app.register_blueprint(api_blueprint, url_prefix='/api')
        
        # ... (registra qui altri blueprint se ne hai)

    # --- Configura Admin, Database e Scheduler ---
    with app.app_context():
        # Admin
        admin.init_app(app)
        setup_admin_views(admin, db)
        print("✅ Admin panel configurato.")

        # Database
        try:
            db.create_all()
            print("✅ Tabelle database verificate/create.")
        except Exception as e:
            print(f"⚠️ Errore creazione tabelle: {e}")

        # Esecuzione task all'avvio
        try:
            from .main.gamification import close_expired_challenges
            closed_count = close_expired_challenges()
            if closed_count > 0:
                print(f"🚀 All'avvio: chiuse {closed_count} sfide scadute.")
        except Exception as e:
            print(f"⚠️ Errore chiusura sfide all'avvio: {e}")

    # --- Scheduler ---
    try:
        if not scheduler.running and not app.debug: # Non avviare lo scheduler in debug mode per evitare esecuzioni doppie
            from .main.gamification import close_expired_challenges
            
            @scheduler.scheduled_job('interval', hours=1)
            def scheduled_close_challenges():
                with app.app_context():
                    close_expired_challenges()
            
            scheduler.start()
            print("✅ Scheduler avviato.")
    except Exception as e:
        print(f"⚠️ Errore avvio scheduler: {e}")

    return app