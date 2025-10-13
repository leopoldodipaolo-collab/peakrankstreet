# --- IMPORT NECESSARIE ---
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from datetime import datetime
from dotenv import load_dotenv
import sys # Necessario per i messaggi di debug su stderr
from flask_apscheduler import APScheduler # <--- AGGIUNGI QUESTA LINEA

# 1. Inizializza le estensioni a livello globale
db = SQLAlchemy()
login_manager = LoginManager()
scheduler = APScheduler() # <--- AGGIUNGI QUESTA LINEA

# 2. Configura Flask-Login
login_manager.login_view = 'auth.login' # Route per il login
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"

# --- IMPORTA QUI I BLUEPRINT PER EVITARE CIRCOLARITA' ---
# Importazioni fatte dentro create_app per risolvere le dipendenze circolari
# from app.main.routes import main as main_blueprint
# from app.auth.routes import auth as auth_blueprint
# from app.api.routes import api as api_blueprint

# --- IMPORTA QUI I MODELLI NECESSARI AL CONTEXT PROCESSOR ---
# Visto che user.city è usato nel context processor, dobbiamo importare User qui
# prima che venga inizializzato l'app contest
from app.models import User, Notification # Notification serve per il conteggio


# --- ISTANZA GLOBALE PER FLASK-ADMIN ---
# Creiamo l'istanza qui, ma la inizializzeremo con l'app dentro create_app
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from wtforms import fields
import traceback # Per il debug

# Vista indice admin protetta
class SecureAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        print(f"DEBUG Admin: Accesso negato a {name}. Reindirizzo al login.", file=sys.stderr)
        sys.stderr.flush()
        return redirect(url_for('auth.login', next=request.url))

# Istanza Admin
admin = Admin(
    name='StreetSport Admin',
    template_mode='bootstrap4',
    index_view=SecureAdminIndexView()
)


