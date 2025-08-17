# Standard library
import json
from decimal import Decimal
from datetime import date, timedelta
from collections import defaultdict

# Django core
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import (
    Sum, Q, F, Case, When, Value, DecimalField
)
from django.urls import reverse

# Local apps
from home.models import User, Training, Announcement, FarmerTip, QuoteOfTheWeek
from manager.models import ChickStock, ChickAllocation
from sales.models import (
    ChickRequest, Farmer, FeedStock, FeedDistribution,
    Manufacturer, Supplier, Payment, FeedRequest
)

# Create your views here.
#============================
# 1) DASHBOARD
#============================

@login_required
def dashboard_view(request):
    """
    Manager dashboard with richer, actionable context.
    - Totals + per-type splits
    - Weekly stats
    - Chick & feed stock breakdowns
    - Revenue splits (chicks vs feeds; 'both' split 50/50)
    - Upcoming trainings
    - Operational alerts (low stock, stale pending, unpicked approvals, expiring feeds, dues soon)
    - Last 5 approvals mini-table
    """
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    month_start = today.replace(day=1)

    # ---------------------- Picked (sold) ----------------------
    picked_qs = ChickRequest.objects.filter(is_picked=True)
    total_chicks_sold = picked_qs.aggregate(total=Sum('quantity'))['total'] or 0

    # Sold by chick type (overall)
    sold_by_type_qs = picked_qs.values('chick_type').annotate(total=Sum('quantity'))
    chicks_sold_by_type = {
        'broiler_local': 0,
        'broiler_exotic': 0,
        'layer_local': 0,
        'layer_exotic': 0,
    }
    for row in sold_by_type_qs:
        chicks_sold_by_type[row['chick_type']] = row['total'] or 0

    # Weekly (picked this week)
    weekly_picked = picked_qs.filter(picked_on__gte=week_start)
    chicks_this_week = weekly_picked.aggregate(total=Sum('quantity'))['total'] or 0

    week_by_type_qs = weekly_picked.values('chick_type').annotate(total=Sum('quantity'))
    chicks_week_by_type = {
        'broiler_local': 0,
        'broiler_exotic': 0,
        'layer_local': 0,
        'layer_exotic': 0,
    }
    for row in week_by_type_qs:
        chicks_week_by_type[row['chick_type']] = row['total'] or 0

    # ---------------------- Requests / farmers ----------------------
    pending_requests = ChickRequest.objects.filter(status='pending').count()
    total_farmers = Farmer.objects.count()
    approved_this_month = ChickRequest.objects.filter(status='approved', approval_date__gte=month_start).count()

    # ---------------------- Chick stock (by type) ----------------------
    stock_by_type_qs = ChickStock.objects.values('chick_type').annotate(total=Sum('quantity'))
    stock_dict = {
        'broiler_local': 0,
        'broiler_exotic': 0,
        'layer_local': 0,
        'layer_exotic': 0,
    }
    for row in stock_by_type_qs:
        stock_dict[row['chick_type']] = row['total'] or 0
    total_remaining_stock = sum(stock_dict.values())

    # ---------------------- Feed stock (by feed_type) ----------------------
    feed_stock_by_type_qs = FeedStock.objects.values('feed_type').annotate(total=Sum('quantity_bags'))
    feed_stock_by_type = {'starter': 0, 'grower': 0, 'finisher': 0}
    for row in feed_stock_by_type_qs:
        feed_stock_by_type[row['feed_type']] = row['total'] or 0
    total_feed_stock = sum(feed_stock_by_type.values())

    # ---------------------- Revenue via Payment (Decimal-safe) ----------------------
    money = DecimalField(max_digits=12, decimal_places=2)
    ZERO = Decimal('0')
    TWO = Decimal('2')

    pay_all = Payment.objects.all()
    agg_all = pay_all.aggregate(
        chicks=Sum(Case(When(payment_for='chicks', then=F('amount')), default=Value(ZERO), output_field=money)),
        feeds =Sum(Case(When(payment_for='feeds',  then=F('amount')), default=Value(ZERO), output_field=money)),
        both  =Sum(Case(When(payment_for='both',   then=F('amount')), default=Value(ZERO), output_field=money)),
    )
    both_all = agg_all['both'] or ZERO
    total_revenue_breakdown = {
        'chicks': (agg_all['chicks'] or ZERO) + (both_all / TWO),
        'feeds':  (agg_all['feeds']  or ZERO) + (both_all / TWO),
    }
    total_revenue = total_revenue_breakdown['chicks'] + total_revenue_breakdown['feeds']

    # Weekly revenue
    pay_week = pay_all.filter(payment_date__gte=week_start)
    agg_week = pay_week.aggregate(
        chicks=Sum(Case(When(payment_for='chicks', then=F('amount')), default=Value(ZERO), output_field=money)),
        feeds =Sum(Case(When(payment_for='feeds',  then=F('amount')), default=Value(ZERO), output_field=money)),
        both  =Sum(Case(When(payment_for='both',   then=F('amount')), default=Value(ZERO), output_field=money)),
    )
    both_week = agg_week['both'] or ZERO
    revenue_week_breakdown = {
        'chicks': (agg_week['chicks'] or ZERO) + (both_week / TWO),
        'feeds':  (agg_week['feeds']  or ZERO) + (both_week / TWO),
    }
    revenue_this_week = revenue_week_breakdown['chicks'] + revenue_week_breakdown['feeds']

    # ---------------------- Upcoming trainings ----------------------
    upcoming_trainings = Training.objects.filter(date__gte=today).order_by('date')[:4]

    # ---------------------- Operational Alerts (actionable) ----------------------
    LOW_CHICK_THRESHOLD = 50   # tweak as needed

    # Low chick stock by type
    low_chick_stock = []
    for ctype, qty in (stock_dict or {}).items():
        if (qty or 0) < LOW_CHICK_THRESHOLD:
            low_chick_stock.append({"type": ctype, "qty": qty or 0})
    low_chick_stock.sort(key=lambda x: x["qty"])  # smallest first

    # Unpicked approvals older than 3 days
    unpicked_qs = (
        ChickRequest.objects
        .filter(status='approved', is_picked=False, approval_date__lt=today - timedelta(days=3))
        .select_related('farmer')
        .order_by('-approval_date')[:5]
    )
    unpicked_approvals = [
        {
            "id": r.id,
            "farmer": r.farmer.name,
            "days": (today - (r.approval_date or month_start)).days
        }
        for r in unpicked_qs
    ]

    # Pending requests older than 48 hours
    pending_qs = (
        ChickRequest.objects
        .filter(status='pending', submitted_on__lt=today - timedelta(days=2))
        .select_related('farmer')
        .order_by('-submitted_on')[:5]
    )
    pending_stale = [
        {
            "id": r.id,
            "farmer": r.farmer.name,
            # submitted_on is a DateField in your model, so we approximate hours
            "days": (today - r.submitted_on).days * 24,
        }
        for r in pending_qs
    ]

    # Feeds expiring within 14 days (detailed list)
    feed_expiring_qs = (
        FeedStock.objects
        .filter(expiry_date__isnull=False, expiry_date__lte=today + timedelta(days=14))
        .order_by('expiry_date')[:5]
    )
    feed_expiring = [
        {"feed_type": f.feed_type, "bags": f.quantity_bags or 0, "expiry": f.expiry_date}
        for f in feed_expiring_qs
    ]

    # Feed distributions due within 7 days (top 5)
    feed_due_qs = (
        FeedDistribution.objects
        .filter(due_date__isnull=False, due_date__lte=today + timedelta(days=7))
        .select_related('farmer')
        .order_by('due_date')[:5]
    )
    feed_due_soon_list = [
        {"farmer": fd.farmer.name, "bags": getattr(fd, 'quantity_bags', 0) or 0, "due": fd.due_date}
        for fd in feed_due_qs
    ]

    alerts = {
        "counts": {
            "unpicked_over_3d": len(unpicked_approvals),
            "pending_over_48h": len(pending_stale),
            "low_chick_types": len(low_chick_stock),
        },
        "low_chick_stock": low_chick_stock,
        "unpicked_approvals": unpicked_approvals,
        "pending_stale": pending_stale,
        "feed_expiring": feed_expiring,
        "feed_due_soon": feed_due_soon_list,
    }

    # ---------------------- Last 5 approvals (for mini-table) ----------------------
    last_approvals = (
        ChickRequest.objects
        .filter(status='approved')
        .select_related('farmer')
        .order_by('-approval_date', '-id')[:5]
    )

    context = {
        # Totals
        'total_chicks_sold': total_chicks_sold,
        'total_revenue': total_revenue,

        # Per-type totals
        'chicks_sold_by_type': chicks_sold_by_type,

        # Weekly
        'chicks_this_week': chicks_this_week,
        'revenue_this_week': revenue_this_week,
        'chicks_week_by_type': chicks_week_by_type,

        # Revenue splits
        'total_revenue_breakdown': total_revenue_breakdown,
        'revenue_week_breakdown': revenue_week_breakdown,

        # Requests / farmers
        'pending_requests': pending_requests,
        'total_farmers': total_farmers,
        'approved_this_month': approved_this_month,

        # Chick stock
        'stock_dict': stock_dict,
        'total_remaining_stock': total_remaining_stock,

        # Feed stock
        'total_feed_stock': total_feed_stock,
        'feed_stock_by_type': feed_stock_by_type,

        # Events
        'upcoming_trainings': upcoming_trainings,

        # Alerts payload for the Operational Alerts card
        'alerts': alerts,

        # Mini-table
        'last_approvals': last_approvals,

        # Username display
        'username': request.user.username,
    }
    return render(request, 'manager/dashboard.html', context)

