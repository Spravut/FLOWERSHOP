from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

def redirect_to_home(request):
    return redirect('home')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('main.urls')),
    path('flowershop/', redirect_to_home),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Error handlers
handler404 = 'main.views.page_not_found'
handler500 = 'main.views.server_error'
handler403 = 'main.views.permission_denied'
handler400 = 'main.views.bad_request'