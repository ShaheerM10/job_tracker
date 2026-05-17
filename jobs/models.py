from django.db import models
from django.contrib.auth.models import User


class JobApplication(models.Model):
    STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('screening', 'Screening'),
        ('interview', 'Interview'),
        ('technical', 'Technical Round'),
        ('offer', 'Offer Received'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
        ('accepted', 'Accepted'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    job_title = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    job_link = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='applied')
    applied_date = models.DateField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-applied_date']

    def __str__(self):
        return f"{self.job_title} at {self.company}"

    @property
    def status_color(self):
        colors = {
            'applied': 'blue',
            'screening': 'purple',
            'interview': 'yellow',
            'technical': 'orange',
            'offer': 'green',
            'rejected': 'red',
            'withdrawn': 'gray',
            'accepted': 'emerald',
        }
        return colors.get(self.status, 'gray')
