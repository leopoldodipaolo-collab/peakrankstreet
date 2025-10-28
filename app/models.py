from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from . import db
from sqlalchemy import event
from sqlalchemy.orm import object_session
from sqlalchemy.orm.attributes import get_history

# =====================================================================
# TABELLE DI ASSOCIAZIONE (Molti-a-Molti)
# Definite qui all'inizio per essere disponibili a tutti i modelli.
# =====================================================================
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    extend_existing=True
)

post_tags = db.Table('post_tags',
    db.Column('post_id', db.Integer, db.ForeignKey('posts.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True),
    extend_existing=True
)


# Tabella di associazione per i membri dei gruppi
group_members = db.Table('group_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id'), primary_key=True),
    extend_existing=True
)


# =====================================================================
# MODELLI PRINCIPALI
# =====================================================================

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    profile_image = db.Column(db.String(120), nullable=False, default='default.png')
    city = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    routes = db.relationship('Route', backref='creator', lazy='dynamic')
    challenges = db.relationship('Challenge', backref='challenger', lazy='dynamic')
    activities = db.relationship('Activity', backref='user_activity', lazy='dynamic')
    comments = db.relationship('Comment', backref='author', lazy='dynamic')
    route_records = db.relationship('RouteRecord', backref='record_holder', lazy='dynamic')
    user_badges = db.relationship('UserBadge', backref='user', lazy='dynamic')

    # --- NUOVI CAMPI PER LA GAMIFICATION FEUDALE ---
    prestige = db.Column(db.Integer, default=0, nullable=False, index=True)
    title = db.Column(db.String(50), default='Popolano', nullable=False)
    # --- FINE NUOVI CAMPI ---
    
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0
    
    def followed_posts(self):
        return Activity.query.join(
            followers, (followers.c.followed_id == Activity.user_id)
        ).filter(followers.c.follower_id == self.id)

    def __repr__(self):
        return f'<User {self.username}>'
    
    # RELAZIONE PER I GRUPPI POSSEDUTI
    owned_groups = db.relationship('Group', foreign_keys='Group.owner_id', backref='owner', lazy='dynamic')

    # RELAZIONE PER I GRUPPI A CUI L'UTENTE È ISCRITTO
    joined_groups = db.relationship('Group',
                                    secondary=group_members,
                                    backref=db.backref('members', lazy='dynamic'),
                                    lazy='dynamic')


