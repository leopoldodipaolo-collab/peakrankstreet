# app/admin.py

from flask import redirect, url_for, request
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from wtforms import fields, validators
from wtforms.fields import SelectField
import os
from datetime import datetime
from flask_admin import BaseView, expose

# --- Vista Indice Personalizzata e Protetta ---
class SecureAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login', next=request.url))
    
    @expose('/')
    def index(self):
        from app.models import (User, Route, Activity, Post, Group, 
                              Challenge, Comment, Badge, Notification, Event)
        stats = {
            'total_users': User.query.count(),
            'total_routes': Route.query.count(),
            'total_activities': Activity.query.count(),
            'total_posts': Post.query.count(),
            'total_groups': Group.query.count(),
            'total_challenges': Challenge.query.count(),
            'total_comments': Comment.query.count(),
            'total_badges': Badge.query.count(),
            'featured_routes': Route.query.filter_by(is_featured=True).count(),
            'classic_routes': Route.query.filter_by(is_classic=True).count(),
            'active_challenges': Challenge.query.filter_by(is_active=True).count(),
            'unread_notifications': Notification.query.filter_by(read=False).count(),
        }
        return self.render('admin/index.html', stats=stats)

# --- Viste Personalizzate e Protette per i Modelli ---
class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login', next=request.url))

# === MODELLI PRINCIPALI ===

class UserAdminView(SecureModelView):
    column_list = ['id', 'username', 'email', 'city', 'prestige', 'title', 'is_admin', 'profile_image', 'created_at']
    column_exclude_list = ['password_hash']
    form_excluded_columns = ['password_hash']
    column_searchable_list = ['username', 'email', 'city']
    column_filters = ['city', 'is_admin', 'prestige', 'title', 'created_at']
    can_create = False
    column_editable_list = ['is_admin', 'prestige', 'title']
    column_default_sort = ('created_at', True)
    
    form_columns = ['username', 'email', 'city', 'profile_image', 'prestige', 'title', 'is_admin', 'onboarding_steps']
    
    form_extra_fields = {
        'onboarding_steps': fields.TextAreaField('Passaggi Onboarding (JSON)', render_kw={"rows": 3}),
    }

class GroupAdminView(SecureModelView):
    column_list = ['id', 'name', 'owner_id', 'city', 'profile_image', 'created_at']
    column_searchable_list = ['name', 'description', 'city']
    column_filters = ['city', 'created_at']
    column_editable_list = ['name', 'city']
    
    form_columns = ['name', 'description', 'owner_id', 'profile_image', 'city']
    
    form_extra_fields = {
        'description': fields.TextAreaField('Descrizione', render_kw={"rows": 4}),
    }

class EventAdminView(SecureModelView):
    column_list = ['id', 'name', 'group_id', 'creator_id', 'event_time', 'location', 'created_at']
    column_searchable_list = ['name', 'description', 'location']
    column_filters = ['event_time', 'created_at']
    column_editable_list = ['name', 'location']
    
    form_columns = ['name', 'description', 'group_id', 'creator_id', 'event_time', 'location']
    
    form_extra_fields = {
        'description': fields.TextAreaField('Descrizione Evento', render_kw={"rows": 4}),
    }

class RouteAdminView(SecureModelView):
    column_list = [
        'id', 'name', 'created_by', 'activity_type', 'distance_km', 'difficulty',
        'is_featured', 'is_classic', 'classic_city', 'classic_status',
        'is_active', 'created_at'
    ]
    column_searchable_list = ['name', 'description', 'classic_city', 'start_location', 'end_location']
    column_filters = [
        'is_featured', 'is_classic', 'is_active', 'activity_type', 
        'difficulty', 'classic_city', 'created_at', 'classic_status'
    ]
    column_editable_list = ['is_featured', 'is_classic', 'is_active', 'classic_status']
    
    form_columns = [
        'name', 'description', 'activity_type', 'coordinates',
        'created_by', 'distance_km', 'is_featured', 'featured_image', 'is_active', 
        'is_classic', 'classic_city', 'start_location', 'end_location',
        'elevation_gain', 'difficulty', 'estimated_time', 'landmarks', 'classic_status'
    ]
    
    form_extra_fields = {
        'description': fields.TextAreaField('Descrizione', render_kw={"rows": 3}),
        'coordinates': fields.TextAreaField('Coordinates (GeoJSON)', render_kw={"rows": 5}),
        'landmarks': fields.TextAreaField('Punti di Riferimento', render_kw={"rows": 3}),
        'featured_image': fields.StringField('Immagine in Evidenza'),
    }

