# app.py
# Questo è il nuovo entry point per Gunicorn.
# Importa la tua factory function e crea l'app qui.

from app import create_app # Importa la tua factory function dalla cartella 'app'

app = create_app() # Chiama la factory function per ottenere l'oggetto Flask