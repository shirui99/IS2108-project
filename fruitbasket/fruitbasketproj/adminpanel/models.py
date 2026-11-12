from django.contrib.auth.models import User
from django.db import models
from django.core.validators import MinValueValidator
from uuid import uuid4
from django.db.models.functions import Length
from django.db.models.lookups import LessThanOrEqual


# Explicit Python str.strip whitespace set, also enforced by SQLite TRIM.
CATEGORY_WHITESPACE = "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"


def category_code():
    return "c" + uuid4().hex[:19]


class Category(models.Model):
    Ccode = models.CharField(max_length=20, primary_key=True, default=category_code, editable=False)
    Cname = models.CharField(max_length=200, unique=True, db_collation="nocase", verbose_name="Category name")

    class Meta:
        ordering = ["Cname", "Ccode"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(Cname="") & models.Q(Cname=models.Func(models.F("Cname"), models.Value(CATEGORY_WHITESPACE), function="TRIM")), name="category_name_trimmed_nonempty"),
            models.CheckConstraint(condition=LessThanOrEqual(Length("Cname"), models.Value(200)), name="category_name_length"),
        ]

    def save(self, *args, **kwargs):
        self.Cname = self.Cname.strip(CATEGORY_WHITESPACE)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.Cname

# Create your models here.

class Product(models.Model):

    Pid = models.CharField(max_length=5, primary_key=True)
    Pname = models.CharField(max_length=200)
    Pcategory = models.ForeignKey(Category, on_delete=models.PROTECT, db_column="Pcategory", related_name="products", verbose_name="Category")
    Psize = models.CharField(max_length=30)
    Pprice = models.FloatField()
    Plowstock = models.IntegerField(validators=[MinValueValidator(0)])
    Ptargetstock = models.PositiveIntegerField(null=True, blank=True, verbose_name='Target stock level')
    Pbulkquantity = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(2)], verbose_name='Bulk quantity threshold')
    Pbulkprice = models.FloatField(null=True, blank=True, verbose_name='Bulk unit price')
    Pactive = models.BooleanField(default=True)
    Pimage = models.ImageField(upload_to='products/', blank=True, null=True)
    Pexpirydays = models.PositiveIntegerField(default=0)

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
            ),
            models.CheckConstraint(condition=models.Q(Ptargetstock__isnull=True) | models.Q(Ptargetstock__gte=models.F('Plowstock')), name='product_target_at_least_low'),
            models.CheckConstraint(condition=(models.Q(Pbulkquantity__isnull=True, Pbulkprice__isnull=True) | models.Q(Pbulkquantity__isnull=False, Pbulkprice__isnull=False, Pbulkquantity__gte=2, Pbulkprice__gt=0, Pbulkprice__lte=models.F('Pprice'))), name='product_bulk_settings_valid')
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

    Ipurchasedprice = models.FloatField(null=True, blank=True, verbose_name='Recorded purchase price')
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
                check=models.Q(Iorder__isnull=True, Istatus__in=['available', 'expired']) | (models.Q(Iorder__isnull=False) & ~models.Q(Istatus='available')),
                name='Iorder_matches_Istatus'
            ),
            models.CheckConstraint(
                check=models.Q(Irating__isnull=True) | models.Q(Irating__gte=1, Irating__lte=5),
                name='Irating_between_one_and_five'
            )
        ]

    def __str__(self):

        return f'Item {self.pk} - {self.Iproduct.Pname} (expires {self.Iexpiry})'


class SupportTicket(models.Model):

    STATUS = [
        ('open', 'Open'),
        ('answered', 'Answered'),
    ]

    Tsubject = models.CharField(max_length=200)
    Tmessage = models.TextField()
    Tresponse = models.TextField(blank=True)
    Tstatus = models.CharField(max_length=10, choices=STATUS, default='open')
    Tsubmitted = models.DateTimeField(auto_now_add=True)
    Tresponded = models.DateTimeField(blank=True, null=True)

    Torder = models.ForeignKey(Orders, on_delete=models.RESTRICT, related_name='order_tickets')
    Tresponder = models.ForeignKey(User, on_delete=models.RESTRICT, related_name='answered_tickets', blank=True, null=True)

    # Add constraint to ensure that an open ticket has no response, and an answered ticket has a response, responder and time

    class Meta:

        constraints = [
            models.CheckConstraint(
                condition=models.Q(Tstatus='open', Tresponse='', Tresponder__isnull=True, Tresponded__isnull=True)
                | (models.Q(Tstatus='answered', Tresponder__isnull=False, Tresponded__isnull=False) & ~models.Q(Tresponse='')),
                name='Tstatus_matches_response'
            )
        ]

    def __str__(self):

        return f'Ticket {self.pk} - {self.Torder.Oid} ({self.Tstatus})'