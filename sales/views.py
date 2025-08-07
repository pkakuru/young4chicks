from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from sales.models import Farmer, ChickRequest, FeedRequest, FeedDistribution
from datetime import datetime, date
from django.core.paginator import Paginator
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from home.models import User

# Create your views here.
def dashboard_view(request):
    return render(request, 'sales/dashboard.html')

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
        if age < 18 or age > 35:
            messages.error(request, "Farmer must be between 18 and 35 years old.")
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
    
    from django.core.paginator import Paginator
    
    # On GET request, render the form
    all_farmers = Farmer.objects.all().order_by('-id')
    paginator = Paginator(all_farmers, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'sales/register.html', {
        'farmers': all_farmers,
        'page_obj': page_obj,
        })



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
            notes = request.POST.get('notes', '').strip()

            farmer = get_object_or_404(Farmer, id=farmer_id)
            farmer_type = farmer.farmer_type  # Starter or Returning

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
        
        # We handle the feed request form from here
        
        elif form_type == 'feed_request':
            # Feed Request Handling
            farmer_id = request.POST.get('farmer')
            feed_type = request.POST.get('feed_type')
            quantity_bags = int(request.POST.get('quantity_bags'))
            approval_notes = request.POST.get('approval_notes', '').strip()

            farmer = get_object_or_404(Farmer, id=farmer_id)

            from home.models import User
            default_user = User.objects.get(username='peter')

            FeedRequest.objects.create(
                farmer=farmer,
                feed_type=feed_type,
                quantity_bags=quantity_bags,
                #requested_by=request.user, Uncomment this line and delete the one below once ready to implement the users
                requested_by=default_user,
                approval_notes=approval_notes,
                status='pending'
            )
            messages.success(request, f"Request for {quantity_bags} bags of {feed_type} feed submitted successfully.")
            return redirect(reverse('submit_chick_request') + '?tab=feed')

    all_requests = ChickRequest.objects.all().order_by('-submitted_on')
    #feed_requests = FeedRequest.objects.filter(requested_by=request.user).order_by('-submitted_on')
    # Please uncomment the line above and delete the three below when ready to do the login part. I am using this to bypass the login requirement
    from home.models import User
    default_user = User.objects.get(username = 'peter')
    feed_requests = FeedRequest.objects.filter(requested_by=default_user).order_by('-submitted_on')
    

    return render(request, 'sales/submit_request.html', {
        'farmers': farmers,
        'all_requests': all_requests,
        'feed_requests': feed_requests,
    })


def history_view(request):
    return render(request, 'sales/history.html')

def pickup_view(request):
    approved_unpicked = ChickRequest.objects.filter(status='approved', is_picked=False).order_by('-approval_date')
    return render(request, 'sales/pickup.html', {'requests': approved_unpicked})





# def mark_request_as_picked(request, request_id):
#     chick_request = get_object_or_404(ChickRequest, id=request_id, status='approved', is_picked=False)

#     if request.method == 'POST':
#         notes = request.POST.get('pickup_notes', '').strip()
#         chick_request.is_picked = True
#         chick_request.picked_on = timezone.now().date()
#         chick_request.pickup_notes = notes
#         chick_request.save()

#         messages.success(request, f"Request #{chick_request.id} marked as picked.")
#         return redirect('sales_pickup')

#     return render(request, 'sales/mark_pickup.html', {'request': chick_request})


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta, date
from sales.models import ChickRequest, FeedStock, FeedDistribution, Payment, ChickStock

def mark_request_as_picked(request, request_id):
    chick_request = get_object_or_404(ChickRequest, id=request_id, status='approved', is_picked=False)
    farmer = chick_request.farmer

    if request.method == 'POST':
        notes = request.POST.get('pickup_notes', '').strip()
        paid_chicks = int(request.POST.get('paid_chicks', 0))
        paid_feeds = int(request.POST.get('paid_feeds', 0))

        # Step 1: Deduct chick stock (FIFO)
        remaining_chicks = chick_request.quantity
        chick_stocks = ChickStock.objects.filter(chick_type=chick_request.chick_type, quantity__gt=0).order_by('recorded_on')

        for stock in chick_stocks:
            if remaining_chicks == 0:
                break
            if stock.quantity <= remaining_chicks:
                remaining_chicks -= stock.quantity
                stock.quantity = 0
            else:
                stock.quantity -= remaining_chicks
                remaining_chicks = 0
            stock.save()

        if remaining_chicks > 0:
            messages.error(request, f"Not enough chick stock available for {chick_request.get_chick_type_display()}.")
            return redirect('sales_pickup')

        # Step 2: Allocate 2 bags of feed (mandatory) using FIFO
        feed_bags_needed = 2
        feed_stocks = FeedStock.objects.filter(quantity_bags__gt=0).order_by('arrival_date')
        for stock in feed_stocks:
            if feed_bags_needed == 0:
                break

            if stock.quantity_bags >= feed_bags_needed:
                used_bags = feed_bags_needed
                stock.quantity_bags -= used_bags
                feed_bags_needed = 0
            else:
                used_bags = stock.quantity_bags
                feed_bags_needed -= stock.quantity_bags
                stock.quantity_bags = 0

            stock.save()

            #Bypass login by using default user
            # Delete these 3 lines and uncomment request.user when login is implemented
            default_user = User.objects.get(username='peter')  
            
            # Save FeedDistribution entry
            FeedDistribution.objects.create(
                farmer=farmer,
                feed_stock=stock,
                distribution_type='initial',
                quantity_bags=used_bags,
                due_date=date.today() + timedelta(days=60),  # 2 months deferral
                recorded_by = default_user,
                #recorded_by=request.user,
                notes='Auto-issued during chick pickup'
            )

        if feed_bags_needed > 0:
            messages.warning(request, f"Only partial feed allocation completed. {feed_bags_needed} bags could not be issued due to low stock.")

        # Step 3: Save Payment(s)
        if paid_chicks > 0:
            Payment.objects.create(
                farmer=farmer,
                amount=paid_chicks,
                payment_for='chicks',
                payment_date=date.today(),
                received_by=default_user,
                #received_by=request.user,
                notes=f"Paid for {chick_request.quantity} chicks during pickup"
            )

        if paid_feeds > 0:
            Payment.objects.create(
                farmer=farmer,
                amount=paid_feeds,
                payment_for='feeds',
                payment_date=date.today(),
                received_by=default_user,
                #received_by=request.user,
                notes="Feed payment at pickup"
            )

        # Step 4: Mark as picked
        chick_request.is_picked = True
        chick_request.picked_on = timezone.now().date()
        chick_request.pickup_notes = notes
        chick_request.save()

        # Step 5: Promote starter to returning
        if farmer.farmer_type == 'starter':
            farmer.farmer_type = 'returning'
            farmer.save()

        messages.success(request, f"Request #{chick_request.id} marked as picked. Stock deducted and payment recorded.")
        return redirect('sales_pickup')

    # GET — still handled as before
    chick_price = 1650
    expected_chick_total = chick_request.quantity * chick_price

    # Latest feed price (to suggest to Sales Rep)
    latest_feed_stock = FeedStock.objects.order_by('-arrival_date').first()
    feed_price = latest_feed_stock.sale_price if latest_feed_stock else 0
    expected_feed_total = 2 * feed_price

    return render(request, 'sales/mark_pickup.html', {
        'request': chick_request,
        'expected_chick_total': expected_chick_total,
        'expected_feed_total': expected_feed_total,
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




