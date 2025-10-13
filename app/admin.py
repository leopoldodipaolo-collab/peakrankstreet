# app/admin.py
import os # <-- AGGIUNGI QUESTA RIGA!
# Importazioni necessarie
from flask import redirect, url_for, request, current_app # current_app è utile per i percorsi base
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.form.upload import ImageUploadField # Necessario per l'upload di immagini
from flask_login import current_user
from wtforms import fields # Necessario per i campi form personalizzati
import sys # Per stampare su stderr
import traceback # Per stampare traceback in caso di errori

# Importazioni dei modelli e di Flask-SQLAlchemy (da __init__.py)
from app.models import (User, Route, Activity, Challenge, ChallengeInvitation,
                          Comment, Like, Badge, UserBadge, Notification,
                          RouteRecord, ActivityLike)
from app import db # Importa l'istanza db

# --- Viste Personalizzate e Protette per i Modelli ---

# Vista Base Protetta
class SecureModelView(ModelView):
    """Vista Base che verifica i permessi admin prima di accedere."""
    def is_accessible(self):
        # Ritorna True solo se l'utente è loggato E se è admin
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
        # Se l'accesso è negato, reindirizza al login
        print(f"DEBUG Admin: Accesso negato a {name}. Reindirizzo al login.", file=sys.stderr)
        sys.stderr.flush()
        # Reindirizza alla pagina di login, passando l'URL richiesto come 'next'
        return redirect(url_for('auth.login', next=request.url))

# Vista Utenti
class UserAdminView(SecureModelView):
    column_list = ['id', 'username', 'email', 'city', 'is_admin', 'created_at']
    column_exclude_list = ['password_hash'] # Non mostrare l'hash della password
    form_excluded_columns = ['password_hash'] # Non mostrare nel form di modifica/creazione
    column_searchable_list = ['username', 'email']
    column_filters = ['city', 'is_admin', 'created_at']
    can_create = False # Non permettere la creazione di utenti dall'admin per sicurezza
    column_default_sort = ('created_at', True) # Ordina per data di creazione (più recenti prima)

# Vista Percorsi
class RouteAdminView(SecureModelView):
    column_list = [
        'id', 'name', 'creator', 'activity_type', 
        'is_featured', 'is_classic', 'classic_city',
        'is_active', 'difficulty', 'distance_km', 'created_at'
    ]
    column_searchable_list = ['name', 'description', 'classic_city', 'start_location']
    column_filters = [
        'is_featured', 'is_classic', 'is_active',
        'activity_type', 'difficulty', 'classic_city', 'created_at'
    ]
    column_editable_list = ['is_featured', 'is_classic', 'is_active'] # Campi modificabili dalla lista
    
    form_columns = [ # Campi da mostrare nel form di creazione/modifica
        'name', 'description', 'activity_type', 'coordinates',
        'created_by', 'distance_km', 'is_featured', 'featured_image',
        'is_active', 'is_classic', 'classic_city', 'start_location',
        'end_location', 'elevation_gain', 'difficulty', 'estimated_time',
        'landmarks'
    ]
    
    form_extra_fields = {
        # Campo per l'upload dell'immagine (configurato qui)
        'featured_image': ImageUploadField(
            'Immagine in Evidenza',
            base_path=os.path.join(current_app.root_path, 'static/featured_routes'), # Percorso base dove salvare
            url_relative_path='static/featured_routes/', # Percorso relativo per l'URL
            thumbnail_size=(150, 150, True), # Anteprima immagine
            validators=[validators.Optional()] # Campo opzionale
        ),
        'coordinates': fields.TextAreaField('Coordinates (GeoJSON)'), # Campo testo per GeoJSON
        'landmarks': fields.TextAreaField('Punti di Riferimento (JSON)') # Campo testo per Landmark
    }
    
    # Qui puoi definire quali campi appaiono nel form di modifica
    form_edit_rules = (
        'name', 'description', 'activity_type', 'coordinates',
        'created_by', 'distance_km', 'is_featured', 'featured_image',
        'is_active', 'is_classic', 'classic_city', 'start_location',
        'end_location', 'elevation_gain', 'difficulty', 'estimated_time',
        'landmarks'
    )

