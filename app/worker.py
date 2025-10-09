# worker.py
import os
import time
from app import create_app, scheduler # Importa create_app e scheduler
from app.models import close_expired_challenges # Importa la funzione dello scheduler

print("Worker: Avvio del servizio worker...")

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