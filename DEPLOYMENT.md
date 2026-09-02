# Deployment guide

This app reads its runtime configuration from environment variables. Copy `.env.example` to `.env` and fill in the values before deploying. Install dependencies with `pip install -r requirements.txt`.

## Required secrets and config

- `SECRET_KEY`: production secret used by Flask sessions and security features.
- `DATABASE_URL`: database connection string. Use a managed database in production, not SQLite unless this is a small/internal deployment.
- `MAIL_*`: SMTP credentials for the primary mail provider and fallback provider.
- `MAIL_DEFAULT_SENDER` and `MAIL_BACKUP_DEFAULT_SENDER`: from-address used for verification and admin emails.
- `STRIPE_SECRET_KEY`: Stripe API secret key.
- `STRIPE_WEBHOOK_SECRET`: signing secret for the `/stripe/webhook` endpoint.
- `STRIPE_CURRENCY`: three-letter billing currency, default `cad`.
- `STRIPE_MONTHLY_AMOUNT_CENTS` and `STRIPE_YEARLY_AMOUNT_CENTS`: configurable subscription prices in cents.
- `SENTRY_DSN`: optional Sentry project DSN for exception tracking.
- `ALERT_WEBHOOK_URL` or `ALERT_EMAIL`: optional error-alert destination.
- `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`: optional bounded local log retention.

## Recommended deployment flow

1. Create a production environment file:
   ```bash
   cp .env.example .env
   ```
2. Replace example values with real credentials.
3. Load the environment variables before starting the app.
4. Run the app with a production WSGI server such as Gunicorn or uWSGI.
5. Confirm that email delivery works using a real verification email flow before exposing the site publicly.
6. In Stripe Dashboard, create a webhook endpoint at `https://your-domain.example/stripe/webhook` and subscribe it to:
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
7. Test both Checkout plans with Stripe test mode before switching to live keys.

## Example start command

```bash
set -a
source .env
set +a
gunicorn farm_marketplace.app:app
```

## Security notes

- Never commit `.env` files to version control.
- Use app-specific passwords for Outlook or Gmail when possible.
- Restrict database access and keep secrets in your hosting provider's secret manager or environment store.
- For production, use a long random `SECRET_KEY` and a non-SQLite database if the application will handle real traffic.
- Set `SESSION_COOKIE_SECURE=true` only when the app is served over HTTPS.
- Stripe is the source of truth for subscription state; do not mark farms live manually in the database.
- Administrators can change prices from the dashboard; changes apply to new checkouts, while existing Stripe subscriptions retain their current price.
- Failed payments set a 14-day grace period and trigger a payment-needed email. After the grace period, the farm is hidden from public marketplace and product routes.
