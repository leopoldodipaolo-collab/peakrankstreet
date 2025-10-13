# wsgi.py
import os
from app import create_app 

# Aggiungiamo esplicitamente la directory corrente al PYTHONPATH
# per assicurarci che 'app' sia trovato, dato che il worker si avvia con 'python worker.py'
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


app = create_app()