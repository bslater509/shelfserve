from django.urls import get_script_prefix, set_script_prefix


class IngressPathMiddleware:
    """Teach Django about Home Assistant Ingress subpaths."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        original_prefix = get_script_prefix()
        ingress_path = request.META.get("HTTP_X_INGRESS_PATH", "").rstrip("/")
        if ingress_path:
            request.META["SCRIPT_NAME"] = ingress_path
            set_script_prefix(f"{ingress_path}/")

        try:
            return self.get_response(request)
        finally:
            set_script_prefix(original_prefix)
