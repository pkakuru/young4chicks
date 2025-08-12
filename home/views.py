from django.shortcuts import render
from datetime import date
from django.utils import timezone
from django.db.models import Q
from home.models import Announcement, Training, FarmerTip, QuoteOfTheWeek  # adjust import path if needed

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


