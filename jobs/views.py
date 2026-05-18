from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db.models import Count
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
    apps = JobApplication.objects.filter(user=request.user)
    total = apps.count()
    status_counts = dict(apps.values_list('status').annotate(count=Count('status')))

    six_months_ago = timezone.now() - timedelta(days=180)
    monthly = (
        apps.filter(applied_date__gte=six_months_ago)
        .annotate(month=TruncMonth('applied_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    monthly_labels = [m['month'].strftime('%b %Y') for m in monthly]
    monthly_data = [m['count'] for m in monthly]

    all_statuses = [s[0] for s in JobApplication.STATUS_CHOICES]
    status_labels = [s[1] for s in JobApplication.STATUS_CHOICES]
    status_data = [status_counts.get(s, 0) for s in all_statuses]

    recent = apps[:5]
    response_rate = 0
    if total > 0:
        responded = sum(status_counts.get(s, 0) for s in ['screening', 'interview', 'technical', 'offer', 'accepted'])
        response_rate = round((responded / total) * 100)

    context = {
        'apps': apps,
        'total': total,
        'status_counts': status_counts,
        'recent': recent,
        'response_rate': response_rate,
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_data': json.dumps(monthly_data),
        'status_labels': json.dumps(status_labels),
        'status_data': json.dumps(status_data),
        'active_count': status_counts.get('interview', 0) + status_counts.get('technical', 0) + status_counts.get('screening', 0),
        'offer_count': status_counts.get('offer', 0) + status_counts.get('accepted', 0),
    }
    return render(request, 'jobs/dashboard.html', context)


@login_required
def application_list(request):
    apps = JobApplication.objects.filter(user=request.user)
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    if status_filter:
        apps = apps.filter(status=status_filter)
    if search:
        apps = apps.filter(job_title__icontains=search) | apps.filter(company__icontains=search)
    context = {
        'apps': apps,
        'status_choices': JobApplication.STATUS_CHOICES,
        'current_status': status_filter,
        'search': search,
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


@login_required
def scrape_job(request):
    """Scrape job details from a URL using trafilatura + BeautifulSoup"""
    if request.method != 'POST':
        from django.http import JsonResponse
        return JsonResponse({'error': 'POST required'}, status=405)

    import json as json_lib
    from django.http import JsonResponse
    import requests as req
    from bs4 import BeautifulSoup
    import re
    import trafilatura

    try:
        body = json_lib.loads(request.body)
        url = body.get('url', '').strip()
    except Exception:
        return JsonResponse({'error': 'Invalid request'}, status=400)

    if not url:
        return JsonResponse({'error': 'No URL provided'}, status=400)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        resp = req.get(url, headers=headers, timeout=12)
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        result = {'title': '', 'company': '', 'description': ''}

        # 1. Try JSON-LD structured data (most reliable - used by LinkedIn, Greenhouse, Lever, Workday)
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json_lib.loads(script.string or '{}')
                if isinstance(data, list): data = data[0]
                if isinstance(data, dict) and 'JobPosting' in str(data.get('@type', '')):
                    result['title'] = result['title'] or str(data.get('title', ''))[:200]
                    org = data.get('hiringOrganization', {})
                    result['company'] = result['company'] or str(org.get('name', '') if isinstance(org, dict) else org)[:100]
                    desc_html = data.get('description', '')
                    if desc_html:
                        desc_text = BeautifulSoup(desc_html, 'html.parser').get_text(separator='\n')
                        result['description'] = re.sub(r'\n{3,}', '\n\n', desc_text).strip()[:5000]
            except Exception:
                pass

        # 2. Try Open Graph / meta tags for title & company
        if not result['title']:
            for attr in [('property','og:title'), ('name','title')]:
                tag = soup.find('meta', {attr[0]: attr[1]})
                if tag and tag.get('content'):
                    t = tag['content']
                    # Strip site name suffix
                    for sep in [' | ', ' - ', ' – ', ' — ']:
                        if sep in t:
                            t = t.split(sep)[0]
                            break
                    result['title'] = t.strip()[:200]
                    break

        # 3. H1 fallback for title
        if not result['title']:
            h1 = soup.find('h1')
            if h1:
                result['title'] = h1.get_text(strip=True)[:200]

        # 4. Use trafilatura for clean description text
        if not result['description']:
            extracted = trafilatura.extract(html, include_comments=False, include_tables=False, no_fallback=False)
            if extracted and len(extracted) > 100:
                result['description'] = extracted[:5000]

        # 5. Company from meta or page title
        if not result['company']:
            page_title = soup.find('title')
            if page_title:
                t = page_title.get_text()
                # Often "Job Title at Company | Site" or "Job Title - Company"
                for sep in [' at ', ' @ ']:
                    if sep in t:
                        parts = t.split(sep)
                        if len(parts) > 1:
                            co = parts[1].split(' | ')[0].split(' - ')[0].strip()
                            if co and len(co) < 80:
                                result['company'] = co
                                break

        # Clean up
        for k in result:
            if isinstance(result[k], str):
                result[k] = result[k].strip()

        return JsonResponse(result)

    except req.exceptions.Timeout:
        return JsonResponse({'error': 'Page took too long to load. Try pasting details manually.'}, status=408)
    except Exception as e:
        return JsonResponse({'error': 'Could not load this page. Try pasting details manually.'}, status=500)


def scrape_job(request):
    """Scrape job details from a URL and return JSON"""
    if request.method != 'POST':
        from django.http import JsonResponse
        return JsonResponse({'error': 'POST required'}, status=405)

    import json as json_lib
    from django.http import JsonResponse
    import requests as req
    from bs4 import BeautifulSoup
    import re

    try:
        body = json_lib.loads(request.body)
        url = body.get('url', '').strip()
    except Exception:
        return JsonResponse({'error': 'Invalid request'}, status=400)

    if not url:
        return JsonResponse({'error': 'No URL provided'}, status=400)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        resp = req.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Remove scripts and styles
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        result = {'title': '', 'company': '', 'description': ''}

        # --- TITLE ---
        # Try common job title selectors
        title_selectors = [
            'h1[class*="job"]', 'h1[class*="title"]', 'h1[class*="position"]',
            '[data-testid*="job-title"]', '[data-testid*="title"]',
            '.job-title', '.jobTitle', '.position-title',
            'h1'
        ]
        for sel in title_selectors:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                result['title'] = el.get_text(strip=True)[:200]
                break

        # Try meta og:title as fallback
        if not result['title']:
            og = soup.find('meta', property='og:title')
            if og:
                result['title'] = og.get('content', '')[:200]

        # --- COMPANY ---
        company_selectors = [
            '[data-testid*="company"]', '[class*="company-name"]',
            '[class*="employer"]', '[class*="companyName"]',
            'a[href*="company"]', '[itemprop="hiringOrganization"]',
            '.company', '.employer-name',
        ]
        for sel in company_selectors:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                result['company'] = el.get_text(strip=True)[:100]
                break

        # Try JSON-LD structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json_lib.loads(script.string or '{}')
                if isinstance(data, list):
                    data = data[0]
                if data.get('@type') in ('JobPosting', 'jobPosting'):
                    if not result['title'] and data.get('title'):
                        result['title'] = data['title'][:200]
                    if not result['company'] and data.get('hiringOrganization'):
                        org = data['hiringOrganization']
                        result['company'] = (org.get('name') if isinstance(org, dict) else str(org))[:100]
                    if data.get('description'):
                        desc = BeautifulSoup(data['description'], 'html.parser').get_text(separator='\n')
                        result['description'] = re.sub(r'\n{3,}', '\n\n', desc).strip()[:5000]
            except Exception:
                pass

        # --- DESCRIPTION ---
        if not result['description']:
            desc_selectors = [
                '[data-testid*="description"]', '[class*="job-description"]',
                '[class*="jobDescription"]', '[class*="description"]',
                '#job-description', '.job-details', '[class*="job-detail"]',
                'article', 'main',
            ]
            for sel in desc_selectors:
                el = soup.select_one(sel)
                if el and len(el.get_text(strip=True)) > 100:
                    text = el.get_text(separator='\n', strip=True)
                    result['description'] = re.sub(r'\n{3,}', '\n\n', text).strip()[:5000]
                    break

        # Clean up title - remove common suffixes
        if result['title']:
            for suffix in [' - Jobs', ' | LinkedIn', ' - Indeed', ' - Glassdoor', ' | Glassdoor']:
                result['title'] = result['title'].replace(suffix, '')
            result['title'] = result['title'].strip()

        return JsonResponse(result)

    except req.exceptions.Timeout:
        return JsonResponse({'error': 'Request timed out. Try pasting the details manually.'}, status=408)
    except Exception as e:
        return JsonResponse({'error': f'Could not scrape this page. Try pasting the details manually.'}, status=500)



def set_timezone(request):
    from django.http import JsonResponse
    import json
    if request.method == 'POST':
        data = json.loads(request.body)
        tz = data.get('timezone', 'UTC')
        request.session['timezone'] = tz
    return JsonResponse({'status': 'ok'})    
