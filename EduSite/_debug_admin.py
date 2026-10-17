import os, sys, tempfile, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DEV_MODE'] = '1'
os.environ['SECRET_KEY'] = 't'
from app import create_app

app = create_app(database_path=os.path.join(tempfile.mkdtemp(), 'x.db'))
app.config['TESTING'] = True
c = app.test_client()
page = c.get('/admin/login').get_data(as_text=True)
m = re.search(r'name="csrf" value="([^"]+)"', page)
print('admin login page has csrf:', bool(m))
if m:
    print('csrf:', m.group(1))
    r = c.post('/admin/login', data={'password': 'admin1234', 'csrf': m.group(1)})
    print('login status:', r.status_code, r.headers.get('Location'))
    page = c.get('/admin/availability').get_data(as_text=True)
    m2 = re.search(r'name="csrf" value="([^"]+)"', page)
    print('availability page has csrf:', bool(m2))
    if m2:
        print('csrf:', m2.group(1))