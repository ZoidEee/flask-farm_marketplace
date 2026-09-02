import os
from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, session, current_app, request
from models import db, User, Farm, Product, Newsletter, NewsletterDelivery, StoreReview, SubscriptionPlan, \
    AnalyticsEvent, favorite_farm
from views.auth import send_email

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def get_newsletter_recipients(audience):
    audience = (audience or 'both').lower().strip()
    emails = []
    seen = set()

    if audience in {'users', 'both'}:
        for user in User.query.filter_by(newsletter_opt_in=True).all():
            if user.email:
                email = user.email.strip().lower()
                if email and email not in seen:
                    emails.append(email)
                    seen.add(email)

    if audience in {'farmers', 'both'}:
        for user in User.query.filter_by(is_farmer=True, newsletter_opt_in=True).all():
            if user.email:
                email = user.email.strip().lower()
                if email and email not in seen:
                    emails.append(email)
                    seen.add(email)

    return emails


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in first.', 'error')
            return redirect(url_for('auth.login'))

        # Check the actual database record
        user = db.session.get(User, user_id)
        if not user or not user.is_admin:
            flash('Access denied: SysAdmin credentials required.', 'error')
            return redirect(url_for('main.index'))

        # Keep session up to date
        session['is_admin'] = user.is_admin
        session['is_farmer'] = user.is_farmer

        return f(*args, **kwargs)

    return decorated_function


def get_farm_analytics(farm):
    profile_views = AnalyticsEvent.query.filter_by(farm_id=farm.id, event_type='farm_profile_view').count()
    favorite_count = db.session.execute(
        db.select(db.func.count()).select_from(favorite_farm).where(favorite_farm.c.farm_id == farm.id)
    ).scalar() or 0
    product_clicks = AnalyticsEvent.query.filter_by(farm_id=farm.id, event_type='product_click').count()
    review_count = StoreReview.query.filter_by(farm_id=farm.id).count()
    conversion_rate = round((favorite_count / profile_views) * 100, 1) if profile_views else 0.0
    return {
        'farm': farm,
        'profile_views': profile_views,
        'favorite_count': favorite_count,
        'product_clicks': product_clicks,
        'review_count': review_count,
        'conversion_rate': conversion_rate,
        'engagement_score': profile_views + favorite_count + product_clicks + review_count
    }


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    users = User.query.order_by(User.id).all()
    farms = Farm.query.order_by(Farm.id).all()
    total_products = Product.query.count()
    total_favorites = db.session.execute(db.select(db.func.count()).select_from(AnalyticsEvent).where(
        AnalyticsEvent.event_type == 'favorite_add')).scalar() or 0
    total_profile_views = AnalyticsEvent.query.filter_by(event_type='farm_profile_view').count()
    total_product_clicks = AnalyticsEvent.query.filter_by(event_type='product_click').count()
    total_reviews = StoreReview.query.count()
    live_farms = Farm.query.filter_by(subscription_status='active').count()
    past_due_farms = Farm.query.filter_by(subscription_status='past_due').count()
    unpaid_farms = Farm.query.filter(Farm.subscription_status != 'active').count()
    monthly_subscriptions = Farm.query.filter_by(subscription_status='active', billing_interval='monthly').count()
    yearly_subscriptions = Farm.query.filter_by(subscription_status='active', billing_interval='yearly').count()
    estimated_monthly_revenue = monthly_subscriptions * 30 + yearly_subscriptions * 25
    estimated_annual_revenue = monthly_subscriptions * 360 + yearly_subscriptions * 300
    conversion_rate = round((total_favorites / total_profile_views) * 100, 1) if total_profile_views else 0.0
    farm_analytics = [get_farm_analytics(farm) for farm in farms]
    top_farms_by_views = sorted(farm_analytics, key=lambda item: item['profile_views'], reverse=True)[:5]
    top_farms_by_engagement = sorted(farm_analytics, key=lambda item: item['engagement_score'], reverse=True)[:5]

    favorite_breakdown = db.session.execute(
        db.select(favorite_farm.c.farm_id, db.func.count(favorite_farm.c.user_id).label('favorite_count'))
        .group_by(favorite_farm.c.farm_id)
        .order_by(db.desc('favorite_count'))
        .limit(5)
    ).all()
    top_favorited_farms = []
    for farm_id, favorite_count in favorite_breakdown:
        farm = db.session.get(Farm, farm_id)
        if farm:
            top_favorited_farms.append({'farm': farm, 'favorite_count': favorite_count})
    recent_newsletters = Newsletter.query.order_by(Newsletter.created_at.desc()).limit(5).all()
    subscription_plans = {plan.interval: plan for plan in SubscriptionPlan.query.all()}
    return render_template(
        'admin/admin_dashboard.html',
        users=users,
        farms=farms,
        total_products=total_products,
        total_favorites=total_favorites,
        total_profile_views=total_profile_views,
        total_product_clicks=total_product_clicks,
        total_reviews=total_reviews,
        live_farms=live_farms,
        past_due_farms=past_due_farms,
        unpaid_farms=unpaid_farms,
        monthly_subscriptions=monthly_subscriptions,
        yearly_subscriptions=yearly_subscriptions,
        estimated_monthly_revenue=estimated_monthly_revenue,
        estimated_annual_revenue=estimated_annual_revenue,
        conversion_rate=conversion_rate,
        top_farms_by_views=top_farms_by_views,
        top_farms_by_engagement=top_farms_by_engagement,
        top_favorited_farms=top_favorited_farms,
        recent_newsletters=recent_newsletters,
        farm_analytics=farm_analytics,
        subscription_plans=subscription_plans
    )


