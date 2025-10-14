# run.py

import click
from app import create_app, db
from app.models import User, Route, Activity,ActivityLike


app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Route': Route, 'Activity': Activity}

@app.cli.command("promote-user")
@click.argument("username")
def promote_user(username):
    """Promuove un utente a ruolo di amministratore."""
    user = User.query.filter_by(username=username).first()
    if user is None:
        print(f"Errore: Utente '{username}' non trovato.")
        return
    user.is_admin = True
    db.session.commit()
    print(f"Successo! L'utente '{username}' è ora un amministratore.")

# =======================================================
# NUOVO COMANDO: INIT-DB
# =======================================================
@app.cli.command("init-db")
def init_db_command():
    """Cancella i dati esistenti, ricrea le tabelle e crea un utente admin."""
    click.echo("Cancellazione del database esistente...")
    db.drop_all()
    click.echo("Creazione di tutte le tabelle del database...")
    db.create_all()
    click.echo("Tabelle create.")

    # Crea l'utente admin
    admin_username = 'admin'
    admin_email = 'admin@example.com'
    admin_password = 'admin123'

    # Controlla se l'utente admin esiste già
    if User.query.filter_by(username=admin_username).first() is None:
        click.echo("Creazione dell'utente amministratore di default...")
        admin_user = User(
            username=admin_username,
            email=admin_email,
            is_admin=True  # Imposta subito il flag admin
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        db.session.commit()
        click.echo(f"Utente admin '{admin_username}' creato con successo.")
    else:
        click.echo(f"L'utente admin '{admin_username}' esiste già.")

    click.echo("Database inizializzato.")
# =======================================================


if __name__ == '__main__':
    # Rimuoviamo db.create_all() da qui per gestire tutto tramite il comando init-db
    app.run(host='0.0.0.0', port=5000, debug=True)