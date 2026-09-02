from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


favorite_farm = db.Table(
    'favorite_farm',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('farm_id', db.Integer, db.ForeignKey('farm.id'), primary_key=True)
)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(30), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_farmer = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    newsletter_opt_in = db.Column(db.Boolean, default=True, nullable=False)
    consent_updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verification_token = db.Column(db.String(255), nullable=True)
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
    password_reset_token = db.Column(db.String(255), nullable=True)
    password_reset_sent_at = db.Column(db.DateTime, nullable=True)

    farms = db.relationship('Farm', backref='owner', lazy=True, cascade="all, delete-orphan")
    newsletters = db.relationship('Newsletter', backref='author', lazy=True)
    reviews = db.relationship('StoreReview', backref='user', lazy=True, cascade="all, delete-orphan")
    favorite_farms = db.relationship(
        'Farm',
        secondary=favorite_farm,
        lazy='dynamic',
        backref=db.backref('favorited_by', lazy='dynamic')
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Farm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    street_address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    province = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(20), nullable=False)
    contact_email = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(30), nullable=True)
    profile_image = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    subscription_status = db.Column(db.String(30), nullable=False, default='unpaid')
    billing_interval = db.Column(db.String(20), nullable=True)
    stripe_customer_id = db.Column(db.String(120), nullable=True)
    stripe_subscription_id = db.Column(db.String(120), nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)
    grace_period_end = db.Column(db.DateTime, nullable=True)
    subscription_notice_sent_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)

    # Payment Method Selection
    accepts_cash = db.Column(db.Boolean, default=True)
    accepts_etransfer = db.Column(db.Boolean, default=False)
    etransfer_email = db.Column(db.String(120), nullable=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    products = db.relationship('Product', backref='farm', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('StoreReview', backref='farm', lazy=True, cascade="all, delete-orphan")

    @property
    def location(self):
        return f"{self.city}, {self.province}"

    @property
    def full_address(self):
        return f"{self.street_address}, {self.city}, {self.province} {self.postal_code}"

    @property
    def payment_methods_display(self):
        """Returns a human-readable list of accepted payments."""
        methods = []
        if self.accepts_cash:
            methods.append("Cash on Pickup")
        if self.accepts_etransfer:
            email_info = f" ({self.etransfer_email})" if self.etransfer_email else ""
            methods.append(f"Interac e-Transfer{email_info}")
        return ", ".join(methods) if methods else "None specified"


class SubscriptionPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    interval = db.Column(db.String(20), unique=True, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='cad')
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)



class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    unit = db.Column(db.String(30), nullable=False)
    stock_quantity = db.Column(db.Integer, default=0)
    image_file = db.Column(db.String(255), nullable=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farm.id'), nullable=False)

    bulk_tiers = db.relationship('BulkPriceTier', backref='product', lazy=True, cascade="all, delete-orphan",
                                 order_by="BulkPriceTier.quantity")

    @property
    def price_display(self):
        parts = [f"1/${self.price:.2f}"]
        for tier in self.bulk_tiers:
            parts.append(f"{tier.quantity}/${tier.price:.2f}")
        return " | ".join(parts)


class BulkPriceTier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)


class AnalyticsEvent(db.Model):
    __tablename__ = 'analytics_event'

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farm.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    session_id = db.Column(db.String(120), nullable=True)
    event_metadata = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


def log_analytics_event(event_type, farm_id=None, product_id=None, user_id=None, session_id=None, metadata=None):
    if not event_type:
        return

    event = AnalyticsEvent(
        event_type=event_type,
        farm_id=farm_id,
        product_id=product_id,
        user_id=user_id,
        session_id=session_id,
        event_metadata=metadata
    )
    db.session.add(event)
    db.session.commit()


class Newsletter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    audience = db.Column(db.String(30), nullable=False, default='both')
    farm_id = db.Column(db.Integer, db.ForeignKey('farm.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    sent_count = db.Column(db.Integer, default=0, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    farm = db.relationship('Farm', backref='newsletters', lazy=True)


class NewsletterDelivery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletter.id'), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    recipient_type = db.Column(db.String(30), nullable=False)
    delivered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    status = db.Column(db.String(20), default='sent', nullable=False)


class StoreReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farm_id = db.Column(db.Integer, db.ForeignKey('farm.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def stars(self):
        return range(1, self.rating + 1)
