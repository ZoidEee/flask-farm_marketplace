import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ('1', 'true', 'yes')
    PERMANENT_SESSION_LIFETIME = 1800
    WTF_CSRF_TIME_LIMIT = 3600
    RATE_LIMIT_WINDOW_SECONDS = 60
    RATE_LIMIT_MAX_REQUESTS = 60
    AUTH_RATE_LIMIT_MAX_REQUESTS = 10
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', '')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', str(10 * 1024 * 1024)))
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', '7'))
    ALERT_WEBHOOK_URL = os.environ.get('ALERT_WEBHOOK_URL', '')
    ALERT_EMAIL = os.environ.get('ALERT_EMAIL', '')
    ALERT_COOLDOWN_SECONDS = int(os.environ.get('ALERT_COOLDOWN_SECONDS', '300'))
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    STRIPE_CURRENCY = os.environ.get('STRIPE_CURRENCY', 'cad')
    STRIPE_MONTHLY_AMOUNT_CENTS = int(os.environ.get('STRIPE_MONTHLY_AMOUNT_CENTS', '3000'))
    STRIPE_YEARLY_AMOUNT_CENTS = int(os.environ.get('STRIPE_YEARLY_AMOUNT_CENTS', '30000'))
    SUBSCRIPTION_GRACE_DAYS = 14
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///farm_marketplace.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Outlook is the primary SMTP provider; Gmail remains a secure backup option.
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.office365.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '') or os.environ.get('MAIL_USERNAME', 'your-email@outlook.com')
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ('1', 'true', 'yes')
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ('1', 'true', 'yes')
    MAIL_DEBUG = os.environ.get('MAIL_DEBUG', 'false').lower() in ('1', 'true', 'yes')

    MAIL_BACKUP_SERVER = os.environ.get('MAIL_BACKUP_SERVER', 'smtp.gmail.com')
    MAIL_BACKUP_PORT = int(os.environ.get('MAIL_BACKUP_PORT', '587'))
    MAIL_BACKUP_USERNAME = os.environ.get('MAIL_BACKUP_USERNAME', '')
    MAIL_BACKUP_PASSWORD = os.environ.get('MAIL_BACKUP_PASSWORD', '')
    MAIL_BACKUP_DEFAULT_SENDER = os.environ.get('MAIL_BACKUP_DEFAULT_SENDER', '') or os.environ.get('MAIL_BACKUP_USERNAME', 'your-email@gmail.com')
    MAIL_BACKUP_USE_TLS = os.environ.get('MAIL_BACKUP_USE_TLS', 'true').lower() in ('1', 'true', 'yes')
    MAIL_BACKUP_USE_SSL = os.environ.get('MAIL_BACKUP_USE_SSL', 'false').lower() in ('1', 'true', 'yes')

    # File Upload Settings
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB max upload limit
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}