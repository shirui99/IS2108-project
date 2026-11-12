from django.contrib.auth.models import User
from django.db import models
from django.core.validators import MinValueValidator

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

    PAYMENT = [
        ('paid', 'Paid (simulated)'),
        ('refunded', 'Refunded (simulated)')
    ]

    Oid = models.CharField(max_length=6, primary_key=True)
    Odate = models.DateField()
    Oaddress = models.CharField(max_length=255)
    Ostatus = models.CharField(max_length=10, choices=STATUS, default='placed')
    Opayment = models.CharField(max_length=10, choices=PAYMENT, default='paid', verbose_name='Simulated payment')

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
    SCresult = models.CharField(max_length=10, choices=RESULT)
    SCnote = models.CharField(max_length=255, blank=True)
    SCsubscription = models.ForeignKey(Subscription, on_delete=models.RESTRICT, related_name='subscription_cycles')
    SCorder = models.OneToOneField(Orders, on_delete=models.RESTRICT, related_name='subscription_cycle', blank=True, null=True)

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
