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
        ('preparing', 'Preparing'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ]

    PAYMENT = [
        ('paid', 'Paid (simulated)'),
        ('refunded', 'Refunded (simulated)')
    ]

    Oid = models.CharField(max_length=6, primary_key=True)
    Odate = models.DateField()
    Oaddress = models.CharField(max_length=255)
    Ostatus = models.CharField(max_length=10, choices=STATUS, default='placed')
    Odispatched = models.DateTimeField(null=True, blank=True, editable=False)
    Odelivered = models.DateTimeField(null=True, blank=True, editable=False)
    Opayment = models.CharField(max_length=10, choices=PAYMENT, default='paid', verbose_name='Simulated payment')

    Ocustomer = models.ForeignKey(Customer, on_delete=models.RESTRICT, related_name='customer_orders')

    def __str__(self):

        return f'{self.Oid} - {self.Ocustomer.Cname}'



class OrderCancellation(models.Model):
    order = models.OneToOneField(Orders, on_delete=models.PROTECT, related_name='cancellation')
    source = models.CharField(max_length=8, choices=[('staff', 'Staff'), ('customer', 'Customer')])
    employee = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    reason = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    payment_before = models.CharField(max_length=10)
    payment_after = models.CharField(max_length=10)


class CancelledAllocation(models.Model):
    cancellation = models.ForeignKey(OrderCancellation, on_delete=models.PROTECT, related_name='allocations')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=200)
    pack_size = models.CharField(max_length=30)
    quantity = models.PositiveIntegerField()
    unit_price = models.FloatField(null=True, blank=True)
    batch = models.ForeignKey('InventoryBatch', null=True, blank=True, on_delete=models.PROTECT)
    batch_reference = models.CharField(max_length=100, null=True, blank=True)
    received = models.DateField()
    recorded_date = models.DateField(null=True, blank=True)


class InventoryBatch(models.Model):
    DATE_TYPES = [('use_by', 'Use by'), ('best_before', 'Best before'), ('expiry', 'Expiry')]
    Breference = models.CharField(max_length=100, unique=True, verbose_name='Batch reference')
    Bproduct = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='inventory_batches')
    Breceived = models.DateField()
    Bquantity = models.PositiveIntegerField()
    Bdatetype = models.CharField(max_length=20, choices=DATE_TYPES, blank=True)
    Bdate = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(Bquantity__gt=0), name='batch_quantity_positive'),
            models.CheckConstraint(condition=(models.Q(Bdatetype='', Bdate__isnull=True) | models.Q(Bdatetype__in=['use_by', 'best_before', 'expiry'], Bdate__isnull=False)), name='batch_date_type_matches_date'),
        ]


class Item(models.Model):

    STATUS = [
        ('available', 'In warehouse'),
        ('adjusted', 'Adjusted out'),
        ('writtenoff', 'Written off'),
        ('allocated', 'Allocated to order'),
        ('delivered', 'Delivered'),
        ('used', 'Used up'),
        ('expired', 'Expired/Discarded')
    ]

    Ipurchasedprice = models.FloatField(null=True, blank=True, verbose_name='Recorded purchase price')
    Ibatch = models.ForeignKey(InventoryBatch, null=True, blank=True, on_delete=models.PROTECT, related_name='items')
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
                check=models.Q(Iorder__isnull=True, Istatus__in=['available', 'expired', 'adjusted', 'writtenoff']) | (models.Q(Iorder__isnull=False) & ~models.Q(Istatus='available')),
                name='Iorder_matches_Istatus'
            ),
            models.CheckConstraint(
                check=models.Q(Irating__isnull=True) | models.Q(Irating__gte=1, Irating__lte=5),
                name='Irating_between_one_and_five'
            )
        ]

    def __str__(self):

        return f'Item {self.pk} - {self.Iproduct.Pname} (expires {self.Iexpiry})'


