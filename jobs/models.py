import datetime
import secrets
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

    EMPLOYMENT_TYPE_CHOICES = [
        ('', '—'),
        ('full_time', 'Full-time'),
        ('part_time', 'Part-time'),
        ('contract', 'Contract'),
        ('internship', 'Internship'),
        ('temporary', 'Temporary'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    job_title = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True, null=True)
    salary_range = models.CharField(max_length=120, blank=True, null=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, blank=True, default='')
    job_link = models.URLField(max_length=1000, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='applied')
    applied_date = models.DateField(default=datetime.date.today)
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


class AuthToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_for_user(cls, user):
        tok = secrets.token_urlsafe(48)
        return cls.objects.create(user=user, token=tok)

    def __str__(self):
        return f"Token for {self.user.email}"