# ... (Aggiungi qui le altre viste admin: ActivityAdminView, ChallengeAdminView, etc. se le hai definite) ...
# Ad esempio, se hai definito ActivityAdminView, CommentAdminView, etc., aggiungile qui.
# Se non le hai ancora definite, puoi aggiungere una SecureModelView di base per ora:

# Esempio: Vista base per Activity (puoi personalizzarla dopo)
class ActivityAdminView(SecureModelView):
    column_list = ['id', 'user', 'route', 'activity_type', 'distance', 'duration', 'created_at']
    column_filters = ['activity_type', 'created_at']
    column_searchable_list = ['activity_type']
    column_default_sort = ('created_at', True)

# Esempio: Vista base per Challenge
class ChallengeAdminView(SecureModelView):
    column_list = ['id', 'name', 'route', 'start_date', 'end_date', 'is_active', 'created_by']
    column_filters = ['start_date', 'end_date', 'is_active']
    column_searchable_list = ['name']

# Esempio: Vista base per Comment
class CommentAdminView(SecureModelView):
    column_list = ['id', 'user', 'route', 'content', 'created_at']
    column_searchable_list = ['content']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)

# Aggiungi qui le viste mancanti che hai definito nei modelli, come:
# ChallengeInvitationAdminView, LikeAdminView, ActivityLikeAdminView, RouteRecordAdminView, BadgeAdminView, UserBadgeAdminView, NotificationAdminView

# --- Vista Indice Personalizzata e Protetta ---
class SecureAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        print(f"DEBUG Admin: Accesso negato a {name}. Reindirizzo al login.", file=sys.stderr)
        sys.stderr.flush()
        return redirect(url_for('auth.login', next=request.url))

# --- Creazione dell'Istanza Admin ---
# L'istanza Admin viene creata qui e configurata in __init__.py
admin = Admin(name='StreetSport Admin', template_mode='bootstrap4', index_view=SecureAdminIndexView())

# --- Funzione per aggiungere le viste ---
# Questa funzione deve essere chiamata da __init__.py dopo aver inizializzato l'app e db
def setup_admin_views(admin_instance, db):
    """Configura le viste dell'Admin Panel."""
    print("DEBUG: Inizio configurazione viste Admin Panel...", file=sys.stderr)
    sys.stderr.flush()
    
    try:
        # Aggiungi tutte le viste che vuoi gestire dall'admin
        admin_instance.add_view(UserAdminView(User, db.session, name='Utenti', endpoint='admin_users'))
        admin_instance.add_view(RouteAdminView(Route, db.session, name='Percorsi', endpoint='admin_routes'))
        # Aggiungi qui le altre viste che hai definito:
        admin_instance.add_view(ActivityAdminView(Activity, db.session, name='Attività', endpoint='admin_activities'))
        admin_instance.add_view(ChallengeAdminView(Challenge, db.session, name='Sfide', endpoint='admin_challenges'))
        # Se hai definito ChallengeInvitationAdminView, LikeAdminView, etc. aggiungile qui
        # admin.add_view(SecureModelView(ChallengeInvitation, db.session, name='Inviti Sfide', endpoint='admin_challenge_invitations'))
        # admin.add_view(SecureModelView(Comment, db.session, name='Commenti', endpoint='admin_comments'))
        # admin.add_view(SecureModelView(Like, db.session, name='Like Commenti', endpoint='admin_likes'))
        # admin.add_view(SecureModelView(ActivityLike, db.session, name='Like Attività', endpoint='admin_activity_likes'))
        # admin.add_view(SecureModelView(RouteRecord, db.session, name='Record Percorsi', endpoint='admin_route_records'))
        # admin.add_view(SecureModelView(Badge, db.session, name='Badge', endpoint='admin_badges'))
        # admin.add_view(SecureModelView(UserBadge, db.session, name='Badge Utenti', endpoint='admin_user_badges'))
        # admin.add_view(SecureModelView(Notification, db.session, name='Notifiche', endpoint='admin_notifications'))
        
        print("✅ Setup viste Admin completato con successo.", file=sys.stderr)
        sys.stderr.flush()
        
    except Exception as e:
        print(f"❌ ERRORE DURANTE SETUP VISTE ADMIN: {e}", file=sys.stderr) 
        traceback.print_exc(file=sys.stderr) 
        sys.stderr.flush()
        # Potresti voler rilanciare l'eccezione o gestirla diversamente
        # raise e