class IngressPathMiddleware:
    """Teach Django about Home Assistant Ingress subpaths."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ingress_path = request.META.get("HTTP_X_INGRESS_PATH", "").rstrip("/")
        if ingress_path:
            request.META["SCRIPT_NAME"] = ingress_path
        return self.get_response(request)

