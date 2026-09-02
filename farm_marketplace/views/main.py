from datetime import datetime, timezone
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from models import Product, Farm, User, db

main_bp = Blueprint('main', __name__)

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


def farm_is_visible(farm):
    if farm.subscription_status == 'active':
        return True
    if farm.subscription_status == 'past_due' and farm.grace_period_end:
        return datetime.now(timezone.utc) <= farm.grace_period_end.replace(tzinfo=timezone.utc)
    return False


@main_bp.route('/')
def index():
    query = request.args.get('q', '').strip()
    selected_category = request.args.get('category', '').strip()
    favorites_only = request.args.get('favorites_only') in {'1', 'true', 'yes', 'on'}

    farms_query = Farm.query

    if query:
        search_filter = f"%{query}%"
        farms_query = farms_query.filter(
            (Farm.name.ilike(search_filter)) |
            (Farm.city.ilike(search_filter)) |
            (Farm.province.ilike(search_filter)) |
            (Farm.products.any(Product.name.ilike(search_filter)))
        )

    if selected_category:
        farms_query = farms_query.filter(
            Farm.products.any(Product.category == selected_category)
        )

    favorite_farm_ids = set()
    user = None
    if session.get('user_id'):
        user = db.session.get(User, session['user_id'])
        if user:
            favorite_farm_ids = {farm.id for farm in user.favorite_farms.all()}
            if favorites_only:
                farms_query = farms_query.filter(Farm.id.in_([farm.id for farm in user.favorite_farms.all()]))

    farms = [farm for farm in farms_query.all() if farm_is_visible(farm)]

    return render_template(
        'public/index.html',
        farms=farms,
        categories=PRODUCT_CATEGORIES,
        query=query,
        selected_category=selected_category,
        favorites_only=favorites_only,
        favorite_farm_ids=favorite_farm_ids
    )


@main_bp.route('/about')
def about():
    return render_template('public/about.html')


@main_bp.route('/privacy')
def privacy():
    return render_template('public/privacy.html')


@main_bp.route('/terms')
def terms():
    return render_template('public/terms.html')


@main_bp.route('/favorites')
def favorites():
    if not session.get('user_id'):
        flash('Please log in to view your favorites.', 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        flash('Your session is no longer valid.', 'error')
        return redirect(url_for('auth.login'))

    farms = [farm for farm in user.favorite_farms.order_by(Farm.name).all() if farm_is_visible(farm)]
    return render_template('public/favorites.html', farms=farms, favorite_farm_ids={farm.id for farm in farms})


@main_bp.route('/newsletter/preferences', methods=['GET', 'POST'])
def newsletter_preferences():
    if not session.get('user_id'):
        flash('Please log in to update your newsletter preferences.', 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        flash('Your account could not be found.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        user.newsletter_opt_in = 'newsletter_opt_in' in request.form
        user.consent_updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash('Your newsletter preferences have been updated.', 'success')
        return redirect(url_for('main.newsletter_preferences'))

    return render_template('public/newsletter_preferences.html', user=user)


@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not name or not email or not subject or not message:
            flash('Please complete all fields before sending your message.', 'error')
        else:
            flash('Thanks for contacting the Farm Marketplace team. We will get back to you soon.', 'success')
            return redirect(url_for('main.contact'))

    return render_template('public/contact.html')
