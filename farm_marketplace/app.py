import os
import logging
import secrets
import time
import json
import smtplib
from email.message import EmailMessage
from collections import defaultdict, deque
from logging.handlers import RotatingFileHandler
from urllib.request import Request, urlopen
from flask import Flask
from flask import abort, jsonify, request, session
from werkzeug.exceptions import HTTPException
from sqlalchemy import text
from config import Config
from models import db, User, SubscriptionPlan
from views.main import main_bp
from views.auth import auth_bp
from views.farms import farms_bp
from views.admin import admin_bp


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'path': getattr(record, 'path', None)
        })


class AlertHandler(logging.Handler):
    def __init__(self, app):
        super().__init__(level=logging.ERROR)
        self.app = app
        self.last_alert = 0.0

    def emit(self, record):
        now = time.monotonic()
        if now - self.last_alert < self.app.config['ALERT_COOLDOWN_SECONDS']:
            return
        self.last_alert = now
        message = self.format(record)
        webhook_url = self.app.config.get('ALERT_WEBHOOK_URL')
        if webhook_url:
            try:
                request = Request(
                    webhook_url,
                    data=json.dumps({'text': f'Farm Marketplace error: {message}'}).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urlopen(request, timeout=5):  # nosec B310 - operator-configured HTTPS alert endpoint
                    pass
            except Exception:
                self.app.logger.exception('Error alert webhook delivery failed.')
        alert_email = self.app.config.get('ALERT_EMAIL')
        if alert_email:
            try:
                sender = self.app.config.get('MAIL_DEFAULT_SENDER') or self.app.config.get('MAIL_USERNAME')
                msg = EmailMessage()
                msg['Subject'] = 'Farm Marketplace application error'
                msg['From'] = sender
                msg['To'] = alert_email
                msg.set_content(message)
                with smtplib.SMTP(self.app.config['MAIL_SERVER'], self.app.config['MAIL_PORT'], timeout=10) as server:
                    if self.app.config.get('MAIL_USE_TLS'):
                        server.starttls()
                    server.login(self.app.config['MAIL_USERNAME'], self.app.config['MAIL_PASSWORD'])
                    server.send_message(msg)
            except Exception:
                self.app.logger.exception('Error alert email delivery failed.')


def ensure_database_schema():
    db.create_all()

    inspector = db.inspect(db.engine)
    user_columns = {col['name'] for col in inspector.get_columns('user')}
    for column_name, column_sql in {
        'phone_number': 'VARCHAR(30)',
        'newsletter_opt_in': 'BOOLEAN NOT NULL DEFAULT 1',
        'email_verified': 'BOOLEAN NOT NULL DEFAULT 0',
        'email_verification_token': 'VARCHAR(255)',
        'email_verification_sent_at': 'DATETIME',
        'password_reset_token': 'VARCHAR(255)',  # nosec B105 - SQL type, not a credential
        'password_reset_sent_at': 'DATETIME'  # nosec B105 - SQL type, not a credential
    }.items():
        if column_name not in user_columns:
            db.session.execute(text(f'ALTER TABLE user ADD COLUMN {column_name} {column_sql}'))

    if 'consent_updated_at' not in user_columns:
        db.session.execute(text('ALTER TABLE user ADD COLUMN consent_updated_at DATETIME'))
        db.session.execute(text('UPDATE user SET consent_updated_at = CURRENT_TIMESTAMP WHERE consent_updated_at IS NULL'))

    farm_columns = {col['name'] for col in inspector.get_columns('farm')}
    for column_name, column_sql in {
        'subscription_status': 'VARCHAR(30) NOT NULL DEFAULT "unpaid"',
        'billing_interval': 'VARCHAR(20)',
        'stripe_customer_id': 'VARCHAR(120)',
        'stripe_subscription_id': 'VARCHAR(120)',
        'current_period_end': 'DATETIME',
        'grace_period_end': 'DATETIME',
        'subscription_notice_sent_at': 'DATETIME',
        'paid_at': 'DATETIME'
    }.items():
        if column_name not in farm_columns:
            db.session.execute(text(f'ALTER TABLE farm ADD COLUMN {column_name} {column_sql}'))

    table_names = set(inspector.get_table_names())
    if 'newsletter' not in table_names:
        db.create_all()
    else:
        newsletter_columns = {col['name'] for col in inspector.get_columns('newsletter')}
        for column_name, column_sql in {
            'audience': 'VARCHAR(30) NOT NULL DEFAULT "both"',
            'farm_id': 'INTEGER',
            'sent_count': 'INTEGER NOT NULL DEFAULT 0',
            'created_by_id': 'INTEGER'
        }.items():
            if column_name not in newsletter_columns:
                db.session.execute(text(f'ALTER TABLE newsletter ADD COLUMN {column_name} {column_sql}'))

    if 'newsletter_delivery' not in table_names:
        db.create_all()
    if 'store_review' not in table_names:
        db.create_all()

    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.logger.setLevel(getattr(logging, app.config['LOG_LEVEL'].upper(), logging.INFO))
    formatter = JsonFormatter()
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)
    if app.config.get('LOG_FILE'):
        file_handler = RotatingFileHandler(
            app.config['LOG_FILE'],
            maxBytes=app.config['LOG_MAX_BYTES'],
            backupCount=app.config['LOG_BACKUP_COUNT'],
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)
    app.logger.addHandler(AlertHandler(app))
    if app.config.get('SENTRY_DSN'):
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            sentry_sdk.init(dsn=app.config['SENTRY_DSN'], integrations=[FlaskIntegration()], traces_sample_rate=0.0)
        except ImportError:
            app.logger.error('SENTRY_DSN is set but sentry-sdk is not installed.')
    request_log = logging.getLogger('farm_marketplace.requests')
    request_log.setLevel(app.logger.level)
    if not request_log.handlers:
        request_log.addHandler(logging.StreamHandler())
    app.extensions['rate_limits'] = defaultdict(deque)

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(farms_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def sync_user_session():
        user_id = session.get('user_id')
        if user_id:
            user = db.session.get(User, user_id)
            if user:
                session['is_admin'] = user.is_admin
                session['is_farmer'] = user.is_farmer
                session['username'] = user.username
            else:
                session.clear()

    @app.before_request
    def protect_requests():
        key = f"{request.remote_addr}:{request.endpoint or request.path}"
        now = time.monotonic()
        requests = app.extensions['rate_limits'][key]
        while requests and now - requests[0] > app.config['RATE_LIMIT_WINDOW_SECONDS']:
            requests.popleft()
        limit = app.config['AUTH_RATE_LIMIT_MAX_REQUESTS'] if request.path in {'/login', '/register', '/forgot-password'} else app.config['RATE_LIMIT_MAX_REQUESTS']
        if len(requests) >= limit:
            return jsonify(error='Too many requests. Please try again later.'), 429
        requests.append(now)

        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.endpoint != 'farms.stripe_webhook' and not app.testing:
            token = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
            if not session.get('_csrf_token'):
                session['_csrf_token'] = secrets.token_urlsafe(32)
            if not token or not secrets.compare_digest(token, session['_csrf_token']):
                abort(400, description='Invalid or missing CSRF token.')

    @app.context_processor
    def expose_security_helpers():
        if not session.get('_csrf_token'):
            session['_csrf_token'] = secrets.token_urlsafe(32)
        return {'csrf_token': session['_csrf_token']}

    @app.route('/healthz')
    def healthz():
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify(status='ok', database='ok')
        except Exception:
            app.logger.exception('Health check database failure')
            return jsonify(status='error', database='unavailable'), 503

    @app.after_request
    def apply_security_headers(response):
        request_log.info('%s %s %s', request.method, request.path, response.status_code)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
        return response

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception('Unhandled application error')
        return 'Internal server error.', 500

    @app.teardown_appcontext
    def shutdown_db_session(exception=None):
        db.session.remove()
        try:
            db.engine.dispose()
        except Exception as exc:
            app.logger.warning('Database engine cleanup failed: %s', exc)

    with app.app_context():
        ensure_database_schema()

        for interval, amount in (
            ('monthly', app.config['STRIPE_MONTHLY_AMOUNT_CENTS']),
            ('yearly', app.config['STRIPE_YEARLY_AMOUNT_CENTS'])
        ):
            plan = SubscriptionPlan.query.filter_by(interval=interval).first()
            if not plan:
                db.session.add(SubscriptionPlan(
                    interval=interval,
                    amount_cents=amount,
                    currency=app.config['STRIPE_CURRENCY']
                ))
        db.session.commit()

        # Seed default SysAdmin account if missing
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@farmdirect.local',
                is_admin=True,
                is_farmer=False,
                newsletter_opt_in=True
            )
            admin.set_password('Admin123!')
            db.session.add(admin)
            db.session.commit()
        else:
            # Ensure existing admin has is_admin=True and is_farmer=False
            changed = False
            if not admin.is_admin:
                admin.is_admin = True
                changed = True
            if admin.is_farmer:
                admin.is_farmer = False
                changed = True
            if admin.newsletter_opt_in is None:
                admin.newsletter_opt_in = True
                changed = True
            if changed:
                db.session.commit()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes'))
