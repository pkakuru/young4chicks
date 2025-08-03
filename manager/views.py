from django.shortcuts import render, redirect
from home.models import User
from django.contrib import messages
from manager.models import ChickStock
from django.core.paginator import Paginator
from sales.models import ChickRequest, Farmer, Manufacturer, Supplier, FeedStock
from datetime import date, timedelta
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from collections import defaultdict
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from datetime import datetime


# Create your views here.
def dashboard_view(request):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # Total Approved requests
    approved_requests = ChickRequest.objects.filter(status = 'approved')

    total_chicks_sold = approved_requests.aggregate(total=Sum('quantity'))['total'] or 0
    total_revenue = total_chicks_sold * 1650

    # Weekly stats
    weekly = approved_requests.filter(submitted_on__gte=week_start)
    chicks_this_week = weekly.aggregate(total=Sum('quantity'))['total'] or 0
    revenue_this_week = chicks_this_week * 1650


    # Pending requests
    pending_requests = ChickRequest.objects.filter(status='pending').count()

    # Farmers count
    total_farmers = Farmer.objects.count()

    # This months approvals
    approved_this_month = approved_requests.filter(approval_date__gte=month_start).count()

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
    }
    return render(request, 'manager/dashboard.html', context)

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
    pending_requests = ChickRequest.objects.filter(status='pending').order_by('-submitted_on')
    approved_requests = ChickRequest.objects.filter(status='approved').order_by('-approval_date')
    history_requests = ChickRequest.objects.exclude(status='pending').order_by('-submitted_on') # All non-pending requests
    
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
            remaining = requested_qty
            stock_entries = ChickStock.objects.filter(chick_type=requested_type, quantity__gt=0).order_by('recorded_on')

            for stock in stock_entries:
                if remaining == 0:
                    break
                if stock.quantity <= remaining:
                    remaining -= stock.quantity
                    stock.quantity = 0
                else:
                    stock.quantity -= remaining
                    remaining = 0
                stock.save()

            # Now approve the request    
            chick_request.status = 'approved'
            messages.success(request, f"Request #{chick_request.id} approved and {requested_qty} deducted from stock.")
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

def feeds_view(request):
    manufacturers = Manufacturer.objects.all()
    suppliers = Supplier.objects.all()
    return render(request, 'manager/feeds.html', {
        'manufacturers': manufacturers,
        'suppliers': suppliers,
    })


def farmers_view(request):
    farmers = Farmer.objects.all().order_by('name')
    return render(request, 'manager/farmers.html', {'farmers': farmers})

def sales_report(request):
    return render(request, 'manager/sales_report.html')

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

def announcements_view(request):
    return render(request, 'manager/announcements.html')

def farmer_request_history(request, nin):
    farmer = get_object_or_404(Farmer, nin=nin)
    requests = ChickRequest.objects.filter(farmer=farmer).order_by('-submitted_on')
    return render(request, 'manager/farmer_request_history.html', {
        'farmer': farmer,
        'requests': requests
    })



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
        date_received = request.POST.get('date_received')
        notes = request.POST.get('notes', '')

        # Validation check
        if not all([feed_type, manufacturer_id, supplier_id, quantity_bags, purchase_price, sale_price, date_received]):
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
            date_received = date_received,
            notes = notes,
            added_by = request.user
        )

        messages.success(request, f"{quantity_bags} bags of {feed_type} feed added to stock successfully.")
        return redirect('add_feed_stock')

    return render(request, 'manager/add_feed_stock.html', {
        'manufacturers': manufacturers,
        'suppliers': suppliers,
    })


def add_manufacturer(request):
    if request.method == 'POST':
        name = request.POST.get('name').strip()
        contact = request.POST.get('contact').strip()
        if name:
            Manufacturer.objects.create(name=name, contact=contact)
            messages.success(request, f"Manufacturer '{name}' added successfully.")
    return redirect('manager_feeds')  # or wherever your main feeds page view is named

def add_supplier(request):
    if request.method == 'POST':
        name = request.POST.get('name').strip()
        contact = request.POST.get('contact').strip()
        if name:
            Supplier.objects.create(name=name, contact=contact)
            messages.success(request, f"Supplier '{name}' added successfully.")
    return redirect('manager_feeds')

from sales.models import Farmer, FeedStock

def distribute_feeds(request):
    farmers = Farmer.objects.all().order_by('name')
    available_feed_stock = FeedStock.objects.filter(quantity_bags__gt=0)

    return render(request, 'manager/distribute_feeds.html', {
        'farmers': farmers,
        'feed_stock': available_feed_stock
    })

from sales.models import FeedStock

def feed_stock_history(request):
    all_feed_stock = FeedStock.objects.all().order_by('-received_date')

    return render(request, 'manager/feed_stock_history.html', {
        'feed_stock': all_feed_stock
    })


