from django.db import models

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