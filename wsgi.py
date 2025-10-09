# wsgi.py
# Questo file serve a Gunicorn per avviare la tua applicazione Flask.
import os
from app import create_app # Importa la tua factory function dalla cartella 'app'

# Chiama la tua factory function per ottenere l'oggetto applicazione Flask.
app = create_app() # L'oggetto applicazione Flask deve essere chiamato 'app'