class ActivityAdminView(SecureModelView):
    column_list = [
        'id', 'user_id', 'route_id', 'challenge_id', 'activity_type', 
        'duration', 'distance', 'avg_speed', 'name', 'created_at'
    ]
    column_filters = ['activity_type', 'created_at']
    column_searchable_list = ['activity_type', 'name', 'description']
    column_default_sort = ('created_at', True)
    
    form_columns = [
        'user_id', 'route_id', 'challenge_id',
        'activity_type', 'gps_track', 'duration', 'avg_speed', 'distance', 'name', 'description'
    ]
    
    form_extra_fields = {
        'gps_track': fields.TextAreaField('Tracciato GPS', render_kw={"rows": 5}),
        'description': fields.TextAreaField('Descrizione Attività', render_kw={"rows": 3}),
    }

class ChallengeAdminView(SecureModelView):
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
    
    form_columns = [
        'name', 'route_id', 'created_by', 'challenge_type',
        'start_date', 'end_date', 'bet_type', 'custom_bet', 'bet_value', 'is_active'
    ]

class ChallengeInvitationAdminView(SecureModelView):
    column_list = [
        'id', 'challenge_id', 'invited_user_id', 'status', 
        'invited_at', 'responded_at'
    ]
    column_filters = ['status', 'invited_at']
    column_editable_list = ['status']
    column_default_sort = ('invited_at', True)
    
    form_columns = ['challenge_id', 'invited_user_id', 'status']

class CommentAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'route_id', 'content', 'created_at']
    column_searchable_list = ['content']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)
    
    form_columns = ['user_id', 'route_id', 'content']
    
    form_extra_fields = {
        'content': fields.TextAreaField('Commento', render_kw={"rows": 4}),
    }

class LikeAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'comment_id', 'created_at']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)
    
    form_columns = ['user_id', 'comment_id']

class ActivityLikeAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'activity_id', 'created_at']
    column_filters = ['created_at']
    column_default_sort = ('created_at', True)
    
    form_columns = ['user_id', 'activity_id']

class RouteRecordAdminView(SecureModelView):
    column_list = [
        'id', 'route_id', 'user_id', 'activity_id', 'activity_type', 'duration', 'created_at'
    ]
    column_filters = ['activity_type', 'created_at']
    column_default_sort = ('duration', False)
    
    form_columns = ['route_id', 'user_id', 'activity_id', 'activity_type', 'duration']

class BadgeAdminView(SecureModelView):
    column_list = ['id', 'name', 'description', 'image_url', 'criteria', 'created_at']
    column_searchable_list = ['name', 'description', 'criteria']
    column_editable_list = ['name', 'description']
    
    form_columns = ['name', 'description', 'image_url', 'criteria']
    
    form_extra_fields = {
        'description': fields.TextAreaField('Descrizione Badge', render_kw={"rows": 3}),
        'criteria': fields.TextAreaField('Criteri per Ottenere il Badge', render_kw={"rows": 4}),
    }

class UserBadgeAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'badge_id', 'awarded_at']
    column_filters = ['awarded_at']
    column_default_sort = ('awarded_at', True)
    
    form_columns = ['user_id', 'badge_id', 'awarded_at']

class NotificationAdminView(SecureModelView):
    column_list = [
        'id', 'recipient_id', 'actor_id', 'action', 
        'object_id', 'object_type', 'read', 'timestamp'
    ]
    column_filters = ['action', 'read', 'timestamp']
    column_editable_list = ['read']
    column_default_sort = ('timestamp', True)
    
    form_columns = ['recipient_id', 'actor_id', 'action', 'object_id', 'object_type', 'read']

class BetAdminView(SecureModelView):
    column_list = [
        'id', 'challenge_id', 'winner_id', 'loser_id', 'bet_type', 
        'bet_value', 'status', 'created_at', 'paid_at'
    ]
    column_filters = ['bet_type', 'status', 'created_at']
    column_editable_list = ['status']
    column_default_sort = ('created_at', True)
    
    form_columns = ['challenge_id', 'winner_id', 'loser_id', 'bet_type', 'bet_value', 'status', 'paid_at']

