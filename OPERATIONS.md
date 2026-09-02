# Operations Runbook

## Backups and restore tests

For SQLite, schedule the following command at least daily:

```text
python scripts/backup_database.py
```

Set `BACKUP_DIR` to encrypted durable storage. Validate the newest backup after each backup job:

```text
python scripts/restore_test.py backups/<backup-file>.sqlite
```

For PostgreSQL, use managed automated backups and test a `pg_dump`/`pg_restore` recovery at least monthly.

## Monitoring and alerting

- Monitor `GET /healthz` every 1-5 minutes and alert on non-200 responses.
- Set `SENTRY_DSN` to enable integration with the selected error-tracking service.
- Forward application and request logs to centralized, access-controlled storage.
- Alert on repeated 5xx responses, database failures, failed Stripe webhooks, and failed email delivery.
- Set `LOG_FILE` for bounded local retention (`LOG_MAX_BYTES` and `LOG_BACKUP_COUNT`) when file logs are required.
- Set `ALERT_WEBHOOK_URL` for Slack/PagerDuty-compatible JSON webhook alerts, or `ALERT_EMAIL` for SMTP error notifications.
- Configure retention and access controls in the hosting/logging provider; do not retain sensitive request bodies or credentials.

## Incident response

1. Confirm impact using logs and `/healthz`.
2. Preserve relevant logs and identify the affected release.
3. Disable the affected feature or deployment if necessary.
4. Restore service, verify authentication, billing, email, and database health.
5. Record the timeline, root cause, customer impact, and corrective action.

## Deployment procedure

1. Install dependencies with `pip install -r requirements.txt`.
2. Review the change and run `python test_suite.py`.
3. Run `python -m pip_audit -r requirements.txt` and `python -m bandit -r farm_marketplace`.
4. Apply/verify database schema changes on a backup or staging copy.
5. Deploy with production secrets, HTTPS, and `SESSION_COOKIE_SECURE=true`.
6. Run smoke tests for `/healthz`, login, farm visibility, Stripe Checkout, and webhooks.
7. Confirm centralized logs, alert delivery, backup completion, and restore validation.
8. Monitor logs and errors after release; keep a rollback release available.
