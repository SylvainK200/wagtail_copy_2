# Generated by Django 3.1.1 on 2020-10-01 18:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("wagtailcore", "0057_page_locale_fields_notnull"),
        ("modeladmintest", "0008_solobook"),
    ]

    operations = [
        migrations.CreateModel(
            name="RelatedLink",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                (
                    "link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="wagtailcore.page",
                    ),
                ),
            ],
        ),
    ]
