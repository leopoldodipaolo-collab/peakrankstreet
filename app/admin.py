# app/admin.py

from flask import redirect, url_for, request, current_app
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.form.upload import ImageUploadField # Importa ImageUploadField
from flask_login import current_user
from wtforms import fields
import sys
import traceback
import os # Importa os qui, è necessario per os.path.join e os.makedirs

# Importa i modelli e db
from app.models import (User, Route, Activity, Challenge, ChallengeInvitation,
                          Comment, Like, Badge, UserBadge, Notification,
                          RouteRecord, ActivityLike)
from app import db

# --- Viste Personalizzate e Protette ---

class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
        print(f"DEBUG Admin: Accesso negato a {name}. Reindirizzo al login.", file=sys.stderr)
        sys.stderr.flush()
        return redirect(url_for('auth.login', next=request.url))

class UserAdminView(SecureModelView):
    column_list = ['id', 'username', 'email', 'city', 'is_admin', 'created_at']
    column_exclude_list = ['password_hash']
    form_excluded_columns = ['password_hash']
    column_searchable_list = ['username', 'email']
    column_filters = ['city', 'is_admin', 'created_at']
    can_create = False
    column_editable_list = ['is_admin']
    column_default_sort = ('created_at', True)

class RouteAdminView(SecureModelView):
    column_list = ['id', 'name', 'creator', 'activity_type', 'is_featured', 'is_classic', 'classic_city', 'is_active', 'difficulty', 'distance_km', 'created_at']
    column_searchable_list = ['name', 'description', 'classic_city', 'start_location']
    column_filters = ['is_featured', 'is_classic', 'is_active', 'activity_type', 'difficulty', 'classic_city', 'created_at']
    column_editable_list = ['is_featured', 'is_classic', 'is_active']
    
    form_columns = [
        'name', 'description', 'activity_type', 'coordinates', 'created_by',
        'distance_km', 'is_featured', 'featured_image', 'is_active', 'is_classic',
        'classic_city', 'start_location', 'end_location', 'elevation_gain',
        'difficulty', 'estimated_time', 'landmarks'
    ]
    
    # --- LOGICA DELL'UPLOAD IMMAGINE ESTERNALIZZATA ---
    # Spostata in setup_admin_views per essere eseguita nel contesto dell'app
    # form_extra_fields = { ... } 
    # form_edit_rules = ( ... )

# ... (Definizioni per ActivityAdminView, ChallengeAdminView, etc. rimangono uguali) ...
class ActivityAdminView(SecureModelView):
    column_list = ['id', 'user', 'route', 'activity_type', 'distance', 'duration', 'avg_speed', 'created_at']
    column_filters = ['activity_type', 'created_at']
    column_searchable_list = ['activity_type']
    column_default_sort = ('created_at', True)
    form_columns = ['user', 'route', 'challenge_id', 'activity_type', 'gps_track', 'duration', 'avg_speed', 'distance']

class ChallengeAdminView(SecureModelView):
    column_list = ['id', 'name', 'route', 'created_by', 'start_date', 'end_date', 'is_active', 'created_at']
    column_filters = ['start_date', 'end_date', 'is_active', 'created_at']
    column_searchable_list = ['name']
    column_editable_list = ['is_active']
    column_default_sort = ('start_date', True)

class ChallengeInvitationAdminView(SecureModelView):
    column_list = ['id', 'challenge', 'invited_user', 'status', 'invited_at']
    column_filters = ['status', 'invited_at']
    column_editable_list = ['status']
    column_default_sort = ('invited_at', True)

class CommentAdminView(SecureModelView):
    column_list = ['id', 'user', 'route', 'content', 'created_at']
    column_searchable_list = ['content']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)

class LikeAdminView(SecureModelView):
    column_list = ['id', 'user', 'comment', 'created_at']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)

class ActivityLikeAdminView(SecureModelView):
    column_list = ['id', 'user', 'activity', 'created_at']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)

class RouteRecordAdminView(SecureModelView):
    column_list = ['id', 'route', 'user', 'activity_type', 'duration', 'created_at']
    column_filters = ['activity_type', 'created_at']
    column_default_sort = ('duration', False) # Ordine crescente per durata

class BadgeAdminView(SecureModelView):
    column_list = ['id', 'name', 'description', 'image_url', 'created_at']
    column_searchable_list = ['name', 'description']
    form_columns = ['name', 'description', 'image_url', 'criteria']
    
    form_extra_fields = {
        'image_url': fields.StringField('URL Immagine Badge'),
        'criteria': fields.TextAreaField('Criteri per Ottenere il Badge')
    }

