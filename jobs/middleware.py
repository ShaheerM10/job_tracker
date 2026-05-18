from zoneinfo import ZoneInfo
import django.utils.timezone as timezone

class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz = request.session.get('timezone', 'UTC')
        try:
            timezone.activate(ZoneInfo(tz))
        except Exception:
            timezone.deactivate()
        return self.get_response(request)