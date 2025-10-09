# app/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
# CORREZIONE: Importazioni consolidate in una sola riga
from flask_login import LoginManager, current_user 
from datetime import datetime

# 1. Inizializza le estensioni
db = SQLAlchemy()
login_manager = LoginManager()

# 2. Configura il LoginManager
login_manager.login_view = 'auth.login'
login_manager.login_message = "Per favore, effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"


def create_app():
    """
    Factory function per creare l'istanza dell'app Flask.
    """
    # 3. Crea l'istanza
    app = Flask(__name__)

    # 4. Carica la configurazione
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-in-production')
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'site.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/profile_pics')

    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    app.jinja_env.add_extension('jinja2.ext.do')

    # 5. Collega le estensioni all'app
    db.init_app(app)
    login_manager.init_app(app)

    # 6. Definisci il user_loader e importa i modelli
    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # 7. Definisci i processori di contesto globale
    @app.context_processor
    def inject_global_variables():
        return dict(
            now=datetime.utcnow(),
            user_city=current_user.city if current_user.is_authenticated else None
        )

    # 8. Importa e registra i Blueprints
    from app.main.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from app.auth.routes import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from app.api.routes import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    return app