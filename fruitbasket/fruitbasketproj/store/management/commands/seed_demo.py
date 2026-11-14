from datetime import timedelta
from io import BytesIO
import uuid

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from adminpanel.models import (
    Customer,
    GroupLine,
    GroupMember,
    GroupPurchase,
    InventoryBatch,
    Item,
    Orders,
    Product,
    Review,
    ReviewModeration,
    SavedItem,
    StockAdjustment,
    StockNotice,
    Subscription,
    SupportTicket,
)
from adminpanel.prediction_records import capture_current
from store.cancellation import cancel_order
from store.ordering import place_order
from store.subscriptions import process_due_subscriptions


DEMO_STAFF_USERNAME = "demo_staff"
DEMO_STAFF_PASSWORD = "DemoStaff123!"
DEMO_CUSTOMER_PASSWORD = "DemoPass123!"

DEMO_CUSTOMERS = (
    ("DM001", "demo_alice", "Demo Alice Tan", "12 Demo Grove Lane", 1, 7),
    ("DM002", "demo_bob", "Demo Bob Lim", "45 Demo Orchard Road", 2, 14),
    ("DM003", "demo_david", "Demo David Chen", "88 Demo Bishan Street", 4, 21),
    ("DM004", "demo_emma", "Demo Emma Ng", "3 Demo Marina Blvd", 1, 5),
    ("DM005", "demo_frank", "Demo Frank Goh", "102 Demo Holland Road", 5, 28),
)


def _next_product_id():
    n = 1
    while Product.objects.filter(pk=f"FB{n:03d}").exists():
        n += 1
    return f"FB{n:03d}"


def _next_customer_id():
    n = 1
    while Customer.objects.filter(pk=f"DM{n:03d}").exists():
        n += 1
    return f"DM{n:03d}"


def _next_username(base):
    if not User.objects.filter(username=base).exists():
        return base
    n = 2
    while User.objects.filter(username=f"{base}_{n}").exists():
        n += 1
    return f"{base}_{n}"


def _ensure_demo_staff():
    existing = User.objects.filter(username=DEMO_STAFF_USERNAME).first()
    if existing is not None and existing.is_staff and existing.is_active:
        return existing, False
    username = _next_username(DEMO_STAFF_USERNAME)
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=DEMO_STAFF_PASSWORD,
        is_staff=True,
        is_active=True,
    )
    return user, True


def _ensure_demo_customer(preferred_cid, base_username, name, address, household_size, meals_per_week):
    existing = Customer.objects.select_related("Cuser").filter(Cname=name).first()
    if existing is not None:
        return existing, False
    cid = preferred_cid if not Customer.objects.filter(pk=preferred_cid).exists() else _next_customer_id()
    username = _next_username(base_username)
    with transaction.atomic():
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=DEMO_CUSTOMER_PASSWORD,
        )
        customer = Customer.objects.create(
            Cid=cid,
            Cname=name,
            Caddress=address,
            Chouseholdsize=household_size,
            Cmealsperweek=meals_per_week,
            Cuser=user,
        )
    return customer, True


def _ensure_product(name, category_id, size, price, lowstock, **extra):
    product = Product.objects.filter(Pname__iexact=name, Pcategory_id=category_id).first()
    if product is not None:
        return product, False
    return (
        Product.objects.create(
            Pid=_next_product_id(),
            Pname=name,
            Pcategory_id=category_id,
            Psize=size,
            Pprice=price,
            Plowstock=lowstock,
            Pactive=True,
            **extra,
        ),
        True,
    )


def _attach_placeholder_image(product, rgb):
    if product.Pimage:
        return
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    img = Image.new("RGB", (240, 240), rgb)
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, 224, 224], outline=(255, 255, 255), width=4)
    buf = BytesIO()
    img.save(buf, format="PNG")
    product.Pimage.save(f"demo_{product.Pid.lower()}.png", ContentFile(buf.getvalue()), save=True)


def _ensure_batch(reference, product, received, quantity, datetype="", recorded_date=None):
    batch = InventoryBatch.objects.filter(Breference=reference).first()
    if batch is not None:
        return batch, False
    with transaction.atomic():
        batch = InventoryBatch.objects.create(
            Breference=reference,
            Bproduct=product,
            Breceived=received,
            Bquantity=quantity,
            Bdatetype=datetype,
            Bdate=recorded_date,
        )
        Item.objects.bulk_create(
            [
                Item(
                    Ibatch=batch,
                    Iproduct=product,
                    Ireceived=received,
                    Iexpiry=recorded_date,
                    Istatus="available",
                )
                for _ in range(quantity)
            ]
        )
    return batch, True


