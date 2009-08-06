from django.dispatch import Signal

pre_subscribe = Signal(providing_args=['created'])
verified = Signal()
updated = Signal(providing_args=['update'])