class UserBadgeAdminView(SecureModelView):
    column_list = ['id', 'user', 'badge', 'awarded_at']
    column_filters = ['awarded_at']
    column_default_sort = ('awarded_at', True)

class NotificationAdminView(SecureModelView):
    column_list = ['id', 'recipient', 'actor', 'action', 'object_id', 'object_type', 'read', 'timestamp']
    column_filters = ['action', 'read', 'timestamp']
    column_editable_list = ['read']
    column_default_sort = ('timestamp', True)


# --- Vista Indice Personalizzata e Protetta ---
class SecureAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        print(f"DEBUG Admin: Accesso negato a {name}. Reindirizzo al login.", file=sys.stderr)
        sys.stderr.flush()
        return redirect(url_for('auth.login', next=request.url))

# --- Creazione dell'Istanza Admin ---
admin = Admin(name='StreetSport Admin', template_mode='bootstrap4', index_view=SecureAdminIndexView())

# --- Funzione per aggiungere le viste ---
# Questa funzione configura le viste dopo che l'admin e db sono stati inizializzati nell'app.
def setup_admin_views(admin_instance, db):
    print("DEBUG: Inizio configurazione viste Admin Panel...", file=sys.stderr)
    sys.stderr.flush()
    
    try:
        # Aggiunta delle viste all'istanza admin
        admin_instance.add_view(UserAdminView(User, db.session, name='Utenti', endpoint='admin_users'))
        
        # Configurazione specifica per RouteAdminView con campi extra
        route_view = RouteAdminView(Route, db.session, name='Percorsi', endpoint='admin_routes')
        route_view.column_list = ['id', 'name', 'creator', 'activity_type', 'is_featured', 'is_classic', 'classic_city', 'distance_km', 'created_at']
        route_view.column_searchable_list = ['name', 'description', 'classic_city']
        route_view.column_filters = ['is_featured', 'is_classic', 'activity_type']
        route_view.column_editable_list = ['is_featured', 'is_classic']
        
        # Definiamo i campi extra qui, usando current_app per il contesto
        route_view.form_extra_fields = {
            'featured_image': ImageUploadField(
                'Immagine in Evidenza',
                base_path=os.path.join(current_app.root_path, 'static/featured_routes'),
                url_relative_path='static/featured_routes/',
                thumbnail_size=(150, 150, True)
            ),
            'coordinates': fields.TextAreaField('Coordinates (GeoJSON)'),
            'landmarks': fields.TextAreaField('Punti di Riferimento (JSON)')
        }
        
        route_view.form_columns = [
            'name', 'description', 'activity_type', 'coordinates', 'created_by',
            'distance_km', 'is_featured', 'featured_image', 'is_classic', 'classic_city',
            'start_location', 'end_location', 'elevation_gain', 'difficulty', 'estimated_time',
            'landmarks'
        ]
        
        admin_instance.add_view(route_view)

        # Aggiungi le altre viste qui, passando i nomi dei blueprint corretti se necessario
        admin_instance.add_view(ActivityAdminView(Activity, db.session, name='Attività', endpoint='admin_activities'))
        admin_instance.add_view(ChallengeAdminView(Challenge, db.session, name='Sfide', endpoint='admin_challenges'))
        admin_instance.add_view(ChallengeInvitationAdminView(ChallengeInvitation, db.session, name='Inviti Sfide', endpoint='admin_challenge_invitations'))
        admin_instance.add_view(CommentAdminView(Comment, db.session, name='Commenti', endpoint='admin_comments'))
        admin_instance.add_view(LikeAdminView(Like, db.session, name='Like Commenti', endpoint='admin_likes'))
        admin_instance.add_view(ActivityLikeAdminView(ActivityLike, db.session, name='Like Attività', endpoint='admin_activity_likes'))
        admin_instance.add_view(RouteRecordAdminView(RouteRecord, db.session, name='Record Percorsi', endpoint='admin_route_records'))
        admin_instance.add_view(BadgeAdminView(Badge, db.session, name='Badge', endpoint='admin_badges'))
        admin_instance.add_view(UserBadgeAdminView(UserBadge, db.session, name='Badge Utenti', endpoint='admin_user_badges'))
        admin_instance.add_view(NotificationAdminView(Notification, db.session, name='Notifiche', endpoint='admin_notifications'))

        print("✅ Setup viste Admin completato con successo.", file=sys.stderr)
        sys.stderr.flush()
        
    except Exception as e:
        print(f"❌ ERRORE DURANTE SETUP VISTE ADMIN: {e}", file=sys.stderr) 
        traceback.print_exc(file=sys.stderr) 
        sys.stderr.flush()
        # È buona norma rilanciare l'eccezione in modo che l'app non si avvii con configurazione incompleta
        raise e