# Puoi aggiungere questa nuova classe dopo la classe User
class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    profile_image = db.Column(db.String(120), nullable=False, default='default_group.png')
    city = db.Column(db.String(100), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # RELAZIONE PER I POST DEL GRUPPO
    posts = db.relationship('Post', backref='group', lazy='dynamic')
    
    events = db.relationship('Event', 
                             back_populates='group', 
                             lazy='dynamic',
                             cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Group {self.name}>'
    
class Route(db.Model):
    __tablename__ = 'Routes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.String(500), nullable=True)
    coordinates = db.Column(db.Text, nullable=False)
    duration = db.Column(db.Integer)
    activity_type = db.Column(db.String(50), nullable=False, default='Corsa', index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    distance_km = db.Column(db.Float, nullable=True)
    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    featured_image = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_classic = db.Column(db.Boolean, default=False, index=True)
    classic_city = db.Column(db.String(100), index=True)
    start_location = db.Column(db.String(200))
    end_location = db.Column(db.String(200))
    elevation_gain = db.Column(db.Integer)
    difficulty = db.Column(db.String(20))
    estimated_time = db.Column(db.String(50))
    landmarks = db.Column(db.Text)
    
    challenges = db.relationship('Challenge', backref='route_info', lazy='dynamic')
    activities = db.relationship('Activity', backref='route_activity', lazy='dynamic')
    comments = db.relationship('Comment', backref='route', lazy='dynamic')
    records = db.relationship('RouteRecord', backref='route', lazy='dynamic')

    # --- NUOVO CAMPO FONDAMENTALE ---
    classic_status = db.Column(db.String(20), default='none', index=True)
    # Valori possibili:
    # 'none' -> Percorso normale creato da un utente
    # 'proposed' -> Proposto come classico, in attesa di revisione
    # 'approved' -> Approvato come classico dall'admin
    # 'rejected' -> Rifiutato come classico dall'admin

    def __repr__(self):
        return f'<Route {self.name}>'


class Challenge(db.Model):
    __tablename__ = 'Challenges'
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('Routes.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, default="Sfida su Percorso", index=True)
    start_date = db.Column(db.DateTime, nullable=False, index=True)
    end_date = db.Column(db.DateTime, nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    challenge_type = db.Column(db.String(20), default='open', index=True)
    bet_type = db.Column(db.String(50), default='none')
    custom_bet = db.Column(db.String(100))
    bet_value = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True, index=True)

    activities = db.relationship('Activity', backref='challenge', lazy='dynamic')
    invitations = db.relationship('ChallengeInvitation', backref='challenge', lazy='dynamic')

    def __repr__(self):
        return f'<Challenge {self.name}>'


class Activity(db.Model):
    __tablename__ = 'Activities'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey('Routes.id'), nullable=True, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('Challenges.id'), nullable=True, index=True)
    activity_type = db.Column(db.String(50), nullable=False, default='Corsa', index=True)
    gps_track = db.Column(db.Text, nullable=False)
    duration = db.Column(db.Integer, nullable=False, index=True)
    avg_speed = db.Column(db.Float, nullable=False)
    distance = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    name = db.Column(db.String(100), nullable=True) 
    description = db.Column(db.String(500), nullable=True) 

    likes = db.relationship('ActivityLike', backref='activity', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Activity {self.id}>'


# =====================================================================
# MODELLI PER POST, COMMENTI, LIKE E TAG
# Riordinati per una corretta definizione delle dipendenze
# =====================================================================

class Tag(db.Model):
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)

    def __repr__(self):
        return f'<Tag #{self.name}>'


class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    post_type = db.Column(db.String(50), default='text', index=True)
    post_category = db.Column(db.String(50), default='user_post', nullable=False, index=True)
    meta_data = db.Column(db.JSON, nullable=True)
    
    user = db.relationship('User', backref='posts')
    comments = db.relationship('PostComment', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    likes = db.relationship('PostLike', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    tags = db.relationship('Tag', secondary=post_tags, backref=db.backref('posts', lazy='dynamic'), lazy='dynamic')

    # --- NUOVO CAMPO FACOLTATIVO ---
    # Se un post è pubblicato in un gruppo, questo campo avrà l'ID del gruppo
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True, index=True)
    # --- FINE NUOVO CAMPO ---
    

    def __repr__(self):
        return f'<Post {self.id}>'


class PostComment(db.Model):
    __tablename__ = 'post_comments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # --- NUOVI CAMPI PER LE RISPOSTE ---
    
    # 1. Aggiungiamo una colonna per memorizzare l'ID del commento genitore.
    #    È nullable=True perché i commenti di primo livello non hanno un genitore.
    parent_id = db.Column(db.Integer, db.ForeignKey('post_comments.id'), nullable=True)

    # 2. Creiamo la relazione per accedere facilmente alle risposte.
    #    'replies' ci darà tutti i figli di un commento.
    replies = db.relationship('PostComment',
                              backref=db.backref('parent', remote_side=[id]),
                              lazy='dynamic',
                              cascade='all, delete-orphan')
    
    # --- FINE NUOVI CAMPI ---

    user = db.relationship('User', backref='post_comments')
    
    def __repr__(self):
        return f'<PostComment {self.id} on Post {self.post_id}>'


class PostLike(db.Model):
    __tablename__ = 'post_likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='_user_post_like_uc'),)
    
    user = db.relationship('User', backref='post_likes')
    
    def __repr__(self):
        return f'<PostLike {self.id}>'


# =====================================================================
# ALTRI MODELLI (Commenti su percorsi, Likes, Badge, Notifiche, etc.)
# =====================================================================

# =====================================================================
# ALTRI MODELLI (Commenti su percorsi, Likes, Badge, Notifiche, etc.)
# =====================================================================

class Comment(db.Model):
    __tablename__ = 'Comments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey('Routes.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    likes = db.relationship('Like', backref='comment_liked', lazy='dynamic')

class Like(db.Model):
    __tablename__ = 'Likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('Comments.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='_user_comment_uc'),)

class ActivityLike(db.Model):
    __tablename__ = 'activity_likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('Activities.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'activity_id', name='_user_activity_uc'),)

