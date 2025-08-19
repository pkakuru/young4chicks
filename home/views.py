from django.shortcuts import render
from datetime import date
from django.utils import timezone
from django.db.models import Q, Sum
from home.models import Announcement, Training, FarmerTip, QuoteOfTheWeek
from django.contrib import messages
from django.shortcuts import render
from django.db.models import Q
from sales.models import Farmer, ChickRequest, FeedRequest, Payment, FeedDistribution

def homePage(request):
    today = timezone.now().date()
    latest_announcement = Announcement.objects.order_by('-posted_on').first()
    upcoming_trainings = Training.objects.filter(date__gte=today).order_by('date')[:3]
    farmer_tips = FarmerTip.objects.order_by('-created_on')[:3]

    current_quote = (QuoteOfTheWeek.objects
                     .filter(effective_from__lte=today)
                     .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
                     .order_by('-effective_from', '-posted_on')
                     .first())

    return render(request, 'index.html', {
        'latest_announcement': latest_announcement,
        'upcoming_trainings': upcoming_trainings,
        'farmer_tips': farmer_tips,
        'current_quote': current_quote
    })




# -------------------------------------------------------------------
# Public: NIN lookup -> list chick & feed requests (view-only)
# -------------------------------------------------------------------

from django.db.models import Sum

CHICK_PRICE = 1650      # UGX per chick (set to 0 if you don’t want to show values)
FEED_BAG_PRICE = 0      # UGX per initial bag (0 keeps it as a count only)

def public_request_status(request):
    nin = (request.GET.get("nin") or request.GET.get("query") or "").strip()

    farmer = None
    chick_requests = []
    feed_requests = []
    payments = []
    feed_summary = None

    if nin:
        farmer = Farmer.objects.filter(nin__iexact=nin).first()
        if farmer:
            chick_requests = (ChickRequest.objects
                              .filter(farmer=farmer)
                              .order_by("-submitted_on", "-id"))
            feed_requests = (FeedRequest.objects
                             .filter(farmer=farmer)
                             .order_by("-submitted_on", "-id"))
            payments = (Payment.objects
                        .filter(farmer=farmer)
                        .order_by("-payment_date", "-id"))

            # --- Existing bits you already had ---
            allocated_bags = (FeedDistribution.objects
                              .filter(farmer=farmer, distribution_type='initial')
                              .aggregate(total=Sum("quantity_bags"))["total"] or 0)

            paid_for_feeds_or_both = (Payment.objects
                                      .filter(farmer=farmer, payment_for__in=["feeds", "both"])
                                      .aggregate(total=Sum("amount"))["total"] or 0)

            paid_total = (Payment.objects
                          .filter(farmer=farmer)
                          .aggregate(total=Sum("amount"))["total"] or 0)

            picked_count = ChickRequest.objects.filter(farmer=farmer, is_picked=True).count()

            # --- New: clearer numbers for the cards ---
            picked_chicks = (ChickRequest.objects
                             .filter(farmer=farmer, is_picked=True)
                             .aggregate(total=Sum("quantity"))["total"] or 0)
            expected_chicks_amount = picked_chicks * CHICK_PRICE
            expected_feeds_amount = allocated_bags * FEED_BAG_PRICE

            # Payment split (keeps it simple; no fancy “split both” logic unless you want it)
            paid_chicks = (Payment.objects
                           .filter(farmer=farmer, payment_for="chicks")
                           .aggregate(total=Sum("amount"))["total"] or 0)
            paid_feeds  = (Payment.objects
                           .filter(farmer=farmer, payment_for="feeds")
                           .aggregate(total=Sum("amount"))["total"] or 0)
            paid_both   = (Payment.objects
                           .filter(farmer=farmer, payment_for="both")
                           .aggregate(total=Sum("amount"))["total"] or 0)

            outstanding = max((expected_chicks_amount + expected_feeds_amount) - paid_total, 0)

            feed_summary = {
                # your original keys (kept for compatibility)
                "picked_chick_requests": picked_count,
                "allocated_bags": allocated_bags,
                "payments_total_feeds": paid_for_feeds_or_both,
                "payments_total_all": paid_total,

                # new clearer keys
                "picked_chicks": picked_chicks,
                "expected_chicks_amount": expected_chicks_amount if CHICK_PRICE else None,
                "expected_feeds_amount": expected_feeds_amount if FEED_BAG_PRICE else None,
                "paid_chicks": paid_chicks,
                "paid_feeds": paid_feeds,
                "paid_both": paid_both,
                "total_paid": paid_total,
                "outstanding": outstanding,
            }
        else:
            messages.warning(request, "We couldn't find a farmer with that NIN.")

    # badges (unchanged)
    req_badge = {"pending": "badge-warning", "approved": "badge-success", "rejected": "badge-danger"}
    pickup_badge = {"picked": "badge-primary", "not_picked": "badge-secondary"}

    for r in chick_requests:
        r.badge_class = req_badge.get(r.status, "badge-secondary")

    for r in feed_requests:
        r.badge_class = req_badge.get(r.status, "badge-secondary")
        r.pickup_badge_class = pickup_badge.get(r.pickup_status, "badge-secondary")

    return render(request, "public/status.html", {
        "nin": nin,
        "farmer": farmer,
        "chick_requests": chick_requests,
        "feed_requests": feed_requests,
        "payments": payments,
        "feed_summary": feed_summary,
    })


# views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from django.contrib import messages
from django.contrib.auth import authenticate, login

def user_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Redirect based on role
            if user.role == "brooder_manager":
                messages.success(request, f"Welcome {user.first_name} {user.last_name} to the Brooder Manager Dashboard!")
                return redirect("manager_dashboard")
            elif user.role == "sales_rep":
                messages.success(request, f"Welcome {user.first_name} {user.last_name} to the Sales Representative Dashboard!")
                return redirect("sales_dashboard")
            else:
                messages.error(request, "Role not recognized.")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "login.html")



def logout_view(request):
    logout(request)  # clears the session
    return redirect('homepage')  # send user back to login page