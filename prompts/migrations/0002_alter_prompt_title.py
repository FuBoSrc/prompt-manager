# Generated by Django 4.2.10 on 2025-06-18 10:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prompts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prompt',
            name='title',
            field=models.CharField(max_length=200, unique=True),
        ),
    ]
