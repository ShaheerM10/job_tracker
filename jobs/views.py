from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.http import FileResponse, Http404
from datetime import timedelta
import os
import json
from .models import JobApplication
from .forms import JobApplicationForm
from zoneinfo import ZoneInfo
import django.utils.timezone as dj_tz


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'jobs/landing.html')


@login_required
def dashboard(request):
    from django.db.models.functions import TruncDay

    apps = JobApplication.objects.filter(user=request.user)
    total = apps.count()
    status_counts = dict(apps.values_list('status').annotate(count=Count('status')))

    today = timezone.localdate()
    thirty_days_ago = today - timedelta(days=29)
    six_months_ago = today - timedelta(days=180)

    # Daily — last 30 days, with zero-fill for empty days
    daily_qs = (
        apps.filter(applied_date__gte=thirty_days_ago)
        .annotate(day=TruncDay('applied_date'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    daily_map = {}
    for row in daily_qs:
        d = row['day']
        if hasattr(d, 'date'):
            d = d.date()
        daily_map[d] = row['count']
    daily_labels = []
    daily_data = []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        daily_labels.append(d.strftime('%b %d'))
        daily_data.append(daily_map.get(d, 0))

    # Monthly — last 6 months
    monthly_qs = (
        apps.filter(applied_date__gte=six_months_ago)
        .annotate(month=TruncMonth('applied_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    monthly_labels = [m['month'].strftime('%b %Y') for m in monthly_qs]
    monthly_data = [m['count'] for m in monthly_qs]

    # Weekly — last 12 weeks (zero-filled)
    from django.db.models.functions import TruncWeek
    twelve_weeks_ago = today - timedelta(weeks=12)
    weekly_qs = (
        apps.filter(applied_date__gte=twelve_weeks_ago)
        .annotate(week=TruncWeek('applied_date'))
        .values('week')
        .annotate(count=Count('id'))
        .order_by('week')
    )
    weekly_map = {}
    for row in weekly_qs:
        d = row['week']
        if hasattr(d, 'date'):
            d = d.date()
        weekly_map[d] = row['count']
    # Build 12-week buckets (Mon-start)
    import datetime as _dt
    # Find the Monday of the week 12 weeks ago
    start_monday = twelve_weeks_ago - _dt.timedelta(days=twelve_weeks_ago.weekday())
    weekly_labels = []
    weekly_data = []
    for i in range(12):
        monday = start_monday + _dt.timedelta(weeks=i)
        weekly_labels.append(monday.strftime('%b %d'))
        weekly_data.append(weekly_map.get(monday, 0))

    # Yearly — all time grouped by year
    from django.db.models.functions import TruncYear
    yearly_qs = (
        apps.annotate(year=TruncYear('applied_date'))
        .values('year')
        .annotate(count=Count('id'))
        .order_by('year')
    )
    yearly_labels = [y['year'].strftime('%Y') for y in yearly_qs]
    yearly_data = [y['count'] for y in yearly_qs]

    all_statuses = [s[0] for s in JobApplication.STATUS_CHOICES]
    status_labels = [s[1] for s in JobApplication.STATUS_CHOICES]
    status_data = [status_counts.get(s, 0) for s in all_statuses]

    # Trend — applied vs responded per day (last 30 days)
    responded_statuses = ['screening', 'interview', 'technical', 'offer', 'accepted']
    responded_qs = (
        apps.filter(applied_date__gte=thirty_days_ago, status__in=responded_statuses)
        .annotate(day=TruncDay('applied_date'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    responded_map = {}
    for row in responded_qs:
        d = row['day']
        if hasattr(d, 'date'):
            d = d.date()
        responded_map[d] = row['count']
    trend_responded_data = [responded_map.get(thirty_days_ago + timedelta(days=i), 0) for i in range(30)]

    # Last-7-days growth vs prior 7 days for the KPI
    last7 = sum(daily_map.get(today - timedelta(days=i), 0) for i in range(7))
    prev7 = sum(daily_map.get(today - timedelta(days=i), 0) for i in range(7, 14))
    if prev7 > 0:
        growth_pct = round(((last7 - prev7) / prev7) * 100)
    elif last7 > 0:
        growth_pct = 100
    else:
        growth_pct = 0

    recent = apps[:5]
    response_rate = 0
    if total > 0:
        responded = sum(status_counts.get(s, 0) for s in responded_statuses)
        response_rate = round((responded / total) * 100)

    # Top companies by application count
    top_companies_qs = (
        apps.values('company')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )
    top_companies = list(top_companies_qs)

    context = {
        'apps': apps,
        'total': total,
        'status_counts': status_counts,
        'recent': recent,
        'response_rate': response_rate,
        'daily_labels': json.dumps(daily_labels),
        'daily_data': json.dumps(daily_data),
        'trend_responded_data': json.dumps(trend_responded_data),
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_data': json.dumps(monthly_data),
        'weekly_labels': json.dumps(weekly_labels),
        'weekly_data': json.dumps(weekly_data),
        'yearly_labels': json.dumps(yearly_labels),
        'yearly_data': json.dumps(yearly_data),
        'status_labels': json.dumps(status_labels),
        'status_data': json.dumps(status_data),
        'last7_count': last7,
        'growth_pct': growth_pct,
        'active_count': status_counts.get('interview', 0) + status_counts.get('technical', 0) + status_counts.get('screening', 0),
        'offer_count': status_counts.get('offer', 0) + status_counts.get('accepted', 0),
        'rejected_count': status_counts.get('rejected', 0),
        'applied_count': status_counts.get('applied', 0),
        'top_companies': top_companies,
    }
    return render(request, 'jobs/dashboard.html', context)


@login_required
def application_list(request):
    apps = JobApplication.objects.filter(user=request.user)
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '').strip()
    if status_filter:
        apps = apps.filter(status=status_filter)
    if search:
        apps = apps.filter(
            Q(job_title__icontains=search)
            | Q(company__icontains=search)
            | Q(location__icontains=search)
        )

    total_count = apps.count()
    paginator = Paginator(apps, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)
    base_qs = querystring.urlencode()

    context = {
        'page_obj': page_obj,
        'apps': page_obj.object_list,
        'paginator': paginator,
        'total_count': total_count,
        'status_choices': JobApplication.STATUS_CHOICES,
        'current_status': status_filter,
        'search': search,
        'base_qs': base_qs,
    }
    return render(request, 'jobs/list.html', context)


@login_required
def add_application(request):
    if request.method == 'POST':
        form = JobApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            app = form.save(commit=False)
            app.user = request.user
            app.save()
            return redirect('dashboard')
    else:
        form = JobApplicationForm()
    return render(request, 'jobs/form.html', {'form': form, 'title': 'New Application'})


@login_required
def edit_application(request, pk):
    app = get_object_or_404(JobApplication, pk=pk, user=request.user)
    if request.method == 'POST':
        form = JobApplicationForm(request.POST, request.FILES, instance=app)
        if form.is_valid():
            form.save()
            return redirect('application_list')
    else:
        form = JobApplicationForm(instance=app)
    return render(request, 'jobs/form.html', {'form': form, 'title': 'Edit Application', 'app': app})


@login_required
def update_status(request, pk):
    from django.http import JsonResponse
    if request.method == 'POST':
        app = get_object_or_404(JobApplication, pk=pk, user=request.user)
        status = request.POST.get('status')
        valid = ['applied','screening','interview','technical','offer','rejected','withdrawn','accepted']
        if status in valid:
            app.status = status
            app.save(update_fields=['status'])
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'status': app.status})
    return redirect('application_list')

@login_required
def delete_application(request, pk):
    app = get_object_or_404(JobApplication, pk=pk, user=request.user)
    if request.method == 'POST':
        app.delete()
        return redirect('application_list')
    return render(request, 'jobs/confirm_delete.html', {'app': app})


@login_required
def view_resume(request, pk):
    app = get_object_or_404(JobApplication, pk=pk, user=request.user)
    if not app.resume:
        raise Http404("No resume uploaded")
    return render(request, 'jobs/resume_view.html', {'app': app})


@login_required
def download_resume(request, pk):
    app = get_object_or_404(JobApplication, pk=pk, user=request.user)
    if not app.resume:
        raise Http404("No resume uploaded")
    file_path = app.resume.path
    if not os.path.exists(file_path):
        raise Http404("File not found")
    filename = os.path.basename(file_path)
    response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
    return response


def logout_view(request):
    logout(request)
    return redirect('landing')


@login_required
def application_detail(request, pk):
    app = get_object_or_404(JobApplication, pk=pk, user=request.user)
    return render(request, 'jobs/detail.html', {'app': app})


@login_required
def serve_resume(request, pk):
    """Serve resume with correct content-type for iframe embedding"""
    app = get_object_or_404(JobApplication, pk=pk, user=request.user)
    if not app.resume:
        raise Http404("No resume")
    import mimetypes
    file_path = app.resume.path
    if not os.path.exists(file_path):
        raise Http404("File not found")
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'application/octet-stream'
    response = FileResponse(open(file_path, 'rb'), content_type=mime_type)
    # Allow iframe embedding (same origin)
    response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@login_required
def company_logo(request, company):
    """Proxy company logos from apistemic API"""
    import requests as req
    import re
    # Clean company name to domain guess
    domain = re.sub(r'[^a-z0-9]', '', company.lower()) + '.com'
    try:
        r = req.get(
            f"https://logos-api.apistemic.com/domain:{domain}",
            headers={"User-Agent": "Trackr (trackr@example.com)"},
            timeout=3
        )
        if r.status_code == 200:
            from django.http import HttpResponse
            return HttpResponse(r.content, content_type=r.headers.get('Content-Type', 'image/png'))
    except Exception:
        pass
    from django.http import HttpResponse
    return HttpResponse(status=404)


EXTRACT_TOOL = {
    "name": "record_job",
    "description": "Record structured job posting details extracted from the provided content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "job_title": {"type": "string", "description": "The job title/role. Empty if unknown."},
            "company": {"type": "string", "description": "The hiring company name. Empty if unknown."},
            "location": {"type": "string", "description": "City, region, country, or 'Remote'. Empty if unknown."},
            "salary_range": {"type": "string", "description": "Free-text salary range exactly as posted (e.g. '$120k–$150k'). Empty if not posted."},
            "employment_type": {
                "type": "string",
                "enum": ["", "full_time", "part_time", "contract", "internship", "temporary"],
                "description": "Use empty string if not explicitly stated.",
            },
            "description": {"type": "string", "description": "A clean readable summary of the role, responsibilities, and requirements. Max ~5000 chars. Exclude site boilerplate, nav, cookie banners."},
        },
        "required": ["job_title", "company", "location", "salary_range", "employment_type", "description"],
    },
}


@login_required
def scrape_job(request):
    """Extract structured job details from a URL or pasted text using Claude."""
    from django.http import JsonResponse
    import json as json_lib
    import requests as req
    import trafilatura

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json_lib.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid request'}, status=400)

    url = (body.get('url') or '').strip()
    text = (body.get('text') or '').strip()
    if not url and not text:
        return JsonResponse({'error': 'Provide a URL or pasted text.'}, status=400)

    content = text
    if not content and url:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            resp = req.get(url, headers=headers, timeout=10)
            content = trafilatura.extract(resp.text, include_comments=False, include_tables=False) or ''
        except req.exceptions.Timeout:
            return JsonResponse({'error': 'Page took too long to load. Try pasting the text.'}, status=408)
        except Exception:
            return JsonResponse({'error': 'Could not load this page. Try pasting the text.'}, status=502)

    if not content.strip():
        return JsonResponse({'error': 'No readable content found at that URL. Try pasting the text.'}, status=422)

    content = content[:15000]

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return JsonResponse({'error': 'Server is not configured for AI extraction.'}, status=500)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-haiku-4-5',
            max_tokens=2000,
            tools=[EXTRACT_TOOL],
            tool_choice={'type': 'tool', 'name': 'record_job'},
            messages=[{
                'role': 'user',
                'content': (
                    "Extract the job posting details from the content below. "
                    "Use empty strings for fields you cannot confidently determine from the content. "
                    "The description should be a clean, readable summary of the role, responsibilities, "
                    "and requirements — not site boilerplate, navigation, or cookie banners.\n\n"
                    "---\n" + content
                ),
            }],
        )
        tool_use = next((b for b in msg.content if getattr(b, 'type', None) == 'tool_use'), None)
        if not tool_use:
            return JsonResponse({'error': 'AI returned no structured result.'}, status=502)
        data = tool_use.input or {}
    except Exception:
        return JsonResponse({'error': 'AI extraction failed. Try again or paste manually.'}, status=502)

    return JsonResponse({
        'title': (data.get('job_title') or '')[:200],
        'company': (data.get('company') or '')[:200],
        'location': (data.get('location') or '')[:200],
        'salary_range': (data.get('salary_range') or '')[:120],
        'employment_type': data.get('employment_type') or '',
        'description': (data.get('description') or '')[:5000],
    })



def set_timezone(request):
    from django.http import JsonResponse
    import json
    if request.method == 'POST':
        data = json.loads(request.body)
        tz = data.get('timezone', 'UTC')
        request.session['timezone'] = tz
    return JsonResponse({'status': 'ok'})    


@login_required
def user_settings(request):
    from django.http import JsonResponse
    import zoneinfo

    # Curated timezone list: (value, label)
    TIMEZONE_CHOICES = [
        ("Africa", [
            ("Africa/Cairo", "Cairo (EET, UTC+2)"),
            ("Africa/Johannesburg", "Johannesburg (SAST, UTC+2)"),
            ("Africa/Lagos", "Lagos (WAT, UTC+1)"),
            ("Africa/Nairobi", "Nairobi (EAT, UTC+3)"),
        ]),
        ("America", [
            ("America/Anchorage", "Anchorage (AKST, UTC-9)"),
            ("America/Chicago", "Chicago (CST, UTC-6)"),
            ("America/Denver", "Denver (MST, UTC-7)"),
            ("America/Halifax", "Halifax (AST, UTC-4)"),
            ("America/Los_Angeles", "Los Angeles (PST, UTC-8)"),
            ("America/Mexico_City", "Mexico City (CST, UTC-6)"),
            ("America/New_York", "New York (EST, UTC-5)"),
            ("America/Phoenix", "Phoenix (MST, UTC-7)"),
            ("America/Sao_Paulo", "São Paulo (BRT, UTC-3)"),
            ("America/St_Johns", "St. John's (NST, UTC-3:30)"),
            ("America/Toronto", "Toronto (EST, UTC-5)"),
            ("America/Vancouver", "Vancouver (PST, UTC-8)"),
            ("America/Winnipeg", "Winnipeg (CST, UTC-6)"),
        ]),
        ("Asia", [
            ("Asia/Almaty", "Almaty (ALMT, UTC+6)"),
            ("Asia/Baghdad", "Baghdad (AST, UTC+3)"),
            ("Asia/Bangkok", "Bangkok (ICT, UTC+7)"),
            ("Asia/Colombo", "Colombo (IST, UTC+5:30)"),
            ("Asia/Dhaka", "Dhaka (BST, UTC+6)"),
            ("Asia/Dubai", "Dubai (GST, UTC+4)"),
            ("Asia/Ho_Chi_Minh", "Ho Chi Minh City (ICT, UTC+7)"),
            ("Asia/Hong_Kong", "Hong Kong (HKT, UTC+8)"),
            ("Asia/Jakarta", "Jakarta (WIB, UTC+7)"),
            ("Asia/Karachi", "Karachi (PKT, UTC+5)"),
            ("Asia/Kolkata", "Kolkata / Mumbai (IST, UTC+5:30)"),
            ("Asia/Kuala_Lumpur", "Kuala Lumpur (MYT, UTC+8)"),
            ("Asia/Kuwait", "Kuwait (AST, UTC+3)"),
            ("Asia/Manila", "Manila (PHT, UTC+8)"),
            ("Asia/Riyadh", "Riyadh (AST, UTC+3)"),
            ("Asia/Seoul", "Seoul (KST, UTC+9)"),
            ("Asia/Shanghai", "Shanghai / Beijing (CST, UTC+8)"),
            ("Asia/Singapore", "Singapore (SGT, UTC+8)"),
            ("Asia/Taipei", "Taipei (CST, UTC+8)"),
            ("Asia/Tashkent", "Tashkent (UZT, UTC+5)"),
            ("Asia/Tehran", "Tehran (IRST, UTC+3:30)"),
            ("Asia/Tokyo", "Tokyo (JST, UTC+9)"),
        ]),
        ("Atlantic / UTC", [
            ("UTC", "UTC (Coordinated Universal Time)"),
            ("Atlantic/Reykjavik", "Reykjavik (GMT, UTC+0)"),
        ]),
        ("Australia", [
            ("Australia/Adelaide", "Adelaide (ACST, UTC+9:30)"),
            ("Australia/Brisbane", "Brisbane (AEST, UTC+10)"),
            ("Australia/Melbourne", "Melbourne (AEST, UTC+10)"),
            ("Australia/Perth", "Perth (AWST, UTC+8)"),
            ("Australia/Sydney", "Sydney (AEST, UTC+10)"),
        ]),
        ("Europe", [
            ("Europe/Amsterdam", "Amsterdam (CET, UTC+1)"),
            ("Europe/Athens", "Athens (EET, UTC+2)"),
            ("Europe/Berlin", "Berlin (CET, UTC+1)"),
            ("Europe/Brussels", "Brussels (CET, UTC+1)"),
            ("Europe/Bucharest", "Bucharest (EET, UTC+2)"),
            ("Europe/Dublin", "Dublin (GMT, UTC+0)"),
            ("Europe/Helsinki", "Helsinki (EET, UTC+2)"),
            ("Europe/Istanbul", "Istanbul (TRT, UTC+3)"),
            ("Europe/Kiev", "Kyiv (EET, UTC+2)"),
            ("Europe/Lisbon", "Lisbon (WET, UTC+0)"),
            ("Europe/London", "London (GMT, UTC+0)"),
            ("Europe/Madrid", "Madrid (CET, UTC+1)"),
            ("Europe/Moscow", "Moscow (MSK, UTC+3)"),
            ("Europe/Oslo", "Oslo (CET, UTC+1)"),
            ("Europe/Paris", "Paris (CET, UTC+1)"),
            ("Europe/Prague", "Prague (CET, UTC+1)"),
            ("Europe/Rome", "Rome (CET, UTC+1)"),
            ("Europe/Stockholm", "Stockholm (CET, UTC+1)"),
            ("Europe/Vienna", "Vienna (CET, UTC+1)"),
            ("Europe/Warsaw", "Warsaw (CET, UTC+1)"),
            ("Europe/Zurich", "Zurich (CET, UTC+1)"),
        ]),
        ("Pacific", [
            ("Pacific/Auckland", "Auckland (NZST, UTC+12)"),
            ("Pacific/Fiji", "Fiji (FJT, UTC+12)"),
            ("Pacific/Honolulu", "Honolulu (HST, UTC-10)"),
        ]),
    ]

    if request.method == 'POST':
        tz = request.POST.get('timezone', 'UTC')
        try:
            zoneinfo.ZoneInfo(tz)   # validate
            request.session['timezone'] = tz
            from django.utils import timezone as dj_tz
            dj_tz.activate(zoneinfo.ZoneInfo(tz))
            from django.contrib import messages
            messages.success(request, 'Timezone updated.')
        except Exception:
            from django.contrib import messages
            messages.error(request, 'Invalid timezone.')
        return redirect('user_settings')

    current_tz = request.session.get('timezone', 'UTC')
    return render(request, 'jobs/settings.html', {
        'timezone_choices': TIMEZONE_CHOICES,
        'current_tz': current_tz,
    })
