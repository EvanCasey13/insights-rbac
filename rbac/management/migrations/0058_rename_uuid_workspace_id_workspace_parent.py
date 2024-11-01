# Generated by Django 4.2.16 on 2024-10-24 20:27

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("management", "0057_remove_workspace_id_remove_workspace_parent_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="workspace",
            old_name="uuid",
            new_name="id",
        ),
        migrations.AddField(
            model_name="workspace",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="management.workspace",
            ),
        ),
    ]