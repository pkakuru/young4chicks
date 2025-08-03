from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from sales.models import Farmer, ChickRequest
from datetime import datetime, date
from django.core.paginator import Paginator
from django.utils import timezone

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

def submit_chick_request(request):
    farmers = Farmer.objects.all().order_by('name')

    if request.method == 'POST':
        farmer_id = request.POST.get('farmer')
        chick_type = request.POST.get('chick_type')
        quantity = int(request.POST.get('quantity'))
        notes = request.POST.get('notes', '').strip()

        farmer = get_object_or_404(Farmer, id=farmer_id)
        farmer_type = farmer.farmer_type  # Starter or returning

        #Enforce quantity limits based on the farmer type
        if farmer_type == 'starter' and quantity > 100:
            messages.error(request,"Starter farmers can only request up to 100 chicks.")
        elif farmer_type == 'returning' and quantity > 500:
            messages.error(request, "Returning farmers can only request up to 500 chicks.")
        else:
            ChickRequest.objects.create(
                farmer = farmer,
                chick_type = chick_type,
                quantity = quantity,
                status = 'pending',
                notes = notes
            )
            messages.success(request, f"Request for {quantity} {chick_type} chicks submitted successfully.")
            return redirect('submit_chick_request')
        
    all_requests = ChickRequest.objects.all().order_by('-submitted_on') 

    return render(request, 'sales/submit_request.html',{
        'farmers': farmers,
        'all_requests': all_requests
    })

def history_view(request):
    return render(request, 'sales/history.html')

def pickup_view(request):
    approved_unpicked = ChickRequest.objects.filter(status='approved', is_picked=False).order_by('-approval_date')
    return render(request, 'sales/pickup.html', {'requests': approved_unpicked})





def mark_request_as_picked(request, request_id):
    chick_request = get_object_or_404(ChickRequest, id=request_id, status='approved', is_picked=False)

    if request.method == 'POST':
        notes = request.POST.get('pickup_notes', '').strip()
        chick_request.is_picked = True
        chick_request.picked_on = timezone.now().date()
        chick_request.pickup_notes = notes
        chick_request.save()

        messages.success(request, f"Request #{chick_request.id} marked as picked.")
        return redirect('sales_pickup')

    return render(request, 'sales/mark_pickup.html', {'request': chick_request})



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