class RouteRecord(db.Model):
    __tablename__ = 'RouteRecords'
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('Routes.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('Activities.id'), unique=True, nullable=False)
    activity_type = db.Column(db.String(50), nullable=False, default='Corsa', index=True)
    duration = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    activity = db.relationship('Activity', backref=db.backref('record_info', uselist=False))

class Badge(db.Model):
    __tablename__ = 'Badges'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    image_url = db.Column(db.String(120), nullable=False, default='badge_default.png')
    criteria = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class UserBadge(db.Model):
    __tablename__ = 'UserBadges'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    badge_id = db.Column(db.Integer, db.ForeignKey('Badges.id'), nullable=False, index=True)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'badge_id', name='_user_badge_uc'),)
    badge = db.relationship('Badge', backref='user_associations')

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    object_id = db.Column(db.Integer, nullable=True)
    object_type = db.Column(db.String(50), nullable=True)
    read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref=db.backref('notifications', lazy='dynamic'))
    actor = db.relationship('User', foreign_keys=[actor_id])

class ChallengeInvitation(db.Model):
    __tablename__ = 'ChallengeInvitations'
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('Challenges.id'), nullable=False, index=True)
    invited_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', index=True)
    invited_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User', backref='invitations_received')
    
class Bet(db.Model):
    __tablename__ = 'bets'
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('Challenges.id'), nullable=False, index=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    loser_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    bet_type = db.Column(db.String(50), nullable=False)
    bet_value = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
    challenge = db.relationship('Challenge', backref='bets')
    winner = db.relationship('User', foreign_keys=[winner_id], backref='bets_won')
    loser = db.relationship('User', foreign_keys=[loser_id], backref='bets_lost')

# =====================================================================
# FUNZIONI HELPER (associate ai modelli)
# =====================================================================

def close_expired_challenges():
    """Chiude automaticamente le sfide scadute e processa le scommesse"""
    from datetime import datetime
    
    try:
        expired_challenges = Challenge.query.filter(
            Challenge.end_date < datetime.utcnow(),
            Challenge.is_active == True
        ).all()
        
        print(f"🔍 Controllo sfide scadute: trovate {len(expired_challenges)}")
        
        for challenge in expired_challenges:
            print(f"🔚 Chiusura automatica sfida: {challenge.name} (ID: {challenge.id})")
            challenge.is_active = False
            
            # Processa scommessa se presente
            if challenge.bet_type != 'none' and challenge.activities:
                process_challenge_bet(challenge)
            
            # Chiudi tutti gli inviti pendenti
            pending_invitations = ChallengeInvitation.query.filter_by(
                challenge_id=challenge.id,
                status='pending'
            ).all()
            
            for invitation in pending_invitations:
                invitation.status = 'expired'
        
        if expired_challenges:
            db.session.commit()
            print(f"✅ Chiuse {len(expired_challenges)} sfide scadute")
            return len(expired_challenges)
        else:
            print("✅ Nessuna sfida da chiudere")
            return 0
            
    except Exception as e:
        print(f"❌ Errore nella chiusura automatica sfide: {e}")
        db.session.rollback()
        return 0
    
def process_challenge_bet(challenge):
    """Processa la scommessa di una sfida terminata"""
    try:
        # Trova il vincitore (miglior tempo)
        winner_activity = Activity.query.filter_by(
            challenge_id=challenge.id
        ).order_by(Activity.duration.asc()).first()
        
        if not winner_activity:
            print(f"❌ Nessuna attività per la sfida {challenge.id} - scommessa saltata")
            return
        
        winner = winner_activity.user_activity
        print(f"🎯 Vincitore sfida {challenge.id}: {winner.username}")
        
        # Per sfide chiuse, tutti gli altri partecipanti perdono
        if challenge.challenge_type == 'closed':
            participants = Activity.query.filter_by(challenge_id=challenge.id).all()
            for activity in participants:
                if activity.user_id != winner.id:
                    create_bet_notification(challenge, winner, activity.user_activity)
        
        # Per sfide aperte, solo il creatore paga (se non ha vinto)
        elif challenge.challenge_type == 'open' and challenge.created_by != winner.id:
            creator = User.query.get(challenge.created_by)
            create_bet_notification(challenge, winner, creator)
            
        print(f"✅ Scommessa processata per {challenge.name}")
        
    except Exception as e:
        print(f"❌ Errore nel processare scommessa per sfida {challenge.id}: {e}")

