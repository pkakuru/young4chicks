from django.urls import path
from manager.views import (
    dashboard_view, chick_stock_view, review_chick_requests, 
    approve_reject_request,farmers_view, announcements_view, 
    farmer_request_history, feeds_view, sales_report, register_user, 
    add_feed_stock, add_manufacturer, add_supplier, distribute_feeds, feed_stock_history,
    delete_manufacturer, delete_supplier
    )


urlpatterns = [
    path('', dashboard_view, name='manager_dashboard'),
    path('chick-stock/', chick_stock_view, name='manager_chick_stock'),
    path('requests/', review_chick_requests, name='review_chick_requests'),
    path('requests/<int:request_id>/action/', approve_reject_request, name='approve_reject_request'),
    path('farmers/', farmers_view, name='manager_farmers'),
    path('feeds/', feeds_view, name='manager_feeds'),
    path('feeds/add', add_feed_stock, name='add_manufacturer'),
    path('feeds/add-manufacturer/', add_manufacturer, name='add_manufacturer'),
    path('feeds/add-supplier/', add_supplier, name='add_supplier'),
    path('feeds/distribute/', distribute_feeds, name='distribute_feeds'),
    path('feeds/history/', feed_stock_history, name='feed_stock_history'),
    path('feeds/delete-manufacturer/<int:pk>/', delete_manufacturer, name='delete_manufacturer'),
    path('feeds/delete-supplier/<int:pk>/', delete_supplier, name='delete_supplier'),

    path('sales/', sales_report, name='manager_reports'),
    path('announcements/', announcements_view, name='manager_announcements'),
    path('farmers/<str:nin>/requests/', farmer_request_history, name='manager_farmer_request_history'),   
    path('register/', register_user, name='manager_user'),
    
    
]
