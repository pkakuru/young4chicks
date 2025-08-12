from django.urls import path
from sales.views import (
    sales_dashboard_view, submit_chick_request,
    history_view, pickup_view, register_farmer,
    edit_farmer, delete_farmer, mark_request_as_picked, feed_pickup_view, mark_feed_request_as_picked
)

urlpatterns = [
    path('', sales_dashboard_view, name='sales_dashboard'),
    path('farmers/', register_farmer, name='register_farmer'),
    path('request/', submit_chick_request, name='submit_chick_request'),
    path('history/', history_view, name='sales_history'),
    path('pickup/', pickup_view, name='sales_pickup'),
    path('famers/<int:farmer_id>/edit/', edit_farmer, name='edit_farmer'),
    path('farmers/<int:farmer_id>/delete/', delete_farmer, name='delete_farmer'),
    path('pickup/confirm/<int:request_id>/', mark_request_as_picked, name='mark_request_as_picked'),
    path('pickups/feeds/', feed_pickup_view, name='sales_feed_pickup'),
    path('pickups/feeds/<int:request_id>/confirm/', mark_feed_request_as_picked, name='mark_feed_request_as_picked'),
]
