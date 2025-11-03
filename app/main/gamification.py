# File: app/main/gamification.py
from app import db
import random
from datetime import datetime
from app.models import User, Notification, Post, Bet, Challenge, Activity, ChallengeInvitation, Route
# Definiamo qui la nostra gerarchia e le soglie di prestigio
TITLES = [
    (0, 'Popolano'),
    (100, 'Vassallo'),
    (300, 'Cavaliere'), # O 'Dama' se vuoi gestire il genere
    (750, 'Barone'),   # O 'Baronessa'
    (1500, 'Conte'),
    (3000, 'Duca'),
    (7500, 'Principe'),
    (15000, 'Re')
]

# Definiamo i punti per ogni azione
PRESTIGE_ACTIONS = {
    'new_activity': 20,
    'new_post': 10,
    'new_comment': 2,
    'receive_like': 1,
    'new_route': 15,
    'win_challenge': 50,
    'get_badge': 30,
    'new_record': 100,
}

def add_prestige(user, action_key):
    """
    Aggiunge prestigio a un utente per un'azione specifica e gestisce il level up.
    """
    if action_key not in PRESTIGE_ACTIONS:
        return

    points_to_add = PRESTIGE_ACTIONS[action_key]
    user.prestige += points_to_add
    
    # Controlla se c'è un "level up" (promozione a un nuovo titolo)
    current_title = user.title
    new_title = current_title
    
    # Scorre la gerarchia per trovare il titolo più alto raggiunto
    for threshold, title_name in TITLES:
        if user.prestige >= threshold:
            new_title = title_name
    
    # Se il titolo è cambiato, aggiorniamolo e creiamo una notifica
    if new_title != current_title:
        user.title = new_title
        
        # Crea una notifica per il "level up"
        notification = Notification(
            recipient_id=user.id,
            actor_id=1, # ID di un utente "sistema" o admin
            action='title_up',
            object_id=user.id, # L'oggetto è l'utente stesso
            object_type='user' 
        )
        db.session.add(notification)
        # Nota: il db.session.commit() verrà fatto nella rotta principale
        
    db.session.add(user)
    return points_to_add


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
    
# Se questa funzione è in models.py, assicurati di avere:
# from app.main.gamification import create_bet_notification

def process_challenge_bet(challenge):
    """Processa la scommessa di una sfida terminata"""
    try:
        winner_activity = Activity.query.filter_by(
            challenge_id=challenge.id
        ).order_by(Activity.duration.asc()).first()
        
        if not winner_activity:
            print(f"-> Nessuna attività per la sfida {challenge.id}, scommessa saltata.")
            return
        
        # --- CORREZIONE QUI ---
        winner = winner_activity.user_activity
        print(f"-> Vincitore sfida {challenge.id}: {winner.username}")
        
        if challenge.challenge_type == 'closed':
            participants = Activity.query.filter_by(challenge_id=challenge.id).all()
            for activity in participants:
                if activity.user_id != winner.id:
                    # --- E CORREZIONE QUI ---
                    create_bet_notification(challenge, winner, activity.user_activity)
        
        elif challenge.challenge_type == 'open' and challenge.created_by != winner.id:
            creator = User.query.get(challenge.created_by)
            if creator:
                create_bet_notification(challenge, winner, creator)
            
        print(f"-> Scommessa processata per '{challenge.name}'")
        
    except Exception as e:
        import traceback
        print(f"❌ Errore nel processare scommessa per sfida {challenge.id}: {e}\n{traceback.format_exc()}")

def create_bet_notification(challenge, winner, loser):
    """
    Crea il record Bet, le notifiche E i post automatici per il feed.
    """
    try:
        # 1. Crea il record della scommessa
        new_bet = Bet(
            challenge_id=challenge.id,
            winner_id=winner.id,
            loser_id=loser.id,
            bet_type=challenge.bet_type,
            bet_value=challenge.bet_value,
            status='pending'
        )
        db.session.add(new_bet)
        
        # --- CORREZIONE: COMPILA LA CREAZIONE DELLE NOTIFICHE ---
        
        # 2. Crea la notifica per il VINCITORE
        winner_notification = Notification(
            recipient_id=winner.id,
            actor_id=loser.id,
            action='bet_won',
            object_id=challenge.id,
            object_type='challenge' # L'oggetto della notifica è la sfida
        )
        db.session.add(winner_notification)
        
        # 3. Crea la notifica per il PERDENTE
        loser_notification = Notification(
            recipient_id=loser.id,
            actor_id=winner.id,
            action='bet_lost',
            object_id=challenge.id,
            object_type='challenge'
        )
        db.session.add(loser_notification)
        
        # --- FINE CORREZIONE ---

        # 4. Crea i post automatici (il tuo codice per questo è corretto)
        win_phrases = [f"🍻 Vittoria! {winner.username} ha vinto {challenge.bet_value} da {loser.username}."]
        winner_post = Post(
            user_id=winner.id,
            content=random.choice(win_phrases) + f" nella sfida '{challenge.name}'.",
            post_category='system_bet_win'
        )
        db.session.add(winner_post)

        loss_phrases = [f"💸 Debito d'onore! {loser.username} ha perso {challenge.bet_value} contro {winner.username}."]
        loser_post_content = random.choice(loss_phrases) + " E il debito è ancora in sospeso! ⏳"
        loser_post = Post(
            user_id=loser.id,
            content=loser_post_content,
            post_category='system_bet_loss'
        )
        db.session.add(loser_post)
        
        db.session.flush() 
        new_bet.related_post_id = loser_post.id
        
        print(f"✅ LOGICA SCOMMESSA: Post e Notifiche preparati per il commit.")
        
    except Exception as e:
        import traceback
        print(f"❌ ERRORE in create_bet_notification: {e}\n{traceback.format_exc()}")