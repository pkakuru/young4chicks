from django.shortcuts import render, redirect, get_object_or_404
from home.models import User
from django.contrib import messages
from manager.models import ChickStock
from django.core.paginator import Paginator
from sales.models import ChickRequest, Farmer, Manufacturer, Supplier, FeedStock, Payment
from datetime import date, timedelta
from django.db.models import Sum
from collections import defaultdict
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from datetime import datetime
from sales.models import FeedRequest, FeedDistribution
from django.utils.timezone import now
from django.db.models import Q




# Create your views here.
#============================
# 1) DASHBOARD
#============================
def dashboard_view(request):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # Total Approved requests
    approved_requests = ChickRequest.objects.filter(status = 'approved')

    picked_requests = ChickRequest.objects.filter(is_picked = True)

    total_chicks_sold = picked_requests.aggregate(total=Sum('quantity'))['total'] or 0
    total_revenue = total_chicks_sold * 1650

    # Weekly stats
    weekly = picked_requests.filter(picked_on__gte=week_start)
    chicks_this_week = weekly.aggregate(total=Sum('quantity'))['total'] or 0
    revenue_this_week = chicks_this_week * 1650


    # Pending requests
    pending_requests = ChickRequest.objects.filter(status='pending').count()

    # Farmers count
    total_farmers = Farmer.objects.count()

    # This months approvals
    approved_this_month = approved_requests.filter(approval_date__gte=month_start).count()

    # Feed Summaries
    total_feed_stock = FeedStock.objects.aggregate(total=Sum('quantity_bags'))['total'] or 0

    # Feeds expiring in next 14 days
    soon_expiring_feeds = FeedStock.objects.filter(expiry_date__isnull=False, expiry_date__lte=today + timedelta(days=14)).count()

    # Feed distributions due for payment soon (e.g Within 7 days)
    feeds_due_soon = FeedDistribution.objects.filter(
        due_date__isnull=False,
        due_date__lte=today + timedelta(days=7)
    ).count()

    # STOCK STATS
    stock_by_type = ChickStock.objects.values('chick_type').annotate(total=Sum('quantity'))
    stock_dict = {entry['chick_type']: entry['total'] for entry in stock_by_type}

    total_remaining_stock = sum([
        stock_dict.get('broiler_local', 0),
        stock_dict.get('broiler_exotic', 0),
        stock_dict.get('layer_local', 0),
        stock_dict.get('layer_exotic', 0),
    ])

    context = {
        'total_chicks_sold': total_chicks_sold,
        'total_revenue': total_revenue,
        'chicks_this_week': chicks_this_week,
        'revenue_this_week': revenue_this_week,
        'pending_requests': pending_requests,
        'total_farmers': total_farmers,
        'approved_this_month': approved_this_month,
        'stock_dict': stock_dict,
        'total_remaining_stock': total_remaining_stock,
        'feeds_due_soon': feeds_due_soon,
        'soon_expiring_feeds': soon_expiring_feeds,
        'total_feed_stock': total_feed_stock,
    }
    return render(request, 'manager/dashboard.html', context)
#======================================
# 2) CHICK STOCK & CHICK REQUESTS
#======================================
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

def review_chick_requests(request):
    pending_requests = ChickRequest.objects.filter(status='pending').select_related('farmer', 'approved_by').order_by('-submitted_on')
    approved_requests = ChickRequest.objects.filter(status='approved').select_related('farmer', 'approved_by').order_by('-approval_date')
    history_requests = ChickRequest.objects.exclude(status='pending').select_related('farmer', 'approved_by').order_by('-submitted_on') # All non-pending requests


    # attach computed metrics (no DB changes)
    today = date.today()
    for r in history_requests:
        # Chicks money
        r.expected_chicks_amount = r.quantity * 1650
        r.chicks_paid_today = 0
        if r.is_picked and r.picked_on:
            r.chicks_paid_today = (Payment.objects
                .filter(farmer=r.farmer, payment_for='chicks', payment_date=r.picked_on)
                .aggregate(s=Sum('amount'))['s'] or 0)
        r.chicks_balance = r.expected_chicks_amount - r.chicks_paid_today

        # Feeds allocation on pickup day (initial 2 bags)
        r.feeds_allocated_bags = 0
        r.feeds_due_date = None
        r.feeds_status = None
        if r.is_picked and r.picked_on:
            dists = FeedDistribution.objects.filter(
                farmer=r.farmer,
                distribution_type='initial',
                distribution_date=r.picked_on
            )
            r.feeds_allocated_bags = dists.aggregate(s=Sum('quantity_bags'))['s'] or 0
            r.feeds_due_date = dists.order_by('-due_date').values_list('due_date', flat=True).first()

            # Simple payment heuristic: any feeds payment on/after pickup day
            feeds_paid_amount = (Payment.objects
                .filter(farmer=r.farmer, payment_for='feeds', payment_date__gte=r.picked_on)
                .aggregate(s=Sum('amount'))['s'] or 0)

            if feeds_paid_amount and r.feeds_allocated_bags:
                r.feeds_status = 'paid'
            elif r.feeds_due_date:
                if r.feeds_due_date < today:
                    r.feeds_status = 'overdue'
                else:
                    r.feeds_status = 'due'
            else:
                r.feeds_status = None  # no feeds issued
    
    return render(request, 'manager/requests.html', {
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'history_requests': history_requests,
    })