class TagAdminView(SecureModelView):
    column_list = ['id', 'name']
    column_searchable_list = ['name']
    column_editable_list = ['name']
    
    form_columns = ['name']

# === MODELLI POST E SOCIAL ===

class PostAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'group_id', 'post_category', 'post_type', 'content', 'image_url', 'created_at']
    column_searchable_list = ['content']
    column_filters = ['post_category', 'post_type', 'created_at']
    column_editable_list = ['post_category']
    
    form_columns = ['user_id', 'group_id', 'content', 'image_url', 'post_category', 'post_type', 'meta_data']
    
    form_overrides = {
        'post_type': SelectField,
        'post_category': SelectField
    }
    
    form_args = {
        'post_category': {
            'choices': [
                ('user_post', 'Post Utente (Standard)'),
                ('admin_announcement', 'Annuncio Admin'),
                ('weekly_tip', 'Consiglio della Settimana'),
                ('system_new_classic', 'Sistema: Nuovo Classico')
            ],
        },
        'post_type': {
            'choices': [
                ('text', 'Solo Testo'),
                ('image', 'Testo con Immagine'),
                ('link', 'Link Esterno')
            ]
        }
    }
    
    form_extra_fields = {
        'content': fields.TextAreaField('Contenuto Post', render_kw={"rows": 5}),
        'meta_data': fields.TextAreaField('Metadati (JSON)', render_kw={"rows": 3}),
    }

class PostCommentAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'post_id', 'parent_id', 'content', 'created_at']
    column_filters = ['created_at']
    column_searchable_list = ['content']
    
    form_columns = ['user_id', 'post_id', 'parent_id', 'content']
    
    form_extra_fields = {
        'content': fields.TextAreaField('Commento', render_kw={"rows": 4}),
    }

class PostLikeAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'post_id', 'created_at']
    column_filters = ['created_at']
    
    form_columns = ['user_id', 'post_id']

# === TABELLE DI ASSOCIAZIONE ===

class FollowersAdminView(SecureModelView):
    column_list = ['follower_id', 'followed_id']
    can_create = True
    can_edit = False
    can_delete = True
    
    def get_query(self):
        from app.models import followers
        return self.session.query(followers)
    
    def get_count_query(self):
        from app.models import followers
        return self.session.query(followers)

class PostTagsAdminView(SecureModelView):
    column_list = ['post_id', 'tag_id']
    can_create = True
    can_edit = False
    can_delete = True
    
    def get_query(self):
        from app.models import post_tags
        return self.session.query(post_tags)
    
    def get_count_query(self):
        from app.models import post_tags
        return self.session.query(post_tags)

class GroupMembersAdminView(SecureModelView):
    column_list = ['user_id', 'group_id']
    can_create = True
    can_edit = False
    can_delete = True
    
    def get_query(self):
        from app.models import group_members
        return self.session.query(group_members)
    
    def get_count_query(self):
        from app.models import group_members
        return self.session.query(group_members)

class EventParticipantsAdminView(SecureModelView):
    column_list = ['user_id', 'event_id']
    can_create = True
    can_edit = False
    can_delete = True
    
    def get_query(self):
        from app.models import event_participants
        return self.session.query(event_participants)
    
    def get_count_query(self):
        from app.models import event_participants
        return self.session.query(event_participants)

# --- Creazione dell'Istanza Admin ---
admin = Admin(
    name='StreetSport Admin',
    template_mode='bootstrap4',
    index_view=SecureAdminIndexView(),
    endpoint='admin'
)

