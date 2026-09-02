import os
import uuid
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from models import db, User, Farm, Product, BulkPriceTier, StoreReview, Newsletter, NewsletterDelivery, AnalyticsEvent, SubscriptionPlan, log_analytics_event, favorite_farm
from views.auth import send_email
from payments import create_checkout_session, get_checkout_session, get_subscription, unix_to_datetime

farms_bp = Blueprint('farms', __name__)

STANDARD_UNITS = [
    'lbs', 'oz', 'kg', 'g', 'dozen', 'half-dozen',
    'each / single', 'bunch', 'pint', 'quart', 'head', 'bag', 'flat', 'jar'
]

PRODUCT_CATEGORIES = [
    'Vegetables',
    'Fruits',
    'Dairy',
    'Meat',
    'Poultry',
    'Honey & Preserves',
    'Bakery',
    'Other'
]


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def save_uploaded_file(file_obj):
    if file_obj and file_obj.filename != '' and allowed_file(file_obj.filename):
        filename = secure_filename(file_obj.filename)
        unique_filename = f"{uuid.uuid4().hex[:10]}_{filename}"

        upload_path = current_app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_path):
            os.makedirs(upload_path, exist_ok=True)

        file_obj.save(os.path.join(upload_path, unique_filename))
        return unique_filename
    return None