class StockAdjustment(models.Model):
    request_id = models.UUIDField(unique=True, editable=False)
    kind = models.CharField(max_length=12, choices=[('correction', 'Count correction'), ('writeoff', 'Write-off')])
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    batch = models.ForeignKey(InventoryBatch, null=True, blank=True, on_delete=models.PROTECT)
    received = models.DateField()
    recorded_date = models.DateField(null=True, blank=True)
    before_count = models.PositiveIntegerField()
    after_count = models.PositiveIntegerField()
    difference = models.IntegerField()
    reason = models.CharField(max_length=500)
    note = models.TextField(blank=True)
    staff = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    items = models.ManyToManyField(Item, related_name='stock_adjustments')

    class Meta:
        ordering = ['-created_at', '-pk']


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



class Review(models.Model):

    Rrating = models.IntegerField()
    Rtext = models.TextField(blank=True)
    Rvisible = models.BooleanField(default=True)
    Rdate = models.DateField()
    Rcustomer = models.ForeignKey(Customer, on_delete=models.RESTRICT, related_name='customer_reviews')
    Rproduct = models.ForeignKey(Product, on_delete=models.RESTRICT, related_name='product_reviews')
    # The delivered item that proves this customer bought the product
    Ritem = models.ForeignKey(Item, on_delete=models.RESTRICT, related_name='item_reviews')

    # Add constraint to ensure one review per customer and product
    # Add constraint to ensure that Rrating is between 1 and 5

    class Meta:

        constraints = [
            models.UniqueConstraint(fields=['Rcustomer', 'Rproduct'], name='one_review_per_customer_product'),
            models.CheckConstraint(
                condition=models.Q(Rrating__gte=1, Rrating__lte=5),
                name='Rrating_between_one_and_five'
            )
        ]

    def __str__(self):

        return f'Review {self.pk} - {self.Rproduct.Pname} ({self.Rrating}/5)'



class Subscription(models.Model):

    STATUS = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('cancelled', 'Cancelled')
    ]

    INTERVAL = [
        (7, 'Every 7 days'),
        (14, 'Every 14 days'),
        (30, 'Every 30 days')
    ]

    Squantity = models.PositiveIntegerField()
    Sinterval = models.IntegerField(choices=INTERVAL)
    Snextdate = models.DateField()
    # The most the customer agreed to pay for one scheduled order
    Sceiling = models.FloatField()
    Sstatus = models.CharField(max_length=10, choices=STATUS, default='active')
    Screated = models.DateField()
    Scustomer = models.ForeignKey(Customer, on_delete=models.RESTRICT, related_name='customer_subscriptions')
    Sproduct = models.ForeignKey(Product, on_delete=models.RESTRICT, related_name='product_subscriptions')

    # Add constraint to ensure that Squantity is at least 1 and Sceiling is greater than 0

    class Meta:

        constraints = [
            models.CheckConstraint(
                condition=models.Q(Squantity__gte=1, Sceiling__gt=0),
                name='Squantity_and_Sceiling_positive'
            )
        ]

    def __str__(self):

        return f'Subscription {self.pk} - {self.Sproduct.Pname} for {self.Scustomer.Cname}'



class SubscriptionCycle(models.Model):

    RESULT = [
        ('ordered', 'Order created'),
        ('failed', 'No order created'),
        ('skipped', 'Skipped by customer')
    ]

    SCdate = models.DateField()
    SCscheduleddate = models.DateField(null=True, blank=True)
    SCretryable = models.BooleanField(default=False)
    SCresult = models.CharField(max_length=10, choices=RESULT)
    SCnote = models.CharField(max_length=255, blank=True)
    SCsubscription = models.ForeignKey(Subscription, on_delete=models.RESTRICT, related_name='subscription_cycles')
    SCorder = models.OneToOneField(Orders, on_delete=models.RESTRICT, related_name='subscription_cycle', blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['SCsubscription', 'SCscheduleddate'], name='unique_subscription_scheduled_cycle')]

    def __str__(self):

        return f'Cycle {self.pk} - subscription {self.SCsubscription_id} on {self.SCdate}'