#======================================
# 2) CHICK STOCK & CHICK REQUESTS
#======================================

@login_required
def chick_stock_view(request):
    if request.method == 'POST':
        chick_type = request.POST.get('chick_type')
        quantity = request.POST.get('quantity')
        age_days = request.POST.get('age_days')
        notes = request.POST.get('notes')

        # Basic Validations
        if not chick_type or not quantity or not age_days:
            messages.error(request, "Please fill in all required fields.")
        else:
            ChickStock.objects.create(
                chick_type = chick_type,
                quantity = quantity,
                age_days = age_days,
                notes = notes,
            )
            messages.success(request, f"{quantity} {chick_type} added to the stock successfully!")
        return redirect('manager_chick_stock')
    
     # Pagination for full stock entries (Tab 2)
    all_stock = ChickStock.objects.all().order_by('-recorded_on')
    paginator = Paginator(all_stock, 25)

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Chick type display labels
    TYPE_LABELS = {
        'broiler_local': 'Broiler - Local',
        'broiler_exotic': 'Broiler - Exotic',
        'layer_local': 'Layer - Local',
        'layer_exotic': 'Layer - Exotic',
    }

    # Summary by type + aging status
    summary = []
    stock_by_type = defaultdict(lambda: {'total': 0, 'available': 0, 'aging': 0, 'expiring': 0})

    for batch in all_stock:
        s = stock_by_type[batch.chick_type]
        s['total'] += batch.quantity
        if batch.age_days <= 14:
            s['available'] += batch.quantity
        elif batch.age_days <= 21:
            s['aging'] += batch.quantity
        else:
            s['expiring'] += batch.quantity

    for chick_type, stats in stock_by_type.items():
        summary.append({
            'label': TYPE_LABELS.get(chick_type, chick_type.replace('_', ' ').title()),
            'total': stats['total'],
            'available': stats['available'],
            'aging': stats['aging'],
            'expiring': stats['expiring'],
        })

    context = {
        'stock': all_stock,
        'page_obj': page_obj,
        'summary': summary,
    }

    return render(request, 'manager/stock.html', context)

