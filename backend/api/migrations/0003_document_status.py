from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_advanced_rag'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('processing', 'Processing'),
                    ('done', 'Done'),
                    ('failed', 'Failed'),
                ],
                default='done',   # existing rows are already fully ingested
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='document',
            name='chunks_total',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='document',
            name='chunks_done',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='document',
            name='error_message',
            field=models.TextField(blank=True, default=''),
        ),
    ]
