from django.db import models
#from sales.models import ChickRequest

class ChickStock(models.Model):
    CHICK_TYPE_CHOICES = (
        ('layer_local', 'Layer - Local'),
        ('layer_exotic', 'Layer - Exotic'),
        ('broiler_local', 'Broiler - Local'),
        ('broiler_exotic', 'Broiler - Exotic'),
    )

    chick_type = models.CharField(max_length=20, choices=CHICK_TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    age_days = models.PositiveIntegerField(help_text="Age of chicks in days")
    recorded_on = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.get_chick_type_display()} - {self.quantity} chicks"
    

class ChickAllocation(models.Model):
    request = models.ForeignKey('sales.ChickRequest', on_delete=models.CASCADE, related_name='allocations')
    stock   = models.ForeignKey('ChickStock', on_delete=models.PROTECT, related_name='allocations')
    quantity = models.PositiveIntegerField()

    allocated_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"REQ{self.request_id} ← {self.quantity} from stock #{self.stock_id}"