@login_required
def review_chick_requests(request):
    tab = request.GET.get('tab', 'pending')
    q = (request.GET.get('q') or '').strip()

    pending_qs = (ChickRequest.objects.filter(status='pending')
                  .select_related('farmer', 'approved_by').order_by('-submitted_on'))
    approved_qs = (ChickRequest.objects.filter(status='approved')
                  .select_related('farmer', 'approved_by').order_by('-approval_date', '-id'))
    history_qs = (ChickRequest.objects.exclude(status='pending')
                  .select_related('farmer', 'approved_by').order_by('-submitted_on', '-id'))

    if q:
        if tab == 'pending':
            pending_qs = pending_qs.filter(
                Q(farmer__name__icontains=q) |
                Q(farmer__nin__icontains=q) |
                Q(id__icontains=q) |
                Q(chick_type__icontains=q)
            )
        elif tab == 'approved':
            approved_qs = approved_qs.filter(
                Q(farmer__name__icontains=q) |
                Q(farmer__nin__icontains=q) |
                Q(id__icontains=q) |
                Q(chick_type__icontains=q) |
                Q(approval_date__icontains=q)
            )
        elif tab == 'history':
            history_qs = history_qs.filter(
                Q(farmer__name__icontains=q) |
                Q(farmer__nin__icontains=q) |
                Q(id__icontains=q) |
                Q(chick_type__icontains=q) |
                Q(submitted_on__icontains=q)
            )

    # annotate history for display
    today = timezone.localdate()  # use local date to avoid TZ off-by-one
    history_requests = list(history_qs)
    for r in history_requests:
        r.expected_chicks_amount = r.quantity * 1650
        r.chicks_paid_today = 0
        if r.is_picked and r.picked_on:
            r.chicks_paid_today = (Payment.objects
                                   .filter(farmer=r.farmer, payment_for='chicks', payment_date=r.picked_on)
                                   .aggregate(s=Sum('amount'))['s'] or 0)
        r.chicks_balance = r.expected_chicks_amount - r.chicks_paid_today
        r.feeds_allocated_bags = 0
        r.feeds_due_date = None
        r.feeds_status = None
        if r.is_picked and r.picked_on:
            dists = FeedDistribution.objects.filter(
                farmer=r.farmer, distribution_type='initial', distribution_date=r.picked_on
            )
            r.feeds_allocated_bags = dists.aggregate(s=Sum('quantity_bags'))['s'] or 0
            r.feeds_due_date = dists.order_by('-due_date').values_list('due_date', flat=True).first()
            feeds_paid_amount = (Payment.objects
                                 .filter(farmer=r.farmer, payment_for='feeds', payment_date__gte=r.picked_on)
                                 .aggregate(s=Sum('amount'))['s'] or 0)
            if feeds_paid_amount and r.feeds_allocated_bags:
                r.feeds_status = 'paid'
            elif r.feeds_due_date:
                r.feeds_status = 'overdue' if r.feeds_due_date < today else 'due'
            else:
                r.feeds_status = None

    # ---------- Build batch JSON (prefer model.age_days; fallback to recorded_on) ----------
    def to_date(d):
        if d is None:
            return None
        try:
            return d.date() if hasattr(d, 'hour') else d
        except Exception:
            return None

    # Pull age_days directly from the model to avoid any drift
    batches = (ChickStock.objects
               .filter(quantity__gt=0)
               .values('id', 'chick_type', 'quantity', 'recorded_on', 'age_days')
               .order_by('chick_type', 'recorded_on', 'id'))

    batch_map = {}
    for b in batches:
        rec_date = to_date(b.get('recorded_on'))
        # Use stored age_days if present; otherwise compute from recorded_on
        if b.get('age_days') is not None:
            age_days = int(b['age_days'])
        else:
            today_local = timezone.localdate()
            age_days = (today_local - rec_date).days if rec_date else None

        batch_map.setdefault(b['chick_type'], []).append({
            'id': b['id'],
            'chick_type': b['chick_type'],
            'quantity': b['quantity'],
            'recorded_on': rec_date.isoformat() if rec_date else None,
            'age_days': age_days,
        })

    batch_json = mark_safe(json.dumps(batch_map, cls=DjangoJSONEncoder))

    context = {
        'pending_requests': pending_qs,
        'approved_requests': approved_qs,
        'history_requests': history_requests,
        'active_tab': tab,
        'q': q,
        'batch_json': batch_json,
    }
    return render(request, 'manager/requests.html', context)

