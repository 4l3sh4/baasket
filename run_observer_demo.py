
"""

Baasket — Observer Pattern 

Boots Flask, uses real SQLite database, writes output to observer_output.txt

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

    log("  Baasket — Observer Pattern Demo (Live Database)")

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

    log("\n[STEP 1] Building NotificationSubject and attaching observers...")

    subject = NotificationSubject()

    subject.attach(BuyerNotificationObserver())

    log("  [attach] BuyerNotificationObserver registered.")

    subject.attach(SellerNotificationObserver())

    log("  [attach] SellerNotificationObserver registered.")

    before = Notification.query.count()

    log(f"\n[INFO] Notifications in database before demo: {before}")

    log("\n[STEP 2] Firing event: offer_accepted")

    subject.notify("offer_accepted", {

        "buyer_id":      buyer.id,

        "seller_id":     seller.id,

        "amount":        "RM140.00",

        "listing_title": "Smart Watch Series",

        "offer_id":      1,

    })

    db.session.commit()

    log("  → db.session.commit() — notifications saved to baasket.db")

    log("\n[STEP 3] Firing event: offer_declined")

    subject.notify("offer_declined", {

        "buyer_id":      buyer.id,

        "amount":        "RM90.00",

        "listing_title": "Vintage Camera",

    })

    db.session.commit()

    log("  → db.session.commit() — notification saved to baasket.db")

    log("\n[STEP 4] Firing event: purchase")

    subject.notify("purchase", {

        "seller_id": seller.id,

        "titles":    ["Smart Watch Series"],

    })

    db.session.commit()

    log("  → db.session.commit() — notification saved to baasket.db")

    after = Notification.query.count()

    log(f"\n[INFO] Notifications in database after demo: {after}")

    log(f"[INFO] New notifications created: {after - before}")

    log("\n[RESULT] New notifications written to baasket.db:")

    new_notifs = Notification.query.order_by(Notification.id.desc()).limit(after - before).all()

    for n in reversed(new_notifs):

        log(f"  id={n.id} | user_id={n.user_id} | category={n.category}")

        log(f"         message: {n.message}")

    log("\n" + "=" * 60)

    log("  Observer pattern executed successfully with real data.")

    log("=" * 60)

output_path = os.path.join(os.path.dirname(__file__), "observer_output.txt")

with open(output_path, "w", encoding="utf-8") as f:

    f.write("\n".join(output_lines))

print(f"\n[SAVED] Output written to: observer_output.txt")

