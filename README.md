# JobTrack — Django Job Application Tracker

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables (create a .env file)
GOOGLE_CLIENT_ID=your-google-oauth-client-id
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
SECRET_KEY=your-django-secret-key

# 3. Run migrations
python manage.py migrate

# 4. Create superuser (optional, for admin access)
python manage.py createsuperuser

# 5. Start server
python manage.py runserver
```

## Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project → Enable "Google OAuth2.0 API"
3. Create OAuth 2.0 credentials (Web Application)
4. Add authorized redirect URI: `http://localhost:8000/accounts/google/login/callback/`
5. Copy Client ID & Secret into your `.env` or `settings.py`

**Alternative without Google OAuth:**  
Users can also register with email/password at `/accounts/signup/`

## Features

- ✅ Google OAuth login + email/password auth
- ✅ Add applications: title, company, resume upload, job link, description
- ✅ 8 status stages: Applied → Accepted
- ✅ Analytics dashboard with bar chart (monthly) + donut (status)
- ✅ Filter/search applications list
- ✅ Edit & delete applications
- ✅ Per-user data isolation
