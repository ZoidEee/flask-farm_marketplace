import os
import sys
import unittest
from decimal import Decimal

# Ensure farm_marketplace directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, 'farm_marketplace'))

from app import create_app
from models import db, User, Farm, Product, BulkPriceTier


class FarmMarketplaceTestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    email='admin@farmdirect.local',
                    is_admin=True,
                    is_farmer=False  # Admin accounts cannot be farmers
                )
                admin.set_password('Admin123!')
                db.session.add(admin)
                db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self, username, password):
        return self.client.post('/login', data={\
            'username': username,\
            'password': password\
        }, follow_redirects=False)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_admin_dashboard_access_control(self):
        # 1. Unauthenticated user cannot access admin dashboard
        response = self.client.get('/admin/dashboard')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

        # 2. Regular user cannot access admin dashboard
        with self.app.app_context():
            user = User(username='regular_user', email='reg@example.com', is_admin=False, is_farmer=False)
            user.set_password('Secret123!')
            db.session.add(user)
            db.session.commit()

        self.login('regular_user', 'Secret123!')
        response = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertIn(b'Access denied: SysAdmin credentials required.', response.data)
        self.logout()

        # 3. Admin user can access admin dashboard
        login_res = self.login('admin', 'Admin123!')
        self.assertEqual(login_res.status_code, 302)
        self.assertIn('/admin/dashboard', login_res.headers['Location'])

        response = self.client.get('/admin/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'System Administration Panel', response.data)
        self.assertIn(b'User Management', response.data)
        self.assertIn(b'Farm Moderation', response.data)

    def test_admin_role_toggling(self):
        with self.app.app_context():
            user = User(username='alice', email='alice@farm.com', is_farmer=False, is_admin=False)
            user.set_password('Pass123!')
            db.session.add(user)
            db.session.commit()
            alice_id = user.id

        self.login('admin', 'Admin123!')

        # Toggle Alice to farmer (must grant farmer, revoke admin if any)
        res = self.client.get(f'/admin/user/toggle-role/{alice_id}/farmer', follow_redirects=True)
        self.assertIn(b'Farmer role granted for alice.', res.data)
        with self.app.app_context():
            alice = db.session.get(User, alice_id)
            self.assertTrue(alice.is_farmer)
            self.assertFalse(alice.is_admin)

        # Toggle Alice to admin (must grant admin, revoke farmer)
        res = self.client.get(f'/admin/user/toggle-role/{alice_id}/admin', follow_redirects=True)
        self.assertIn(b'Admin role granted for alice.', res.data)
        with self.app.app_context():
            alice = db.session.get(User, alice_id)
            self.assertTrue(alice.is_admin)
            self.assertFalse(alice.is_farmer)  # Admin cannot be farmer

        # Admin cannot revoke own admin rights
        with self.app.app_context():
            admin_id = User.query.filter_by(username='admin').first().id
        res = self.client.get(f'/admin/user/toggle-role/{admin_id}/admin', follow_redirects=True)
        self.assertIn(b'You cannot revoke your own admin rights.', res.data)

    def test_registration_and_login_flow(self):
        # Register new farmer
        res = self.client.post('/register', data={
            'username': 'bob_farmer',
            'email': 'bob@greenfields.ca',
            'password': 'FarmerPassword123',
            'is_farmer': 'true'
        }, follow_redirects=True)
        self.assertIn(b'Registration successful! Please log in.', res.data)

        # Login as bob_farmer -> redirects to farms.dashboard
        login_res = self.login('bob_farmer', 'FarmerPassword123')
        self.assertEqual(login_res.status_code, 302)
        self.assertIn('/dashboard', login_res.headers['Location'])

        self.logout()

        # Duplicate registration prevented
        res = self.client.post('/register', data={
            'username': 'bob_farmer',
            'email': 'bob2@greenfields.ca',
            'password': 'FarmerPassword123'
        }, follow_redirects=True)
        self.assertIn(b'Username already exists.', res.data)

    def test_farm_and_product_crud_with_bulk_pricing(self):
        # Create a farmer user first (since admins cannot own farms)
        with self.app.app_context():
            farmer_user = User(username='charlie_farmer', email='charlie@farm.ca', is_farmer=True)
            farmer_user.set_password('Charlie123!')
            db.session.add(farmer_user)
            db.session.commit()
            farmer_id = farmer_user.id

        self.login('charlie_farmer', 'Charlie123!')

        # 1. Create a Farm
        res = self.client.post('/farm/add', data={
            'name': 'Sunny Acres Farm',
            'contact_email': 'info@sunnyacres.ca',
            'contact_phone': '555-123-4567',
            'street_address': '456 Country Line Rd',
            'city': 'Guelph',
            'province': 'ON',
            'postal_code': 'N1H 6H8',
            'description': 'Fresh organic apples and vegetables.',
            'accepts_cash': 'true',
            'accepts_etransfer': 'true',
            'etransfer_email': 'payments@sunnyacres.ca'
        }, follow_redirects=True)
        self.assertIn(b'Sunny Acres Farm', res.data)
        self.assertIn(b'created successfully!', res.data)

        with self.app.app_context():
            farm = Farm.query.filter_by(name='Sunny Acres Farm').first()
            self.assertIsNotNone(farm)
            self.assertEqual(farm.location, 'Guelph, ON')
            self.assertEqual(farm.payment_methods_display, 'Cash on Pickup, Interac e-Transfer (payments@sunnyacres.ca)')
            farm_id = farm.id

        # 2. Add a Product with Bulk Tiers (Multi-buy)
        res = self.client.post(f'/farm/{farm_id}/product/add', data={
            'name': 'Honeycrisp Apples',
            'category': 'Fruits',
            'price': '4.50',
            'unit': 'lbs',
            'stock_quantity': '100',
            'bulk_quantities[]': ['3', '5'],
            'bulk_prices[]': ['12.00', '18.00']
        }, follow_redirects=True)
        self.assertIn(b'Honeycrisp Apples', res.data)
        self.assertIn(b'added successfully!', res.data)

        with self.app.app_context():
            product = Product.query.filter_by(name='Honeycrisp Apples').first()
            self.assertIsNotNone(product)
            self.assertEqual(len(product.bulk_tiers), 2)
            self.assertEqual(product.price_display, '1/$4.50 | 3/$12.00 | 5/$18.00')
            product_id = product.id

        # 3. View Farm Storefront
        res = self.client.get(f'/farm/{farm_id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Sunny Acres Farm', res.data)
        self.assertIn(b'Honeycrisp Apples', res.data)
        self.assertIn(b'1/$4.50 | 3/$12.00 | 5/$18.00', res.data)

        # 4. Edit Product
        res = self.client.post(f'/product/{product_id}/edit', data={
            'name': 'Organic Honeycrisp Apples',
            'category': 'Fruits',
            'price': '4.75',
            'unit': 'lbs',
            'stock_quantity': '80',
            'bulk_quantities[]': ['3'],
            'bulk_prices[]': ['13.00']
        }, follow_redirects=True)
        self.assertIn(b'Organic Honeycrisp Apples', res.data)
        self.assertIn(b'updated successfully!', res.data)

        with self.app.app_context():
            product = db.session.get(Product, product_id)
            self.assertEqual(product.name, 'Organic Honeycrisp Apples')
            self.assertEqual(product.price_display, '1/$4.75 | 3/$13.00')

        # 5. Delete Product
        res = self.client.post(f'/product/{product_id}/delete', follow_redirects=True)
        self.assertIn(b'deleted.', res.data)

        with self.app.app_context():
            self.assertIsNone(db.session.get(Product, product_id))

        # 6. Delete Farm
        res = self.client.post(f'/farm/{farm_id}/delete', follow_redirects=True)
        self.assertIn(b'deleted.', res.data)

        with self.app.app_context():
            self.assertIsNone(db.session.get(Farm, farm_id))

    def test_marketplace_search_and_filtering(self):
        with self.app.app_context():
            farmer = User(username='farmer11', email='f11@farm.ca', is_farmer=True)
            farmer.set_password('Pass123!')
            db.session.add(farmer)
            db.session.commit()

            farm1 = Farm(
                name='Blue Ridge Orchards',
                street_address='100 Apple Way',
                city='Kelowna',
                province='BC',
                postal_code='V1Y 1Y1',
                contact_email='kelowna@orchards.ca',
                accepts_cash=True,
                subscription_status='active',
                user_id=farmer.id
            )
            farm2 = Farm(
                name='Green Valley Dairy',
                street_address='200 Milk Lane',
                city='Woodstock',
                province='ON',
                postal_code='N4S 1A1',
                contact_email='woodstock@dairy.ca',
                accepts_cash=True,
                subscription_status='active',
                user_id=farmer.id
            )
            db.session.add_all([farm1, farm2])
            db.session.commit()

            p1 = Product(name='Gala Apples', category='Fruits', price=Decimal('3.00'), unit='lbs', stock_quantity=50, farm_id=farm1.id)
            p2 = Product(name='Fresh Cheddar', category='Dairy', price=Decimal('8.50'), unit='flat', stock_quantity=20, farm_id=farm2.id)
            p3 = Product(name='Apple Cider', category='Honey & Preserves', price=Decimal('6.00'), unit='jar', stock_quantity=15, farm_id=farm1.id)
            db.session.add_all([p1, p2, p3])
            db.session.commit()

        # Search by keyword "Apples" -> Sells apples -> matches Blue Ridge Orchards
        res = self.client.get('/?q=Apples')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Blue Ridge Orchards', res.data)
        self.assertNotIn(b'Green Valley Dairy', res.data)

        # Filter by category "Dairy" -> Sells dairy -> matches Green Valley Dairy
        res = self.client.get('/?category=Dairy')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Green Valley Dairy', res.data)
        self.assertNotIn(b'Blue Ridge Orchards', res.data)

        # Search by City "Kelowna" -> matches Blue Ridge Orchards
        res = self.client.get('/?q=Kelowna')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Blue Ridge Orchards', res.data)
        self.assertNotIn(b'Green Valley Dairy', res.data)


    def test_unauthorized_farm_and_product_access(self):
        # Create user 1 with a farm
        with self.app.app_context():
            u1 = User(username='farmer1', email='f1@farm.ca', is_farmer=True)
            u1.set_password('Pass123!')
            u2 = User(username='farmer2', email='f2@farm.ca', is_farmer=True)
            u2.set_password('Pass123!')
            db.session.add_all([u1, u2])
            db.session.commit()

            farm1 = Farm(
                name='Farmer 1 Farm',
                street_address='123 St',
                city='Barrie',
                province='ON',
                postal_code='L4M 1A1',
                contact_email='f1@farm.ca',
                user_id=u1.id
            )
            db.session.add(farm1)
            db.session.commit()
            f1_id = farm1.id

            prod1 = Product(name='Tomatoes', category='Vegetables', price=Decimal('2.50'), unit='lbs', stock_quantity=10, farm_id=f1_id)
            db.session.add(prod1)
            db.session.commit()
            p1_id = prod1.id

        # Log in as farmer2 and try to edit farmer1's farm
        self.login('farmer2', 'Pass123!')
        res = self.client.post(f'/farm/{f1_id}/edit', data={
            'name': 'Hacked Farm',
            'contact_email': 'f1@farm.ca',
            'street_address': '123 St',
            'city': 'Barrie',
            'province': 'ON',
            'postal_code': 'L4M 1A1',
            'accepts_cash': 'true'
        }, follow_redirects=True)
        self.assertIn(b'Unauthorized', res.data)

        # Try to edit farmer1's product
        res = self.client.post(f'/product/{p1_id}/edit', data={
            'name': 'Hacked Tomatoes',
            'category': 'Vegetables',
            'price': '1.00',
            'unit': 'lbs',
            'stock_quantity': '10'
        }, follow_redirects=True)
        self.assertIn(b'Unauthorized', res.data)

        # Try to delete farmer1's product
        res = self.client.post(f'/product/{p1_id}/delete', follow_redirects=True)
        self.assertIn(b'Unauthorized', res.data)

        # Verify no changes happened
        with self.app.app_context():
            farm = db.session.get(Farm, f1_id)
            self.assertEqual(farm.name, 'Farmer 1 Farm')
            prod = db.session.get(Product, p1_id)
            self.assertEqual(prod.name, 'Tomatoes')


if __name__ == '__main__':
    unittest.main()
