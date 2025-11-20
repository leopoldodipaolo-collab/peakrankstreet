from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from app.models import User, Badge, UserBadge # Assicurati che questi modelli siano importati
from app import db # Assicurati che db sia importato
# Importaaward_badge_if_earned se si trova in un altro file (es. utils.py)
# from app.utils import award_badge_if_earned 
# Se award_badge_if_earned è nello stesso file, lasciala qui.

# --- FUNZIONE HELPER PER I BADGE ---
# NOTA: È FORTEMENTE RACCOMANDATO spostare questa funzione in app/utils.py o simile.
def award_badge_if_earned(user, badge_name):
    # Stampa di debug iniziale
    print(f"--- DEBUG AWARD: Tentativo per utente {user.username} con badge '{badge_name}' ---")
    
    badge = Badge.query.filter_by(name=badge_name).first()
    print(f"--- DEBUG AWARD: Badge trovato nel DB: {badge} ---")

    if not badge:
        # Qui definiamo SOLO i badge che NON sono ancora nel DB.
        # Idealmente, tutti i badge dovrebbero essere nel DB.
        if badge_name == "Nuovo Atleta":
            badge = Badge(name="Nuovo Atleta", description="Registrazione avvenuta con successo!", image_url="badge_new_athlete.png")
            print(f"--- DEBUG AWARD: Badge '{badge_name}' NON trovato, creato oggetto Badge. ---")
            # Aggiungi e committa immediatamente questo nuovo badge se viene creato qui
            db.session.add(badge)
            db.session.commit() 
            print(f"--- DEBUG AWARD: Badge '{badge_name}' aggiunto e committato nel DB. ---")
        elif badge_name == "Membro Fondatore": # AGGIUNTO QUI
            badge = Badge(name="Membro Fondatore", description="Sei tra i primi 50 utenti registrati!", image_url="badge_founding_member.png")
            print(f"--- DEBUG AWARD: Badge '{badge_name}' NON trovato, creato oggetto Badge. ---")
            db.session.add(badge)
            db.session.commit()
            print(f"--- DEBUG AWARD: Badge '{badge_name}' aggiunto e committato nel DB. ---")
        # Aggiungi qui altri badge che potrebbero dover essere creati al volo se non sono nel DB
        # Es: elif badge_name == "Primo Percorso": ...
        else:
            # Se il badge non è stato trovato e non è stato definito qui per la creazione,
            # significa che non esiste e non sappiamo come crearlo.
            print(f"--- DEBUG AWARD: Badge '{badge_name}' non trovato e non definito per la creazione. ---")
            return False # Non possiamo procedere senza un badge valido
    
    # Se il badge è stato trovato o appena creato
    if badge:
        # Controlla se l'utente ha GIA' QUESTO BADGE
        user_has_badge = UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first()
        print(f"--- DEBUG AWARD: Utente {user.username} ha già il badge '{badge_name}'? {bool(user_has_badge)} ---")

        if not user_has_badge: # Se l'utente NON ha ancora questo badge
            print(f"--- DEBUG AWARD: Assegnazione badge '{badge_name}' all'utente {user.username}. ---")
            user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(user_badge)
            
            # Qui NON facciamo commit subito, aggiungiamo tutto alla sessione e committiamo alla fine della route principale o qui se è un'azione atomica.
            # Se l'assegnazione del badge è un'operazione atomica, possiamo committare qui.
            # Dal tuo codice originale, sembrava che assegnazione badge + post + prestige fossero atomici.
            
            # Aggiungiamo il post (se necessario, come nel tuo codice originale)
            # Assicurati che il modello Post e la funzione add_prestige siano importati e disponibili
            try:
                badge_post_content = f"🏅 Badge Sbloccato! {user.username} ha ottenuto il badge: '{badge.name}'!"
                badge_post = Post( # Assumendo che il modello Post esista
                    user_id=user.id,
                    content=badge_post_content,
                    post_category='system_badge', # Assicurati che questa categoria esista
                    post_type='text'
                )
                db.session.add(badge_post)
                
                # Aggiungi prestigio (se presente e funzionante)
                add_prestige(user, 'get_badge') # Assicurati che add_prestige sia definita e importata

            except NameError:
                print("--- DEBUG AWARD: Funzione add_prestige o modello Post non trovati/importati. ---")
            except Exception as e:
                print(f"--- DEBUG AWARD: Errore durante l'aggiunta di post/prestigio: {e} ---")
                # Non vogliamo bloccare l'assegnazione del badge per un errore nel post/prestigio, quindi non facciamo rollback qui se il badge è l'obiettivo primario.
            
            try:
                db.session.commit() # Committa l'assegnazione del badge, il post e il prestigio
                flash(f'Congratulazioni! Hai ottenuto il badge: "{badge.name}"!', 'info')
                print(f"--- DEBUG AWARD: Badge '{badge.name}' assegnato, committato con successo. ---")
                return True
            except Exception as e:
                db.session.rollback() # Annulla le modifiche se il commit fallisce
                print(f"--- DEBUG AWARD: Errore durante il commit dell'assegnazione badge: {e} ---")
                return False # Fallimento
        else:
            print(f"--- DEBUG AWARD: Utente {user.username} ha già il badge '{badge_name}'. Nessuna nuova assegnazione. ---")
            return False # L'utente ha già il badge
    else:
        print(f"--- DEBUG AWARD: Badge '{badge_name}' non valido dopo la ricerca/creazione. ---")
        return False # Badge non trovato o non creato