@admin_bp.route('/subscription-plans', methods=['POST'])
@admin_required
def update_subscription_plans():
    for interval in ('monthly', 'yearly'):
        raw_amount = request.form.get(f'{interval}_amount', '').strip()
        try:
            amount = int(raw_amount)
        except ValueError:
            flash(f'Enter a valid {interval} price in cents.', 'error')
            return redirect(url_for('admin.dashboard'))
        if amount <= 0:
            flash(f'{interval.title()} price must be greater than zero.', 'error')
            return redirect(url_for('admin.dashboard'))
        plan = SubscriptionPlan.query.filter_by(interval=interval).first()
        if not plan:
            plan = SubscriptionPlan(interval=interval, currency=current_app.config['STRIPE_CURRENCY'])
            db.session.add(plan)
        plan.amount_cents = amount
        plan.currency = current_app.config['STRIPE_CURRENCY']
        plan.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    flash('Subscription prices updated. New checkouts will use the new prices.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/newsletter', methods=['GET', 'POST'])
@admin_required
def newsletter():
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        audience = request.form.get('audience', 'both').strip().lower()

        if audience not in {'users', 'farmers', 'both'}:
            flash('Please choose a valid newsletter audience.', 'error')
            return render_template('admin/admin_newsletter.html',
                                   newsletters=Newsletter.query.order_by(Newsletter.created_at.desc()).all())

        if not subject or not body:
            flash('Subject and message are required before sending a newsletter.', 'error')
        else:
            recipients = get_newsletter_recipients(audience)
            if not recipients:
                flash('There are no newsletter subscribers in the selected audience.', 'info')
            else:
                newsletter = Newsletter(
                    subject=subject,
                    body=body,
                    audience=audience,
                    created_by_id=session.get('user_id'),
                    sent_at=datetime.now(timezone.utc),
                    sent_count=0
                )
                db.session.add(newsletter)
                db.session.flush()

                delivered = 0
                for email in recipients:
                    status = 'sent' if send_email(email, subject, body) else 'failed'
                    db.session.add(NewsletterDelivery(
                        newsletter_id=newsletter.id,
                        email=email,
                        recipient_type='user',
                        status=status
                    ))
                    if status == 'sent':
                        delivered += 1

                newsletter.sent_count = delivered
                db.session.commit()
                flash(f'Newsletter "{subject}" sent to {delivered} of {len(recipients)} recipients.', 'success')
                return redirect(url_for('admin.newsletter'))

    newsletters = Newsletter.query.order_by(Newsletter.created_at.desc()).all()
    return render_template('admin/admin_newsletter.html', newsletters=newsletters)


@admin_bp.route('/user/toggle-role/<int:user_id>/<string:role>')
@admin_required
def toggle_user_role(user_id, role):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.dashboard'))

    if user.id == session.get('user_id') and role == 'admin':
        flash('You cannot revoke your own admin rights.', 'error')
        return redirect(url_for('admin.dashboard'))

    if role == 'admin':
        user.is_admin = not user.is_admin
        if user.is_admin:
            user.is_farmer = False
        action_name = "Admin"
    elif role == 'farmer':
        user.is_farmer = not user.is_farmer
        if user.is_farmer:
            user.is_admin = False
        action_name = "Farmer"
    else:
        flash('Invalid role specified.', 'error')
        return redirect(url_for('admin.dashboard'))

    db.session.commit()

    if user.id == session.get('user_id'):
        session['is_admin'] = user.is_admin
        session['is_farmer'] = user.is_farmer

    status_str = "granted" if getattr(user, f"is_{role}") else "revoked"
    flash(f'{action_name} role {status_str} for {user.username}.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/user/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.dashboard'))

    if user.id == session.get('user_id'):
        flash('You cannot delete your own admin account.', 'error')
        return redirect(url_for('admin.dashboard'))

    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if upload_folder:
        for farm in user.farms:
            if farm.profile_image:
                img_path = os.path.join(upload_folder, farm.profile_image)
                if os.path.exists(img_path):
                    try:
                        os.remove(img_path)
                    except OSError:
                        pass
            for product in farm.products:
                if product.image_file:
                    prod_img = os.path.join(upload_folder, product.image_file)
                    if os.path.exists(prod_img):
                        try:
                            os.remove(prod_img)
                        except OSError:
                            pass

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{username}" and associated farms deleted successfully.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/farm/delete/<int:farm_id>', methods=['POST'])
@admin_required
def delete_farm(farm_id):
    farm = db.session.get(Farm, farm_id)
    if not farm:
        flash('Farm not found.', 'error')
        return redirect(url_for('admin.dashboard'))

    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if upload_folder:
        if farm.profile_image:
            img_path = os.path.join(upload_folder, farm.profile_image)
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except OSError:
                    pass
        for product in farm.products:
            if product.image_file:
                prod_img = os.path.join(upload_folder, product.image_file)
                if os.path.exists(prod_img):
                    try:
                        os.remove(prod_img)
                    except OSError:
                        pass

    farm_name = farm.name
    db.session.delete(farm)
    db.session.commit()
    flash(f'Farm "{farm_name}" deleted.', 'success')
    return redirect(url_for('admin.dashboard'))
