import os, sys, tempfile, re, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DEV_MODE'] = '1'
os.environ['DATABASE_PATH'] = os.path.join(tempfile.mkdtemp(), 'x.db')
os.environ['SECRET_KEY'] = 't'
from app import create_app

app = create_app()
app.config['TESTING'] = True
c = app.test_client()

page = c.get('/register').get_data(as_text=True)
csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
c.post('/register', data={'phone': '09123456700', 'csrf': csrf})
page = c.get('/register/otp').get_data(as_text=True)
m = re.search(r'کد آزمایشی:\s*<strong>(\d{6})</strong>', page)
print('dev code found:', bool(m), m.group(1) if m else '')
idx = page.find('dev-note')
print('snippet:', re.sub(r'\s+', ' ', page[idx:idx+120]) if idx >= 0 else 'NOT FOUND')
