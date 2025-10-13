#admin.py
from flask import redirect, url_for, request
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from wtforms import fields, validators

# --- Vista Indice Personalizzata e Protetta ---
class SecureAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login', next=request.url))

# --- Viste Personalizzate e Protette per i Modelli ---
class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
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
    # RISOLTO: Usa 'created_by' invece di 'creator' per evitare problemi di relazione
    column_list = [
        'id', 'name', 'created_by', 'activity_type', 
        'is_featured', 'is_classic', 'classic_city',
        'is_active', 'difficulty', 'distance_km', 'created_at'
    ]
    column_searchable_list = ['name', 'description', 'classic_city', 'start_location']
    column_filters = [
        'is_featured', 'is_classic', 'is_active',
        'activity_type', 'difficulty', 'classic_city', 'created_at'
    ]
    column_editable_list = ['is_featured', 'is_classic', 'is_active']
    
    # RISOLTO: Definisci esplicitamente le colonne del form
    form_columns = [
        'name', 'description', 'activity_type', 'coordinates',
        'created_by', 'distance_km', 'is_featured', 'featured_image',
        'is_active', 'is_classic', 'classic_city', 'start_location',
        'end_location', 'elevation_gain', 'difficulty', 'estimated_time',
        'landmarks'
    ]
    
    form_extra_fields = {
        'featured_image': fields.StringField('Nome Immagine'),
        'coordinates': fields.TextAreaField('Coordinates (GeoJSON)'),
        'landmarks': fields.TextAreaField('Punti di Riferimento')
    }
    
    # RISOLTO: Aggiungi created_at alle regole del form
    form_edit_rules = (
        'name', 'description', 'activity_type', 'coordinates',
        'created_by', 'distance_km', 'is_featured', 'featured_image',
        'is_active', 'is_classic', 'classic_city', 'start_location',
        'end_location', 'elevation_gain', 'difficulty', 'estimated_time',
        'landmarks'#, 'created_at'
    )

class ActivityAdminView(SecureModelView):
    # RISOLTO: Usa ID invece di relazioni complesse
    column_list = [
        'id', 'user_id', 'route_id', 'activity_type', 
        'duration', 'distance', 'avg_speed', 'created_at'
    ]
    column_filters = ['activity_type', 'created_at']
    column_searchable_list = ['activity_type']
    column_default_sort = ('created_at', True)
    
    form_columns = [
        'user_id', 'route_id', 'challenge_id',
        'activity_type', 'gps_track', 'duration', 'avg_speed', 'distance'
    ]

class ChallengeAdminView(SecureModelView):
    # RISOLTO: Usa ID invece di relazioni
    column_list = [
        'id', 'name', 'route_id', 'created_by', 
        'challenge_type', 'bet_type', 'bet_value',
        'start_date', 'end_date', 'is_active', 'created_at'
    ]
    column_filters = [
        'start_date', 'end_date', 'challenge_type', 
        'bet_type', 'is_active', 'created_at'
    ]
    column_searchable_list = ['name', 'custom_bet']
    column_editable_list = ['is_active']
    column_default_sort = ('start_date', True)

class ChallengeInvitationAdminView(SecureModelView):
    column_list = [
        'id', 'challenge_id', 'invited_user_id', 'status', 
        'invited_at', 'responded_at'
    ]
    column_filters = ['status', 'invited_at']
    column_editable_list = ['status']
    column_default_sort = ('invited_at', True)

class CommentAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'route_id', 'content', 'created_at']
    column_searchable_list = ['content']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)

class LikeAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'comment_id', 'created_at']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)

class ActivityLikeAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'activity_id', 'created_at']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)

class RouteRecordAdminView(SecureModelView):
    column_list = [
        'id', 'route_id', 'user_id', 
        'activity_type', 'duration', 'created_at'
    ]
    column_filters = ['activity_type', 'created_at']
    column_default_sort = ('duration', False)

class BadgeAdminView(SecureModelView):
    column_list = ['id', 'name', 'description', 'image_url', 'created_at']
    column_searchable_list = ['name', 'description']
    form_columns = ['name', 'description', 'image_url', 'criteria']
    
    form_extra_fields = {
        'image_url': fields.StringField('URL Immagine Badge'),
        'criteria': fields.TextAreaField('Criteri per Ottenere il Badge')
    }

class UserBadgeAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'badge_id', 'awarded_at']
    column_filters = ['awarded_at']
    column_default_sort = ('awarded_at', True)

class NotificationAdminView(SecureModelView):
    column_list = [
        'id', 'recipient_id', 'actor_id', 'action', 
        'object_id', 'object_type', 'read', 'timestamp'
    ]
    column_filters = ['action', 'read', 'timestamp']
    column_editable_list = ['read']
    column_default_sort = ('timestamp', True)

# --- Creazione dell'Istanza Admin ---
admin = Admin(
    name='StreetSport Admin',
    template_mode='bootstrap4',
    index_view=SecureAdminIndexView(),
    endpoint='admin'
)

def setup_admin_views(db):
    """Importa i modelli SOLO quando viene chiamata questa funzione"""
    from app.models import (User, Route, Activity, Challenge, ChallengeInvitation,
                          Comment, Like, Badge, UserBadge, Notification,
                          RouteRecord, ActivityLike)
    
    try:
        # === AGGIUNGI TUTTE LE VISTE CON ENDPOINT UNIVOCI ===
        admin.add_view(UserAdminView(User, db.session, name='Utenti', endpoint='admin_users'))
        admin.add_view(RouteAdminView(Route, db.session, name='Percorsi', endpoint='admin_routes'))
        admin.add_view(ActivityAdminView(Activity, db.session, name='Attività', endpoint='admin_activities'))
        admin.add_view(ChallengeAdminView(Challenge, db.session, name='Sfide', endpoint='admin_challenges'))
        admin.add_view(ChallengeInvitationAdminView(ChallengeInvitation, db.session, name='Inviti Sfide', endpoint='admin_challenge_invitations'))
        admin.add_view(CommentAdminView(Comment, db.session, name='Commenti', endpoint='admin_comments'))
        admin.add_view(LikeAdminView(Like, db.session, name='Like Commenti', endpoint='admin_likes'))
        admin.add_view(ActivityLikeAdminView(ActivityLike, db.session, name='Like Attività', endpoint='admin_activity_likes'))
        admin.add_view(RouteRecordAdminView(RouteRecord, db.session, name='Record Percorsi', endpoint='admin_route_records'))
        admin.add_view(BadgeAdminView(Badge, db.session, name='Badge', endpoint='admin_badges'))
        admin.add_view(UserBadgeAdminView(UserBadge, db.session, name='Badge Utenti', endpoint='admin_user_badges'))
        admin.add_view(NotificationAdminView(Notification, db.session, name='Notifiche', endpoint='admin_notifications'))

        print("✅ Admin panel COMPLETO configurato con successo!")
        
    except Exception as e:
        print(f"❌ Errore durante la configurazione dell'Admin Panel: {e}")