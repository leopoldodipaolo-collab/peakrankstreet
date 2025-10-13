# worker.py (ora nella radice del progetto)
import os
import time
# Se esegui dalla radice, Python deve sapere dove trovare la cartella 'app'
# Solitamente basta che la cartella 'app' sia nella stessa directory
# ma per sicurezza, o se ci fossero problemi, si potrebbe modificare l'import:
# from app.app import create_app, scheduler # Se il tuo __init__.py fosse app/app.py
from app import create_app, scheduler # <--- Questa dovrebbe funzionare se 'app' è una cartella Python Module
from app.models import close_expired_challenges 

print("Worker: Avvio del servizio worker...")

# Aggiungiamo esplicitamente la directory corrente al PYTHONPATH
# per assicurarci che 'app' sia trovato, dato che il worker si avvia con 'python worker.py'
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


app = create_app() # Crea l'app per inizializzare lo scheduler

# Esegui la logica di chiusura all'avvio del worker
with app.app_context():
    print("Worker: Esecuzione di close_expired_challenges all'avvio del worker.")
    try:
        close_expired_challenges()
    except Exception as e:
        print(f"Worker: Errore durante close_expired_challenges all'avvio: {e}")

print("Worker: Scheduler in background attivo. Il worker rimarrà attivo.")
while True:
    time.sleep(3600) # Mantieni il processo attivo