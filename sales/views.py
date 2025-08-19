# Standard library
from datetime import date, timedelta, datetime
from decimal import Decimal

# Django
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.db.models import Sum

# Local apps
from home.models import User  # TODO: drop when auth wiring is complete
from manager.models import ChickStock
from sales.models import (
    Farmer, ChickRequest, FeedRequest, FeedDistribution, FeedStock, Payment
)


@login_required
def sales_dashboard_view(request):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    # --- Queues (what Sales needs to act on) ---
    pending_chick_qs = (ChickRequest.objects
                        .filter(status='approved', is_picked=False)
                        .select_related('farmer')
                        .order_by('approval_date', 'id'))
    pending_feed_qs = (FeedRequest.objects
                       .filter(status='approved', pickup_status='not_picked')
                       .select_related('farmer')
                       .order_by('approved_on', 'id'))

    pending_chick_count = pending_chick_qs.count()
    pending_chick_qty   = pending_chick_qs.aggregate(n=Sum('quantity'))['n'] or 0

    pending_feed_count = pending_feed_qs.count()
    pending_feed_bags  = pending_feed_qs.aggregate(n=Sum('quantity_bags'))['n'] or 0

    # --- Cash collected (today & this week) ---
    today_chick_cash = Payment.objects.filter(payment_for='chicks', payment_date=today).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    today_feed_cash  = Payment.objects.filter(payment_for='feeds',  payment_date=today).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    today_total_cash = today_chick_cash + today_feed_cash

    week_chick_cash = Payment.objects.filter(payment_for='chicks', payment_date__gte=week_start).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    week_feed_cash  = Payment.objects.filter(payment_for='feeds',  payment_date__gte=week_start).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    week_total_cash = week_chick_cash + week_feed_cash

    # --- Quick stock snapshot ---
    chicks_in_stock = ChickStock.objects.aggregate(n=Sum('quantity'))['n'] or 0
    feed_bags_in_stock = FeedStock.objects.aggregate(n=Sum('quantity_bags'))['n'] or 0

    # --- Overdue initial-feeds follow-ups (simple & readable) ---
    # Value (bags * sale_price) vs paid (payments linked to that distribution)
    initial_dists = (FeedDistribution.objects
                     .filter(distribution_type='initial')
                     .select_related('feed_stock', 'farmer'))
    # preload payments for those distributions
    dist_ids = list(initial_dists.values_list('id', flat=True))
    paid_map = {}
    if dist_ids:
        for row in (Payment.objects
                    .filter(related_feed_distribution_id__in=dist_ids, payment_for='feeds')
                    .values('related_feed_distribution')
                    .annotate(s=Sum('amount'))):
            paid_map[row['related_feed_distribution']] = row['s'] or Decimal('0')

    overdue_followups = 0
    for fd in initial_dists:
        unit = (fd.feed_stock.sale_price if fd.feed_stock and fd.feed_stock.sale_price else Decimal('0'))
        value = unit * Decimal(fd.quantity_bags or 0)
        paid  = paid_map.get(fd.id, Decimal('0'))
        balance = value - paid
        if balance > 0 and fd.due_date and fd.due_date < today:
            overdue_followups += 1

    context = dict(
        # cards
        pending_chick_count=pending_chick_count,
        pending_chick_qty=pending_chick_qty,
        pending_feed_count=pending_feed_count,
        pending_feed_bags=pending_feed_bags,
        today_chick_cash=today_chick_cash,
        today_feed_cash=today_feed_cash,
        today_total_cash=today_total_cash,
        week_chick_cash=week_chick_cash,
        week_feed_cash=week_feed_cash,
        week_total_cash=week_total_cash,
        chicks_in_stock=chicks_in_stock,
        feed_bags_in_stock=feed_bags_in_stock,
        overdue_followups=overdue_followups,

        # small tables (limit to 10 rows each)
        next_chick_pickups=pending_chick_qs[:10],
        next_feed_pickups=pending_feed_qs[:10],
    )
    return render(request, 'sales/dashboard.html', context)

