import os, sys, tempfile, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DEV_MODE'] = '1'
os.environ['SECRET_KEY'] = 't'
from app import create_app
from app.services import booking
from app import db

app = create_app(database_path=os.path.join(tempfile.mkdtemp(), 'x.db'))
app.config['TESTING'] = True

with app.app_context():
    from app import db as db_module
    dates = booking.booking_dates()
    target = dates[5]
    print('target date:', target)

c = app.test_client()

# Admin login
page = c.get('/admin/login').get_data(as_text=True)
m = re.search(r'name="csrf" value="([^"]+)"', page)
csrf = m.group(1)
r = c.post('/admin/login', data={'password': 'admin1234', 'csrf': csrf})
print('login:', r.status_code, r.headers.get('Location'))

# Set day to close
with app.app_context():
    from app.services import booking
    dates = booking.booking_dates()
    target = dates[5]
    print('target date:', target)

page = c.get('/admin/availability').get_data(as_text=True)
m = re.search(r'name="csrf" value="([^"]+)"', page)
csrf_admin = m.group(1)
print('csrf_admin:', csrf_admin)

r = c.post('/admin/availability/day', data={'date': target, 'mode': 'close', 'csrf': csrf_admin})
print('set_day:', r.status_code, r.headers.get('Location'))

# Check if slots are disabled
with app.app_context():
    conn = db.connect(app.config['DATABASE_PATH'])
    for idx in range(3):
        active = booking.is_slot_active(conn, target, idx)
        print(f'slot {idx} active:', active)
    conn.close()