@login_required
def approve_reject_request(request, request_id):
    """
    Approve/Reject a ChickRequest.
    - Stores manager decision metadata (decision_note/by/at) for both actions.
    - On approve: validates explicit batch allocations and decrements stock atomically.
    """
    req = get_object_or_404(ChickRequest, id=request_id)

    if request.method != 'POST':
        return redirect('review_chick_requests')

    action = request.POST.get('action')
    decision_note = (request.POST.get('decision_note') or '').strip()

    # ---------- REJECT ----------
    if action == 'reject':
        req.status = 'rejected'  # matches STATUS_CHOICES
        update_fields = ['status']

        # Save decision note if the field exists; otherwise fall back to `notes`
        if hasattr(req, 'decision_note'):
            req.decision_note = decision_note or None
            update_fields.append('decision_note')
        elif decision_note and hasattr(req, 'notes'):
            req.notes = decision_note
            update_fields.append('notes')

        # Optional metadata if these fields exist on your model
        if hasattr(req, 'decision_by'):
            req.decision_by = request.user if request.user.is_authenticated else None
            update_fields.append('decision_by')

        if hasattr(req, 'decision_at'):
            req.decision_at = timezone.now()
            update_fields.append('decision_at')

        req.save(update_fields=list(set(update_fields)))
        messages.warning(
            request,
            f"Request #REQ{req.id} rejected" + (f": {decision_note}" if decision_note else "")
        )
    return redirect('/manager/requests/?tab=pending')


    # Must be approve from here on
    if action != 'approve':
        messages.error(request, 'Invalid action.')
        return redirect('/manager/requests/?tab=pending')

    # ---------- APPROVE WITH EXPLICIT ALLOCATIONS ----------
    requested_type = req.chick_type
    requested_qty  = req.quantity

    # allocations[] entries come as "<stock_id>:<qty>"
    raw_allocs = request.POST.getlist('allocations[]')
    parsed = []
    total_alloc = 0
    for item in raw_allocs:
        try:
            sid_str, q_str = item.split(':', 1)
            sid = int(sid_str)
            q = int(q_str)
            if q > 0:
                parsed.append((sid, q))
                total_alloc += q
        except Exception:
            # ignore any malformed items
            pass

    if total_alloc != requested_qty or not parsed:
        messages.error(
            request,
            f"Allocation mismatch. You allocated {total_alloc} chicks, but the request needs {requested_qty}."
        )
        return redirect('/manager/requests/?tab=pending')

    # Optional max age gate
    max_age_days = request.POST.get('max_age_days')
    try:
        max_age_days = int(max_age_days) if max_age_days else None
    except ValueError:
        max_age_days = None

    date_field = 'recorded_on'  # adjust if your stock age comes from a different field
    today = timezone.localdate()

    with transaction.atomic():
        # Type-level availability check
        available = (ChickStock.objects
                     .filter(chick_type=requested_type, quantity__gt=0)
                     .aggregate(total=Sum('quantity'))['total'] or 0)
        if requested_qty > available:
            messages.error(
                request,
                f"Insufficient stock for {requested_type.replace('_',' ').title()}. "
                f"Requested: {requested_qty}, Available: {available}"
            )
            transaction.set_rollback(True)
            return redirect('/manager/requests/?tab=pending')

        # Validate each batch and decrement
        for stock_id, qty in parsed:
            stock = (ChickStock.objects
                     .select_for_update()
                     .filter(id=stock_id, chick_type=requested_type)
                     .first())
            if not stock:
                messages.error(request, f"Selected stock #{stock_id} not found for {requested_type}.")
                transaction.set_rollback(True)
                return redirect('/manager/requests/?tab=pending')

            if stock.quantity < qty:
                messages.error(
                    request,
                    f"Stock #{stock.id} has only {stock.quantity} chicks; you allocated {qty}."
                )
                transaction.set_rollback(True)
                return redirect('/manager/requests/?tab=pending')

            # Age check (supports date or datetime on recorded_on)
            stock_date = getattr(stock, date_field, None)
            if max_age_days is not None and stock_date:
                stock_d = stock_date if hasattr(stock_date, 'year') and not hasattr(stock_date, 'hour') else stock_date.date()
                age_days = (today - stock_d).days
                if age_days > max_age_days:
                    messages.error(
                        request,
                        f"Stock #{stock.id} is {age_days} days old (> {max_age_days} days)."
                    )
                    transaction.set_rollback(True)
                    return redirect('/manager/requests/?tab=pending')

            # Decrement and record allocation
            stock.quantity -= qty
            stock.save(update_fields=['quantity'])
            ChickAllocation.objects.create(request=req, stock=stock, quantity=qty)

        # Mark approved + approval metadata + decision metadata
        req.status = 'approved'
        req.approval_date = today
        req.approved_by = request.user if request.user.is_authenticated else None
        req.save(update_fields=[
            'status', 'approval_date', 'approved_by',
            'decision_note', 'decision_by', 'decision_at'
        ])

    messages.success(
        request,
        f"Approved REQ{req.id} with batch allocations "
        f"({len(parsed)} batch{'es' if len(parsed)!=1 else ''})."
    )
    return redirect('/manager/requests/?tab=pending')

