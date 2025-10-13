# app/__init__.py

import os
import sys 
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

# Carica le variabili d'ambiente dal file .env nella cartella principale
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '..', '.env'))

# Inizializza le estensioni globalmente
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"
jwt = JWTManager()

# Crea lo scheduler globalmente ma non avviarlo ancora
scheduler = BackgroundScheduler()

# === DICHIARAZIONE GLOBALE PER FLASK-ADMIN ===
# Rimuoviamo le variabili globali `admin_instance` e `setup_admin_func`
# L'istanza Admin verrà creata direttamente in create_app()
# === FINE DICHIARAZIONE ===

# === RIMUOVI COMPLETAMENTE L'INTERO BLOCCO 'INIZIALIZZAZIONE PRECOCE ADMIN PANEL' QUI ===


def create_app():
    """Factory function per creare l'istanza dell'app Flask."""
    app = Flask(__name__)

    # --- CONFIGURAZIONE ROBUSTA ---
    basedir = os.path.abspath(os.path.dirname(__file__)) 
    
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'un-valore-di-default-per-sicurezza'
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'
    
    # COSTRUISCE IL PERCORSO ASSOLUTO AL DATABASE
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
                                        'sqlite:///' + os.path.join(basedir, 'site.db')
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Percorso per le immagini del profilo, relativo alla directory 'app'
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/profile_pics') 
    # --- FINE SEZIONE ---
    
    # Crea la cartella per le immagini se non esiste
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # Aggiunge estensioni a Jinja2 se necessario
    app.jinja_env.add_extension('jinja2.ext.do')

    # Inizializza le estensioni con l'app
    db.init_app(app)
    login_manager.init_app(app)
    jwt.init_app(app)
    CORS(app)

    # --- IMPORTA E REGISTRA BLUEPRINTS ---
    from .main.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .auth.routes import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .api.routes import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    from .mobile.routes import mobile as mobile_blueprint
    app.register_blueprint(mobile_blueprint, url_prefix='/api/mobile')

    # --- IMPORTA MODELLI ---
    from .models import User, Activity, Route, Challenge, Notification, Comment, Like, ActivityLike, RouteRecord, Badge, UserBadge, ChallengeInvitation

    # Configura il gestore degli utenti per Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))

    # Aggiunge variabili globali accessibili nei template Jinja2
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
            user_city=current_user.city if current_user.is_authenticated and hasattr(current_user, 'city') else None,
            unread_notifications_count=unread_notifications_count
        )
    
    # --- ADMIN PANEL ---
    print("DEBUG: create_app: Inizio inizializzazione Admin Panel.", file=sys.stderr)
    sys.stderr.flush()
    try:
        # Importa le classi Admin e le viste qui, all'interno della funzione
        from .admin import Admin, SecureAdminIndexView, setup_admin_views, UserAdminView, RouteAdminView, ActivityAdminView, ChallengeAdminView, ChallengeInvitationAdminView, CommentAdminView, LikeAdminView, ActivityLikeAdminView, RouteRecordAdminView, BadgeAdminView, UserBadgeAdminView, NotificationAdminView
        
        # Crea l'istanza Admin e la inizializza direttamente con l'app
        admin = Admin(
            app, # <--- Passa l'istanza dell'app qui
            name='StreetSport Admin',
            template_mode='bootstrap4',
            index_view=SecureAdminIndexView(),
            endpoint='admin',
            url='/admin' # <--- Specifica esplicitamente l'URL
        )
        print("DEBUG: create_app: Flask-Admin istanza creata e inizializzata con l'app.", file=sys.stderr)
        sys.stderr.flush()

        with app.app_context():
            print("DEBUG: create_app: Entrato nel contesto dell'app per setup_admin_views.", file=sys.stderr)
            sys.stderr.flush()
            # Chiama la funzione per configurare le viste, passandole l'istanza admin e db
            setup_admin_views(db) # setup_admin_views ora deve ricevere 'admin' come argomento
            print("DEBUG: create_app: setup_admin_views completato.", file=sys.stderr)
            sys.stderr.flush()
        print("✅ Admin panel caricato con successo", file=sys.stderr)
        sys.stderr.flush()
    except Exception as e: 
        print(f"❌ CRITICAL ERROR: create_app: L'inizializzazione dell'Admin Panel è fallita: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
    
    # --- CREA LE TABELLE DEL DATABASE ---
    with app.app_context():
        try:
            db.create_all() 
            print("✅ Tabelle database verificate/create", file=sys.stderr)
            sys.stderr.flush()
        except Exception as e:
            print(f"⚠️  Errore durante la creazione delle tabelle: {e}", file=sys.stderr)
            sys.stderr.flush()
    
    # --- CHIUSURA AUTOMATICA SFIDE SCADUTE ---
    with app.app_context():
        try:
            from .models import close_expired_challenges
            closed_count = close_expired_challenges()
            if closed_count > 0:
                print(f"🚀 All'avvio: chiuse {closed_count} sfide scadute", file=sys.stderr)
            else:
                print("✅ All'avvio: Nessuna sfida da chiudere", file=sys.stderr)
            sys.stderr.flush()
        except Exception as e:
            print(f"⚠️  Errore chiusura sfide all'avvio: {e}", file=sys.stderr)
            sys.stderr.flush()

    # --- SCHEDULER PER CHIUSURA GIORNALIERA ---
    try:
        if not scheduler.running:
            from .models import close_expired_challenges
            
            @scheduler.scheduled_job('cron', hour=0, minute=0)  # Mezzanotte ogni giorno
            def close_daily_expired_challenges():
                with app.app_context():
                    try:
                        closed_count = close_expired_challenges()
                        if closed_count > 0:
                            print(f"⏰ Scheduler: chiuse {closed_count} sfide scadute", file=sys.stderr)
                        else:
                            print("⏰ Scheduler: nessuna sfida da chiudere", file=sys.stderr)
                        sys.stderr.flush()
                    except Exception as e:
                        print(f"❌ Errore scheduler: {e}", file=sys.stderr)
                        sys.stderr.flush()
            
            scheduler.start()
            print("✅ Scheduler avviato - chiusura automatica sfide attiva", file=sys.stderr)
            sys.stderr.flush()
        else:
            print("✅ Scheduler già attivo", file=sys.stderr)
            sys.stderr.flush()
            
    except Exception as e:
        print(f"⚠️  Errore nell'avvio dello scheduler: {e}", file=sys.stderr)
        sys.stderr.flush()

    app.jinja_env.globals.update(
        datetime=datetime,
        timedelta=timedelta,
        today_minus_1day=datetime.utcnow() - timedelta(days=1)
    )
    
    return app

# Funzione per fermare lo scheduler (utile per testing)
def stop_scheduler():
    """Ferma lo scheduler (per testing)"""
    if scheduler.running:
        scheduler.shutdown()
        print("⏹️  Scheduler fermato", file=sys.stderr)
        sys.stderr.flush()