def setup_admin_views(admin_instance, db):
    """Configura TUTTE le viste admin per tutti i modelli."""
    from app.models import (
        User, Group, Event, Route, Activity, Challenge, ChallengeInvitation,
        Comment, Like, ActivityLike, RouteRecord, Badge, UserBadge, 
        Notification, Bet, Tag, Post, PostComment, PostLike
    )
    
    try:
        # === CATEGORIA: UTENTI E SOCIAL ===
        admin_instance.add_view(UserAdminView(User, db.session, name='Utenti', category='Utenti e Social'))
        admin_instance.add_view(GroupAdminView(Group, db.session, name='Gruppi', category='Utenti e Social'))
        admin_instance.add_view(EventAdminView(Event, db.session, name='Eventi', category='Utenti e Social'))
        
        # === CATEGORIA: POST E COMMUNITY ===
        admin_instance.add_view(PostAdminView(Post, db.session, name='Post', category='Post e Community'))
        admin_instance.add_view(PostCommentAdminView(PostComment, db.session, name='Commenti Post', category='Post e Community'))
        admin_instance.add_view(PostLikeAdminView(PostLike, db.session, name='Like Post', category='Post e Community'))
        admin_instance.add_view(TagAdminView(Tag, db.session, name='Tag', category='Post e Community'))
        
        # === CATEGORIA: ATTIVITÀ SPORTIVE ===
        admin_instance.add_view(RouteAdminView(Route, db.session, name='Percorsi', category='Attività Sportive'))
        admin_instance.add_view(ActivityAdminView(Activity, db.session, name='Attività', category='Attività Sportive'))
        admin_instance.add_view(RouteRecordAdminView(RouteRecord, db.session, name='Record Percorsi', category='Attività Sportive'))
        
        # === CATEGORIA: SFIDE E COMPETIZIONI ===
        admin_instance.add_view(ChallengeAdminView(Challenge, db.session, name='Sfide', category='Sfide e Competizioni'))
        admin_instance.add_view(ChallengeInvitationAdminView(ChallengeInvitation, db.session, name='Inviti Sfide', category='Sfide e Competizioni'))
        admin_instance.add_view(BetAdminView(Bet, db.session, name='Scommesse', category='Sfide e Competizioni'))
        
        # === CATEGORIA: BADGE E RICONOSCIMENTI ===
        admin_instance.add_view(BadgeAdminView(Badge, db.session, name='Badge', category='Badge e Riconoscimenti'))
        admin_instance.add_view(UserBadgeAdminView(UserBadge, db.session, name='Badge Utenti', category='Badge e Riconoscimenti'))
        
        # === CATEGORIA: INTERAZIONI ===
        admin_instance.add_view(CommentAdminView(Comment, db.session, name='Commenti Percorsi', category='Interazioni'))
        admin_instance.add_view(LikeAdminView(Like, db.session, name='Like Commenti', category='Interazioni'))
        admin_instance.add_view(ActivityLikeAdminView(ActivityLike, db.session, name='Like Attività', category='Interazioni'))
        
        # === CATEGORIA: SISTEMA ===
        admin_instance.add_view(NotificationAdminView(Notification, db.session, name='Notifiche', category='Sistema'))
        
        # === CATEGORIA: TABELLE DI ASSOCIAZIONE ===
        admin_instance.add_view(FollowersAdminView(name='Followers', category='Tabelle Associazioni'))
        admin_instance.add_view(PostTagsAdminView(name='Post Tags', category='Tabelle Associazioni'))
        admin_instance.add_view(GroupMembersAdminView(name='Membri Gruppi', category='Tabelle Associazioni'))
        admin_instance.add_view(EventParticipantsAdminView(name='Partecipanti Eventi', category='Tabelle Associazioni'))

        print("✅ Admin panel COMPLETO configurato con successo!")
        
    except Exception as e:
        print(f"❌ Errore durante la configurazione dell'Admin Panel: {e}")
        import traceback
        traceback.print_exc()