def approve_reject_request(request, request_id):
    chick_request = get_object_or_404(ChickRequest, id=request_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            requested_type = chick_request.chick_type
            requested_qty = chick_request.quantity

            # Total available stock for that chick type
            total_stock = ChickStock.objects.filter(chick_type=requested_type).aggregate(total=Sum('quantity'))['total'] or 0

            if requested_qty > total_stock:
                messages.error(request, f"Insufficient stock for {requested_type.replace('_',' ').title()}. Requested: {requested_qty}, Available: {total_stock}")
                return redirect('review_chick_requests')
            
            # Deduct from oldest stock records first (FIFO)
            # remaining = requested_qty
            # stock_entries = ChickStock.objects.filter(chick_type=requested_type, quantity__gt=0).order_by('recorded_on')

            # for stock in stock_entries:
            #     if remaining == 0:
            #         break
            #     if stock.quantity <= remaining:
            #         remaining -= stock.quantity
            #         stock.quantity = 0
            #     else:
            #         stock.quantity -= remaining
            #         remaining = 0
            #     stock.save()

            # Now approve the request    
            chick_request.status = 'approved'
            messages.success(request, f"Request No.{chick_request.id} of {chick_request.chick_type} approved!")
        elif action == 'reject':
            chick_request.status = 'rejected'
            messages.warning(request, f"Request #{chick_request.id} rejected")

        chick_request.approval_date = date.today()
        #chick_request.approved_by = request.user
        from home.models import User # Remove this line and the two belwo it after designing the login page. Then uncomment the one above
        default_manager = User.objects.get(username='peter')
        chick_request.approved_by = default_manager
        chick_request.save()

    return redirect('review_chick_requests')

#=================================================
# 3) FEEDS (STOCK, DISTRIBUTION & FEED SOURCES)
#=================================================

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

# from sales.models import FeedDistribution
# from django.db.models import Q

# def distribute_feeds_view(request):
#     query = request.GET.get('q')
#     feed_distributions = FeedDistribution.objects.select_related('farmer', 'feed_stock', 'recorded_by')

#     if query:
#         feed_distributions = feed_distributions.filter(
#             Q(farmer__name__icontains=query) |
#             Q(feed_stock__feed_type__icontains=query)
#         )

#     return render(request, 'manager/partials/distribute_feeds.html', {
#         'distributions': feed_distributions
#     })


# We are using this view to manage the feed suppliers and feed manufacturers
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
#@login_required
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


def add_manufacturer(request):
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        contact = (request.POST.get('contact') or '').strip()
        location = (request.POST.get('location') or '').strip()
        if name:
            Manufacturer.objects.create(
                name=name,
                contact=contact,
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


# def distribute_feeds(request):
#     query = request.GET.get('q')
#     feed_distributions = FeedDistribution.objects.select_related('farmer', 'feed_stock', 'recorded_by')

#     if query:
#         feed_distributions = feed_distributions.filter(
#             Q(farmer__name__icontains=query) |
#             Q(feed_stock__feed_type__icontains=query)
#         )

#     return render(request, 'manager/partials/distribute_feeds.html', {
#         'distributions': feed_distributions
#     })

#@login_required
def feed_stock_history(request):
    feed_stocks = FeedStock.objects.select_related('manufacturer', 'supplier').order_by('-arrival_date')
    return render(request, 'manager/partials/feed_history.html', {
        'feed_stocks': feed_stocks,
    })


#=======================================================
# FEED REQUEST APPROVAL (MANAGER)
#=======================================================
#@login_required
# --- FEED REQUESTS (Manager) ---


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
def farmers_view(request):
    farmers = Farmer.objects.all().order_by('name')
    return render(request, 'manager/farmers.html', {'farmers': farmers})

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
from datetime import date, timedelta
from decimal import Decimal
from django.shortcuts import render
from django.db.models import Sum
from sales.models import ChickRequest, FeedDistribution, Payment
from sales.models import FeedStock  # only for select_related safety
from manager.models import ChickStock

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

# manager/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.http import require_POST
# from django.contrib.auth.decorators import login_required
# from .permissions import manager_required  # if you have one
from home.models import Announcement, Training, FarmerTip, QuoteOfTheWeek

# @login_required
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