@login_required
def reject_request(request, pk=None):
    # Support both routes:
    # - /requests/<pk>/reject/  (pk in path)
    # - /requests/reject/       (id in POST: request_id)
    if request.method != "POST":
        return redirect(f"{reverse('review_chick_requests')}?tab=pending")

    target_id = pk or request.POST.get("request_id")
    req = get_object_or_404(ChickRequest, pk=target_id)

    reason = (request.POST.get("rejection_reason")
              or request.POST.get("decision_note")
              or "").strip()

    # Use your model's existing fields
    req.status = "rejected"

    # Save the manager reason into notes (append if rep already wrote something)
    if reason:
        if req.notes:
            req.notes = f"{req.notes}\n\n[Manager rejection] {reason}"
        else:
            req.notes = reason

    # If you want to track who rejected / when and such fields exist, they’ll be set
    if hasattr(req, "approved_by") and req.approved_by is None and request.user.is_authenticated:
        # not required, but safe if you want something in there
        pass

    # Persist
    if reason:
        req.save(update_fields=["status", "notes"])
    else:
        req.save(update_fields=["status"])

    messages.warning(request, f"Request #REQ{req.id} rejected" + (f": {reason}" if reason else ""))

    return redirect(f"{reverse('review_chick_requests')}?tab=pending")




#=================================================
# 3) FEEDS (STOCK, DISTRIBUTION & FEED SOURCES)
#=================================================

@login_required
def feeds_view(request):
    manufacturers = Manufacturer.objects.all()
    suppliers = Supplier.objects.all()
    feed_stocks = FeedStock.objects.all().order_by('-arrival_date')
    distributions = FeedDistribution.objects.select_related('farmer', 'feed_stock', 'recorded_by')

    query = request.GET.get('q')
    distributions = FeedDistribution.objects.select_related('farmer', 'feed_stock', 'recorded_by')

    if query:
        distributions = distributions.filter(
            Q(farmer__name__icontains=query) |
            Q(feed_stock__feed_type__icontains=query)
        )
    
    context = {
        'feed_stocks': feed_stocks,
        'manufacturers': manufacturers,
        'suppliers': suppliers,
        'distributions': distributions,
    }
    
    return render(request, 'manager/feeds.html', context)

@login_required
def manage_feed_sources(request):
    if request.method == 'POST':
        if 'add_manufacturer' in request.POST:
            name = request.POST.get('manufacturer_name').strip()
            if name:
                Manufacturer.objects.create(name=name)
                messages.success(request, "Manufacturer added.")
        elif 'add_supplier' in request.POST:
            name = request.POST.get('supplier_name').strip()
            contact = request.POST.get('supplier_contact').strip()
            if name:
                Supplier.objects.create(name=name, contact=contact)
                messages.success(request, "Supplier added.")

        return redirect('manage_feed_sources')

    manufacturers = Manufacturer.objects.all()
    suppliers = Supplier.objects.all()
    return render(request, 'sales/manage_feeds_sources.html', {
        'manufacturers': manufacturers,
        'suppliers': suppliers,
    })

