from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404

from djpubsubhubbub.models import Subscription
from djpubsubhubbub.signals import verified

def callback(request, pk):
    if request.method == 'GET':
        mode = request.GET['hub.mode']
        topic = request.GET['hub.topic']
        challenge = request.GET['hub.challenge']
        lease_seconds = request.GET.get('hub.lease_seconds')
        verify_token = request.GET.get('hub.verify_token', '')

        if mode == 'subscribe':
            if not verify_token.startswith('subscribe'):
                raise Http404
            subscription = get_object_or_404(Subscription,
                                             pk=pk,
                                             topic=topic,
                                             verify_token=verify_token)
            subscription.verified = True
            subscription.set_expiration(int(lease_seconds))
            verified.send(sender=subscription)

        return HttpResponse(challenge, content_type='text/plain')

    return Http404