class GroupPurchase(models.Model):

    STATUS = [
        ('open', 'Open'),
        ('locked', 'Locked'),
        ('ordered', 'Ordered')
    ]

    Gname = models.CharField(max_length=100)
    # Random text in the invitation link, so only invited customers can find the group
    Gcode = models.CharField(max_length=32, unique=True)
    Gaddress = models.CharField(max_length=255)
    Gstatus = models.CharField(max_length=10, choices=STATUS, default='open')
    Gcreated = models.DateField()
    Gorganiser = models.ForeignKey(Customer, on_delete=models.RESTRICT, related_name='organised_groups')
    Gorder = models.OneToOneField(Orders, on_delete=models.RESTRICT, related_name='group_purchase', blank=True, null=True)

    # Add constraint to ensure that only an ordered group has an order

    class Meta:

        constraints = [
            models.CheckConstraint(
                condition=models.Q(Gstatus='ordered', Gorder__isnull=False) | (~models.Q(Gstatus='ordered') & models.Q(Gorder__isnull=True)),
                name='Gorder_matches_Gstatus'
            )
        ]

    def __str__(self):

        return f'Group {self.pk} - {self.Gname}'



class GroupMember(models.Model):

    GMgroup = models.ForeignKey(GroupPurchase, on_delete=models.CASCADE, related_name='group_members')
    GMcustomer = models.ForeignKey(Customer, on_delete=models.RESTRICT, related_name='customer_groups')

    class Meta:

        constraints = [
            models.UniqueConstraint(fields=['GMgroup', 'GMcustomer'], name='one_membership_per_customer_group')
        ]

    def __str__(self):

        return f'{self.GMcustomer.Cname} in {self.GMgroup.Gname}'



class GroupLine(models.Model):

    GLquantity = models.PositiveIntegerField()
    GLgroup = models.ForeignKey(GroupPurchase, on_delete=models.CASCADE, related_name='group_lines')
    GLcustomer = models.ForeignKey(Customer, on_delete=models.RESTRICT, related_name='customer_group_lines')
    GLproduct = models.ForeignKey(Product, on_delete=models.RESTRICT, related_name='product_group_lines')

    # Add constraint to ensure one line per member and product, with a quantity of at least 1

    class Meta:

        constraints = [
            models.UniqueConstraint(fields=['GLgroup', 'GLcustomer', 'GLproduct'], name='one_line_per_member_product'),
            models.CheckConstraint(condition=models.Q(GLquantity__gte=1), name='GLquantity_at_least_one')
        ]

    def __str__(self):

        return f'{self.GLquantity} x {self.GLproduct.Pname} for {self.GLcustomer.Cname}'



class SavedItem(models.Model):

    # A product on a customer's shopping list

    SVadded = models.DateField()
    SVcustomer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='customer_saved_items')
    SVproduct = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_saved_items')

    class Meta:

        constraints = [
            models.UniqueConstraint(fields=['SVcustomer', 'SVproduct'], name='one_saved_item_per_customer_product')
        ]

    def __str__(self):

        return f'{self.SVproduct.Pname} saved by {self.SVcustomer.Cname}'



class StockNotice(models.Model):

    # A customer asked to be told when an unavailable product can be bought again

    SNcreated = models.DateField()
    SNcustomer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='customer_notices')
    SNproduct = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_notices')

    class Meta:

        constraints = [
            models.UniqueConstraint(fields=['SNcustomer', 'SNproduct'], name='one_notice_per_customer_product')
        ]

    def __str__(self):

        return f'{self.SNcustomer.Cname} waiting for {self.SNproduct.Pname}'


class RestockCapture(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    employee = models.ForeignKey(User, on_delete=models.PROTECT)
    captured_at = models.DateTimeField(auto_now_add=True)
    fingerprint = models.CharField(max_length=64, unique=True)
    snapshot = models.JSONField()

    class Meta:
        ordering = ['-captured_at', '-pk']


class ReviewModeration(models.Model):
    review = models.ForeignKey(Review, on_delete=models.PROTECT, related_name='moderation_history')
    employee = models.ForeignKey(User, on_delete=models.PROTECT)
    action = models.CharField(max_length=7, choices=[('hide', 'Hidden'), ('restore', 'Restored')])
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
