# wsgi.py
# Questo file serve a Gunicorn per avviare la tua applicazione Flask.
import os
from app import create_app # Importa la tua factory function create_app dal modulo 'app'

# Opzionale: se hai bisogno di caricare .env per Render o altri contesti,
# puoi farlo qui, ma Render gestisce le ENV Vars direttamente.
# from dotenv import load_dotenv
# if os.path.exists('.env'):
#     load_dotenv()

# Chiama la tua factory function per ottenere l'oggetto applicazione Flask.
app = create_app()