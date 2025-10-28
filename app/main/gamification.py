# File: app/main/gamification.py

from app.models import User, Notification
from app import db

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