@login_required
def register_farmer(request):
    errors = {}

    if request.method == 'POST':        
        form_data = request.POST
        name = form_data['name']
        dob = form_data['dob']
        gender = form_data['gender']
        contact = form_data['contact']
        nin = form_data['nin']
        recommender = form_data['recommender']
        recommender_nin = form_data['recommender_nin'].strip().upper()

        # Convert DOB string to date object
        try:
            dob_obj = datetime.strptime(dob, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            messages.error(request, "Invalid Date of Birth Format. Please use YYYY-MM-DD.")
            return redirect('register_farmer')
        
        # Calculate the age
        today = date.today()
        age = today.year - dob_obj.year - ( (today.month, today.day) < (dob_obj.month, dob_obj.day) )

        # Check age range
        if age < 18 or age > 30:
            messages.error(request, "Farmer must be between 18 and 30 years old.")
            return redirect('register_farmer')
        
        # Check if farmer already exists
        if Farmer.objects.filter(nin=nin).exists():
            messages.error(request, f"A farmer with the NIN {nin} already exists.")
            return redirect('register_farmer')
        
        errors = {}
        nin = request.POST.get('nin', '').strip().upper()

        # Enforce uppercase and format check
        if not nin.startswith(('CM', 'CF')) or len(nin) !=14:
            errors['nin'] = "NIN must start with 'CM' or 'CF' and be exactly 14 characters."
        
        # Save new farmer
        Farmer.objects.create(
            name = name,
            dob = dob_obj,
            gender = gender,
            nin = nin,
            contact = contact,
            recommender = recommender,
            recommender_nin = recommender_nin,
            farmer_type = 'starter' #default type
        )

        messages.success(request, f"Farmer {name} registered successfully!")
        return redirect('register_farmer')
    
    
    
    # On GET request, render the form
    all_farmers = Farmer.objects.all().order_by('-id')
    paginator = Paginator(all_farmers, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'sales/register.html', {
        'farmers': all_farmers,
        'page_obj': page_obj,
        })

def edit_farmer(request, farmer_id):
    farmer = get_object_or_404(Farmer, id=farmer_id)
    errors = {}

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        dob = request.POST.get('dob', '')
        gender = request.POST.get('gender', '')
        contact = request.POST.get('phone', '')
        nin = request.POST.get('youth_nin', '').strip()
        recommender = request.POST.get('recommender_name', '').strip()
        recommender_nin = request.POST.get('recommender_nin', '').strip()

        # Validate fields
        if not name:
            errors['name'] = "Full name is required."
        if not dob:
            errors['dob'] = 'Date of birth is required.'
        if not gender:
            errors['gender'] = 'Select a valid gender.'
        if not contact:
            errors['contact'] = 'Contact number is required.'
        if not nin:
            errors['nin'] = 'NIN is required.'
        if not recommender:
            errors['recommender'] = 'Recommender name is required.'
        if not recommender_nin:
            errors['recommender_nin'] = 'Recommender NIN is required.'

        if not errors:
            farmer.name = name
            farmer.dob = dob
            farmer.gender = gender
            farmer.contact = contact
            farmer.nin = nin
            farmer.recommender = recommender
            farmer.recommender_nin = recommender_nin
            farmer.save()
            messages.success(request, f"Farmer {farmer.name}'s details updated successfully.")
            return redirect('register_farmer')

    # Ensure context is always defined
    context = {
        'farmer': farmer,
        'errors': errors,
    }
    return render(request, 'sales/edit_farmer.html', context)

def delete_farmer(request, farmer_id):
    farmer = get_object_or_404(Farmer, id=farmer_id)
    farmer.delete()
    messages.success(request, f"Farmer {farmer.name} deleted successfully.")
    return redirect('register_farmer')

#@login_required
def submit_chick_request(request):
    farmers = Farmer.objects.all().order_by('name')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'chick_request':
            # Chick Request Handling
            farmer_id = request.POST.get('farmer')
            chick_type = request.POST.get('chick_type')
            quantity = int(request.POST.get('quantity'))
            notes = (request.POST.get('notes') or '').strip()

            farmer = get_object_or_404(Farmer, id=farmer_id)
            farmer_type = farmer.farmer_type  # starter / returning

            # ---- 4-month rule (use 120 days) ----
            FOUR_MONTHS = timedelta(days=120)
            last_req = (ChickRequest.objects
                        .filter(farmer=farmer)
                        .order_by('-submitted_on', '-id')
                        .first())

            if last_req:
                cutoff = last_req.submitted_on + FOUR_MONTHS
                today = date.today()
                if today < cutoff:
                    messages.error(
                        request,
                        f"{farmer.name} last requested on {last_req.submitted_on:%b %d, %Y}. "
                        f"Next eligible date is {cutoff:%b %d, %Y}."
                    )
                    return redirect(reverse('submit_chick_request') + '?tab=chick')

            # ---- quantity caps by farmer type ----
            if farmer_type == 'starter' and quantity > 100:
                messages.error(request, "Starter farmers can only request up to 100 chicks.")
            elif farmer_type == 'returning' and quantity > 500:
                messages.error(request, "Returning farmers can only request up to 500 chicks.")
            else:
                ChickRequest.objects.create(
                    farmer=farmer,
                    chick_type=chick_type,
                    quantity=quantity,
                    status='pending',
                    notes=notes
                )
                messages.success(request, f"Request for {quantity} {chick_type} chicks submitted successfully.")
                return redirect(reverse('submit_chick_request') + '?tab=chick')

        elif form_type == 'feed_request':
            # Feed Request Handling
            farmer_id = request.POST.get('farmer')
            feed_type = request.POST.get('feed_type')
            quantity_bags = int(request.POST.get('quantity_bags'))
            approval_notes = (request.POST.get('approval_notes') or '').strip()

            farmer = get_object_or_404(Farmer, id=farmer_id)

            from home.models import User
            default_user = User.objects.get(username='peter')

            FeedRequest.objects.create(
                farmer=farmer,
                feed_type=feed_type,
                quantity_bags=quantity_bags,
                requested_by=request.user,  # when auth is ready
                #requested_by=default_user,
                approval_notes=approval_notes,
                status='pending'
            )
            messages.success(request, f"Request for {quantity_bags} bags of {feed_type} feed submitted successfully.")
            return redirect(reverse('submit_chick_request') + '?tab=feed')

    all_requests = ChickRequest.objects.all().order_by('-submitted_on')

    # temporary: filter by default user until auth is ready
    from home.models import User
    default_user = User.objects.get(username=request.user)
    feed_requests = FeedRequest.objects.filter(requested_by=request.user).order_by('-submitted_on')

    return render(request, 'sales/submit_request.html', {
        'farmers': farmers,
        'all_requests': all_requests,
        'feed_requests': feed_requests,
    })

def history_view(request):
    """
    Search a farmer by NIN (exact, case-insensitive) or by name (icontains),
    then show their chick + feed request history.
    """
    q = (request.GET.get('q') or '').strip()
    farmer = None
    chick_requests = []
    feed_requests = []

    if q:
        # Prefer exact NIN match first
        farmer = Farmer.objects.filter(nin__iexact=q).first()
        if not farmer:
            # Fallback: partial name match (first result)
            farmer = Farmer.objects.filter(name__icontains=q).order_by('name').first()

        if farmer:
            chick_requests = (ChickRequest.objects
                              .filter(farmer=farmer)
                              .order_by('-submitted_on'))
            feed_requests = (FeedRequest.objects
                             .filter(farmer=farmer)
                             .order_by('-submitted_on'))

    context = {
        'query': q,
        'farmer': farmer,
        'chick_requests': chick_requests,
        'feed_requests': feed_requests,
    }
    return render(request, 'sales/history.html', context)


def pickup_view(request):
    approved_unpicked = (
        ChickRequest.objects
        .filter(status='approved', is_picked=False)
        .select_related('farmer')
        .order_by('-approval_date')
    )
    return render(request, 'sales/pickup.html', {'requests': approved_unpicked})


def peek_fifo_cost(qty_needed, feed_type=None, with_breakdown=False):
    """
    Generic FIFO cost peek.
    Returns (enough: bool, total: Decimal, breakdown: list[dict])
    """
    remaining = int(qty_needed or 0)
    total = Decimal('0')
    breakdown = []

    qs = FeedStock.objects.filter(quantity_bags__gt=0).order_by('arrival_date')
    if feed_type:
        qs = qs.filter(feed_type=feed_type)

    for s in qs:
        if remaining <= 0:
            break
        take = min(s.quantity_bags, remaining)
        if take <= 0:
            continue
        unit = s.sale_price  # Decimal
        subtotal = unit * Decimal(take)
        total += subtotal
        if with_breakdown:
            breakdown.append({
                'date': s.arrival_date,
                'bags': take,
                'unit_price': unit,
                'subtotal': subtotal,
                'manufacturer': getattr(s.manufacturer, 'name', None),
                'supplier': getattr(s.supplier, 'name', None),
            })
        remaining -= take

    return (remaining == 0, total, breakdown if with_breakdown else [])


def _peek_fifo_feed_cost(bags_needed=2):
    """Back-compat shim: use the new peek_fifo_cost but keep old call sites working."""
    enough, total, _ = peek_fifo_cost(qty_needed=bags_needed, feed_type=None, with_breakdown=False)
    return (enough, total)


def mark_request_as_picked(request, request_id):
    chick_request = get_object_or_404(ChickRequest, id=request_id, status='approved', is_picked=False)
    farmer = chick_request.farmer

    # constants
    CHICK_PRICE = Decimal('1650')

    # Compute expected amounts (GET and POST use same numbers)
    expected_chick_total = CHICK_PRICE * Decimal(chick_request.quantity)
    enough_feeds, expected_initial_feeds_total = _peek_fifo_feed_cost(bags_needed=2)
    grand_total = expected_chick_total + (expected_initial_feeds_total if enough_feeds else Decimal('0'))

    if request.method == 'POST':
        notes = (request.POST.get('pickup_notes') or '').strip()

        # Robust parse for optional fields (blank -> 0)
        try:
            paid_chicks = Decimal(request.POST.get('paid_chicks') or 0)
        except Exception:
            paid_chicks = Decimal('0')
        try:
            paid_feeds = Decimal(request.POST.get('paid_feeds') or 0)
        except Exception:
            paid_feeds = Decimal('0')

        # Step 1: Deduct chick stock (FIFO)
        remaining_chicks = chick_request.quantity
        chick_stocks = ChickStock.objects.filter(
            chick_type=chick_request.chick_type, quantity__gt=0
        ).order_by('recorded_on')

        for stock in chick_stocks:
            if remaining_chicks == 0:
                break
            deduct = min(stock.quantity, remaining_chicks)
            stock.quantity -= deduct
            remaining_chicks -= deduct
            stock.save()

        if remaining_chicks > 0:
            messages.error(request, f"Not enough chick stock available for {chick_request.get_chick_type_display()}.")
            return redirect('sales_pickup')

        # Step 2: Allocate 2 bags of feed (mandatory, deferred by policy)
        feed_bags_needed = 2
        feed_stocks = FeedStock.objects.filter(quantity_bags__gt=0).order_by('arrival_date')

        # Use a single recorded_by for all entries (until auth)
        default_user = User.objects.get(username='peter')  # replace with request.user when ready

        created_distributions = []
        for stock in feed_stocks:
            if feed_bags_needed == 0:
                break
            take = min(stock.quantity_bags, feed_bags_needed)
            if take <= 0:
                continue
            stock.quantity_bags -= take
            stock.save()

            fd = FeedDistribution.objects.create(
                farmer=farmer,
                feed_stock=stock,
                distribution_type='initial',
                quantity_bags=take,
                due_date=date.today() + timedelta(days=60),  # 2 months deferral
                recorded_by=request.user,  # request.user
                notes='Auto-issued during chick pickup',
            )
            created_distributions.append(fd)
            feed_bags_needed -= take

        if feed_bags_needed > 0:
            messages.warning(request, f"Only partial feed allocation completed. {feed_bags_needed} bag(s) could not be issued due to low stock.")

        # Step 3: Save Payment(s)
        # Chicks — expected to be paid now
        if paid_chicks > 0:
            Payment.objects.create(
                farmer=farmer,
                amount=paid_chicks,
                payment_for='chicks',
                payment_date=date.today(),
                received_by=default_user,  # request.user
                notes=f"Paid for {chick_request.quantity} chicks during pickup",
            )

        # Initial feeds — OPTIONAL at pickup (allowed to be 0)
        if paid_feeds > 0:
            # Optionally link to the first distribution we just created (if any)
            related_fd = created_distributions[0] if created_distributions else None
            Payment.objects.create(
                farmer=farmer,
                amount=paid_feeds,
                payment_for='feeds',
                related_feed_distribution=related_fd,
                payment_date=date.today(),
                received_by=default_user,  # request.user
                notes="Initial 2-bag feed payment at pickup",
            )

        # Step 4: Mark as picked
        chick_request.is_picked = True
        chick_request.picked_on = timezone.now().date()
        chick_request.pickup_notes = notes
        chick_request.save()

        # Step 5: Promote starter -> returning
        if farmer.farmer_type == 'starter':
            farmer.farmer_type = 'returning'
            farmer.save()

        messages.success(request, f"Request #{chick_request.id} marked as picked. Stock updated and payments recorded.")
        return redirect('sales_pickup')

    # GET — render with expected totals
    return render(request, 'sales/mark_pickup.html', {
        'request': chick_request,
        'expected_chick_total': int(expected_chick_total),
        'expected_initial_feeds_total': int(expected_initial_feeds_total) if enough_feeds else None,
        'grand_total': int(grand_total) if enough_feeds else int(expected_chick_total),
        'feeds_available_for_two': enough_feeds,
    })



def feed_pickup_view(request):
    """List approved & not picked feed requests for pickup."""
    to_pick = (FeedRequest.objects
               .filter(status='approved', pickup_status='not_picked')
               .select_related('farmer')
               .order_by('-approved_on'))
    return render(request, 'sales/feed_pickup.html', {'requests': to_pick})

def mark_feed_request_as_picked(request, request_id):
    """Confirm pickup for an approved feed request (extra purchase). Payment required upfront."""
    feed_req = get_object_or_404(
        FeedRequest, id=request_id, status='approved', pickup_status='not_picked'
    )
    farmer = feed_req.farmer

    # 1) Compute total + breakdown from FIFO (used for GET display and POST validation)
    enough, expected_total, breakdown = peek_fifo_cost(
        qty_needed=feed_req.quantity_bags,
        feed_type=feed_req.feed_type,
        with_breakdown=True
    )
    if not enough:
        messages.error(request, f"Insufficient {feed_req.feed_type} stock for {feed_req.quantity_bags} bag(s).")
        return redirect('sales_feed_pickup')

    if request.method == 'POST':
        notes = (request.POST.get('pickup_notes') or '').strip()
        try:
            paid_feeds = Decimal(request.POST.get('paid_feeds') or 0)
        except Exception:
            paid_feeds = Decimal('0')

        # Rule: extra feed purchases must be fully paid before pickup
        if paid_feeds < expected_total:
            messages.error(
                request,
                f"Payment is insufficient. Expected UGX {int(expected_total):,} for {feed_req.quantity_bags} bag(s)."
            )
            return redirect('mark_feed_request_as_picked', request_id=feed_req.id)

        # 2) Deduct stock FIFO and create FeedDistribution purchase records
        remaining = feed_req.quantity_bags
        stocks = FeedStock.objects.filter(
            feed_type=feed_req.feed_type, quantity_bags__gt=0
        ).order_by('arrival_date')

        default_user = User.objects.get(username='peter')  # replace with request.user later

        for stock in stocks:
            if remaining <= 0:
                break
            take = min(stock.quantity_bags, remaining)
            if take <= 0:
                continue

            stock.quantity_bags -= take
            stock.save()

            FeedDistribution.objects.create(
                farmer=farmer,
                feed_stock=stock,
                distribution_type='purchase',
                quantity_bags=take,
                recorded_by=request.user,  # request.user
                notes=f"Purchase for FeedRequest #{feed_req.id}" + (f". {notes}" if notes else "")
            )
            remaining -= take

        if remaining > 0:
            messages.error(request, "Unexpected stock shortfall during deduction. No changes recorded.")
            return redirect('sales_feed_pickup')

        # 3) Record payment
        Payment.objects.create(
            farmer=farmer,
            amount=paid_feeds,
            payment_for='feeds',
            payment_date=date.today(),
            received_by=default_user,  # request.user
            notes=f"Payment for {feed_req.quantity_bags} bag(s) {feed_req.feed_type} at pickup (FeedRequest #{feed_req.id})"
        )

        # 4) Mark feed request as picked
        feed_req.pickup_status = 'picked'
        feed_req.picked_on = timezone.now()
        feed_req.save(update_fields=['pickup_status', 'picked_on'])

        messages.success(
            request,
            f"FeedRequest #{feed_req.id} picked. UGX {int(paid_feeds):,} received and stock updated."
        )
        return redirect('sales_feed_pickup')

    # GET — show request details, expected total, and breakdown
    return render(request, 'sales/mark_feed_pickup.html', {
        'req': feed_req,
        'expected_total': expected_total,   # Decimal; template will format
        'breakdown': breakdown,
    })





