from datetime import datetime, timedelta
import urllib2

from django.core.urlresolvers import reverse
from django.test import TestCase

from djpubsubhubbub.models import Subscription, SubscriptionManager

class MockResponse(object):
    def __init__(self, status, data=None):
        self.status = status
        self.data = data

    def info(self):
        return self

    def read(self):
        if self.data is None:
            return ''
        data, self.data = self.data, None
        return data

class PSHBSubscriptionManagerTest(TestCase):

    def setUp(self):
        self._old_send_request = SubscriptionManager._send_request
        SubscriptionManager._send_request = self._send_request
        self.responses = []
        self.requests = []

    def tearDown(self):
        SubscriptionManager._send_request = self._old_send_request
        del self._old_send_request

    def _send_request(self, url, data):
        self.requests.append((url, data))
        return self.responses.pop()

    def test_sync_verify(self):
        """
        If the hub returns a 204 response, the subscription is verified and
        active.
        """
        self.responses.append(MockResponse(204))
        sub = Subscription.objects.subscribe('topic', 'hub', 'callback', 2000)
        self.assertEquals(sub.hub, 'hub')
        self.assertEquals(sub.topic, 'topic')
        self.assertEquals(sub.verified, True)
        rough_expires = datetime.now() + timedelta(seconds=2000)
        self.assert_(abs(sub.lease_expires - rough_expires).seconds < 5,
                     'lease more than 5 seconds off')
        self.assertEquals(len(self.requests), 1)
        request = self.requests[0]
        self.assertEquals(request[0], 'hub')
        self.assertEquals(request[1]['mode'], 'subscribe')
        self.assertEquals(request[1]['topic'], 'topic')
        self.assertEquals(request[1]['callback'], 'callback')
        self.assertEquals(request[1]['verify'], ('async', 'sync'))
        self.assertEquals(request[1]['verify_token'], sub.verify_token)
        self.assertEquals(request[1]['lease_seconds'], 2000)

    def test_async_verify(self):
        """
        If the hub returns a 202 response, we should not assume the
        subscription is verified.
        """
        self.responses.append(MockResponse(202))
        sub = Subscription.objects.subscribe('topic', 'hub', 'callback', 2000)
        self.assertEquals(sub.hub, 'hub')
        self.assertEquals(sub.topic, 'topic')
        self.assertEquals(sub.verified, False)
        rough_expires = datetime.now() + timedelta(seconds=2000)
        self.assert_(abs(sub.lease_expires - rough_expires).seconds < 5,
                     'lease more than 5 seconds off')
        self.assertEquals(len(self.requests), 1)
        request = self.requests[0]
        self.assertEquals(request[0], 'hub')
        self.assertEquals(request[1]['mode'], 'subscribe')
        self.assertEquals(request[1]['topic'], 'topic')
        self.assertEquals(request[1]['callback'], 'callback')
        self.assertEquals(request[1]['verify'], ('async', 'sync'))
        self.assertEquals(request[1]['verify_token'], sub.verify_token)
        self.assertEquals(request[1]['lease_seconds'], 2000)

    def test_least_seconds_default(self):
        """
        If the number of seconds to lease the subscription is not specified, it
        should default to 2592000 (30 days).
        """
        self.responses.append(MockResponse(202))
        sub = Subscription.objects.subscribe('topic', 'hub', 'callback')
        rough_expires = datetime.now() + timedelta(seconds=2592000)
        self.assert_(abs(sub.lease_expires - rough_expires).seconds < 5,
                     'lease more than 5 seconds off')
        self.assertEquals(len(self.requests), 1)
        request = self.requests[0]
        self.assertEquals(request[1]['lease_seconds'], 2592000)

    def test_error_on_subscribe_raises_URLError(self):
        """
        If a non-202/204 status is returned, raise a URLError.
        """
        self.responses.append(MockResponse(500, 'error data'))
        try:
            Subscription.objects.subscribe('topic', 'hub', 'callback')
        except urllib2.URLError, e:
            self.assertEquals(e.reason,
                              'error subscribing to topic on hub:\nerror data')
        else:
            self.fail('subscription did not raise URLError exception')

class PSHBCallbackViewTestCase(TestCase):

    urls = 'djpubsubhubbub.urls'

    def test_verify(self):
        """
        Getting the callback from the server should verify the subscription.
        """
        sub = Subscription.objects.create(
            topic='topic',
            hub='hub',
            verified=False)
        verify_token = sub.generate_token('subscribe')

        response = self.client.get(reverse('pubsubhubbub_callback',
                                           args=(sub.pk,)),
                                   {'hub.mode': 'subscribe',
                                    'hub.topic': sub.topic,
                                    'hub.challenge': 'challenge',
                                    'hub.lease_seconds': 2000,
                                    'hub.verify_token': verify_token})

        self.assertEquals(response.status_code, 200)
        self.assertEquals(response.content, 'challenge')
        sub = Subscription.objects.get(pk=sub.pk)
        self.assertEquals(sub.verified, True)

    def test_404(self):
        """
        Various things sould return a 404:

        * invalid primary key in the URL
        * token doesn't start with 'subscribe'
        * subscription doesn't exist
        * token doesn't match the subscription
        """
        sub = Subscription.objects.create(
            topic='topic',
            hub='hub',
            verified=False)
        verify_token = sub.generate_token('subscribe')

        response = self.client.get(reverse('pubsubhubbub_callback',
                                           args=(0,)),
                                   {'hub.mode': 'subscribe',
                                    'hub.topic': sub.topic,
                                    'hub.challenge': 'challenge',
                                    'hub.lease_seconds': 2000,
                                    'hub.verify_token': verify_token[1:]})
        self.assertEquals(response.status_code, 404)

        response = self.client.get(reverse('pubsubhubbub_callback',
                                           args=(sub.pk,)),
                                   {'hub.mode': 'subscribe',
                                    'hub.topic': sub.topic,
                                    'hub.challenge': 'challenge',
                                    'hub.lease_seconds': 2000,
                                    'hub.verify_token': verify_token[1:]})
        self.assertEquals(response.status_code, 404)

        response = self.client.get(reverse('pubsubhubbub_callback',
                                           args=(sub.pk,)),
                                   {'hub.mode': 'subscribe',
                                    'hub.topic': sub.topic + 'extra',
                                    'hub.challenge': 'challenge',
                                    'hub.lease_seconds': 2000,
                                    'hub.verify_token': verify_token})
        self.assertEquals(response.status_code, 404)

        response = self.client.get(reverse('pubsubhubbub_callback',
                                           args=(sub.pk,)),
                                   {'hub.mode': 'subscribe',
                                    'hub.topic': sub.topic,
                                    'hub.challenge': 'challenge',
                                    'hub.lease_seconds': 2000,
                                    'hub.verify_token': verify_token[:-5]})
        self.assertEquals(response.status_code, 404)
