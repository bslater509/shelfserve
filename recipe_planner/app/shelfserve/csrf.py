import logging

from django.conf import settings
from django.views.csrf import csrf_failure as default_csrf_failure


logger = logging.getLogger("shelfserve.csrf")


def csrf_failure(request, reason=""):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("CSRF failure diagnostics: %s", _csrf_diagnostics(request, reason))

    return default_csrf_failure(request, reason=reason)


def _csrf_diagnostics(request, reason):
    meta = request.META
    post_field_names, submitted_token_present = _safe_post_field_names(request)

    return {
        "reason": reason,
        "method": request.method,
        "path": request.get_full_path(),
        "content_type": meta.get("CONTENT_TYPE", ""),
        "content_length": meta.get("CONTENT_LENGTH", ""),
        "host_header": meta.get("HTTP_HOST", ""),
        "origin": meta.get("HTTP_ORIGIN", ""),
        "referer": meta.get("HTTP_REFERER", ""),
        "x_ingress_path": meta.get("HTTP_X_INGRESS_PATH", ""),
        "x_forwarded_host": meta.get("HTTP_X_FORWARDED_HOST", ""),
        "x_forwarded_proto": meta.get("HTTP_X_FORWARDED_PROTO", ""),
        "script_name": meta.get("SCRIPT_NAME", ""),
        "wsgi_url_scheme": meta.get("wsgi.url_scheme", ""),
        "django_host": _safe_get_host(request),
        "is_secure": request.is_secure(),
        "csrf_cookie_present": settings.CSRF_COOKIE_NAME in request.COOKIES,
        "submitted_csrf_field_present": submitted_token_present,
        "post_field_names": post_field_names,
    }


def _safe_get_host(request):
    try:
        return request.get_host()
    except Exception as exc:
        return f"<error: {exc.__class__.__name__}>"


def _safe_post_field_names(request):
    try:
        field_names = sorted(request.POST.keys())
    except Exception as exc:
        return [f"<error: {exc.__class__.__name__}>"], False

    return field_names, "csrfmiddlewaretoken" in field_names
