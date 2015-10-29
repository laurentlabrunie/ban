from django.conf.urls import include, url
from django.contrib import admin

from ban.http import urls as http_urls

urlpatterns = [
    url(r'^admin/', include(admin.site.urls)),
    url(r'^api/', include(http_urls, namespace='api')),
    url(r'^auth/', include('oauth2_provider.urls',
                           namespace='oauth2_provider')),
]
