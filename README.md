# Farm Marketplace

Farm Marketplace is a Flask-based local farm directory and storefront application for connecting buyers with nearby farms. It supports farm profiles, product listings, favorites, analytics, secure account flows, and direct communication tools for farm-to-customer engagement.

## Current status

This project is now a more complete MVP focused on stability, user trust, and marketplace utility rather than a pure prototype. It includes core marketplace browsing, farm registration, favorites, user newsletters, secure auth flows, admin analytics, and deployable email configuration.

## What is built

### Marketplace and storefront features

- Farm registration and farm profile management
- Product creation, editing, bulk pricing tiers, and inventory tracking
- Search by farm name, city, product name, and category filters
- Favorite farms so shoppers can save local businesses for later
- Marketplace favorites-only filtering
- Farm detail and product detail pages with engagement tracking
- Paid farm subscriptions through Stripe with environment-configurable monthly and yearly prices
- Subscription-gated storefront visibility; unpaid farms are hidden from shoppers
- A 14-day grace period for missed monthly payments
- Stripe webhook handling for successful renewals, failed payments, cancellations, and subscription status updates

### User account and security features

- Registration, login, logout, and profile management
- Username input is limited to 80 characters server-side and in the registration form
- Email verification flow
- Forgot-password and reset-password support
- Change-password support from the profile page
- Email preferences for newsletter opt-in/opt-out
- Secure session configuration and security headers for safer deployment

### Farm and audience communication

- Shop-specific newsletters for users who have favorited a farm
- Opt-in newsletter preferences for buyers
- Admin newsletter tools for broader audience messaging
- Privacy page and communication consent information

### Analytics and admin tools

- Farm profile view tracking
- Product click tracking
- Favorite counts and conversion-style reporting
- Admin dashboard with engagement metrics and top-farm summaries
- Admin-configurable subscription pricing for new Stripe Checkout sessions
- Farmer dashboard with per-farm profile, product, and favorite analytics
- Admin moderation workflow for users and farm records

### Email and deployment readiness

- SMTP configuration for Outlook-first setup with Gmail backup
- Environment-driven email settings
- Safe local development fallback for email logging when credentials are absent
- Example environment file and deployment notes
- Automated backup/restore validation helpers, health monitoring, structured request logging, and optional Sentry error tracking
- Configurable rotating log retention and webhook/email alert routing for application errors
- CSRF protection, rate limiting, terms/privacy pages, and a release QA checklist

## Project structure

- `farm_marketplace/app.py` initializes the Flask app and database checks
- `farm_marketplace/config.py` holds environment-based app and email settings
- `farm_marketplace/models.py` defines the core models, favorites, newsletter, and analytics tables
- `farm_marketplace/views/` contains auth, public, farm, and admin routes
- `farm_marketplace/templates/` contains the app UI
- `farm_marketplace/static/uploads/` stores uploaded farm and product images

## Setup

1. Open the project directory.
2. Create and activate a virtual environment.
3. Install required packages.
4. Copy the example environment file and set real secrets.
5. Run the app.

Example:

```bash
cd Farmers-Marketplace
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
python farm_marketplace/app.py
```

## Environment and deployment

The app uses environment variables for secrets, database setup, and email delivery. See `DEPLOYMENT.md` and `.env.example` for production-ready baseline settings.

Required settings include:

- `SECRET_KEY`: application secret for Flask sessions
- `DATABASE_URL`: production database connection string
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`: primary SMTP settings
- `MAIL_BACKUP_SERVER`, `MAIL_BACKUP_PORT`, `MAIL_BACKUP_USERNAME`, `MAIL_BACKUP_PASSWORD`: fallback email provider
- `MAIL_DEFAULT_SENDER` and `MAIL_BACKUP_DEFAULT_SENDER`: sender address used for system email
- `SESSION_COOKIE_SECURE`: enable secure cookies in production deployments
- `STRIPE_SECRET_KEY`: Stripe secret API key; use a test key locally and a live key only in production
- `STRIPE_WEBHOOK_SECRET`: signing secret for Stripe webhook processing
- `STRIPE_CURRENCY`: billing currency, default `cad`
- `STRIPE_MONTHLY_AMOUNT_CENTS`: monthly subscription price in cents, default `3000`
- `STRIPE_YEARLY_AMOUNT_CENTS`: yearly subscription price in cents, default `30000`

Never commit a real `.env` file to version control. In production, use environment injection or a secure secret manager.

## Security and compliance notes

The app includes a basic hardening layer appropriate for an MVP:

- secure session cookies
- HTTP security headers
- no hardcoded secrets in the default config
- email opt-in controls for newsletters
- privacy page explaining how user data is handled
- password reset and account recovery flows

The technical controls are ready for staging. Before full public launch, configure the external services, verify retention and alert policies, and obtain legal review of the privacy and terms language.

## Development notes

- This is built as a lightweight marketplace MVP and is designed to be extended.
- The core data model supports future e-commerce workflows such as carts, checkout, shipping, and order tracking.
- Admin and farmer permissions remain explicit and reviewable.
- The app is intentionally modular so future features can be added without rewriting the foundation.
- Stripe Checkout must be configured before farmers can use the Go Live button. Payment confirmation is verified server-side before a farm is marked live. Change subscription prices through the deployment environment variables; existing Stripe subscriptions keep their current Stripe price until changed through Stripe billing.

## Current roadmap

### Near-term

- Configure live hosting, HTTPS, PostgreSQL, Stripe, SMTP, Sentry, centralized logs, and alert routing
- Schedule encrypted backups and complete a documented restore drill
- Complete staging browser, mobile, accessibility, subscription, and webhook QA
- Obtain legal review and approval for privacy, terms, consent, and retention policies
- Add formal admin audit trails and moderation workflows
- Expand analytics export/reporting features

### Medium-term

- Checkout, cart, and payment support
- Order lifecycle tracking and customer order history
- Inventory and fulfillment tooling
- Review moderation and complaint handling

### Long-term

- Marketplace expansion into larger regional coverage
- Subscription and CSA-style ordering patterns
- Advanced recommendation and discovery logic
- Mobile-first UX and loyalty features

## Summary

Farm Marketplace is now a functional local food marketplace and communication platform that links shoppers, farmers, and administrators around discovery, trust, and engagement. It includes favorites, secure account recovery, farm newsletters, and admin analytics, while still leaving room for commerce and production-hardening work before a full public launch.
