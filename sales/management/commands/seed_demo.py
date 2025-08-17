import random
import string
from datetime import timedelta, date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

try:
    from faker import Faker
    _FAKER = Faker("en_UG")
except Exception:  # pragma: no cover
    _FAKER = None

# Import your models
from sales.models import (
    Farmer,
    ChickRequest,
    FeedRequest,
    Payment,
    FeedDistribution,
)

# Optional models (exist in your project but guard just in case)
try:
    from sales.models import Manufacturer, Supplier, FeedStock
except Exception:  # pragma: no cover
    Manufacturer = Supplier = FeedStock = None

FOUR_MONTHS_DAYS = 120  # simple, conservative window

CHICK_TYPES = [
    ("broiler_local", "Broiler - Local"),
    ("broiler_exotic", "Broiler - Exotic"),
    ("layer_local", "Layer - Local"),
    ("layer_exotic", "Layer - Exotic"),
]
FEED_TYPES = ["starter", "grower", "finisher"]
FARMER_TYPES = ["starter", "returning"]


def rand_name():
    if _FAKER:
        return _FAKER.name()
    first = random.choice(["Amina", "John", "Jane", "Brian", "Stella", "Grace", "Ivan", "Ruth", "Noah", "Mercy"])  # noqa: E501
    last = random.choice(["Okello", "Namatovu", "Mugisha", "Kato", "Nankya", "Tumusiime", "Mukasa", "Ocen"])  # noqa: E501
    return f"{first} {last}"


def rand_phone():
    if _FAKER:
        return _FAKER.msisdn()[0:10]
    return "07" + str(random.randint(10000000, 99999999))


def rand_nin(gender: str) -> str:
    """Return a 14-character NIN. Males start with CM..., females with CF...; mix letters+digits."""
    prefix = "CM" if gender == "M" else "CF"
    tail = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    return prefix + tail


def rand_dob_18_to_30():
    """Random DOB such that age is between 18 and 30 (approx; 365-day years)."""
    today = date.today()
    years = random.randint(18, 30)
    extra_days = random.randint(0, 364)
    return today - timedelta(days=years * 365 + extra_days)


def random_datetime_within_months(months_back=9):
    """Return a random datetime within the last `months_back` months."""
    now = timezone.now()
    start = now - timedelta(days=30 * months_back)
    delta = now - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def around_four_months_ago(variance_days=8, as_date=False):
    base = timezone.now() - timedelta(days=FOUR_MONTHS_DAYS + random.randint(-variance_days, variance_days))
    return base.date() if as_date else base


