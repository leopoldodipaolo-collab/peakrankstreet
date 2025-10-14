import click
from app import create_app, db
from app.models import User, Route, Activity, ActivityLike

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

@app.cli.command("init-db")
def init_db_command():
    """Cancella i dati esistenti, ricrea le tabelle e crea un utente admin."""
    click.echo("Cancellazione del database esistente...")
    db.drop_all()
    click.echo("Creazione di tutte le tabelle del database...")
    db.create_all()
    click.echo("Tabelle create.")
    
    admin_username = 'admin'
    admin_email = 'admin@example.com'
    admin_password = 'admin123'
    
    if User.query.filter_by(username=admin_username).first() is None:
        click.echo("Creazione dell'utente amministratore di default...")
        admin_user = User(
            username=admin_username,
            email=admin_email,
            is_admin=True
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        db.session.commit()
        click.echo(f"Utente admin '{admin_username}' creato con successo.")
    else:
        click.echo(f"L'utente admin '{admin_username}' esiste già.")
    
    click.echo("Database inizializzato.")

@app.cli.command("update-route-field")
@click.argument("route_id", type=int)
@click.argument("field")
@click.argument("value")
def update_route_field(route_id, field, value):
    """Aggiorna un campo specifico di una rotta."""
    from app.models import Route
    route = Route.query.get(route_id)
    if not route:
        click.echo(f"❌ Route con id={route_id} non trovata.")
        return
    if not hasattr(route, field):
        click.echo(f"❌ Campo '{field}' non esiste sul modello Route.")
        return
    
    column_type = type(getattr(Route, field).type)
    if column_type.__name__ == "Boolean":
        value = value.lower() in ("1", "true", "yes")
    elif column_type.__name__ in ("Integer", "Float"):
        try:
            value = int(value) if column_type.__name__ == "Integer" else float(value)
        except ValueError:
            click.echo(f"❌ Valore '{value}' non valido per il campo {field}.")
            return
    
    setattr(route, field, value)
    db.session.commit()
    click.echo(f"✅ Campo '{field}' della Route id={route_id} aggiornato a '{value}'.")

@app.cli.command("update-route-fields")
@click.argument("route_id", type=int)
@click.argument("json_fields")
def update_route_fields(route_id, json_fields):
    """Aggiorna più campi di una rotta contemporaneamente tramite JSON."""
    from app.models import Route
    import json
    
    route = Route.query.get(route_id)
    if not route:
        click.echo(f"❌ Route con id={route_id} non trovata.")
        return
    
    try:
        fields_dict = json.loads(json_fields)
    except json.JSONDecodeError:
        click.echo("❌ JSON non valido.")
        return
    
    updated_fields = []
    for field, value in fields_dict.items():
        if not hasattr(route, field):
            click.echo(f"⚠️  Campo '{field}' non esiste, saltato.")
            continue
        
        column_type = type(getattr(Route, field).type)
        try:
            if column_type.__name__ == "Boolean":
                value = value.lower() in ("1", "true", "yes") if isinstance(value, str) else bool(value)
            elif column_type.__name__ == "Integer":
                value = int(value)
            elif column_type.__name__ == "Float":
                value = float(value)
        except (ValueError, TypeError) as e:
            click.echo(f"⚠️  Valore '{value}' non valido per {field}, saltato.")
            continue
        
        setattr(route, field, value)
        updated_fields.append(f"{field}='{value}'")
    
    if updated_fields:
        db.session.commit()
        click.echo(f"✅ Route id={route_id} aggiornata: {', '.join(updated_fields)}")
    else:
        click.echo("ℹ️  Nessun campo aggiornato.")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)