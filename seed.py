from app import create_app, db
from app.models import User, Post

app = create_app()

with app.app_context():
    print("Inizio il seeding del database...")

    # 1. Trova l'utente admin
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        print("Errore: Utente 'admin' non trovato. Impossibile creare i post.")
    else:
        # --- BLOCCO MODIFICATO ---
        
        # Definiamo i post che vogliamo creare
        post_benvenuto_content = "🚀 Benvenuti su PeakRankStreet! La piattaforma è ufficialmente online. Iniziate a esplorare...!"
        post_consiglio_content = "💡 Consiglio della settimana: non dimenticate l'idratazione! Bere piccole quantità d'acqua frequentemente è meglio che bere molto tutto in una volta."

        # Controlla se il post di benvenuto esiste GIÀ CONTROLLANDO IL CONTENUTO
        if not Post.query.filter_by(content=post_benvenuto_content).first():
            annuncio = Post(
                user_id=admin_user.id,
                content=post_benvenuto_content,
                post_category='admin_announcement' # Manteniamo la categoria per coerenza
            )
            db.session.add(annuncio)
            print("-> Creato post di benvenuto.")
        else:
            print("-> Post di benvenuto già esistente. Saltato.")

        # Controlla se il consiglio esiste GIÀ CONTROLLANDO IL CONTENUTO
        if not Post.query.filter_by(content=post_consiglio_content).first():
            consiglio = Post(
                user_id=admin_user.id,
                content=post_consiglio_content,
                post_category='weekly_tip' # Manteniamo la categoria
            )
            db.session.add(consiglio)
            print("-> Creato il primo consiglio della settimana.")
        else:
            print("-> Consiglio della settimana già esistente. Saltato.")

        # --- FINE BLOCCO MODIFICATO ---

        # 3. Salva tutto
        db.session.commit()
        print("✅ Seeding completato!")