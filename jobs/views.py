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
    apps = JobApplication.objects.filter(user=request.user).order_by('-applied_date', '-id')
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
        local_today = timezone.localdate()
        form = JobApplicationForm(initial={'applied_date': local_today})
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

    content = content[:30000]

    # Try AI extraction via Groq (free tier)
    groq_key = os.environ.get('GROQ_API_KEY')
    if groq_key:
        try:
            import requests as _gr, json as _gj, re as _gre

            def _groq(messages, max_tokens=512):
                r = _gr.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + groq_key, 'Content-Type': 'application/json'},
                    json={
                        'model': 'llama-3.1-8b-instant',
                        'messages': messages,
                        'max_tokens': max_tokens,
                        'temperature': 0.1,
                    },
                    timeout=25,
                )
                if r.ok:
                    return r.json()['choices'][0]['message']['content'].strip()
                return None

            # CALL 1: extract structured fields as clean JSON (no description)
            fields_prompt = (
                "From the job posting text below, extract ONLY these fields as a JSON object:\n"
                "  job_title, company, location, salary_range, employment_type\n"
                "Rules:\n"
                "- Reply with ONLY the JSON object, no explanation, no code fences\n"
                "- employment_type: one of full_time, part_time, contract, internship, temporary, or empty string\n"
                "- Use empty string for any field not found\n\n"
                "Text:\n" + content[:5000]
            )
            fields_out = _groq([{'role': 'user', 'content': fields_prompt}], max_tokens=256)
            fields = {}
            if fields_out:
                m = _gre.search(r'\{[^{}]*\}', fields_out, _gre.S)
                if m:
                    fields = _gj.loads(m.group())

            # CALL 2: extract full description as plain Markdown (not inside JSON)
            desc_prompt = (
                "From the job posting text below, extract the COMPLETE job description.\n"
                "Format it in Markdown:\n"
                "- Use ## for main section headings (About the Role, Responsibilities, Requirements, Qualifications, Benefits, etc.)\n"
                "- Use bullet points (- item) for lists\n"
                "- Use **bold** for important terms\n"
                "- Preserve ALL content — do not skip or summarise anything\n"
                "- Output ONLY the formatted description, nothing else\n\n"
                "Text:\n" + content[:20000]
            )
            desc_out = _groq([{'role': 'user', 'content': desc_prompt}], max_tokens=1500)

            if fields or desc_out:
                return JsonResponse({
                    'title':           (fields.get('job_title') or '')[:200],
                    'company':         (fields.get('company') or '')[:200],
                    'location':        (fields.get('location') or '')[:200],
                    'salary_range':    (fields.get('salary_range') or '')[:120],
                    'employment_type': fields.get('employment_type') or '',
                    'description':     (desc_out or _plaintext_to_md(content[:10000]))[:20000],
                })
        except Exception:
            pass  # Fall through to heuristic extraction

    # Heuristic extraction (no API key needed)
    import re as _re
    import json as _jmod

    def _plaintext_to_md(text):
        """Convert raw plain text job description to basic Markdown formatting."""
        if not text:
            return text
        # Known section heading keywords
        headings = [
            'about the role', 'about the job', 'about us', 'about the company',
            'the role', 'the position', 'job summary', 'job overview', 'overview',
            'responsibilities', 'what you will do', "what you'll do", 'your role',
            'requirements', 'qualifications', "what we're looking for", 'what you bring',
            'what you need', 'preferred qualifications', 'nice to have',
            'benefits', 'perks', 'what we offer', 'compensation', 'salary',
            'how to apply', 'apply', 'about the team',
        ]
        lines = text.splitlines()
        out = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                out.append('')
                continue
            lower = stripped.lower().rstrip(':').rstrip('.')
            if lower in headings or any(lower == h for h in headings):
                out.append('\n## ' + stripped.rstrip(':'))
            elif stripped.startswith(('• ', '· ', '- ', '* ', '◦ ')):
                out.append('- ' + stripped[2:].strip())
            elif len(stripped) < 80 and stripped.endswith(':') and stripped[0].isupper():
                out.append('\n## ' + stripped[:-1])
            else:
                out.append(stripped)
        return '\n'.join(out).strip()

    raw_html = ''
    if url:
        try:
            import requests as _req
            _r = _req.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            raw_html = _r.text
        except Exception:
            raw_html = ''

    def _get_meta(html, prop_name):
        """Extract meta tag content by property or name attribute."""
        tag_re = _re.compile(r'<meta\b[^>]*/?\s*>', _re.I | _re.S)
        for tag in tag_re.findall(html):
            nm = _re.search(r'(?:name|property)\s*=\s*["\']([^"\']+)["\']', tag, _re.I)
            if nm and nm.group(1).lower() == prop_name.lower():
                cm = _re.search(r'content\s*=\s*["\']([^"\']+)["\']', tag, _re.I)
                if cm:
                    return cm.group(1).strip()
        return ''

    result = {'title': '', 'company': '', 'location': '', 'salary_range': '', 'employment_type': '', 'description': ''}

    # 1. JSON-LD schema.org JobPosting
    script_re = _re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', _re.S | _re.I)
    for block in script_re.findall(raw_html):
        try:
            schema = _jmod.loads(block)
            if isinstance(schema, list):
                schema = schema[0]
            if isinstance(schema, dict) and schema.get('@type', '').lower() == 'jobposting':
                result['title']   = result['title']   or schema.get('title', '')
                org = schema.get('hiringOrganization', {})
                result['company'] = result['company'] or (org.get('name', '') if isinstance(org, dict) else '')
                loc = schema.get('jobLocation', {})
                if isinstance(loc, dict):
                    addr = loc.get('address', {})
                    if isinstance(addr, dict):
                        parts = [addr.get('addressLocality',''), addr.get('addressRegion',''), addr.get('addressCountry','')]
                        result['location'] = result['location'] or ', '.join(p for p in parts if p)
                    elif isinstance(addr, str):
                        result['location'] = result['location'] or addr
                result['description'] = result['description'] or str(schema.get('description', ''))[:20000]
                emp = schema.get('employmentType', '')
                emp_map = {'FULL_TIME': 'full_time', 'PART_TIME': 'part_time', 'CONTRACTOR': 'contract', 'INTERN': 'internship'}
                result['employment_type'] = emp_map.get(str(emp).upper(), '')
                break
        except Exception:
            continue

    # 2. Open Graph / meta tags
    if not result['title']:
        og = _get_meta(raw_html, 'og:title') or _get_meta(raw_html, 'twitter:title')
        if og:
            result['title'] = _re.sub(r'\s*[|\-]\s*.+$', '', og).strip()
    if not result['title']:
        m = _re.search(r'<title[^>]*>([^<]+)</title>', raw_html, _re.I)
        if m:
            result['title'] = _re.sub(r'\s*[|\-]\s*.+$', '', m.group(1)).strip()

    # 3. Text fallback
    if not result['title'] and content:
        lines_txt = [l.strip() for l in content.split('\n') if l.strip()]
        if lines_txt:
            result['title'] = lines_txt[0][:120]
    if not result['company'] and url:
        m = _re.search(r'https?://(?:www\.)?([^./]+)', url)
        if m:
            result['company'] = m.group(1).replace('-', ' ').title()
    if not result['description'] and content:
        result['description'] = _plaintext_to_md(content[:10000])

    # Clean HTML from description (but preserve newlines for Markdown)
    result['description'] = _re.sub(r'<[^>]+>', ' ', result['description'])
    result['description'] = result['description'].strip()[:20000]

    return JsonResponse({
        'title':           result['title'][:200],
        'company':         result['company'][:200],
        'location':        result['location'][:200],
        'salary_range':    result['salary_range'][:120],
        'employment_type': result['employment_type'],
        'description':     result['description'],
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


# ─────────────────────────────────────────────────────────────
#  CHROME EXTENSION API
# ─────────────────────────────────────────────────────────────
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import AuthToken

def _cors(response):
    """Add CORS headers so the Chrome extension can call the API."""
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
    response['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return response

def _json(data, status=200):
    return _cors(JsonResponse(data, status=status))

def _get_api_user(request):
    """Return User from Authorization: Token <tok> header, or None."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Token '):
        try:
            tok = AuthToken.objects.select_related('user').get(token=auth[6:])
            return tok.user
        except AuthToken.DoesNotExist:
            pass
    return None

def _api_auth(view_fn):
    from functools import wraps
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if request.method == 'OPTIONS':
            return _cors(JsonResponse({}))
        user = _get_api_user(request)
        if not user:
            return _json({'error': 'Unauthorized'}, 401)
        request.api_user = user
        return view_fn(request, *args, **kwargs)
    return wrapper


@csrf_exempt
def api_login(request):
    if request.method == 'OPTIONS':
        return _cors(JsonResponse({}))
    if request.method != 'POST':
        return _json({'error': 'POST required'}, 405)
    import json as _json_lib
    from django.contrib.auth import authenticate
    try:
        body = _json_lib.loads(request.body)
    except Exception:
        return _json({'error': 'Invalid JSON'}, 400)
    email = body.get('email', '').strip().lower()
    password = body.get('password', '')
    from django.contrib.auth.models import User as _User
    try:
        user_obj = _User.objects.get(email__iexact=email)
        username = user_obj.username
    except _User.DoesNotExist:
        return _json({'error': 'Invalid email or password'}, 401)
    user = authenticate(request, username=username, password=password)
    if not user:
        return _json({'error': 'Invalid email or password'}, 401)
    tok = AuthToken.create_for_user(user)
    return _json({
        'token': tok.token,
        'user': {'id': user.id, 'email': user.email,
                 'name': user.get_full_name() or user.email.split('@')[0]}
    })


@csrf_exempt
def api_signup(request):
    if request.method == 'OPTIONS':
        return _cors(JsonResponse({}))
    if request.method != 'POST':
        return _json({'error': 'POST required'}, 405)
    import json as _json_lib
    from django.contrib.auth.models import User as _User
    try:
        body = _json_lib.loads(request.body)
    except Exception:
        return _json({'error': 'Invalid JSON'}, 400)
    email = body.get('email', '').strip().lower()
    password = body.get('password', '')
    first_name = body.get('first_name', '').strip()
    last_name = body.get('last_name', '').strip()
    if not email or not password:
        return _json({'error': 'Email and password required'}, 400)
    if len(password) < 8:
        return _json({'error': 'Password must be at least 8 characters'}, 400)
    if _User.objects.filter(email__iexact=email).exists():
        return _json({'error': 'An account with this email already exists'}, 400)
    user = _User.objects.create_user(
        username=email, email=email, password=password,
        first_name=first_name, last_name=last_name
    )
    tok = AuthToken.create_for_user(user)
    return _json({
        'token': tok.token,
        'user': {'id': user.id, 'email': user.email,
                 'name': user.get_full_name() or email.split('@')[0]}
    }, 201)


@csrf_exempt
@_api_auth
def api_logout(request):
    if request.method == 'OPTIONS':
        return _cors(JsonResponse({}))
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Token '):
        AuthToken.objects.filter(token=auth[6:]).delete()
    return _json({'ok': True})


@csrf_exempt
@_api_auth
def api_me(request):
    if request.method == 'OPTIONS':
        return _cors(JsonResponse({}))
    u = request.api_user
    apps = JobApplication.objects.filter(user=u)
    counts = dict(apps.values_list('status').annotate(c=Count('status')))
    return _json({
        'id': u.id, 'email': u.email,
        'name': u.get_full_name() or u.email.split('@')[0],
        'total': apps.count(),
        'counts': counts,
    })


@csrf_exempt
@_api_auth
def api_applications(request):
    if request.method == 'OPTIONS':
        return _cors(JsonResponse({}))
    user = request.api_user

    if request.method == 'GET':
        apps = JobApplication.objects.filter(user=user)[:10]
        data = [{
            'id': a.pk,
            'company': a.company,
            'job_title': a.job_title,
            'status': a.status,
            'status_display': a.get_status_display(),
            'applied_date': str(a.applied_date),
            'location': a.location or '',
        } for a in apps]
        return _json({'applications': data})

    if request.method == 'POST':
        import json as _json_lib
        import datetime as _dt
        # Support both JSON and multipart/form-data (for file uploads)
        ct = request.content_type or ''
        if 'multipart' in ct or 'form-data' in ct:
            body = request.POST
            get = lambda k, d='': (body.get(k) or d)
        else:
            try:
                body = _json_lib.loads(request.body)
            except Exception:
                return _json({'error': 'Invalid JSON'}, 400)
            get = lambda k, d='': (body.get(k) or d)
        job_title = get('job_title').strip()
        company   = get('company').strip()
        if not job_title or not company:
            return _json({'error': 'job_title and company are required'}, 400)
        date_str = get('applied_date')
        try:
            applied_date = _dt.date.fromisoformat(date_str)
        except Exception:
            applied_date = timezone.localdate()
        # Sanitise employment_type — only accept valid model choices
        VALID_EMP = {'full_time', 'part_time', 'contract', 'internship', 'temporary'}
        emp_type = get('employment_type').strip().lower().replace('-', '_').replace(' ', '_')
        if emp_type not in VALID_EMP:
            emp_type = ''

        # Sanitise status
        VALID_STATUS = {'applied','screening','interview','technical','offer','rejected','withdrawn','accepted'}
        status_val = get('status', 'applied').strip().lower()
        if status_val not in VALID_STATUS:
            status_val = 'applied'

        try:
            app = JobApplication.objects.create(
                user=user,
                job_title=job_title[:200],
                company=company[:200],
                location=(get('location').strip())[:200],
                salary_range=(get('salary_range').strip())[:120],
                employment_type=emp_type,
                job_link=(get('job_link').strip())[:1000],
                status=status_val,
                applied_date=applied_date,
                description=(get('description').strip())[:20000],
                notes=(get('notes').strip())[:5000],
            )
        except Exception as e:
            return _json({'error': 'Could not save application: ' + str(e)}, 500)

        # Attach resume if uploaded
        if 'resume' in request.FILES:
            try:
                app.resume = request.FILES['resume']
                app.save()
            except Exception:
                pass  # resume save failure shouldn't block the app being added

        return _json({'ok': True, 'id': app.pk,
                      'company': app.company, 'job_title': app.job_title}, 201)

    return _json({'error': 'Method not allowed'}, 405)


@csrf_exempt
@_api_auth
def api_scrape(request):
    """Proxy to the existing scrape_job logic, token-auth'd for the extension."""
    if request.method == 'OPTIONS':
        return _cors(JsonResponse({}))
    if request.method != 'POST':
        return _json({'error': 'POST required'}, 405)
    # Temporarily set request.user so scrape_job works
    request.user = request.api_user
    resp = scrape_job(request)
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


@login_required
def api_extension_token(request):
    """Called after Google OAuth — generates a token the extension can read."""
    tok = AuthToken.create_for_user(request.user)
    return render(request, 'jobs/extension_token.html', {
        'token': tok.token,
        'user': request.user,
    })