class Command(BaseCommand):
    help = "Seed demo data: farmers, manufacturers, suppliers, feed stock, chick & feed requests, payments."

    def add_arguments(self, parser):
        parser.add_argument("--farmers", type=int, default=60, help="How many farmers to create")
        parser.add_argument("--chicks", type=int, default=90, help="How many chick requests to create")
        parser.add_argument("--feeds", type=int, default=80, help="How many feed requests to create")
        parser.add_argument("--payments", type=int, default=70, help="How many payments to create")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
        parser.add_argument("--wipe", action="store_true", help="Delete existing demo data before seeding")

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(opts["seed"])
        if _FAKER:
            _FAKER.seed_instance(opts["seed"])

        self.stdout.write(self.style.MIGRATE_HEADING("Seeding demo data…"))

        if opts["wipe"]:
            self._wipe()

        farmers = self._ensure_farmers(opts["farmers"])
        manufs, sups = self._ensure_sources()
        self._ensure_feed_stock(manufs, sups)

        self._create_chick_requests(farmers, opts["chicks"])
        self._create_feed_requests(farmers, opts["feeds"])
        self._create_payments(farmers, opts["payments"])

        self.stdout.write(self.style.SUCCESS("Done. Happy testing!"))

    # -------------------- helpers --------------------

    def _wipe(self):
        self.stdout.write("Wiping existing demo rows…")
        # Keep auth and contenttypes intact
        models = [FeedDistribution, Payment, FeedRequest, ChickRequest, Farmer]
        for m in models:
            try:
                m.objects.all().delete()
            except Exception:
                pass
        if FeedStock:
            FeedStock.objects.all().delete()
        if Manufacturer:
            Manufacturer.objects.all().delete()
        if Supplier:
            Supplier.objects.all().delete()

    def _ensure_farmers(self, target):
        count = Farmer.objects.count()
        to_make = max(0, target - count)
        farmers = list(Farmer.objects.all())
        for _ in range(to_make):
            gender = random.choice(["M", "F"])  # M → CM..., F → CF...
            nin = rand_nin(gender)
            while Farmer.objects.filter(nin=nin).exists():
                nin = rand_nin(gender)

            farmer = Farmer(
                name=rand_name(),
                dob=rand_dob_18_to_30(),
                gender=gender,
                nin=nin,
                recommender=rand_name(),
                recommender_nin=rand_nin(random.choice(["M", "F"])),
                contact=rand_phone(),
                farmer_type='starter',  # everyone starts as starter
            )
            farmer.save()
            farmers.append(farmer)
        self.stdout.write(f"Farmers: {len(farmers)}")
        return farmers

    def _ensure_sources(self):
        manufs = []
        sups = []
        if Manufacturer:
            if Manufacturer.objects.count() == 0:
                for nm in ["KukuFeeds Ltd", "AgriMix Uganda", "GreenMaize Mills"]:
                    manufs.append(Manufacturer.objects.create(name=nm))
            else:
                manufs = list(Manufacturer.objects.all())
        if Supplier:
            if Supplier.objects.count() == 0:
                for nm in ["Kisenyi Agri", "Wandegeya Farm Supply", "Kireka Agro"]:
                    sups.append(Supplier.objects.create(name=nm, contact=rand_phone()))
            else:
                sups = list(Supplier.objects.all())
        self.stdout.write(f"Manufacturers: {len(manufs)} | Suppliers: {len(sups)}")
        return manufs, sups

    def _ensure_feed_stock(self, manufs, sups):
        if not FeedStock:
            self.stdout.write("FeedStock model not present — skipping stock seed.")
            return
        if FeedStock.objects.exists():
            self.stdout.write("FeedStock already present — leaving as-is.")
            return
        # Seed some stock entries
        for ft in FEED_TYPES:
            FeedStock.objects.create(
                feed_type=ft,
                quantity_bags=random.randint(40, 120),
                manufacturer=random.choice(manufs) if manufs else None,
                supplier=random.choice(sups) if sups else None,
                unit_cost=random.randint(25000, 45000) if hasattr(FeedStock, 'unit_cost') else None,
                received_on=timezone.now().date() - timedelta(days=random.randint(0, 30)) if hasattr(FeedStock, 'received_on') else None,
            )
        self.stdout.write("FeedStock: seeded a few entries.")

    def _create_chick_requests(self, farmers, how_many):
        self.stdout.write("Creating chick requests…")
        created = 0
        for _ in range(how_many):
            farmer = random.choice(farmers)
            chick_type = random.choice([ct[0] for ct in CHICK_TYPES])
            qty_cap = 100 if farmer.farmer_type == 'starter' else 500
            quantity = random.randint(20, qty_cap)

            # 30% exactly around four months ago, rest random last 9 months
            if random.random() < 0.3:
                submitted_on = around_four_months_ago(as_date=True)
            else:
                submitted_on = random_datetime_within_months(9).date()

            cr = ChickRequest.objects.create(
                farmer=farmer,
                chick_type=chick_type,
                quantity=quantity,
                status=random.choice(['pending', 'approved', 'rejected']),
                submitted_on=submitted_on,
                notes=("Auto-seeded"),
            )

            # Simulate pickups for some approved requests
            if cr.status == 'approved' and random.random() < 0.6:
                cr.is_picked = True
                cr.picked_on = submitted_on + timedelta(days=random.randint(1, 14))
                cr.save(update_fields=["is_picked", "picked_on"])
                # Promote starter -> returning on first pickup
                if farmer.farmer_type == 'starter':
                    farmer.farmer_type = 'returning'
                    farmer.save(update_fields=["farmer_type"])
                # Initial 2 bags allocation via FeedDistribution
                try:
                    FeedDistribution.objects.create(
                        farmer=farmer,
                        request=cr,
                        distribution_type='initial',
                        quantity_bags=2,
                        notes='Initial allocation at pickup',
                    )
                except Exception:
                    pass

            created += 1
        self.stdout.write(f"ChickRequests: {created}")

    def _create_feed_requests(self, farmers, how_many):
        self.stdout.write("Creating feed requests…")
        created = 0
        for _ in range(how_many):
            farmer = random.choice(farmers)
            # 30% around four months ago, rest random
            if random.random() < 0.3:
                submitted_on = around_four_months_ago()
            else:
                submitted_on = random_datetime_within_months(9)

            fr = FeedRequest.objects.create(
                farmer=farmer,
                feed_type=random.choice(FEED_TYPES),
                quantity_bags=random.randint(1, 10),
                status=random.choice(['pending', 'approved', 'rejected']),
                approval_notes='Auto-seeded',
                submitted_on=submitted_on,
            )
            if fr.status == 'approved' and random.random() < 0.55:
                fr.pickup_status = 'picked'
                fr.picked_on = fr.submitted_on + timedelta(days=random.randint(1, 10))
                fr.save(update_fields=['pickup_status', 'picked_on'])
            created += 1
        self.stdout.write(f"FeedRequests: {created}")

    def _create_payments(self, farmers, how_many):
        self.stdout.write("Creating payments…")
        created = 0
        for _ in range(how_many):
            farmer = random.choice(farmers)
            pfor = random.choice(['chicks', 'feeds', 'both', 'other'])

            # Some payments 4 months back, others random recent
            if random.random() < 0.35:
                payment_date = around_four_months_ago(as_date=True)
            else:
                payment_date = random_datetime_within_months(9).date()

            amt = random.randint(50000, 300000)
            p = Payment.objects.create(
                farmer=farmer,
                amount=amt,
                payment_for=pfor,
                notes='Auto-seeded',
            )
            # override auto_now_add to desired date
            try:
                p.payment_date = payment_date
                p.save(update_fields=['payment_date'])
            except Exception:
                pass

            created += 1
        self.stdout.write(f"Payments: {created}")
