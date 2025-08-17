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

def public_request_status(request):
    nin = (request.GET.get("nin") or request.GET.get("query") or "").strip()

    farmer = None
    chick_requests = []
    feed_requests = []
    payments = []
    feed_summary = None  # NEW

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

            # ---- Summaries from your existing data ----
            # Initial allocation = sum of FeedDistribution 'initial' bags
            allocated_bags = (FeedDistribution.objects
                              .filter(farmer=farmer, distribution_type='initial')
                              .aggregate(total=Sum("quantity_bags"))["total"] or 0)

            # Payments toward feeds (or both) in UGX
            paid_for_feeds = (Payment.objects
                              .filter(farmer=farmer, payment_for__in=["feeds", "both"])
                              .aggregate(total=Sum("amount"))["total"] or 0)

            # (Optional) total payments all categories
            paid_total = (Payment.objects
                          .filter(farmer=farmer)
                          .aggregate(total=Sum("amount"))["total"] or 0)

            # Picked chick requests (your source of the “2 mandatory bags”)
            picked_count = ChickRequest.objects.filter(farmer=farmer, is_picked=True).count()

            feed_summary = {
                "picked_chick_requests": picked_count,
                "allocated_bags": allocated_bags,
                "payments_total_feeds": paid_for_feeds,
                "payments_total_all": paid_total,
            }
        else:
            messages.warning(request, "We couldn't find a farmer with that NIN.")

    # badges (your earlier template expects these per-record attributes)
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
        "feed_summary": feed_summary,  # NEW
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