def delete_file_if_exists(filename):
    if not filename:
        return
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if upload_folder:
        file_path = os.path.join(upload_folder, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


def process_bulk_tiers(product, quantities, prices):
    """Utility function to replace or create multi-buy bulk price tiers."""
    BulkPriceTier.query.filter_by(product_id=product.id).delete()

    for qty_str, price_str in zip(quantities, prices):
        qty_str = str(qty_str).strip()
        price_str = str(price_str).strip()
        if qty_str and price_str:
            try:
                q_val = int(qty_str)
                p_val = Decimal(price_str)
                if q_val > 1 and p_val > 0:
                    tier = BulkPriceTier(product_id=product.id, quantity=q_val, price=p_val)
                    db.session.add(tier)
            except (ValueError, InvalidOperation):
                continue


# ==========================================
# FARM ROUTES
# ==========================================

def get_farm_metrics(farm):
    profile_views = AnalyticsEvent.query.filter_by(farm_id=farm.id, event_type='farm_profile_view').count()
    product_clicks = AnalyticsEvent.query.filter_by(farm_id=farm.id, event_type='product_click').count()
    favorite_count = db.session.execute(
        db.select(db.func.count()).select_from(favorite_farm).where(favorite_farm.c.farm_id == farm.id)
    ).scalar() or 0
    review_count = len(farm.reviews)
    conversion_rate = round((favorite_count / profile_views) * 100, 1) if profile_views else 0.0
    return {
        'profile_views': profile_views,
        'product_clicks': product_clicks,
        'favorite_count': favorite_count,
        'review_count': review_count,
        'conversion_rate': conversion_rate
    }


@farms_bp.route('/dashboard')
def dashboard():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to access the farmer dashboard.', 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, user_id)
    if not user or (not user.is_farmer and not user.is_admin):
        flash('Access restricted to registered farm owners and admins.', 'error')
        return redirect(url_for('main.index'))

    if user.is_admin:
        farms = Farm.query.order_by(Farm.id.desc()).all()
        farm_metrics = [get_farm_metrics(farm) for farm in farms]
        dashboard_summary = {
            'profile_views': sum(metric['profile_views'] for metric in farm_metrics),
            'favorite_count': sum(metric['favorite_count'] for metric in farm_metrics),
            'product_clicks': sum(metric['product_clicks'] for metric in farm_metrics),
            'conversion_rate': round((sum(metric['favorite_count'] for metric in farm_metrics) / sum(metric['profile_views'] for metric in farm_metrics)) * 100, 1) if sum(metric['profile_views'] for metric in farm_metrics) else 0.0
        }
        newsletters_by_farm = {
            farm.id: Newsletter.query.filter_by(farm_id=farm.id).order_by(Newsletter.created_at.desc()).all()
            for farm in farms
        }
        return render_template('farms/dashboard.html', farms=farms, is_admin_moderation=True, farm_metrics=farm_metrics, dashboard_summary=dashboard_summary, newsletters_by_farm=newsletters_by_farm)

    farms = Farm.query.filter_by(user_id=user.id).order_by(Farm.id.desc()).all()
    farm_metrics = [get_farm_metrics(farm) for farm in farms]
    dashboard_summary = {
        'profile_views': sum(metric['profile_views'] for metric in farm_metrics),
        'favorite_count': sum(metric['favorite_count'] for metric in farm_metrics),
        'product_clicks': sum(metric['product_clicks'] for metric in farm_metrics),
        'conversion_rate': round((sum(metric['favorite_count'] for metric in farm_metrics) / sum(metric['profile_views'] for metric in farm_metrics)) * 100, 1) if sum(metric['profile_views'] for metric in farm_metrics) else 0.0
    }
    newsletters_by_farm = {
        farm.id: Newsletter.query.filter_by(farm_id=farm.id).order_by(Newsletter.created_at.desc()).all()
        for farm in farms
    }
    return render_template('farms/dashboard.html', farms=farms, is_admin_moderation=False, farm_metrics=farm_metrics, dashboard_summary=dashboard_summary, newsletters_by_farm=newsletters_by_farm)


@farms_bp.route('/farm/<int:farm_id>/go-live', methods=['POST'])
def go_live(farm_id):
    user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
    farm = db.session.get(Farm, farm_id)
    if not user:
        flash('Please log in to activate a farm subscription.', 'error')
        return redirect(url_for('auth.login'))
    if not farm or (farm.user_id != user.id and not user.is_admin):
        flash('You can only activate your own farm.', 'error')
        return redirect(url_for('farms.dashboard'))

    interval = request.form.get('interval', 'monthly').strip().lower()
    try:
        plan = SubscriptionPlan.query.filter_by(interval=interval).first()
        if not plan or plan.amount_cents <= 0:
            raise RuntimeError('This subscription plan is not available.')
        checkout = create_checkout_session(
            current_app.config,
            farm,
            user,
            interval,
            url_for('farms.subscription_success', farm_id=farm.id, _external=True),
            url_for('farms.dashboard', _external=True),
            plan.amount_cents
        )
        return redirect(checkout['url'])
    except (RuntimeError, ValueError, KeyError) as exc:
        current_app.logger.error('Unable to create Stripe checkout for farm %s: %s', farm.id, exc)
        flash(str(exc), 'error')
        return redirect(url_for('farms.dashboard'))


@farms_bp.route('/farm/<int:farm_id>/subscription/success')
def subscription_success(farm_id):
    user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
    farm = db.session.get(Farm, farm_id)
    session_id = request.args.get('session_id', '')
    if not user or not farm or (farm.user_id != user.id and not user.is_admin):
        flash('Subscription access denied.', 'error')
        return redirect(url_for('main.index'))
    try:
        checkout = get_checkout_session(current_app.config, session_id)
        metadata = checkout.get('metadata', {})
        if checkout.get('payment_status') != 'paid' or metadata.get('farm_id') != str(farm.id):
            raise RuntimeError('Stripe could not confirm this payment.')
        subscription = checkout.get('subscription')
        subscription_data = get_subscription(current_app.config, subscription)
        farm.subscription_status = 'active'
        farm.billing_interval = metadata.get('interval', 'monthly')
        farm.stripe_customer_id = checkout.get('customer')
        farm.stripe_subscription_id = subscription
        farm.current_period_end = unix_to_datetime(subscription_data.get('current_period_end'))
        farm.grace_period_end = None
        farm.paid_at = datetime.now(timezone.utc)
        farm.subscription_notice_sent_at = None
        db.session.commit()
        flash('Payment confirmed. Your farm is now live.', 'success')
    except (RuntimeError, ValueError, KeyError) as exc:
        current_app.logger.error('Unable to confirm Stripe checkout for farm %s: %s', farm.id, exc)
        flash('Payment could not be confirmed. Please contact support if you were charged.', 'error')
    return redirect(url_for('farms.dashboard'))


@farms_bp.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    webhook_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')
    signature = request.headers.get('Stripe-Signature', '')
    payload = request.get_data()
    if not webhook_secret or not signature:
        return 'Webhook is not configured.', 400

    timestamp = next((part.split('=', 1)[1] for part in signature.split(',') if part.startswith('t=')), '')
    signatures = [part.split('=', 1)[1] for part in signature.split(',') if part.startswith('v1=')]
    signed_payload = f'{timestamp}.{payload.decode("utf-8")}'.encode('utf-8')
    expected = hmac.new(webhook_secret.encode('utf-8'), signed_payload, hashlib.sha256).hexdigest()
    try:
        timestamp_valid = bool(timestamp) and abs(time.time() - int(timestamp)) <= 300
    except ValueError:
        timestamp_valid = False
    if not timestamp_valid or not any(hmac.compare_digest(expected, value) for value in signatures):
        return 'Invalid webhook signature.', 400

    try:
        event = json.loads(payload.decode('utf-8'))
        event_type = event.get('type', '')
        data = event.get('data', {}).get('object', {})
        subscription_id = data.get('subscription') if event_type.startswith('invoice.') else data.get('id')
        farm = Farm.query.filter_by(stripe_subscription_id=subscription_id).first()
        if farm:
            if event_type == 'invoice.payment_failed':
                farm.subscription_status = 'past_due'
                period_end = unix_to_datetime(data.get('period_end')) or farm.current_period_end
                farm.current_period_end = period_end
                farm.grace_period_end = period_end + timedelta(days=current_app.config['SUBSCRIPTION_GRACE_DAYS']) if period_end else datetime.now(timezone.utc) + timedelta(days=current_app.config['SUBSCRIPTION_GRACE_DAYS'])
                if not farm.subscription_notice_sent_at:
                    send_email(
                        farm.owner.email,
                        f'Payment needed to keep {farm.name} live',
                        f'Your subscription payment for {farm.name} was missed. Your farm will remain visible for 14 days while you update payment details. Please remedy the payment before the grace period ends.'
                    )
                    farm.subscription_notice_sent_at = datetime.now(timezone.utc)
            elif event_type == 'customer.subscription.updated':
                farm.subscription_status = data.get('status', farm.subscription_status)
                farm.current_period_end = unix_to_datetime(data.get('current_period_end'))
                if farm.subscription_status == 'active':
                    farm.grace_period_end = None
                    farm.subscription_notice_sent_at = None
                elif farm.subscription_status in {'past_due', 'unpaid'} and farm.current_period_end:
                    farm.grace_period_end = farm.current_period_end + timedelta(days=current_app.config['SUBSCRIPTION_GRACE_DAYS'])
            elif event_type == 'customer.subscription.deleted':
                farm.subscription_status = 'canceled'
                farm.grace_period_end = None
            db.session.commit()
    except (ValueError, json.JSONDecodeError) as exc:
        current_app.logger.error('Invalid Stripe webhook payload: %s', exc)
        return 'Invalid webhook payload.', 400
    return '', 200


@farms_bp.route('/farm/<int:farm_id>/newsletter', methods=['GET', 'POST'])
def send_shop_newsletter(farm_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to send a farm newsletter.', 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, user_id)
    farm = db.session.get(Farm, farm_id)
    if not farm:
        flash('Farm not found.', 'error')
        return redirect(url_for('main.index'))

    if not user or (farm.user_id != user.id and not user.is_admin):
        flash('You can only send newsletters for your own farm.', 'error')
        return redirect(url_for('farms.dashboard'))

    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        if not subject or not body:
            flash('Subject and message are required.', 'error')
            return render_template('farms/newsletter_form.html', farm=farm)

        recipients = db.session.query(User).join(
            favorite_farm,
            favorite_farm.c.user_id == User.id
        ).filter(
            favorite_farm.c.farm_id == farm.id,
            User.newsletter_opt_in.is_(True),
            User.email.isnot(None)
        ).all()

        if not recipients:
            flash('No favorited users are currently opted in to receive your newsletter.', 'info')
            return render_template('farms/newsletter_form.html', farm=farm)

        campaign = Newsletter(
            subject=subject,
            body=(body + '\n\n---\nTo update your preferences, visit: ' + url_for('main.newsletter_preferences', _external=True)),
            audience='favorites',
            farm_id=farm.id,
            created_by_id=user.id,
            sent_at=None,
            sent_count=0
        )
        db.session.add(campaign)
        db.session.flush()

        delivered = 0
        for recipient in recipients:
            email_body = f"Hi {recipient.username},\n\n{body}\n\n---\nThis email was sent to people who favorited {farm.name}. To update your preferences, visit: {url_for('main.newsletter_preferences', _external=True)}"
            status = 'sent' if send_email(recipient.email, subject, email_body) else 'failed'
            db.session.add(NewsletterDelivery(
                newsletter_id=campaign.id,
                email=recipient.email,
                recipient_type='favorited_user',
                status=status
            ))
            if status == 'sent':
                delivered += 1

        campaign.sent_at = datetime.now(timezone.utc)
        campaign.sent_count = delivered
        db.session.commit()
        flash(f'Newsletter sent to {delivered} favorited user(s).', 'success')
        return redirect(url_for('farms.dashboard'))

    return render_template('farms/newsletter_form.html', farm=farm)


@farms_bp.route('/farm/<int:farm_id>')
def farm_detail(farm_id):
    farm = db.session.get(Farm, farm_id)
    if not farm:
        flash('Farm profile not found.', 'error')
        return redirect(url_for('main.index'))
    owner_or_admin = session.get('user_id') in {farm.user_id} or session.get('is_admin')
    if not owner_or_admin:
        from views.main import farm_is_visible
        if not farm_is_visible(farm):
            flash('This farm is not currently live.', 'info')
            return redirect(url_for('main.index'))

    log_analytics_event('farm_profile_view', farm_id=farm.id, user_id=session.get('user_id'))

    favorite = False
    if session.get('user_id'):
        user = db.session.get(User, session['user_id'])
        if user:
            favorite = farm in user.favorite_farms.all()

    return render_template('farms/farm_detail.html', farm=farm, favorite=favorite)


@farms_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('main.index'))
    farm = product.farm
    owner_or_admin = session.get('user_id') in {farm.user_id} or session.get('is_admin')
    if not owner_or_admin:
        from views.main import farm_is_visible
        if not farm_is_visible(farm):
            flash('This farm is not currently live.', 'info')
            return redirect(url_for('main.index'))

    log_analytics_event('product_click', farm_id=product.farm_id, product_id=product.id, user_id=session.get('user_id'))

    favorite = False
    if session.get('user_id'):
        user = db.session.get(User, session['user_id'])
        if user:
            favorite = farm in user.favorite_farms.all()

    return render_template('farms/product_detail.html', product=product, farm=farm, favorite=favorite)


@farms_bp.route('/farm/<int:farm_id>/favorite', methods=['POST'])
def toggle_favorite(farm_id):
    if not session.get('user_id'):
        flash('Please log in to save favorites.', 'error')
        return redirect(url_for('auth.login'))

    farm = db.session.get(Farm, farm_id)
    if not farm:
        flash('Farm not found.', 'error')
        return redirect(url_for('main.index'))

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        flash('Your session is no longer valid.', 'error')
        return redirect(url_for('auth.login'))

    if farm in user.favorite_farms.all():
        user.favorite_farms.remove(farm)
        log_analytics_event('favorite_remove', farm_id=farm.id, user_id=user.id)
        flash(f'"{farm.name}" was removed from your favorites.', 'info')
    else:
        user.favorite_farms.append(farm)
        log_analytics_event('favorite_add', farm_id=farm.id, user_id=user.id)
        flash(f'"{farm.name}" was added to your favorites.', 'success')

    db.session.commit()
    return redirect(request.referrer or url_for('main.index'))


@farms_bp.route('/farm/<int:farm_id>/review', methods=['POST'])
def submit_review(farm_id):
    if not session.get('user_id'):
        flash('Please log in to leave a review.', 'error')
        return redirect(url_for('auth.login'))

    farm = db.session.get(Farm, farm_id)
    if not farm:
        flash('Farm not found.', 'error')
        return redirect(url_for('main.index'))

    if farm.user_id == session.get('user_id'):
        flash('You cannot review your own farm.', 'error')
        return redirect(url_for('farms.farm_detail', farm_id=farm.id))

    rating = request.form.get('rating', '0')
    comment = request.form.get('comment', '').strip()

    try:
        rating_value = int(rating)
    except ValueError:
        rating_value = 0

    if rating_value < 1 or rating_value > 5:
        flash('Please choose a valid star rating between 1 and 5.', 'error')
        return redirect(url_for('farms.farm_detail', farm_id=farm.id))

    if not comment:
        flash('Please leave a review comment.', 'error')
        return redirect(url_for('farms.farm_detail', farm_id=farm.id))

    review = StoreReview(
        farm_id=farm.id,
        user_id=session['user_id'],
        rating=rating_value,
        comment=comment
    )
    db.session.add(review)
    db.session.commit()

    flash('Thank you for leaving a review!', 'success')
    return redirect(url_for('farms.farm_detail', farm_id=farm.id))


@farms_bp.route('/farm/add', methods=['GET', 'POST'])
def add_farm():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in first to create a farm.', 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, user_id)
    if not user:
        flash('User account not found.', 'error')
        return redirect(url_for('auth.login'))

    if user.is_admin:
        flash('Admin accounts cannot register or own farms.', 'error')
        return redirect(url_for('farms.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        contact_email = request.form.get('contact_email', '').strip()
        street_address = request.form.get('street_address', '').strip()
        city = request.form.get('city', '').strip()
        province = request.form.get('province', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        contact_phone = request.form.get('contact_phone', '').strip()
        description = request.form.get('description', '').strip()

        if not name or not contact_email or not street_address or not city or not province or not postal_code:
            flash('Please fill in all required farm address and contact fields.', 'error')
            return render_template('farms/add_farm.html')

        accepts_cash = 'accepts_cash' in request.form
        accepts_etransfer = 'accepts_etransfer' in request.form
        etransfer_email = request.form.get('etransfer_email', '').strip()

        if not accepts_cash and not accepts_etransfer:
            flash('Please select at least one accepted payment method.', 'error')
            return render_template('farms/add_farm.html')

        image_file = request.files.get('profile_image')
        filename = save_uploaded_file(image_file)

        farm = Farm(
            name=name,
            street_address=street_address,
            city=city,
            province=province,
            postal_code=postal_code,
            contact_email=contact_email,
            contact_phone=contact_phone or None,
            profile_image=filename,
            description=description or None,
            accepts_cash=accepts_cash,
            accepts_etransfer=accepts_etransfer,
            etransfer_email=etransfer_email if accepts_etransfer else None,
            user_id=user.id
        )

        if not user.is_farmer:
            user.is_farmer = True
            session['is_farmer'] = True

        db.session.add(farm)
        db.session.commit()
        flash(f'Farm profile "{farm.name}" created successfully!', 'success')
        return redirect(url_for('farms.dashboard'))

    return render_template('farms/add_farm.html')


@farms_bp.route('/farm/<int:farm_id>/edit', methods=['GET', 'POST'])
def edit_farm(farm_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in first.', 'error')
        return redirect(url_for('auth.login'))

    farm = db.session.get(Farm, farm_id)
    if not farm:
        flash('Farm not found.', 'error')
        return redirect(url_for('farms.dashboard'))

    if farm.user_id != user_id and not session.get('is_admin'):
        flash('Unauthorized: You can only edit your own farms.', 'error')
        return redirect(url_for('farms.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        contact_email = request.form.get('contact_email', '').strip()
        street_address = request.form.get('street_address', '').strip()
        city = request.form.get('city', '').strip()
        province = request.form.get('province', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        contact_phone = request.form.get('contact_phone', '').strip()
        description = request.form.get('description', '').strip()

        if not name or not contact_email or not street_address or not city or not province or not postal_code:
            flash('Please fill in all required farm fields.', 'error')
            return render_template('farms/edit_farm.html', farm=farm)

        accepts_cash = 'accepts_cash' in request.form
        accepts_etransfer = 'accepts_etransfer' in request.form
        etransfer_email = request.form.get('etransfer_email', '').strip()

        if not accepts_cash and not accepts_etransfer:
            flash('Please select at least one accepted payment method.', 'error')
            return render_template('farms/edit_farm.html', farm=farm)

        farm.name = name
        farm.contact_email = contact_email
        farm.street_address = street_address
        farm.city = city
        farm.province = province
        farm.postal_code = postal_code
        farm.contact_phone = contact_phone or None
        farm.description = description or None
        farm.accepts_cash = accepts_cash
        farm.accepts_etransfer = accepts_etransfer
        farm.etransfer_email = etransfer_email if accepts_etransfer else None

        # Update coordinates automatically
        farm.update_coordinates()

        image_file = request.files.get('profile_image')
        if image_file and image_file.filename != '':
            new_filename = save_uploaded_file(image_file)
            if new_filename:
                delete_file_if_exists(farm.profile_image)
                farm.profile_image = new_filename

        db.session.commit()
        flash('Farm details updated successfully!', 'success')
        return redirect(url_for('farms.dashboard'))

    return render_template('farms/edit_farm.html', farm=farm)


@farms_bp.route('/farm/<int:farm_id>/delete', methods=['POST'])
def delete_farm(farm_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in first.', 'error')
        return redirect(url_for('auth.login'))

    farm = db.session.get(Farm, farm_id)
    if not farm:
        flash('Farm not found.', 'error')
        return redirect(url_for('farms.dashboard'))

    if farm.user_id != user_id and not session.get('is_admin'):
        flash('Unauthorized access.', 'error')
        return redirect(url_for('farms.dashboard'))

    delete_file_if_exists(farm.profile_image)
    for p in farm.products:
        delete_file_if_exists(p.image_file)

    farm_name = farm.name
    db.session.delete(farm)
    db.session.commit()
    flash(f'Farm "{farm_name}" and its products were deleted.', 'success')
    return redirect(url_for('farms.dashboard'))


# ==========================================
# PRODUCT ROUTES
# ==========================================

@farms_bp.route('/farm/<int:farm_id>/product/add', methods=['GET', 'POST'])
def add_product(farm_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in first.', 'error')
        return redirect(url_for('auth.login'))

    farm = db.session.get(Farm, farm_id)
    if not farm:
        flash('Farm not found.', 'error')
        return redirect(url_for('farms.dashboard'))

    if farm.user_id != user_id:
        flash('Unauthorized: You can only add products to your own farms.', 'error')
        return redirect(url_for('farms.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        unit = request.form.get('unit', '').strip()

        try:
            price = Decimal(request.form.get('price', '0'))
            stock_quantity = int(request.form.get('stock_quantity', '0'))

            if not name or price <= 0 or stock_quantity < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            flash('Please enter a valid product name, positive price, and non-negative inventory count.', 'error')
            return render_template('farms/add_product.html', farm=farm, units=STANDARD_UNITS, categories=PRODUCT_CATEGORIES)

        image_file = request.files.get('product_image')
        filename = save_uploaded_file(image_file)

        product = Product(
            name=name,
            category=category,
            price=price,
            unit=unit,
            stock_quantity=stock_quantity,
            image_file=filename,
            farm_id=farm.id
        )
        db.session.add(product)
        db.session.commit()

        # Save dynamic multi-buy pricing tiers
        quantities = request.form.getlist('bulk_quantities[]')
        prices = request.form.getlist('bulk_prices[]')
        process_bulk_tiers(product, quantities, prices)
        db.session.commit()

        flash(f'Product "{product.name}" added successfully!', 'success')
        return redirect(url_for('farms.dashboard'))

    return render_template('farms/add_product.html', farm=farm, units=STANDARD_UNITS, categories=PRODUCT_CATEGORIES)


@farms_bp.route('/product/<int:product_id>/edit', methods=['GET', 'POST'])
def edit_product(product_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in first.', 'error')
        return redirect(url_for('auth.login'))

    product = db.session.get(Product, product_id)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('farms.dashboard'))

    if product.farm.user_id != user_id:
        flash('Unauthorized: You can only edit your own products.', 'error')
        return redirect(url_for('farms.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        unit = request.form.get('unit', '').strip()

        try:
            price = Decimal(request.form.get('price', '0'))
            stock_quantity = int(request.form.get('stock_quantity', '0'))

            if not name or price <= 0 or stock_quantity < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            flash('Please enter a valid product name, positive price, and non-negative inventory count.', 'error')
            return render_template('farms/edit_product.html', product=product, units=STANDARD_UNITS, categories=PRODUCT_CATEGORIES)

        product.name = name
        product.category = category
        product.price = price
        product.unit = unit
        product.stock_quantity = stock_quantity

        image_file = request.files.get('product_image')
        if image_file and image_file.filename != '':
            new_filename = save_uploaded_file(image_file)
            if new_filename:
                delete_file_if_exists(product.image_file)
                product.image_file = new_filename

        # Update dynamic multi-buy pricing tiers
        quantities = request.form.getlist('bulk_quantities[]')
        prices = request.form.getlist('bulk_prices[]')
        process_bulk_tiers(product, quantities, prices)

        db.session.commit()
        flash(f'Product "{product.name}" updated successfully!', 'success')
        return redirect(url_for('farms.dashboard'))

    return render_template('farms/edit_product.html', product=product, units=STANDARD_UNITS, categories=PRODUCT_CATEGORIES)


@farms_bp.route('/product/<int:product_id>/delete', methods=['POST'])
def delete_product(product_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in first.', 'error')
        return redirect(url_for('auth.login'))

    product = db.session.get(Product, product_id)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('farms.dashboard'))

    if product.farm.user_id != user_id:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('farms.dashboard'))

    delete_file_if_exists(product.image_file)

    product_name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f'Product "{product_name}" deleted.', 'success')
    return redirect(url_for('farms.dashboard'))
