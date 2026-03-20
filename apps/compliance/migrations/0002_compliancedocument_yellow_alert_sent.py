# Generated migration for adding yellow_alert_sent field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="compliancedocument",
            name="yellow_alert_sent",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When the yellow 'expiring soon' alert was sent",
            ),
        ),
    ]