def setup_admin_views(admin_instance, db):
    """Configura TUTTE le viste admin per tutti i modelli."""
    from app.models import (
        User, Group, Event, Route, Activity, Challenge, ChallengeInvitation,
        Comment, Like, ActivityLike, RouteRecord, Badge, UserBadge, 
        Notification, Bet, Tag, Post, PostComment, PostLike
    )
    
    try:
        # === CATEGORIA: UTENTI E SOCIAL ===
        admin_instance.add_view(UserAdminView(User, db.session, name='Utenti', category='Utenti e Social'))
        admin_instance.add_view(GroupAdminView(Group, db.session, name='Gruppi', category='Utenti e Social'))
        admin_instance.add_view(EventAdminView(Event, db.session, name='Eventi', category='Utenti e Social'))
        
        # === CATEGORIA: POST E COMMUNITY ===
        admin_instance.add_view(PostAdminView(Post, db.session, name='Post', category='Post e Community'))
        admin_instance.add_view(PostCommentAdminView(PostComment, db.session, name='Commenti Post', category='Post e Community'))
        admin_instance.add_view(PostLikeAdminView(PostLike, db.session, name='Like Post', category='Post e Community'))
        admin_instance.add_view(TagAdminView(Tag, db.session, name='Tag', category='Post e Community'))
        
        # === CATEGORIA: ATTIVITÀ SPORTIVE ===
        admin_instance.add_view(RouteAdminView(Route, db.session, name='Percorsi', category='Attività Sportive'))
        admin_instance.add_view(ActivityAdminView(Activity, db.session, name='Attività', category='Attività Sportive'))
        admin_instance.add_view(RouteRecordAdminView(RouteRecord, db.session, name='Record Percorsi', category='Attività Sportive'))
        
        # === CATEGORIA: SFIDE E COMPETIZIONI ===
        admin_instance.add_view(ChallengeAdminView(Challenge, db.session, name='Sfide', category='Sfide e Competizioni'))
        admin_instance.add_view(ChallengeInvitationAdminView(ChallengeInvitation, db.session, name='Inviti Sfide', category='Sfide e Competizioni'))
        admin_instance.add_view(BetAdminView(Bet, db.session, name='Scommesse', category='Sfide e Competizioni'))
        
        # === CATEGORIA: BADGE E RICONOSCIMENTI ===
        admin_instance.add_view(BadgeAdminView(Badge, db.session, name='Badge', category='Badge e Riconoscimenti'))
        admin_instance.add_view(UserBadgeAdminView(UserBadge, db.session, name='Badge Utenti', category='Badge e Riconoscimenti'))
        
        # === CATEGORIA: INTERAZIONI ===
        admin_instance.add_view(CommentAdminView(Comment, db.session, name='Commenti Percorsi', category='Interazioni'))
        admin_instance.add_view(LikeAdminView(Like, db.session, name='Like Commenti', category='Interazioni'))
        admin_instance.add_view(ActivityLikeAdminView(ActivityLike, db.session, name='Like Attività', category='Interazioni'))
        
        # === CATEGORIA: SISTEMA ===
        admin_instance.add_view(NotificationAdminView(Notification, db.session, name='Notifiche', category='Sistema'))
        
        # === CATEGORIA: TABELLE DI ASSOCIAZIONE (BASEVIEW) ===
        from flask_admin import BaseView, expose

        class FollowersAdminView(BaseView):
            def is_accessible(self):
                return current_user.is_authenticated and current_user.is_admin
            def inaccessible_callback(self, name, **kwargs):
                return redirect(url_for('auth.login', next=request.url))
            @expose('/')
            def index(self):
                from app.models import followers
                rows = db.session.query(followers).all()
                return "<pre>" + "\n".join(str(r) for r in rows) + "</pre>"

        class PostTagsAdminView(BaseView):
            def is_accessible(self):
                return current_user.is_authenticated and current_user.is_admin
            def inaccessible_callback(self, name, **kwargs):
                return redirect(url_for('auth.login', next=request.url))
            @expose('/')
            def index(self):
                from app.models import post_tags
                rows = db.session.query(post_tags).all()
                return "<pre>" + "\n".join(str(r) for r in rows) + "</pre>"

        class GroupMembersAdminView(BaseView):
            def is_accessible(self):
                return current_user.is_authenticated and current_user.is_admin
            def inaccessible_callback(self, name, **kwargs):
                return redirect(url_for('auth.login', next=request.url))
            @expose('/')
            def index(self):
                from app.models import group_members
                rows = db.session.query(group_members).all()
                return "<pre>" + "\n".join(str(r) for r in rows) + "</pre>"

        class EventParticipantsAdminView(BaseView):
            def is_accessible(self):
                return current_user.is_authenticated and current_user.is_admin
            def inaccessible_callback(self, name, **kwargs):
                return redirect(url_for('auth.login', next=request.url))
            @expose('/')
            def index(self):
                from app.models import event_participants
                rows = db.session.query(event_participants).all()
                return "<pre>" + "\n".join(str(r) for r in rows) + "</pre>"

        # aggiunta al pannello admin
        admin_instance.add_view(FollowersAdminView(name='Followers', category='Tabelle Associazioni'))
        admin_instance.add_view(PostTagsAdminView(name='Post Tags', category='Tabelle Associazioni'))
        admin_instance.add_view(GroupMembersAdminView(name='Membri Gruppi', category='Tabelle Associazioni'))
        admin_instance.add_view(EventParticipantsAdminView(name='Partecipanti Eventi', category='Tabelle Associazioni'))

        print("✅ Admin panel COMPLETO configurato con successo!")

    except Exception as e:
        print(f"❌ Errore durante la configurazione dell'Admin Panel: {e}")
        import traceback
        traceback.print_exc()
