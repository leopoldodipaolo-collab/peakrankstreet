import os
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

def create_app():
    """Factory function per creare l'istanza dell'app Flask."""
    app = Flask(__name__)

    # --- CONFIGURAZIONE ROBUSTA ---
    basedir = os.path.abspath(os.path.dirname(__file__)) 
    
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'un-valore-di-default-per-sicurezza'
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'
    
    # COSTRUISCE IL PERCORSO ASSOLUTO AL DATABASE
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'site.db')
    
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
            user_city=current_user.city if current_user.is_authenticated else None,
            unread_notifications_count=unread_notifications_count
        )
    
    # --- ADMIN PANEL ---
    try:
        from .admin import admin
        admin.init_app(app)
        print("✅ Admin panel inizializzato")
    except Exception as e:
        print(f"⚠️  Errore durante l'inizializzazione dell'Admin Panel: {e}")
        
        # --- CREA LE TABELLE DEL DATABASE ---
        with app.app_context():
            try:
                db.create_all()
                print("✅ Tabelle database verificate/creato")
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


def init_admin_views(app):
    """Initialize admin views after app context is available"""
    with app.app_context():
        try:
            from .admin import setup_admin_views
            setup_admin_views(db)
            print("✅ Admin views configurati con successo!")
        except Exception as e:
            print(f"❌ Errore nella configurazione delle admin views: {e}")