# --- FACTORY FUNCTION ---
def create_app():
    """
    Factory function per creare e configurare l'applicazione Flask.
    """
    app = Flask(__name__)

    # --- CONFIGURAZIONE DELL'APPLICAZIONE ---
    basedir = os.path.abspath(os.path.dirname(__file__))
    load_dotenv(os.path.join(basedir, '..', '.env')) # Carica da .env nella cartella principale

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'un-valore-di-default-molto-sicuro-da-cambiare'
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'site.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/profile_pics')

    # Configurazione per APScheduler (esempio, puoi personalizzarla)
    app.config['SCHEDULER_API_ENABLED'] = True # Se vuoi abilitare l'API per controllare lo scheduler
    # app.config['SCHEDULER_JOBSTORES'] = {
    #     'default': {'type': 'sqlalchemy', 'url': app.config['SQLALCHEMY_DATABASE_URI']}
    # }
    # app.config['SCHEDULER_EXECUTORS'] = {
    #     'default': {'type': 'threadpool', 'max_workers': 20}
    # }
    # app.config['SCHEDULER_JOB_DEFAULTS'] = {
    #     'coalesce': False,
    #     'max_instances': 3
    # }


    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    app.jinja_env.add_extension('jinja2.ext.do')
    # --- FINE CONFIGURAZIONE ---

    # Inizializza le estensioni con l'app
    db.init_app(app)
    login_manager.init_app(app)
    scheduler.init_app(app) # <--- AGGIUNGI QUESTA LINEA

    # --- BLOCCO PER GLI IMPORT NECESSARI E IL USER_LOADER ---
    # Importiamo i modelli QUI dentro per evitare ImportError dovuti a dipendenze circolari
    from .models import User, Notification

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    # --- FINE BLOCCO ---

    # --- CONTEXT PROCESSOR ---
    @app.context_processor
    def inject_global_variables():
        unread_notifications_count = 0
        if current_user.is_authenticated:
            # Utilizza il db importato globalmente
            unread_notifications_count = Notification.query.filter_by(
                recipient_id=current_user.id, read=False
            ).count()
        return dict(
            now=datetime.utcnow(),
            user_city=current_user.city if current_user.is_authenticated else None,
            unread_notifications_count=unread_notifications_count
        )
    # --- FINE CONTEXT PROCESSOR ---

    # --- REGISTRAZIONE BLUEPRINTS ---
    from .main.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .auth.routes import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .api.routes import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    # --- INIZIALIZZAZIONE FLASK-ADMIN ---
    # Inizializza Flask-Admin con l'app e il db
    admin.init_app(app)

    # Aggiunge le viste dei modelli all'istanza admin
    # Usiamo un blocco app_context per assicurarci che 'current_app' sia disponibile
    with app.app_context():
        # Importiamo i modelli necessari QUI, DOPO aver importato db e admin
        from .models import User, Route, Activity, Challenge, ChallengeInvitation, Comment, Like, RouteRecord, Badge, UserBadge, Notification, ActivityLike
        from wtforms import fields # Necessario per i campi personalizzati

        # --- Configurazione delle Viste Admin ---

        # Vista Utenti
        UserAdminView = type('UserAdminView', (SecureModelView,), {
            'column_list': ['id', 'username', 'email', 'city', 'is_admin', 'created_at'],
            'column_exclude_list': ['password_hash'],
            'form_excluded_columns': ['password_hash'],
            'column_searchable_list': ['username', 'email'],
            'column_filters': ['city', 'is_admin', 'created_at'],
            'can_create': False,
            'column_editable_list': ['is_admin'],
            'column_default_sort': ('created_at', True)
        })
        admin.add_view(UserAdminView(User, db.session, name='Utenti', endpoint='admin_users'))

        # Vista Percorsi
        RouteAdminView = type('RouteAdminView', (SecureModelView,), {
            'column_list': ['id', 'name', 'creator', 'activity_type', 'is_featured', 'is_classic', 'classic_city', 'distance_km', 'created_at'],
            'column_searchable_list': ['name', 'description', 'classic_city', 'start_location'],
            'column_filters': ['is_featured', 'is_classic', 'is_active', 'activity_type', 'difficulty', 'classic_city', 'created_at'],
            'column_editable_list': ['is_featured', 'is_classic', 'is_active'],
            'form_columns': [
                'name', 'description', 'activity_type', 'coordinates', 'created_by',
                'distance_km', 'is_featured', 'featured_image', 'is_active', 'is_classic',
                'classic_city', 'start_location', 'end_location', 'elevation_gain',
                'difficulty', 'estimated_time', 'landmarks'
            ],
            'form_extra_fields': {
                'featured_image': ImageUploadField(
                    'Immagine in Evidenza',
                    base_path=os.path.join(current_app.root_path, 'static/featured_routes'),
                    url_relative_path='static/featured_routes/',
                    thumbnail_size=(150, 150, True)
                ),
                'coordinates': fields.TextAreaField('Coordinates (GeoJSON)'),
                'landmarks': fields.TextAreaField('Punti di Riferimento (JSON)')
            },
            'form_edit_rules': ('name', 'description', 'activity_type', 'coordinates', 'created_by', 'distance_km', 'is_featured', 'featured_image', 'is_active', 'is_classic', 'classic_city', 'start_location', 'end_location', 'elevation_gain', 'difficulty', 'estimated_time', 'landmarks')
        })
        admin.add_view(RouteAdminView(Route, db.session, name='Percorsi', endpoint='admin_routes'))

        # Aggiungi le altre viste qui sotto in modo simile
        admin.add_view(ModelView(Activity, db.session, name='Attività', endpoint='admin_activities'))
        admin.add_view(ModelView(Challenge, db.session, name='Sfide', endpoint='admin_challenges'))
        admin.add_view(ModelView(ChallengeInvitation, db.session, name='Inviti Sfide', endpoint='admin_challenge_invitations'))
        admin.add_view(ModelView(Comment, db.session, name='Commenti', endpoint='admin_comments'))
        admin.add_view(ModelView(Like, db.session, name='Like Commenti', endpoint='admin_likes'))
        admin.add_view(ModelView(ActivityLike, db.session, name='Like Attività', endpoint='admin_activity_likes'))
        admin.add_view(ModelView(RouteRecord, db.session, name='Record Percorsi', endpoint='admin_route_records'))
        admin.add_view(ModelView(Badge, db.session, name='Badge', endpoint='admin_badges'))
        admin.add_view(ModelView(UserBadge, db.session, name='Badge Utenti', endpoint='admin_user_badges'))
        admin.add_view(ModelView(Notification, db.session, name='Notifiche', endpoint='admin_notifications'))

        print("✅ Setup viste Admin completato con successo.", file=sys.stderr)
        sys.stderr.flush()

    return app