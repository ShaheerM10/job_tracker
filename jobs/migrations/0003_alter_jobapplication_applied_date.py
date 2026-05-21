import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0002_jobapplication_employment_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobapplication',
            name='applied_date',
            field=models.DateField(default=datetime.date.today),
        ),
    ]