# View to handle displaying the form and saving feed_stock on post
@login_required
def add_feed_stock(request):
    manufacturers = Manufacturer.objects.all()
    suppliers = Supplier.objects.all()

    if request.method == 'POST':
        feed_type = request.POST.get('feed_type')
        manufacturer_id = request.POST.get('manufacturer')
        supplier_id = request.POST.get('supplier')
        quantity_bags = request.POST.get('quantity_bags')
        purchase_price = request.POST.get('purchase_price')
        sale_price = request.POST.get('sale_price')
        arrival_date = request.POST.get('arrival_date')
        expiry_date = request.POST.get('expiry_date')
        notes = request.POST.get('notes', '')

        # Validation check
        if not all([feed_type, manufacturer_id, supplier_id, quantity_bags, purchase_price, sale_price, arrival_date]):
            messages.error(request, "Please fill in all required fields.")
            return redirect('add_feed_stock')

        # Convert and save
        manufacturer = Manufacturer.objects.get(id=manufacturer_id)
        supplier = Supplier.objects.get(id=supplier_id)

        FeedStock.objects.create(
            feed_type = feed_type,
            manufacturer = manufacturer,
            supplier = supplier,
            quantity_bags = quantity_bags,
            purchase_price = purchase_price,
            sale_price = sale_price,
            arrival_date = arrival_date,
            expiry_date = expiry_date,
            notes = notes,            
        )

        messages.success(request, f"{quantity_bags} bags of {feed_type} feed added to stock successfully.")
        return redirect('manager_feeds')

    return redirect('manager_feeds')

@login_required
def add_manufacturer(request):
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        contact_person = (request.POST.get('contact_person') or '').strip()
        phone_number = (request.POST.get('phone_number') or '').strip()
        location = (request.POST.get('location') or '').strip()
        if name:
            Manufacturer.objects.create(
                name=name,
                contact_person = contact_person,
                phone_number = phone_number,
                location=location,
                )
            messages.success(request, f"Manufacturer '{name}' added successfully.")
    return redirect('manager_feeds')  # or wherever your main feeds page view is named

def add_supplier(request):
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        contact_person = (request.POST.get('contact_person') or '').strip()
        phone_number = (request.POST.get('phone_number') or '').strip()
        location = (request.POST.get('location') or '').strip()
        if name:
            Supplier.objects.create(
                name=name,
                contact_person=contact_person,
                phone_number=phone_number,
                location=location,
                )
            messages.success(request, f"Supplier '{name}' added successfully.")
    return redirect('manager_feeds')



def delete_manufacturer(request, pk):
    manufacturer = get_object_or_404(Manufacturer, pk=pk)
    manufacturer.delete()
    messages.success(request, f"Manufacturer '{manufacturer.name}' deleted successfully.")
    return redirect('manager_feeds')

