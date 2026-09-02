import secrets
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from models import db, User

auth_bp = Blueprint('auth', __name__)


def send_email(recipient_email, subject, body, sender_name='Farm Marketplace'):
    sender = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME') or 'your-proton-email@proton.me'
    mail_server = current_app.config.get('MAIL_SERVER', '')
    mail_port = current_app.config.get('MAIL_PORT', 465)
    mail_username = current_app.config.get('MAIL_USERNAME', '')
    mail_password = current_app.config.get('MAIL_PASSWORD', '')
    use_tls = current_app.config.get('MAIL_USE_TLS', False)
    use_ssl = current_app.config.get('MAIL_USE_SSL', True)

    if not mail_server or not mail_username or not mail_password:
        print(f'[DEV EMAIL] To: {recipient_email}')
        print(f'[DEV EMAIL] Subject: {subject}')
        print(f'[DEV EMAIL] Body:\n{body}')
        return True

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient_email
    msg.set_content(body)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(mail_server, mail_port) as server:
                server.login(mail_username, mail_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(mail_server, mail_port) as server:
                if use_tls:
                    server.starttls()
                server.login(mail_username, mail_password)
                server.send_message(msg)
        return True
    except Exception as exc:
        flash(f'Email delivery failed in this environment: {exc}', 'error')
        return False


def send_verification_email(user):
    token = secrets.token_urlsafe(32)
    user.email_verification_token = token
    user.email_verification_sent_at = datetime.now(timezone.utc)
    user.email_verified = False
    db.session.commit()

    verification_url = url_for('auth.verify_email', token=token, _external=True)
    subject = 'Verify your Farm Marketplace email'
    body = (
        f"Hi {user.username},\n\n"
        f"Thanks for joining Farm Marketplace. Please verify your email address by visiting:\n\n"
        f"{verification_url}\n\n"
        "If you did not create this account, you can ignore this message."
    )

    sent = send_email(user.email, subject, body)
    if not sent:
        return verification_url

    return verification_url


def send_password_reset_email(user):
    token = secrets.token_urlsafe(32)
    user.password_reset_token = token
    user.password_reset_sent_at = datetime.now(timezone.utc)
    db.session.commit()

    reset_url = url_for('auth.reset_password', token=token, _external=True)
    subject = 'Reset your Farm Marketplace password'
    body = (
        f"Hi {user.username},\n\n"
        "We received a request to reset your Farm Marketplace password.\n\n"
        f"Use this link to choose a new password: {reset_url}\n\n"
        "If you did not request this, you can safely ignore this email."
    )
    send_email(user.email, subject, body)
    return reset_url


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        if session.get('is_admin'):
            return redirect(url_for('admin.dashboard'))
        elif session.get('is_farmer'):
            return redirect(url_for('farms.dashboard'))
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('auth/login.html')

        user = User.query.filter(User.username.ilike(username)).first()

        if not user or not user.check_password(password):
            flash('Invalid username or password.', 'error')
            return render_template('auth/login.html')

        session['user_id'] = user.id
        session['username'] = user.username
        session['is_farmer'] = user.is_farmer
        session['is_admin'] = user.is_admin

        if not user.email_verified:
            flash('Please verify your email address before continuing.', 'info')
        flash(f'Welcome back, {user.username}!', 'success')

        if user.is_admin:
            return redirect(url_for('admin.dashboard'))
        elif user.is_farmer:
            return redirect(url_for('farms.dashboard'))

        return redirect(url_for('main.index'))

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        is_farmer = 'is_farmer' in request.form
        newsletter_opt_in = 'newsletter_opt_in' in request.form

        if not username or len(username) < 3:
            flash('Username must be at least 3 characters long.', 'error')
            return render_template('auth/register.html')

        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
            return render_template('auth/register.html')

        if not password or len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('auth/register.html')

        if User.query.filter(User.username.ilike(username)).first():
            flash('Username already exists. Please choose another.', 'error')
            return render_template('auth/register.html')

        if User.query.filter(User.email.ilike(email)).first():
            flash('Email already registered. Please log in or use another email.', 'error')
            return render_template('auth/register.html')

        new_user = User(
            username=username,
            email=email,
            is_farmer=is_farmer,
            is_admin=False,
            newsletter_opt_in=newsletter_opt_in,
            consent_updated_at=datetime.now(timezone.utc),
            email_verified=False
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        send_verification_email(new_user)
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    user = User.query.filter_by(email_verification_token=token).first()
    if not user:
        flash('That verification link is invalid or expired.', 'error')
        return redirect(url_for('main.index'))

    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_sent_at = None
    db.session.commit()

    flash('Email verified successfully. Thank you!', 'success')
    return redirect(url_for('auth.profile'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('auth/forgot_password.html')

        user = User.query.filter(User.email.ilike(email)).first()
        if user:
            send_password_reset_email(user)
        flash('If an account exists for that email, a password reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(password_reset_token=token).first()
    if not user:
        flash('This password reset link is invalid or has expired.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not password or len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('auth/reset_password.html', token=token)

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token)

        user.set_password(password)
        user.password_reset_token = None
        user.password_reset_sent_at = None
        db.session.commit()
        flash('Your password has been reset successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('user_id'):
        flash('Please log in to access your profile.', 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        flash('Your session is no longer valid.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_email = request.form.get('email', '').strip().lower()
        phone_number = request.form.get('phone_number', '').strip()
        current_password = request.form.get('current_password', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        newsletter_opt_in = 'newsletter_opt_in' in request.form

        if not new_email or '@' not in new_email:
            flash('Please enter a valid email address.', 'error')
            return render_template('auth/profile.html', user=user)

        if new_email != user.email:
            existing = User.query.filter(User.email.ilike(new_email), User.id != user.id).first()
            if existing:
                flash('That email address is already in use by another account.', 'error')
                return render_template('auth/profile.html', user=user)
            user.email = new_email
            user.email_verified = False
            user.email_verification_token = None
            send_verification_email(user)
            flash('Your email was updated and a new verification message has been sent.', 'success')

        user.phone_number = phone_number or None
        user.newsletter_opt_in = newsletter_opt_in
        user.consent_updated_at = datetime.now(timezone.utc)

        if password:
            if not current_password or not user.check_password(current_password):
                flash('Your current password is required to change passwords.', 'error')
                return render_template('auth/profile.html', user=user)
            if len(password) < 6:
                flash('New password must be at least 6 characters long.', 'error')
                return render_template('auth/profile.html', user=user)
            if password != confirm_password:
                flash('New password and confirmation do not match.', 'error')
                return render_template('auth/profile.html', user=user)
            user.set_password(password)
            flash('Your password was updated successfully.', 'success')

        db.session.commit()
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', user=user)


@auth_bp.route('/resend-verification')
def resend_verification():
    if not session.get('user_id'):
        flash('Please log in to resend your verification email.', 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        flash('Your session is no longer valid.', 'error')
        return redirect(url_for('auth.login'))

    if user.email_verified:
        flash('Your email is already verified.', 'info')
        return redirect(url_for('auth.profile'))

    send_verification_email(user)
    flash('A new verification email has been sent.', 'success')
    return redirect(url_for('auth.profile'))


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))