# --- DEFINIZIONE CONSTANTE ---
# È meglio metterla in un file di configurazione o costanti globali
# Esempio: MAX_FOUNDERS = current_app.config.get('MAX_FOUNDERS', 50)
MAX_FOUNDERS = 50 

# --- BLUEPRINT AUTH ---
auth = Blueprint('auth', __name__)

# --- ROUTE DI REGISTRAZIONE ---
@auth.route('/register', methods=['GET', 'POST'])
def register():
    # Se l'utente è già autenticato, reindirizzalo alla home page
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        city = request.form.get('city') # Recupera la città dal form
        accept_privacy = request.form.get('accept_privacy')

        # Controllo per l'accettazione della privacy policy
        if not accept_privacy:
            flash('Devi accettare la Privacy Policy e la Cookie Policy per registrarti.', 'danger')
            return redirect(url_for('auth.register'))

        # --- Validazioni per username, email, password ---
        # Implementa qui le tue validazioni specifiche (es. lunghezza password, formato email, ecc.)
        # Se una validazione fallisce:
        # flash('Messaggio di errore', 'danger')
        # return redirect(url_for('auth.register'))

        # Crea il nuovo utente
        new_user = User(username=username, email=email, city=city) # La città viene passata qui
        new_user.set_password(password)
        
        db.session.add(new_user)
        
        try:
            # --- COMMIT IMMEDIATO PER OTTENERE L'ID ---
            db.session.commit() 
            print(f"--- DEBUG REGISTER COMMIT: Utente {new_user.username} salvato con ID: {new_user.id}. ---")

            # --- LOGICA PER IL BADGE "Membro Fondatore" ---
            print(f"--- DEBUG REGISTER BADGE CHECK: ID Utente: {new_user.id}, MAX_FOUNDERS: {MAX_FOUNDERS}. ---")
            if new_user.id <= MAX_FOUNDERS: 
                print(f"--- DEBUG REGISTER BADGE CHECK: Condizione ID <= MAX_FOUNDERS soddisfatta. Tentativo di assegnare 'Membro Fondatore'. ---")
                award_badge_if_earned(new_user, "Membro Fondatore") # Chiamata alla funzione helper
                print(f"--- DEBUG REGISTER BADGE CHECK: Chiamata a award_badge_if_earned per 'Membro Fondatore' completata. ---")
            else:
                print(f"--- DEBUG REGISTER BADGE CHECK: Condizione ID <= MAX_FOUNDERS NON soddisfatta. Nessuna assegnazione per 'Membro Fondatore'. ---")

            # --- Badge "Nuovo Atleta" (già presente) ---
            print(f"--- DEBUG REGISTER BADGE CHECK: Tentativo di assegnare 'Nuovo Atleta'. ---")
            award_badge_if_earned(new_user, "Nuovo Atleta") # Chiamata alla funzione helper
            print(f"--- DEBUG REGISTER BADGE CHECK: Chiamata a award_badge_if_earned per 'Nuovo Atleta' completata. ---")
            
            flash('Registrazione avvenuta con successo! Effettua il login.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback() # Annulla le modifiche in caso di errore
            print(f"--- DEBUG REGISTER ERROR: Si è verificato un errore durante la registrazione: {e} ---")
            flash(f'Si è verificato un errore durante la registrazione: {e}', 'danger')
            # Aggiungi un log più dettagliato se necessario: current_app.logger.error(f"Errore registrazione: {e}")
            return redirect(url_for('auth.register'))
        
    # --- LOGICA PER LA RICHIESTA GET (Mostra il form di registrazione) ---
    # Passa la variabile 'city_value' per precompilare il campo se viene inviato un POST con errori
    return render_template('register.html', is_homepage=False, city_value=request.form.get('city') if request.method == 'POST' else None)

# --- ROUTE DI LOGIN, LOGOUT, ecc. ---
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            flash('Login avvenuto con successo!', 'success')
            return redirect(next_page or url_for('main.index'))
        else:
            flash('Login fallito. Controlla username e password.', 'danger')
    return render_template('login.html', is_homepage=False)

@auth.route('/logout')
@login_required # Richiede che l'utente sia loggato per poter fare logout
def logout():
    logout_user()
    flash('Sei stato disconnesso.', 'info')
    return redirect(url_for('main.index'))