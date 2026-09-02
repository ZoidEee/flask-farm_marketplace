# Release QA checklist

Run this checklist against a staging deployment before production:

- Test Chrome, Firefox, Safari, and Edge at desktop, tablet, and 320px mobile widths.
- Confirm keyboard navigation, visible focus states, form labels, alt text, heading order, and sufficient color contrast.
- Test registration, email verification, login, logout, password reset, and change password.
- Test farm creation, image upload limits, product CRUD, favorites, reviews, and farmer newsletters.
- Test unpaid, active, past-due, grace-period, expired, renewed, and cancelled farm subscriptions.
- Confirm `/healthz`, centralized logs, Sentry events, alert routing, backups, and restore validation.
- Verify privacy, terms, newsletter consent, unsubscribe/preferences, and data-retention workflows.
