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
        post_benvenuto_content = """<p>Ciao a tutti, e benvenuti nella community di PeakRankStreet!</p>
        <p>Siamo un team di appassionati di sport, proprio come voi. Per anni, abbiamo tracciato le nostre corse, le nostre uscite in bici, le nostre escursioni. Abbiamo usato le grandi piattaforme, collezionato chilometri e celebrato record. Ma sentivamo che mancava qualcosa di fondamentale: il gioco, il legame, il divertimento genuino che nasce quando lo sport diventa un'esperienza condivisa.</p>

        <p>È per questo che è nato PeakRankStreet. La nostra missione non è solo darvi un altro strumento per misurare le performance, ma offrirvi un campo da gioco digitale. Un luogo dove ogni strada può diventare un'arena, ogni salita una sfida e ogni caffè post-allenamento una posta in gioco.</p>

        <p><strong>Cosa rende PeakRankStreet speciale?</strong><br>
        Abbiamo costruito questa piattaforma attorno a tre idee fondamentali: Esplorazione, Competizione Amichevole e Community.</p>

        <p>🗺️ <strong>Scopri e Crea Percorsi Leggendari:</strong><br>
        La nostra mappa non è solo un elenco di strade. È una tela che dipingiamo insieme. Puoi esplorare i "Percorsi Classici" già approvati, ma il vero potere è nelle tue mani: conosci un giro fantastico che tutti nella tua zona dovrebbero provare? Mappalo, descrivilo e proponilo come "Percorso Classico" per la tua città! Il nostro team lo revisionerà e, se approvato, diventerà un punto di riferimento per l'intera community locale.</p>

        <p>🏆 <strong>Lancia Sfide... con un Pizzico di Sale!</strong><br>
        Questa è l'anima di PeakRankStreet. Non limitarti a battere il tuo record personale. Sfida direttamente un amico, un rivale o un compagno di squadra. E per rendere le cose interessanti, usa la nostra funzione Scommesse: mettete in palio un caffè, una birra o una pizza. Perché la gloria è importante, ma una scommessa vinta ha un sapore speciale. 🍺☕</p>

        <p>🤝 <strong>Unisciti alla Tua Tribù:</strong><br>
        Lo sport è più bello in gruppo. Crea o unisciti a Gruppi basati sui tuoi interessi o sulla tua zona. Organizza l'uscita del sabato mattina, condividi consigli, lancia sfide interne e trasforma la passione individuale in un'avventura di squadra.</p>

        <p><strong>Il Tuo Viaggio Inizia Ora: 4 Semplici Passi</strong><br>
        1. Personalizza il Tuo Profilo: Aggiungi una foto e una città. È il tuo biglietto da visita nella community.<br>
        2. Esplora la Mappa: Cerca la tua zona e scopri se ci sono già percorsi creati da altri atleti.<br>
        3. Registra (o Carica) la Tua Prima Attività: Fai il tuo ingresso in campo. Ogni attività è un pezzo della tua storia sportiva.<br>
        4. Interagisci! Lascia un commento su un percorso, metti un "like" all'attività di un amico, o lancia la tua prima, audace sfida.</p>

        <p>PeakRankStreet è una piattaforma costruita per gli sportivi, con gli sportivi. Ogni vostro feedback è cruciale per renderla sempre migliore. Questo è solo l'inizio del viaggio, e siamo entusiasti di avervi a bordo.</p>

        <p>Ci vediamo sui percorsi,<br>
        Il Team di PeakRankStreet</p>
        """

        # Controlla se il post di benvenuto esiste GIÀ CONTROLLANDO IL CONTENUTO
        if not Post.query.filter_by(content=post_benvenuto_content).first():
            annuncio = Post(
                user_id=admin_user.id,
                content=post_benvenuto_content,
                image_url='LogoPeakRankStreetSS.png',
                post_category='admin_announcement' # Manteniamo la categoria per coerenza
            )
            db.session.add(annuncio)
            print("-> Creato post di benvenuto.")
        else:
            print("-> Post di benvenuto già esistente. Saltato.")

        #post_consiglio_content = "💡 Consiglio della settimana: non dimenticate l'idratazione! Bere piccole quantità d'acqua frequentemente è meglio che bere molto tutto in una volta."

        #if not Post.query.filter_by(content=post_consiglio_content).first():
        #    consiglio = Post(
        #        user_id=admin_user.id,
        #        content=post_consiglio_content,
        #        post_category='weekly_tip' # Manteniamo la categoria
        #    )
        #    db.session.add(consiglio)
        #    print("-> Creato il primo consiglio della settimana.")
        #else:
        #    print("-> Consiglio della settimana già esistente. Saltato.")

        # --- FINE BLOCCO MODIFICATO ---

        # 3. Salva tutto
        db.session.commit()
        print("✅ Seeding completato!")