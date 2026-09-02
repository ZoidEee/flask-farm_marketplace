import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def _stripe_request(config, method, path, payload=None):
    secret_key = config.get('STRIPE_SECRET_KEY')
    if not secret_key:
        raise RuntimeError('Stripe is not configured. Set STRIPE_SECRET_KEY.')

    data = None
    headers = {'Authorization': f'Bearer {secret_key}'}
    if payload is not None:
        data = urlencode(payload).encode('utf-8')
        headers['Content-Type'] = 'application/x-www-form-urlencoded'

    request = Request(
        f'https://api.stripe.com/v1/{path}',
        data=data,
        headers=headers,
        method=method
    )
    try:
        with urlopen(request, timeout=20) as response:  # nosec B310 - fixed HTTPS Stripe API URL
            return json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError) as exc:
        detail = exc.read().decode('utf-8') if isinstance(exc, HTTPError) else str(exc)
        raise RuntimeError(f'Stripe request failed: {detail}') from exc


def create_checkout_session(config, farm, user, interval, success_url, cancel_url, amount_cents=None):
    plans = {
        'monthly': (str(config.get('STRIPE_MONTHLY_AMOUNT_CENTS', 3000)), 'month'),
        'yearly': (str(config.get('STRIPE_YEARLY_AMOUNT_CENTS', 30000)), 'year')
    }
    if interval not in plans:
        raise ValueError('Choose a monthly or yearly subscription.')

    amount, recurring_interval = plans[interval]
    payload = {
        'mode': 'subscription',
        'success_url': success_url + '?session_id={CHECKOUT_SESSION_ID}',
        'cancel_url': cancel_url,
        'customer_email': user.email,
        'line_items[0][quantity]': '1',
        'line_items[0][price_data][currency]': config.get('STRIPE_CURRENCY', 'cad'),
        'line_items[0][price_data][unit_amount]': str(amount_cents if amount_cents is not None else amount),
        'line_items[0][price_data][recurring][interval]': recurring_interval,
        'line_items[0][price_data][product_data][name]': f'{farm.name} marketplace subscription',
        'metadata[farm_id]': str(farm.id),
        'metadata[interval]': interval,
    }
    return _stripe_request(config, 'POST', 'checkout/sessions', payload)


def get_checkout_session(config, session_id):
    if not session_id or not session_id.replace('_', '').isalnum():
        raise ValueError('Invalid Stripe checkout session.')
    return _stripe_request(config, 'GET', f'checkout/sessions/{session_id}')


def get_subscription(config, subscription_id):
    if not subscription_id:
        raise ValueError('Stripe subscription is missing.')
    return _stripe_request(config, 'GET', f'subscriptions/{subscription_id}')


def unix_to_datetime(value):
    return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
