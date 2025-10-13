import os
import sys # <--- NUOVO IMPORT PER sys.stderr
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
# Assicurati che .env sia caricato, ma non è rilevante per Render in produzione
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
# Queste variabili saranno impostate a None se l'import fallisce
admin_instance = None 
setup_admin_func = None
# === FINE DICHIARAZIONE ===

# === INIZIALIZZAZIONE PRECOCE ADMIN PANEL (PER DEBUG) ===
# Questa parte tenta di importare i moduli Flask-Admin il prima possibile.
# Se c'è un errore nell'import, verrà catturato qui.
print("DEBUG: Caricamento app/__init__.py - Inizio tentativo di setup Admin Panel.") 
try:
    from .admin import admin as imported_admin_instance, setup_admin_views as imported_setup_admin_func
    # Assegna le istanze importate alle variabili globali
    admin_instance = imported_admin_instance
    setup_admin_func = imported_setup_admin_func
    print("DEBUG: Admin: Moduli Flask-Admin importati con successo.")
except ImportError as e:
    print(f"❌ CRITICAL ERROR: Admin: Impossibile importare moduli Flask-Admin: {e}", file=sys.stderr)
except Exception as e:
    print(f"❌ CRITICAL ERROR: Admin: Errore generico durante l'import di Flask-Admin: {e}", file=sys.stderr)
# === FINE INIZIALIZZAZIONE PRECOCE ADMIN PANEL ===


def create_app():
    """Factory function per creare l'istanza dell'app Flask."""
    app = Flask(__name__)

    # --- CONFIGURAZIONE ROBUSTA ---
    # basedir già definito all'inizio
    
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
        # current_user è disponibile solo all'interno di una richiesta
        if current_user.is_authenticated:
            from .models import Notification
            unread_notifications_count = Notification.query.filter_by(
                recipient_id=current_user.id, read=False
            ).count()
        return dict(
            now=datetime.utcnow(),
            # user_city è disponibile solo se current_user è autenticato e ha una città
            user_city=current_user.city if current_user.is_authenticated and hasattr(current_user, 'city') else None,
            unread_notifications_count=unread_notifications_count
        )
    
    # --- ADMIN PANEL --- (La configurazione reale avviene qui, ma l'import è già stato tentato)
    if admin_instance and setup_admin_func: # Solo se l'import è riuscito nella fase precoce
        print("DEBUG: create_app: Inizializzazione Flask-Admin con l'app.") 
        try:
            admin_instance.init_app(app) # Inizializza con l'istanza dell'app
            print("DEBUG: create_app: Flask-Admin istanza inizializzata con l'app.")
            with app.app_context():
                print("DEBUG: create_app: Entrato nel contesto dell'app per setup_admin_views.")
                try: # Aggiungiamo un try/except qui per catturare errori specifici di setup_admin_views
                    setup_admin_func(db) # Chiama la funzione per configurare le viste
                    print("DEBUG: create_app: setup_admin_views completato.")
                except Exception as e:
                    print(f"❌ CRITICAL ERROR: create_app: Errore durante setup_admin_views: {e}", file=sys.stderr)
                    import traceback # Assicurati che sia importato all'inizio del file, o qui.
                    traceback.print_exc(file=sys.stderr)
            print("✅ Admin panel caricato con successo")
        except Exception as e: # Cattura errori durante admin_instance.init_app(app)
            print(f"❌ CRITICAL ERROR: create_app: Errore durante admin_instance.init_app(app): {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
    else:
        print("⚠️ Admin panel inizializzazione saltata perché i moduli non sono stati importati.")

    # --- CREA LE TABELLE DEL DATABASE ---
    # Questa sezione viene eseguita solo una volta durante il primo deploy o se il DB è vuoto
    # e non è più necessario eseguirla manualmente dalla shell dopo.
    with app.app_context():
        try:
            db.create_all() 
            print("✅ Tabelle database verificate/create")
        except Exception as e:
            print(f"⚠️  Errore durante la creazione delle tabelle: {e}")
    
    # --- CHIUSURA AUTOMATICA SFIDE SCADUTE ---
    with app.app_context():
        try:
            from .models import close_expired_challenges
            closed_count = close_expired_challenges()
            if closed_count > 0:
                print(f"🚀 All'avvio: chiuse {closed_count} sfide scadute")
        except Exception as e:
            print(f"⚠️  Errore chiusura sfide all'avvio: {e}")

    # --- SCHEDULER PER CHIUSURA GIORNALIERA ---
    try:
        # Configura lo scheduler solo se non è già running
        if not scheduler.running:
            from .models import close_expired_challenges
            
            @scheduler.scheduled_job('cron', hour=0, minute=0)  # Mezzanotte ogni giorno
            def close_daily_expired_challenges():
                with app.app_context():
                    try:
                        closed_count = close_expired_challenges()
                        if closed_count > 0:
                            print(f"⏰ Scheduler: chiuse {closed_count} sfide scadute")
                        else:
                            print("⏰ Scheduler: nessuna sfida da chiudere")
                    except Exception as e:
                        print(f"❌ Errore scheduler: {e}")
            
            scheduler.start()
            print("✅ Scheduler avviato - chiusura automatica sfide attiva")
        else:
            print("✅ Scheduler già attivo")
            
    except Exception as e:
        print(f"⚠️  Errore nell'avvio dello scheduler: {e}")

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
        print("⏹️  Scheduler fermato")