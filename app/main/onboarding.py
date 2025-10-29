# File: app/main/onboarding.py
from app import db

# Definiamo i passi dell'onboarding in un unico posto
ONBOARDING_CHECKLIST = {
    'profile_complete': "Crea il tuo Stemma (Completa il profilo)",
    'followed_users': "Giura Fedeltà (Segui 3 utenti)",
    'joined_group': "Unisciti a una Gilda (Iscriviti a un gruppo)",
    'first_post': "Lascia il Segno (Pubblica il tuo primo post)"
}

def get_onboarding_status(user):
    """
    Restituisce lo stato di completamento dell'onboarding per un utente.
    Inizializza lo stato se non esiste.
    """
    if user.onboarding_steps is None:
        # Inizializza il dizionario con tutti i passi a False
        user.onboarding_steps = {step: False for step in ONBOARDING_CHECKLIST.keys()}
        db.session.commit()
    
    # Controlla se tutti i valori nel dizionario sono True
    is_complete = all(user.onboarding_steps.values())
    
    return user.onboarding_steps, is_complete

def complete_onboarding_step(user, step_name):
    """
    Segna un passo dell'onboarding come completato.
    """
    if user.onboarding_steps is None:
        # Assicura che lo status sia inizializzato
        get_onboarding_status(user)

    if step_name in user.onboarding_steps and not user.onboarding_steps[step_name]:
        # Crea una copia per forzare SQLAlchemy a rilevare la modifica del JSON
        steps = user.onboarding_steps.copy()
        steps[step_name] = True
        user.onboarding_steps = steps
        
        # Aggiungiamo un piccolo bonus di Prestigio per ogni passo completato!
        from .gamification import add_prestige
        add_prestige(user, 'onboarding_step') # Dovremo aggiungere questa nuova azione
        
        db.session.commit()
        return True # Ritorna True se il passo è stato appena completato
    return False