def create_bet_notification(challenge, winner, loser):
    """Crea le notifiche per vincitore e perdente"""
    try:
        # Crea record scommessa
        new_bet = Bet(
            challenge_id=challenge.id,
            winner_id=winner.id,
            loser_id=loser.id,
            bet_type=challenge.bet_type,
            bet_value=challenge.bet_value,
            status='pending'
        )
        db.session.add(new_bet)
        
        # Notifica per il VINCITORE
        winner_notification = Notification(
            recipient_id=winner.id,
            actor_id=loser.id,
            action='bet_won',
            object_id=challenge.id,
            object_type='bet'
        )
        db.session.add(winner_notification)
        
        # Notifica per il PERDENTE
        loser_notification = Notification(
            recipient_id=loser.id,
            actor_id=winner.id,
            action='bet_lost',
            object_id=challenge.id,
            object_type='bet'
        )
        db.session.add(loser_notification)
        
        print(f"💰 Scommessa creata: {winner.username} → {loser.username}: {challenge.bet_value}")
        
    except Exception as e:
        print(f"❌ Errore creazione scommessa: {e}")


def after_route_approved(mapper, connection, target):
    """
    Questa funzione viene chiamata automaticamente dopo che una Route viene aggiornata.
    Controlla se lo stato è appena diventato 'approved'.
    """
    # Usiamo 'is_modified' per assicurarci che questa logica venga eseguita
    # solo quando il campo 'classic_status' è effettivamente cambiato.
    history = get_history(target, 'classic_status')
    
    # Controlliamo se il valore è cambiato e se il nuovo valore è 'approved'
    if history.has_changes() and target.classic_status == 'approved':
        
        # --- INIZIO BLOCCO INDENTATO CORRETTAMENTE ---
        
        print(f"✅ DEBUG: Il percorso ID {target.id} è stato approvato! Creo la notifica.")

        # Assicurati che il creatore esista prima di procedere
        if not target.creator:
            print(f"❌ ERRORE: Impossibile trovare il creatore per il percorso ID {target.id}. Salto la notifica.")
            return

        # 1. Crea la notifica per l'utente che ha proposto il percorso
        notification = Notification(
            recipient_id=target.created_by,
            actor_id=1, # Assumendo che l'utente con ID 1 sia un admin. Modifica se necessario.
            action='route_approved',
            object_id=target.id,
            object_type='route'
        )
        
        # 2. Crea un post automatico nel feed
        post_content = (
            f"🗺️ Nuovo Percorso Classico! Grazie a {target.creator.username}, "
            f"il percorso '{target.name}' a {target.classic_city} è ora disponibile per tutti. "
            "Scopritelo!"
        )
        
        new_post = Post(
            user_id=target.created_by,
            content=post_content,
            post_category='system_new_classic',
            post_type='text'
        )

        # Usiamo la sessione legata all'oggetto 'target' per aggiungere i nuovi oggetti
        session = object_session(target)
        if session:
            session.add(notification)
            session.add(new_post)
            # Nota: Non facciamo session.commit() qui. L'evento 'after_update' 
            # viene eseguito all'interno di una transazione esistente.
            # SQLAlchemy si occuperà del commit.

        # --- FINE BLOCCO INDENTATO ---


# Registra il listener per il modello Route
event.listen(Route, 'after_update', after_route_approved)



# All'inizio del file, insieme alle altre tabelle di associazione
event_participants = db.Table('event_participants',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('event_id', db.Integer, db.ForeignKey('events.id'), primary_key=True),
    extend_existing=True
)

# ... (gli altri tuoi modelli) ...

# Puoi aggiungere questa nuova classe dopo la classe Group
class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    description = db.Column(db.Text)
    event_time = db.Column(db.DateTime, nullable=False, index=True)
    location = db.Column(db.String(200)) # Es. "Ingresso Parco della Caffarella"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Chi ha creato l'evento
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    creator = db.relationship('User', backref='created_events')
    
    # A quale gruppo appartiene l'evento
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    group = db.relationship('Group', back_populates='events')

    # Relazione per accedere ai partecipanti
    participants = db.relationship('User', secondary=event_participants,
                                   backref=db.backref('joined_events', lazy='dynamic'),
                                   lazy='dynamic')
    
    def __repr__(self):
        return f'<Event {self.name}>'