def _fulfil_to(order, target_status, dispatched_at=None, delivered_at=None):
    steps = ["placed", "preparing", "dispatched", "delivered"]
    current_idx = steps.index(order.Ostatus)
    target_idx = steps.index(target_status)
    now = timezone.now()
    for step in steps[current_idx + 1 : target_idx + 1]:
        updates = {"Ostatus": step}
        if step == "dispatched":
            updates["Odispatched"] = dispatched_at or now
        elif step == "delivered":
            updates["Odelivered"] = delivered_at or now
        Orders.objects.filter(pk=order.pk).update(**updates)
    if target_status == "delivered":
        Item.objects.filter(Iorder=order, Istatus="allocated").update(Istatus="delivered")
    order.refresh_from_db()


class Command(BaseCommand):
    help = "Populate coherent, idempotent FruitBasket demo workflows with dedicated demo accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-images",
            action="store_true",
            help="Generate placeholder PNG images for featured demo products when Pimage is empty.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        now = timezone.now()

        staff_user, _ = _ensure_demo_staff()
        demo_map = {}
        for cid, uname, name, addr, hh, meals in DEMO_CUSTOMERS:
            cust, _ = _ensure_demo_customer(cid, uname, name, addr, hh, meals)
            demo_map[uname] = cust

        c_alice = demo_map["demo_alice"]
        c_bob = demo_map["demo_bob"]
        c_david = demo_map["demo_david"]
        c_emma = demo_map["demo_emma"]
        c_frank = demo_map["demo_frank"]

        blueberries, _ = _ensure_product("Blueberries", "fruit", "125 g", 4.90, lowstock=2)
        yogurt, _ = _ensure_product("Greek Yogurt", "dairy", "500 g", 5.20, lowstock=2)
        eggs, _ = _ensure_product("Free Range Eggs", "dairy", "10 eggs", 5.80, lowstock=2)
        croissants, _ = _ensure_product("Croissants", "bakery", "4 pieces", 4.80, lowstock=2)
        paper_towels, _ = _ensure_product("Paper Towels", "household", "2 rolls", 4.50, lowstock=2)
        inactive_rice = Product.objects.filter(pk="DEMO3", Pactive=False).first()

        avocados, _ = _ensure_product(
            "Organic Avocados",
            "fruit",
            "4 pieces",
            6.80,
            lowstock=3,
            Ptargetstock=12,
            Pbulkquantity=4,
            Pbulkprice=5.50,
            Pexpirydays=2,
        )
        olive_oil, _ = _ensure_product(
            "Extra Virgin Olive Oil",
            "rice",
            "500 ml",
            13.90,
            lowstock=3,
            Ptargetstock=10,
            Pbulkquantity=3,
            Pbulkprice=11.50,
            Pexpirydays=0,
        )

        if options.get("with_images"):
            _attach_placeholder_image(avocados, (76, 135, 62))
            _attach_placeholder_image(blueberries, (62, 84, 152))
            _attach_placeholder_image(olive_oil, (156, 134, 48))

        # 1. Inventory batches (meets cutoff, near date, past date, undated)
        _ensure_batch("BATCH-202611-FR1", avocados, today - timedelta(days=1), 12, "best_before", today + timedelta(days=14))
        b_blue, _ = _ensure_batch("BATCH-202611-FR2", blueberries, today - timedelta(days=2), 10, "use_by", today + timedelta(days=10))
        _ensure_batch("BATCH-202611-DY1", yogurt, today - timedelta(days=1), 6, "use_by", today + timedelta(days=5))
        b_crois, _ = _ensure_batch("BATCH-202611-BK1", croissants, today - timedelta(days=5), 4, "best_before", today - timedelta(days=2))
        _ensure_batch("BATCH-202611-HH1", paper_towels, today - timedelta(days=3), 6, "", None)
        _ensure_batch("BATCH-202611-RC1", olive_oil, today - timedelta(days=1), 10, "best_before", today + timedelta(days=180))

        # 2. Stock adjustments (1 count correction + 1 write-off)
        corr_uuid = uuid.uuid5(uuid.NAMESPACE_URL, "fruitbasket-demo-correction-fr2")
        if not StockAdjustment.objects.filter(request_id=corr_uuid).exists():
            with transaction.atomic():
                items = list(
                    Item.objects.filter(
                        Ibatch=b_blue, Istatus="available", Iorder__isnull=True
                    ).order_by("pk")[:1]
                )
                before = Item.objects.filter(Ibatch=b_blue, Istatus="available", Iorder__isnull=True).count()
                if items:
                    audit = StockAdjustment.objects.create(
                        request_id=corr_uuid,
                        kind="correction",
                        product=blueberries,
                        batch=b_blue,
                        received=b_blue.Breceived,
                        recorded_date=b_blue.Bdate,
                        before_count=before,
                        after_count=before - 1,
                        difference=-1,
                        reason="Damaged punnet found during morning stocktake",
                        staff=staff_user,
                    )
                    Item.objects.filter(pk=items[0].pk).update(Istatus="adjusted")
                    audit.items.add(items[0].pk)

        writeoff_uuid = uuid.uuid5(uuid.NAMESPACE_URL, "fruitbasket-demo-writeoff-bk1")
        if not StockAdjustment.objects.filter(request_id=writeoff_uuid).exists():
            with transaction.atomic():
                items = list(
                    Item.objects.filter(
                        Ibatch=b_crois, Istatus="available", Iorder__isnull=True
                    ).order_by("pk")[:2]
                )
                before = Item.objects.filter(Ibatch=b_crois, Istatus="available", Iorder__isnull=True).count()
                if len(items) == 2:
                    audit = StockAdjustment.objects.create(
                        request_id=writeoff_uuid,
                        kind="writeoff",
                        product=croissants,
                        batch=b_crois,
                        received=b_crois.Breceived,
                        recorded_date=b_crois.Bdate,
                        before_count=before,
                        after_count=before - 2,
                        difference=-2,
                        reason="expired",
                        note="Past best-before date; removed from display",
                        staff=staff_user,
                    )
                    ids = [item.pk for item in items]
                    Item.objects.filter(pk__in=ids).update(Istatus="writtenoff")
                    audit.items.add(*ids)

        # 3. Complete order lifecycle & ML personal history for demo_alice (Blueberries x2 dates due within 3 days)
        if not Orders.objects.filter(Ocustomer=c_alice, order_items__Iproduct=blueberries, Ostatus="delivered").exists():
            o_hist1, _ = place_order(c_alice, c_alice.Caddress, {blueberries.Pid: 1})
            Orders.objects.filter(pk=o_hist1.pk).update(Odate=today - timedelta(days=25))
            _fulfil_to(
                o_hist1,
                "delivered",
                dispatched_at=now - timedelta(days=24, hours=4),
                delivered_at=now - timedelta(days=24),
            )
            Item.objects.filter(Iorder=o_hist1).update(Istatus="used", Ifinished=today - timedelta(days=18), Irating=5)

            o_hist2, _ = place_order(c_alice, c_alice.Caddress, {blueberries.Pid: 2})
            Orders.objects.filter(pk=o_hist2.pk).update(Odate=today - timedelta(days=11))
            _fulfil_to(
                o_hist2,
                "delivered",
                dispatched_at=now - timedelta(days=10, hours=3),
                delivered_at=now - timedelta(days=10),
            )

        # demo_david delivered order for Avocados (used for hidden/moderated review + INITIAL fallback capture)
        if not Orders.objects.filter(Ocustomer=c_david, order_items__Iproduct=avocados, Ostatus="delivered").exists():
            o_david_deliv, _ = place_order(c_david, c_david.Caddress, {avocados.Pid: 1})
            Orders.objects.filter(pk=o_david_deliv.pk).update(Odate=today - timedelta(days=4))
            _fulfil_to(
                o_david_deliv,
                "delivered",
                dispatched_at=now - timedelta(days=3, hours=5),
                delivered_at=now - timedelta(days=3),
            )

        # demo_bob dispatched order
        if not Orders.objects.filter(Ocustomer=c_bob, Ostatus="dispatched").exists():
            o_disp, _ = place_order(c_bob, c_bob.Caddress, {yogurt.Pid: 1, paper_towels.Pid: 1})
            _fulfil_to(o_disp, "dispatched", dispatched_at=now - timedelta(hours=2))

        # demo_david preparing order
        if not Orders.objects.filter(Ocustomer=c_david, Ostatus="preparing").exists():
            o_prep, _ = place_order(c_david, c_david.Caddress, {eggs.Pid: 1})
            _fulfil_to(o_prep, "preparing")

        # demo_emma placed order
        if not Orders.objects.filter(Ocustomer=c_emma, Ostatus="placed").exists():
            place_order(c_emma, c_emma.Caddress, {avocados.Pid: 1})

        # 4. Cancellations (1 customer-initiated, 1 staff-initiated)
        if not Orders.objects.filter(Ocustomer=c_bob, cancellation__source="customer").exists():
            o_cust_cancel, _ = place_order(c_bob, c_bob.Caddress, {olive_oil.Pid: 1})
            cancel_order(o_cust_cancel.Oid, customer_id=c_bob.Cid)

        if not Orders.objects.filter(Ocustomer=c_frank, cancellation__source="staff").exists():
            o_staff_cancel, _ = place_order(c_frank, c_frank.Caddress, {blueberries.Pid: 1})
            cancel_order(
                o_staff_cancel.Oid,
                employee=staff_user,
                reason="Customer requested cancellation before packing due to travel",
            )

        # 5. Support tickets (1 open, 1 answered)
        bob_disp = Orders.objects.filter(Ocustomer=c_bob, Ostatus="dispatched").first()
        if bob_disp and not SupportTicket.objects.filter(Torder=bob_disp, Tsubject="Delivery window inquiry").exists():
            SupportTicket.objects.create(
                Torder=bob_disp,
                Tsubject="Delivery window inquiry",
                Tmessage="Could the courier call on arrival at the guardhouse?",
                Tstatus="open",
            )

        alice_deliv = Orders.objects.filter(Ocustomer=c_alice, Ostatus="delivered").order_by("-Odate").first()
        if alice_deliv and not SupportTicket.objects.filter(Torder=alice_deliv, Tsubject="Cold pack return").exists():
            SupportTicket.objects.create(
                Torder=alice_deliv,
                Tsubject="Cold pack return",
                Tmessage="Can I return the insulated ice packs on my next delivery?",
                Tstatus="answered",
                Tresponse="Yes, please leave them in a bag outside your door and our driver will collect them.",
                Tresponder=staff_user,
                Tresponded=now - timedelta(hours=12),
            )

        # 6. Reviews & Review Moderation
        alice_item = Item.objects.filter(
            Iorder__Ocustomer=c_alice, Iproduct=blueberries, Istatus__in=["delivered", "used"]
        ).first()
        if alice_item and not Review.objects.filter(Rcustomer=c_alice, Rproduct=blueberries).exists():
            Review.objects.create(
                Rcustomer=c_alice,
                Rproduct=blueberries,
                Ritem=alice_item,
                Rrating=5,
                Rtext="Crisp, sweet berries and packed securely.",
                Rvisible=True,
                Rdate=today - timedelta(days=3),
            )

        david_item = Item.objects.filter(
            Iorder__Ocustomer=c_david, Iproduct=avocados, Istatus__in=["delivered", "used"]
        ).first()
        if david_item and not Review.objects.filter(Rcustomer=c_david, Rproduct=avocados).exists():
            rev = Review.objects.create(
                Rcustomer=c_david,
                Rproduct=avocados,
                Ritem=david_item,
                Rrating=2,
                Rtext="Check out my promo link for unrelated coupons.",
                Rvisible=False,
                Rdate=today - timedelta(days=2),
            )
            ReviewModeration.objects.create(
                review=rev,
                employee=staff_user,
                action="hide",
                reason="Off-topic promotional content",
            )

        # 7. Subscriptions & Cycles (1 processed ordered, 1 failed/on-hold, 1 paused)
        if not Subscription.objects.filter(Scustomer=c_alice, Sproduct=yogurt).exists():
            sub_ok = Subscription.objects.create(
                Scustomer=c_alice,
                Sproduct=yogurt,
                Squantity=1,
                Sinterval=7,
                Snextdate=today,
                Sceiling=6.00,
                Sstatus="active",
                Screated=today - timedelta(days=7),
            )
            process_due_subscriptions(today=today, subscription_id=sub_ok.pk)

        if not Subscription.objects.filter(Scustomer=c_david, Sproduct=olive_oil).exists():
            sub_fail = Subscription.objects.create(
                Scustomer=c_david,
                Sproduct=olive_oil,
                Squantity=1,
                Sinterval=14,
                Snextdate=today,
                Sceiling=5.00,
                Sstatus="active",
                Screated=today - timedelta(days=14),
            )
            process_due_subscriptions(today=today, subscription_id=sub_fail.pk)

        if not Subscription.objects.filter(Scustomer=c_bob, Sproduct=eggs).exists():
            Subscription.objects.create(
                Scustomer=c_bob,
                Sproduct=eggs,
                Squantity=1,
                Sinterval=7,
                Snextdate=today + timedelta(days=5),
                Sceiling=7.00,
                Sstatus="paused",
                Screated=today - timedelta(days=10),
            )

        # Unprocessed due active subscription so staff can demonstrate live due processing (AD21)
        if not Subscription.objects.filter(Scustomer=c_emma, Sproduct=yogurt).exists():
            Subscription.objects.create(
                Scustomer=c_emma,
                Sproduct=yogurt,
                Squantity=1,
                Sinterval=7,
                Snextdate=today,
                Sceiling=6.00,
                Sstatus="active",
                Screated=today - timedelta(days=7),
            )

        # 8. Group purchases (1 open meeting bulk threshold, 1 ordered with bulk price)
        if not GroupPurchase.objects.filter(Gcode="DEMO-GRP-OPEN-01").exists():
            with transaction.atomic():
                grp_open = GroupPurchase.objects.create(
                    Gname="Grove Lane Avocado Co-op",
                    Gcode="DEMO-GRP-OPEN-01",
                    Gaddress=c_alice.Caddress,
                    Gstatus="open",
                    Gcreated=today - timedelta(days=1),
                    Gorganiser=c_alice,
                )
                GroupMember.objects.create(GMgroup=grp_open, GMcustomer=c_alice)
                GroupMember.objects.create(GMgroup=grp_open, GMcustomer=c_bob)
                GroupLine.objects.create(GLgroup=grp_open, GLcustomer=c_alice, GLproduct=avocados, GLquantity=2)
                GroupLine.objects.create(GLgroup=grp_open, GLcustomer=c_bob, GLproduct=avocados, GLquantity=2)

        if not GroupPurchase.objects.filter(Gcode="DEMO-GRP-ORD-02").exists():
            with transaction.atomic():
                grp_order, _ = place_order(c_david, c_david.Caddress, {olive_oil.Pid: 3}, use_bulk_price=True)
                grp_ord = GroupPurchase.objects.create(
                    Gname="Bishan Olive Oil Bulk Buy",
                    Gcode="DEMO-GRP-ORD-02",
                    Gaddress=c_david.Caddress,
                    Gstatus="ordered",
                    Gcreated=today - timedelta(days=2),
                    Gorganiser=c_david,
                    Gorder=grp_order,
                )
                GroupMember.objects.create(GMgroup=grp_ord, GMcustomer=c_david)
                GroupMember.objects.create(GMgroup=grp_ord, GMcustomer=c_frank)
                GroupLine.objects.create(GLgroup=grp_ord, GLcustomer=c_david, GLproduct=olive_oil, GLquantity=2)
                GroupLine.objects.create(GLgroup=grp_ord, GLcustomer=c_frank, GLproduct=olive_oil, GLquantity=1)

        # 9. Saved items & Stock notices
        SavedItem.objects.get_or_create(SVcustomer=c_alice, SVproduct=olive_oil, defaults={"SVadded": today})
        SavedItem.objects.get_or_create(SVcustomer=c_emma, SVproduct=blueberries, defaults={"SVadded": today})
        if inactive_rice:
            StockNotice.objects.get_or_create(SNcustomer=c_bob, SNproduct=inactive_rice, defaults={"SNcreated": today})
            StockNotice.objects.get_or_create(SNcustomer=c_emma, SNproduct=inactive_rice, defaults={"SNcreated": today})

        # 10. ML Restock Captures (MODEL, INITIAL fallback, and UNAVAILABLE)
        capture_current(c_alice, blueberries, staff_user)
        capture_current(c_david, avocados, staff_user)
        capture_current(c_emma, avocados, staff_user)

        self.stdout.write(self.style.SUCCESS("Demo workflows seeded cleanly."))
