# Generated by Django 2.2.24 on 2022-01-14 18:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('management', '0036_auto_20211118_1956'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='admin_default',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='role',
            name='admin_default',
            field=models.BooleanField(default=False),
        )
    ]
