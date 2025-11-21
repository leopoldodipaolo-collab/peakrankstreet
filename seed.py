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
        # 2. Controlla se i post esistono già per evitare duplicati
        if not Post.query.filter_by(post_category='admin_announcement').first():
            annuncio = Post(
                user_id=admin_user.id,
                content="🚀 Benvenuti su PeakRankStreet! La piattaforma è ufficialmente online. Iniziate a esplorare...!",
                post_category='admin_announcement'
            )
            db.session.add(annuncio)
            print("-> Creato post di benvenuto.")

        if not Post.query.filter_by(post_category='weekly_tip').first():
            consiglio = Post(
                user_id=admin_user.id,
                content="💡 Consiglio della settimana: non dimenticate l'idratazione! Bere piccole quantità d'acqua frequentemente è meglio che bere molto tutto in una volta.",
                post_category='weekly_tip'
            )
            db.session.add(consiglio)
            print("-> Creato il primo consiglio della settimana.")

        # 3. Salva tutto
        db.session.commit()
        print("✅ Seeding completato!")
