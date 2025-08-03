from django.contrib import admin
from manager.models import ChickStock
from sales.models import Manufacturer, Supplier, FeedStock, FeedDistribution, Payment

# Register your models here.


@admin.register(ChickStock)
class ChickStockAdmin(admin.ModelAdmin):
    list_display = ('chick_type', 'quantity', 'age_days', 'recorded_on')
    list_filter = ('chick_type', 'recorded_on')
    search_fields = ('chick_type',)

admin.site.register(Payment)
admin.site.register(FeedDistribution)
admin.site.register(FeedStock)
admin.site.register(Supplier)
admin.site.register(Manufacturer)
