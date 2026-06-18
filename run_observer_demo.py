"""
Baasket — Observer Pattern Live Demo Runner (GoF Compliant)
Subject.SetState() → Subject.Notify() → Observer.Update() → Subject.GetState()
"""
import os
import sys
from datetime import datetime

from main import create_app
app = create_app()

output_lines = []

def log(msg):
    print(msg)
    output_lines.append(msg)

with app.app_context():
    from extensions import db
    from models import Notification, User
    from notifications import (
        NotificationSubject,
        BuyerNotificationObserver,
        SellerNotificationObserver,
    )

    log("=" * 60)
    log("  Baasket — Observer Pattern Demo (GoF Compliant)")
    log(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    users = User.query.all()
    if len(users) < 2:
        log("\n[ERROR] Need at least 2 users in the database.")
        sys.exit(1)

    buyer  = users[0]
    seller = users[1]
    log(f"\n[INFO] Using buyer  → id={buyer.id}  username={buyer.username}")
    log(f"[INFO] Using seller → id={seller.id}  username={seller.username}")

    # ── STEP 1: Build Subject and Attach Observers ─────────────────────
    log("\n[STEP 1] Build NotificationSubject + Attach observers")
    subject = NotificationSubject()
    subject.attach(BuyerNotificationObserver())
    log("  [Attach] BuyerNotificationObserver registered.")
    subject.attach(SellerNotificationObserver())
    log("  [Attach] SellerNotificationObserver registered.")

    before = Notification.query.count()
    log(f"\n[INFO] Notifications in database BEFORE demo: {before}")

    # ── STEP 2: SetState → Notify → Update → GetState ─────────────────
    log("\n[STEP 2] Subject.SetState('offer_accepted') → Notify() → Observer.Update() → GetState()")
    subject.set_state("offer_accepted", {
        "buyer_id":      buyer.id,
        "seller_id":     seller.id,
        "amount":        "RM140.00",
        "listing_title": "Smart Watch Series",
        "offer_id":      1,
    })
    db.session.commit()
    log("  → db.session.commit() — notifications saved to baasket.db")

    log("\n[STEP 3] Subject.SetState('offer_declined') → Notify() → Observer.Update() → GetState()")
    subject.set_state("offer_declined", {
        "buyer_id":      buyer.id,
        "amount":        "RM90.00",
        "listing_title": "Vintage Camera",
    })
    db.session.commit()
    log("  → db.session.commit() — notification saved to baasket.db")

    log("\n[STEP 4] Subject.SetState('purchase') → Notify() → Observer.Update() → GetState()")
    subject.set_state("purchase", {
        "seller_id": seller.id,
        "titles":    ["Smart Watch Series"],
    })
    db.session.commit()
    log("  → db.session.commit() — notification saved to baasket.db")

    # ── STEP 3: Verify ─────────────────────────────────────────────────
    after = Notification.query.count()
    log(f"\n[INFO] Notifications in database AFTER demo: {after}")
    log(f"[INFO] New notifications created: {after - before}")

    log("\n[RESULT] New notifications written to baasket.db:")
    new_notifs = Notification.query.order_by(Notification.id.desc()).limit(after - before).all()
    for n in reversed(new_notifs):
        log(f"  id={n.id} | user_id={n.user_id} | category={n.category}")
        log(f"         message: {n.message}")

    log("\n" + "=" * 60)
    log("  GoF Observer pattern executed with real database.")
    log("  Flow: SetState() → Notify() → Update() → GetState()")
    log("=" * 60)

output_path = os.path.join(os.path.dirname(__file__), "observer_output.txt")
with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print(f"\n[SAVED] Output written to: observer_output.txt")
