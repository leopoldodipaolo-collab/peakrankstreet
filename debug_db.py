import os
import sqlalchemy
from dotenv import load_dotenv # <-- AGGIUNGI QUESTO IMPORT

# Trova il percorso del file .env e caricalo
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env')) # <-- AGGIUNGI QUESTA RIGA

# --- CONFIGURAZIONE ---
# Inserisci qui gli username e il nome del gruppo che vuoi controllare.
# Assicurati che siano scritti ESATTAMENTE come nel database.
USER_TO_CHECK = 'Leopoldo'
GROUP_TO_CHECK = 'L\'Aquila gruppo test'
# --------------------

def run_debug_queries():
    """
    Esegue una serie di query di debug sul database per verificare le relazioni
    tra utenti e gruppi.
    """
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ ERRORE: Variabile d'ambiente DATABASE_URL non trovata.")
        print("Assicurati di lanciare lo script dallo stesso terminale in cui avvii l'app Flask.")
        return

    # Aggiusta l'URL per SQLAlchemy se inizia con 'postgres://'
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        
    print(f"✅ Connessione al database in corso...")

    try:
        engine = sqlalchemy.create_engine(database_url)
        with engine.connect() as connection:
            print("✅ Connessione al database riuscita!\n")

            # --- Query 1: Trova l'utente ---
            print(f"--- 1. Cerco l'utente '{USER_TO_CHECK}' ---")
            user_query = sqlalchemy.text('SELECT id, username FROM "user" WHERE username = :username')
            user_result = connection.execute(user_query, {'username': USER_TO_CHECK}).fetchone()
            
            if not user_result:
                print(f"❌ RISULTATO: Utente '{USER_TO_CHECK}' NON trovato nel database. Controlla il nome esatto.")
                return
            
            user_id, user_name = user_result
            print(f"✔️  Trovato: ID = {user_id}, Username = {user_name}\n")

            # --- Query 2: Trova il gruppo ---
            print(f"--- 2. Cerco il gruppo '{GROUP_TO_CHECK}' ---")
            group_query = sqlalchemy.text("SELECT id, name FROM groups WHERE name = :groupname")
            group_result = connection.execute(group_query, {'groupname': GROUP_TO_CHECK}).fetchone()

            if not group_result:
                print(f"❌ RISULTATO: Gruppo '{GROUP_TO_CHECK}' NON trovato nel database. Controlla il nome esatto.")
                return
                
            group_id, group_name = group_result
            print(f"✔️  Trovato: ID = {group_id}, Nome = {group_name}\n")

            # --- Query 3: Controlla l'associazione ---
            print(f"--- 3. Verifico l'iscrizione nella tabella 'group_members' ---")
            print(f"   (Controllo se l'utente ID {user_id} è membro del gruppo ID {group_id})")
            membership_query = sqlalchemy.text("SELECT * FROM group_members WHERE user_id = :user_id AND group_id = :group_id")
            membership_result = connection.execute(membership_query, {'user_id': user_id, 'group_id': group_id}).fetchone()

            if membership_result:
                print("\n✔️  RISULTATO FINALE: L'iscrizione ESISTE nel database.")
                print("   Il problema è quasi certamente nel codice Python (modelli o query).")
            else:
                print("\n❌ RISULTATO FINALE: L'iscrizione NON ESISTE nel database.")
                print("   L'utente non è membro del gruppo. Il problema è nella logica di iscrizione (rotta join_group) o il test non è stato completato.")

    except Exception as e:
        print(f"\n❌ Si è verificato un errore durante l'esecuzione delle query: {e}")

if __name__ == "__main__":
    run_debug_queries()