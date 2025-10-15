
# app/models.py

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from . import db

followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)


class User(db.Model, UserMixin):
    # MODIFICATO: Classe User potenziata con funzionalità social
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    profile_image = db.Column(db.String(120), nullable=False, default='default.png')
    city = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # MODIFICATO: lazy='dynamic' permette di aggiungere filtri successivi alle query
    routes = db.relationship('Route', backref='creator', lazy='dynamic')
    challenges = db.relationship('Challenge', backref='challenger', lazy='dynamic')
    activities = db.relationship('Activity', backref='user_activity', lazy='dynamic')
    comments = db.relationship('Comment', backref='author', lazy='dynamic')
    likes = db.relationship('Like', backref='user_liker', lazy='dynamic')
    route_records = db.relationship('RouteRecord', backref='record_holder', lazy='dynamic')
    user_badges = db.relationship('UserBadge', backref='badge_recipient', lazy='dynamic')
    activity_likes = db.relationship('ActivityLike', backref='user', lazy='dynamic')
    # NUOVO: Relazione per utenti seguiti e follower
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # NUOVO: Funzioni helper per la logica social
    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0
    
    # NUOVO: Funzione per recuperare le attività per il feed personalizzato
    def followed_posts(self):
        return Activity.query.join(
            followers, (followers.c.followed_id == Activity.user_id)
        ).filter(followers.c.follower_id == self.id)

    def __repr__(self):
        return f'<User {self.username}>'

class Route(db.Model):
    __tablename__ = 'Routes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.String(500), nullable=True)
    coordinates = db.Column(db.Text, nullable=False)
    duration = db.Column(db.Integer)  # in secondi
    distance = db.Column(db.Float)    # in km
    activity_type = db.Column(db.String(50), nullable=False, default='Corsa', index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    distance_km = db.Column(db.Float, nullable=True)
    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    featured_image = db.Column(db.String(120), nullable=True)
    
    # === NUOVI CAMPI PER PERCORSI CLASSICI ===
    is_active = db.Column(db.Boolean, default=True)  # ← NUOVA COLONNA
    is_classic = db.Column(db.Boolean, default=False, index=True)
    classic_city = db.Column(db.String(100), index=True)
    start_location = db.Column(db.String(200))
    end_location = db.Column(db.String(200))
    elevation_gain = db.Column(db.Integer)
    difficulty = db.Column(db.String(20))
    estimated_time = db.Column(db.String(50))
    landmarks = db.Column(db.Text)
    # === FINE NUOVI CAMPI ===


    challenges = db.relationship('Challenge', backref='route_info', lazy=True)
    activities = db.relationship('Activity', backref='route_activity', lazy=True)
    comments = db.relationship('Comment', backref='route_commented', lazy=True)
    records = db.relationship('RouteRecord', backref='recorded_route', lazy=True)

    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    featured_image = db.Column(db.String(120), nullable=True) # Nome del file immagine

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
    
    # === NUOVI CAMPI PER SFIDE AVANZATE ===
    challenge_type = db.Column(db.String(20), default='open', index=True)  # 'open' o 'closed'
    bet_type = db.Column(db.String(50), default='none')  # 'none', 'beer', 'dinner', 'coffee', 'custom'
    custom_bet = db.Column(db.String(100))  # Se bet_type = 'custom'
    bet_value = db.Column(db.String(100))  # "1 birra", "Una cena", etc.
    is_active = db.Column(db.Boolean, default=True, index=True)
    # === FINE NUOVI CAMPI ===

    activities = db.relationship('Activity', backref='challenge_info', lazy=True)
    invitations = db.relationship('ChallengeInvitation', backref='challenge', lazy=True)

    def __repr__(self):
        return f'<Challenge {self.name} on Route {self.route_id}>'
    
class ChallengeInvitation(db.Model):
    __tablename__ = 'ChallengeInvitations'
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('Challenges.id'), nullable=False, index=True)
    invited_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', index=True)  # 'pending', 'accepted', 'declined'
    invited_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    
    # Relazioni
    invited_user = db.relationship('User', backref='challenge_invitations')

    def __repr__(self):
        return f'<ChallengeInvitation {self.challenge_id} -> {self.invited_user_id}>'  

class Activity(db.Model):
    __tablename__ = 'Activities'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey('Routes.id'), nullable=False, index=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('Challenges.id'), nullable=True, index=True)
    activity_type = db.Column(db.String(50), nullable=False, default='Corsa', index=True)
    gps_track = db.Column(db.Text, nullable=False)
    duration = db.Column(db.Integer, nullable=False, index=True)
    avg_speed = db.Column(db.Float, nullable=False)
    distance = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    likes = db.relationship('ActivityLike', backref='activity', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Activity {self.id} by User {self.user_id} on Route {self.route_id}>'

class Comment(db.Model):
    __tablename__ = 'Comments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey('Routes.id'), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    likes = db.relationship('Like', backref='comment_liked', lazy=True)
    
    def __repr__(self):
        return f'<Comment {self.id} by {self.user_id} on Route {self.route_id}>'

class Like(db.Model):
    __tablename__ = 'Likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('Comments.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='_user_comment_uc'),)

    def __repr__(self):
        return f'<Like {self.id} by User {self.user_id} on Comment {self.comment_id}>'


class ActivityLike(db.Model):
    __tablename__ = 'activity_likes' # Nome tabella al plurale per coerenza
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('Activities.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Vincolo di unicità: un utente può mettere like a un'attività una sola volta
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

    activity = db.relationship('Activity', backref='record_set', lazy=True, uselist=False)
    
    def __repr__(self):
        return f'<RouteRecord Route:{self.route_id} User:{self.user_id} Duration:{self.duration}>'

class Badge(db.Model):
    __tablename__ = 'Badges'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    image_url = db.Column(db.String(120), nullable=False, default='badge_default.png')
    criteria = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Badge {self.name}>'

class UserBadge(db.Model):
    __tablename__ = 'UserBadges'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    badge_id = db.Column(db.Integer, db.ForeignKey('Badges.id'), nullable=False, index=True)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'badge_id', name='_user_badge_uc'),)
    
    badge_info = db.relationship('Badge', backref='recipients', lazy=True)

    def __repr__(self):
        return f'<UserBadge User:{self.user_id} Badge:{self.badge_id}>'
    

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

    # MODIFICA: Aggiungiamo lazy='dynamic' al backref 'notifications'
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref=db.backref('notifications', lazy='dynamic'))
    actor = db.relationship('User', foreign_keys=[actor_id])

    def __repr__(self):
        return f'<Notification {self.action} for User {self.recipient_id}>'
    

# Aggiungi in fondo a app/models.py
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

class Bet(db.Model):
    __tablename__ = 'bets'
    
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('Challenges.id'), nullable=False, index=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    loser_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    bet_type = db.Column(db.String(50), nullable=False)  # 'beer', 'coffee', 'dinner', 'custom'
    bet_value = db.Column(db.String(100), nullable=False)  # "1 birra", "Una cena", etc.
    status = db.Column(db.String(20), default='pending', index=True)  # 'pending', 'paid', 'cancelled'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
    
    # Relazioni
    challenge = db.relationship('Challenge', backref='bets')
    winner = db.relationship('User', foreign_keys=[winner_id], backref='bets_won')
    loser = db.relationship('User', foreign_keys=[loser_id], backref='bets_lost')
    
    def __repr__(self):
        return f'<Bet {self.bet_value} - Winner:{self.winner_id} Loser:{self.loser_id}>'