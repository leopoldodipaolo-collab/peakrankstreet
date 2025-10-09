from app import create_app, db
from app.models import Bet

# Crea il contesto dell'app
app = create_app()

with app.app_context():
    try:
        # Prova a contare le scommesse
        bet_count = Bet.query.count()
        print(f"✅ Tabella Bets esiste già: {bet_count} scommesse")
    except Exception as e:
        print(f"❌ Tabella Bets non esiste: {e}")
        print("Creo la tabella...")
        db.create_all()
        print("✅ Tabella Bets creata!")