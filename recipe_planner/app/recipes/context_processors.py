from .models import AppSetting


def accent(request):
    setting = AppSetting.current()
    return {"accent_color": setting.accent_color}
