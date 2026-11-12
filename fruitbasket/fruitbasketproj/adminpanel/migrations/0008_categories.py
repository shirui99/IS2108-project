# AD07 category migration, 13 November 2026 (Django 5.2.19).

import adminpanel.models
import django.db.models.deletion
import django.db.models.functions
import django.db.models.lookups
from django.db import migrations, models


LEGACY = [
    ('dairy', 'Dairy, Chilled & Eggs'), ('fruit', 'Fruit & Vegetables'),
    ('meat', 'Meat & Seafood'), ('bakery', 'Bakery'),
    ('rice', 'Rice, Noodles & Cooking Ingredients'),
    ('snacks', 'Snacks & Confectionery'), ('frozen', 'Frozen'), ('household', 'Household'),
]


def seed_categories(apps, schema_editor):
    Product = apps.get_model('adminpanel', 'Product')
    Category = apps.get_model('adminpanel', 'Category')
    alias = schema_editor.connection.alias
    unexpected = set(Product.objects.using(alias).values_list('Pcategory', flat=True)) - dict(LEGACY).keys()
    if unexpected:
        raise RuntimeError('AD07 cannot migrate unexpected category codes: ' + repr(sorted(unexpected)))
    for code, name in LEGACY:
        Category.objects.using(alias).create(Ccode=code, Cname=name)


def check_rollback(apps, schema_editor):
    Category = apps.get_model('adminpanel', 'Category')
    if Category.objects.using(schema_editor.connection.alias).exclude(Ccode__in=dict(LEGACY)).exists():
        raise RuntimeError('AD07 rollback blocked: export and resolve staff-created categories before reversing; old code only supports eight categories.')


class Migration(migrations.Migration):

    dependencies = [
        ('adminpanel', '0007_item_ipurchasedprice_product_pbulkprice_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('Ccode', models.CharField(default=adminpanel.models.category_code, editable=False, max_length=20, primary_key=True, serialize=False)),
                ('Cname', models.CharField(db_collation='nocase', max_length=200, unique=True, verbose_name='Category name')),
            ],
            options={
                'ordering': ['Cname', 'Ccode'],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('Cname', ''), _negated=True), ('Cname', models.Func(models.F('Cname'), models.Value('\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'), function='TRIM'))), name='category_name_trimmed_nonempty'), models.CheckConstraint(condition=django.db.models.lookups.LessThanOrEqual(django.db.models.functions.Length('Cname'), models.Value(200)), name='category_name_length')],
            },
        ),
        migrations.RunPython(seed_categories, check_rollback),
        migrations.AlterField(
            model_name='product',
            name='Pcategory',
            field=models.ForeignKey(db_column='Pcategory', on_delete=django.db.models.deletion.PROTECT, related_name='products', to='adminpanel.category', verbose_name='Category'),
        ),
    ]
