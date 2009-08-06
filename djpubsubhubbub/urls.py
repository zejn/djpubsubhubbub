from django.conf.urls.defaults import *

urlpatterns = patterns('djpubsubhubbub.views',
                       (r'^(\d+)/$', 'callback', {}, 'pubsubhubbub_callback'))
