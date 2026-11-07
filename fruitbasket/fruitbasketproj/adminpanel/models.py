from django.contrib.auth.models import User
from django.db import models

# Create your models here.

class Product(models.Model):

    CATEGORY = [
        ('dairy', 'Dairy, Chilled & Eggs'),
        ('fruit', 'Fruit & Vegetables'),
        ('meat', 'Meat & Seafood'),
        ('bakery', 'Bakery'),
        ('rice', 'Rice, Noodles & Cooking Ingredients'),
        ('snacks', 'Snacks & Confectionery'),
        ('frozen', 'Frozen'),
        ('household', 'Household')
    ]

    Pid = models.CharField(max_length=5, primary_key=True)
    Pname = models.CharField(max_length=200)
    Pcategory = models.CharField(max_length=20, choices=CATEGORY)
    Psize = models.CharField(max_length=30)
    Pprice = models.FloatField()
    Plowstock = models.IntegerField()
    Pactive = models.BooleanField(default=True)

    # Add constraint to ensure that Pprice is greater than 0
    # Add constraint to ensure that Plowstock is not negative

    class Meta:

        constraints = [
            models.CheckConstraint(
                check=models.Q(Pprice__gt=0),
                name='Pprice_greater_than_zero'
            ),
            models.CheckConstraint(
                check=models.Q(Plowstock__gte=0),
                name='Plowstock_not_negative'
            )
        ]

    def __str__(self):

        return f'{self.Pid} - {self.Pname} ({self.Psize})'



class Customer(models.Model):

    Cid = models.CharField(max_length=5, primary_key=True)
    Cname = models.CharField(max_length=255)
    Caddress = models.CharField(max_length=255)
    Chouseholdsize = models.IntegerField()
    Cmealsperweek = models.IntegerField()

    Cuser = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer')

    # Add constraint to ensure that Chouseholdsize is at least 1
    # Add constraint to ensure that Cmealsperweek is not negative

    class Meta:

        constraints = [
            models.CheckConstraint(
                check=models.Q(Chouseholdsize__gte=1),
                name='Chouseholdsize_at_least_one'
            ),
            models.CheckConstraint(
                check=models.Q(Cmealsperweek__gte=0),
                name='Cmealsperweek_not_negative'
            )
        ]

    def __str__(self):

        return f'{self.Cid} - {self.Cname}'



class Orders(models.Model):

    STATUS = [
        ('placed', 'Placed'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ]

    Oid = models.CharField(max_length=6, primary_key=True)
    Odate = models.DateField()
    Oaddress = models.CharField(max_length=255)
    Ostatus = models.CharField(max_length=10, choices=STATUS, default='placed')

    Ocustomer = models.ForeignKey(Customer, on_delete=models.RESTRICT, related_name='customer_orders')

    def __str__(self):

        return f'{self.Oid} - {self.Ocustomer.Cname}'



class Item(models.Model):

    STATUS = [
        ('available', 'In warehouse'),
        ('delivered', 'Delivered'),
        ('used', 'Used up'),
        ('expired', 'Expired/Discarded')
    ]

    Ireceived = models.DateField()
    Iexpiry = models.DateField(blank=True, null=True)
    Istatus = models.CharField(max_length=10, choices=STATUS, default='available')
    Ifinished = models.DateField(blank=True, null=True)
    Irating = models.IntegerField(blank=True, null=True)

    Iproduct = models.ForeignKey(Product, on_delete=models.RESTRICT, related_name='product_items')
    Iorder = models.ForeignKey(Orders, on_delete=models.RESTRICT, related_name='order_items', blank=True, null=True)

    # Add constraint to ensure that an item without an order is available, and an item with an order is not
    # Add constraint to ensure that Irating is between 1 and 5 if given

    class Meta:

        constraints = [
            models.CheckConstraint(
                check=models.Q(Iorder__isnull=True, Istatus='available') | (models.Q(Iorder__isnull=False) & ~models.Q(Istatus='available')),
                name='Iorder_matches_Istatus'
            ),
            models.CheckConstraint(
                check=models.Q(Irating__isnull=True) | models.Q(Irating__gte=1, Irating__lte=5),
                name='Irating_between_one_and_five'
            )
        ]

    def __str__(self):

        return f'Item {self.pk} - {self.Iproduct.Pname} (expires {self.Iexpiry})'