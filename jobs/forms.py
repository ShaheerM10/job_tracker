from django import forms
from .models import JobApplication


class JobApplicationForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = ['job_title', 'company', 'location', 'salary_range', 'employment_type',
                  'job_link', 'description', 'resume', 'status', 'applied_date', 'notes']
        widgets = {
            'job_title':       forms.TextInput(attrs={'placeholder': 'e.g. Senior Software Engineer', 'class': 'form-input'}),
            'company':         forms.TextInput(attrs={'placeholder': 'e.g. Google', 'class': 'form-input'}),
            'location':        forms.TextInput(attrs={'placeholder': 'e.g. Remote · New York, NY', 'class': 'form-input'}),
            'salary_range':    forms.TextInput(attrs={'placeholder': 'e.g. $120k–$150k', 'class': 'form-input'}),
            'employment_type': forms.Select(attrs={'class': 'form-select'}),
            'job_link':        forms.URLInput(attrs={'placeholder': 'https://...', 'class': 'form-input'}),
            'description':     forms.Textarea(attrs={'rows': 4, 'placeholder': 'Job description, requirements...', 'class': 'form-textarea'}),
            'notes':           forms.Textarea(attrs={'rows': 3, 'placeholder': 'Your notes, follow-ups...', 'class': 'form-textarea'}),
            'status':          forms.Select(attrs={'class': 'form-select'}),
            'resume':          forms.FileInput(attrs={'class': 'form-file', 'accept': '.pdf,.doc,.docx'}),
            'applied_date':    forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
        }