def delete_supplier(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    supplier.delete()
    messages.success(request, f"Supplier '{supplier.name}' deleted successfully.")
    return redirect('manager_feeds')


@login_required
def feed_stock_history(request):
    feed_stocks = FeedStock.objects.select_related('manufacturer', 'supplier').order_by('-arrival_date')
    return render(request, 'manager/partials/feed_history.html', {
        'feed_stocks': feed_stocks,
    })


#=======================================================
# FEED REQUEST APPROVAL (MANAGER)
#=======================================================
# --- FEED REQUESTS (Manager) ---

@login_required
def review_feed_requests(request):
    pending = (FeedRequest.objects
               .filter(status='pending')
               .select_related('farmer', 'requested_by')
               .order_by('-submitted_on'))

    approved = (FeedRequest.objects
                .filter(status='approved')
                .select_related('farmer', 'approved_by')
                .order_by('-approved_on'))

    rejected = (FeedRequest.objects
                .filter(status='rejected')
                .select_related('farmer', 'approved_by')
                .order_by('-approved_on'))

    all_requests = (FeedRequest.objects
                    .select_related('farmer', 'requested_by', 'approved_by')
                    .order_by('-submitted_on'))

    return render(request, 'manager/review_feed_requests.html', {
        'pending_requests': pending,
        'approved_requests': approved,
        'rejected_requests': rejected,
        'all_requests': all_requests,
    })

@login_required
def approve_reject_feed_request(request, request_id):
    feed_request = get_object_or_404(FeedRequest, id=request_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        notes = (request.POST.get('approval_notes') or '').strip()

        # TODO: replace with request.user when auth is ready
        default_user = User.objects.get(username='peter')

        if action == 'approve':
            feed_request.status = 'approved'
            feed_request.approval_notes = notes
            feed_request.approved_by = default_user  # request.user
            feed_request.approved_on = now()
            feed_request.save()
            messages.success(request, f"Feed request #{feed_request.id} approved.")
        elif action == 'reject':
            feed_request.status = 'rejected'
            feed_request.approval_notes = notes
            feed_request.approved_by = default_user  # request.user
            feed_request.approved_on = now()
            feed_request.save()
            messages.warning(request, f"Feed request #{feed_request.id} rejected.")
        else:
            messages.error(request, "Invalid action.")

    return redirect('review_feed_requests')



#==============================================
# FARMERS ON THE MANAGER SIDE
#==============================================
@login_required
def farmers_view(request):
    q = (request.GET.get("q") or "").strip()

    farmers = Farmer.objects.all()
    if q:
        farmers = farmers.filter(
            Q(name__icontains=q) |
            Q(nin__icontains=q) |
            Q(recommender__icontains=q) |
            Q(recommender_nin__icontains=q) |
            Q(contact__icontains=q)
        )
    farmers = farmers.order_by('name')

    return render(request, 'manager/farmers.html', {
        'farmers': farmers,
        'q': q,                     # so the input keeps its value
        'results_count': farmers.count(),  # optional: show count
    })

def farmer_request_history(request, nin):
    farmer = get_object_or_404(Farmer, nin=nin)
    requests = ChickRequest.objects.filter(farmer=farmer).order_by('-submitted_on')
    return render(request, 'manager/farmer_request_history.html', {
        'farmer': farmer,
        'requests': requests
    })

#==============================================
# SALES REPORT / PAYMENTS ON THE MANAGER SIDE
#==============================================


CHICK_PRICE = Decimal('1650')  # fixed price per chick

def sales_report(request):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # ----------------------------
    # 1) Chicks picked (expected revenue)
    # ----------------------------
    picked = ChickRequest.objects.filter(is_picked=True)

    # Chicks expected (approved but not yet picked)
    chicks_expected = (
        ChickRequest.objects
        .filter(status='approved', is_picked=False)
        .aggregate(n=Sum('quantity'))['n'] or 0
    )

    # Chicks currently available in stock (all batches summed)
    chicks_in_stock = ChickStock.objects.aggregate(n=Sum('quantity'))['n'] or 0


    chicks_sold = picked.aggregate(n=Sum('quantity'))['n'] or 0
    chick_expected_total = CHICK_PRICE * Decimal(chicks_sold)

    chicks_this_week = picked.filter(picked_on__gte=week_start).aggregate(n=Sum('quantity'))['n'] or 0
    chicks_this_month = picked.filter(picked_on__gte=month_start).aggregate(n=Sum('quantity'))['n'] or 0

    # ----------------------------
    # 2) Payments (actual cash in)
    # ----------------------------
    total_chick_payments = Payment.objects.filter(payment_for='chicks').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_feed_payments  = Payment.objects.filter(payment_for='feeds').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_payments = total_chick_payments + total_feed_payments

    # ----------------------------
    # 3) Initial 2-bag feeds receivables
    #    (value at issuance batch price vs what’s paid against that distribution)
    # ----------------------------
    # Pull all initial allocations with their batch and farmer
    initial_dists = list(
        FeedDistribution.objects
        .filter(distribution_type='initial')
        .select_related('feed_stock', 'farmer')
        .order_by('distribution_date', 'id')
    )

    # Preload payments linked to those distributions (feeds only)
    dist_ids = [fd.id for fd in initial_dists]
    payments_by_dist = {}
    if dist_ids:
        rows = (Payment.objects
                .filter(related_feed_distribution_id__in=dist_ids, payment_for='feeds')
                .values('related_feed_distribution')
                .annotate(total=Sum('amount')))
        payments_by_dist = {row['related_feed_distribution']: row['total'] or Decimal('0') for row in rows}

    total_initial_value = Decimal('0')
    total_initial_paid  = Decimal('0')
    total_initial_balance = Decimal('0')

    overdue_count = 0
    due_soon_count = 0

    # Build farmer-level balances to get top debtors
    farmer_balances = {}  # farmer_id -> {'farmer__name': ..., 'total_value': D, 'total_paid': D}
    for fd in initial_dists:
        # Skip if feed_stock missing (shouldn’t, but model allows null)
        if not fd.feed_stock:
            unit = Decimal('0')
        else:
            unit = fd.feed_stock.sale_price or Decimal('0')

        value = unit * Decimal(fd.quantity_bags)
        paid = payments_by_dist.get(fd.id, Decimal('0'))
        balance = value - paid

        total_initial_value += value
        total_initial_paid  += paid
        total_initial_balance += balance

        # Due/overdue counts (only if something is outstanding)
        if balance > 0 and fd.due_date:
            if fd.due_date < today:
                overdue_count += 1
            elif today <= fd.due_date <= (today + timedelta(days=7)):
                due_soon_count += 1

        # Aggregate per farmer
        fid = fd.farmer.id
        if fid not in farmer_balances:
            farmer_balances[fid] = {
                'farmer__name': fd.farmer.name,
                'total_value': Decimal('0'),
                'total_paid':  Decimal('0'),
            }
        farmer_balances[fid]['total_value'] += value
        farmer_balances[fid]['total_paid']  += paid

    # Turn into list with balances and sort
    debtors = []
    for _, rec in farmer_balances.items():
        balance = rec['total_value'] - rec['total_paid']
        if balance > 0:
            debtors.append({
                'farmer__name': rec['farmer__name'],
                'total_value': rec['total_value'],
                'total_paid':  rec['total_paid'],
                'balance':     balance,
            })
    debtors.sort(key=lambda d: d['balance'], reverse=True)
    debtors = debtors[:10]

    # ----------------------------
    # 4) Recent payments (last 20)
    # ----------------------------
    recent_payments = (Payment.objects
                       .select_related('farmer', 'related_feed_distribution')
                       .order_by('-payment_date', '-id')[:20])

    context = {
        # summary cards
        'chicks_sold': chicks_sold,
        'chick_expected_total': chick_expected_total,
        'chicks_this_week': chicks_this_week,
        'chicks_this_month': chicks_this_month,
        'total_chick_payments': total_chick_payments,
        'total_feed_payments': total_feed_payments,
        'total_payments': total_payments,
        'chicks_expected': chicks_expected,
        'chicks_in_stock': chicks_in_stock,

        # initial feeds receivables
        'total_initial_value': total_initial_value,
        'total_initial_paid': total_initial_paid,
        'total_initial_balance': total_initial_balance,
        'overdue_count': overdue_count,
        'due_soon_count': due_soon_count,

        # tables
        'debtors': debtors,
        'recent_payments': recent_payments,
    }
    return render(request, 'manager/sales_report.html', context)



#====================================
# REGISTER NEW USERS FOR THE SYSTEM
#====================================
@login_required
def register_user(request):
    if request.method == 'POST':
        form_data = request.POST
        full_name = form_data['full_name']
        dob = form_data['dob']
        email = form_data['email']
        phone = form_data['phone']
        username = form_data['username']
        password = form_data['password']
        role = form_data['role']

        # Split full name
        name_parts = full_name.split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        # Check for duplicate usernames
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists. Please choose another one")
            return render(request, 'manager/register_user.html')

        # Create the user
        user = User.objects.create_user (
            username = username,
            password = password,
            email = email,
            role = role,
            phone_number = phone,
            first_name = first_name,
            last_name = last_name
        )

        messages.success(request, f"New {role.replace('_', ' ').title()} '{username}' registered successfully.")
        return redirect('manager_user')


    return render(request, 'manager/register_user.html')


#=================================================
# ANNOUNCEMENTS THAT APPEAR ON THE LANDING PAGE
#=================================================

@login_required
# @manager_required
def announcements_view(request):
    # Handle Quote create/delete posted to this same route
    if request.method == 'POST':
        form_type = (request.POST.get('form_type') or '').strip()

        if form_type == 'quote':
            text = (request.POST.get('text') or '').strip()
            author = (request.POST.get('author') or '').strip()
            eff_from = request.POST.get('effective_from')  # yyyy-mm-dd
            eff_to = request.POST.get('effective_to') or None

            if not text or not eff_from:
                messages.error(request, "Quote text and Effective From are required.")
            else:
                QuoteOfTheWeek.objects.create(
                    text=text,
                    author=author,
                    effective_from=eff_from,
                    effective_to=eff_to if eff_to else None,
                )
                messages.success(request, "Quote saved.")
            return redirect('manager_announcements')

        elif form_type == 'delete_quote':
            qid = request.POST.get('quote_id')
            quote = get_object_or_404(QuoteOfTheWeek, pk=qid)
            quote.delete()
            messages.success(request, "Quote deleted.")
            return redirect('manager_announcements')

        # Fallback (in case something else posts here)
        return redirect('manager_announcements')

    # GET: show lists
    announcements = Announcement.objects.order_by('-posted_on')
    trainings = Training.objects.order_by('date')
    tips = FarmerTip.objects.order_by('-created_on')
    quotes = QuoteOfTheWeek.objects.order_by('-effective_from', '-posted_on')

    return render(request, 'manager/announcements.html', {
        'announcements': announcements,
        'trainings': trainings,
        'tips': tips,
        'quotes': quotes,
    })


# --- Create / Delete for announcements ---
@require_POST
def create_announcement(request):
    title = (request.POST.get('title') or '').strip()
    content = (request.POST.get('content') or '').strip()
    if title and content:
        Announcement.objects.create(title=title, content=content)
        messages.success(request, "Announcement posted.")
    else:
        messages.error(request, "Title and message are required.")
    return redirect('manager_announcements')

@require_POST
def delete_announcement(request, pk):
    get_object_or_404(Announcement, pk=pk).delete()
    messages.success(request, "Announcement deleted.")
    return redirect('manager_announcements')


# --- Create / Delete for trainings ---
@require_POST
def create_training(request):
    title = (request.POST.get('title') or '').strip()
    date_str = request.POST.get('date')  # yyyy-mm-dd
    location = (request.POST.get('location') or '').strip()
    notes = (request.POST.get('notes') or '').strip()
    if title and date_str:
        Training.objects.create(title=title, date=date_str, location=location, notes=notes)
        messages.success(request, "Training added.")
    else:
        messages.error(request, "Title and date are required.")
    return redirect('manager_announcements')

@require_POST
def delete_training(request, pk):
    get_object_or_404(Training, pk=pk).delete()
    messages.success(request, "Training deleted.")
    return redirect('manager_announcements')


# --- Create / Delete for tips ---
@require_POST
def create_tip(request):
    text = (request.POST.get('text') or '').strip()
    if text:
        FarmerTip.objects.create(text=text)
        messages.success(request, "Tip added.")
    else:
        messages.error(request, "Tip cannot be empty.")
    return redirect('manager_announcements')

@require_POST
def delete_tip(request, pk):
    get_object_or_404(FarmerTip, pk=pk).delete()
    messages.success(request, "Tip deleted.")
    return redirect('manager_announcements')


