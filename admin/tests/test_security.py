"""Security regressions use temporary data, accounts and an isolated browser."""
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from html.parser import HTMLParser
from PIL import Image
from test_accounts import Client, ROOT


class SecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='zq-security-')
        cls.root = Path(cls.temp.name)
        shutil.copytree(ROOT / 'admin', cls.root / 'admin', ignore=shutil.ignore_patterns('private', 'backups', '__pycache__'))
        shutil.copytree(ROOT / 'src', cls.root / 'src')
        shutil.copy2(ROOT / 'build.py', cls.root / 'build.py')
        shutil.copytree(ROOT / 'assets', cls.root / 'assets', ignore=lambda path, names: [n for n in names if not n.endswith('.json')])
        (cls.root / 'assets' / 'people').mkdir()
        cls.public = cls.root / 'public'
        cls.public.mkdir()
        (cls.public / 'index.html').write_text('previous public site')
        cls.base = 'http://127.0.0.1:8792'
        cls.env = dict(os.environ, ZQ_CMS_PORT='8792', ZQ_CMS_ACCOUNT='qa-admin', ZQ_CMS_PASSWORD='qa-password-123',
                       ZQ_CMS_AUTH_DB=str(cls.root / 'admin/private/accounts.sqlite3'), ZQ_CMS_PUBLIC_ROOT=str(cls.public))
        cls.log = (cls.root / 'server.log').open('w')
        cls.process = subprocess.Popen(['python3', str(cls.root / 'admin/server.py')], env=cls.env, stdout=cls.log, stderr=cls.log)
        for _ in range(100):
            try:
                Client(cls.base).call('session')
                break
            except OSError:
                if cls.process.poll() is not None: raise RuntimeError((cls.root / 'server.log').read_text())
                time.sleep(.1)
        cls.admin = Client(cls.base)
        assert cls.admin.call('login', {'account': 'qa-admin', 'password': 'qa-password-123'})[0] == 200

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait()
        cls.log.close()
        cls.temp.cleanup()

    def save(self, name, data=None):
        status, value = self.admin.call('data/' + name)
        self.assertEqual(status, 200)
        result = self.admin.call('data/' + name, {'data': value['data'] if data is None else data, 'revision': value['revision']})
        self.assertEqual(result[0], 200, result)

    def test_01_draft_is_not_published_until_saved_reference(self):
        image = io.BytesIO()
        Image.new('RGB', (17, 13), '#417baa').save(image, 'PNG')
        status, upload = self.admin.call('upload', {'base64': base64.b64encode(image.getvalue()).decode()})
        self.assertEqual(status, 200)
        key = upload['key']
        private = self.root / 'admin/private/media-drafts'
        variant = json.loads((private / 'manifest.json').read_text())[key]
        saved_manifest = self.root / 'assets/image-variants.json'
        self.assertNotIn(key, json.loads(saved_manifest.read_text()))
        self.assertEqual(Client(self.base).call('media')[0], 401)
        # A leftover dist file from an earlier build must not enter publication.
        stale = self.root / 'dist' / variant['small']
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes((private / variant['small']).read_bytes())
        self.save('site')
        for field in ('small', 'large', 'thumb', 'original'):
            self.assertFalse((self.public / variant[field]).exists())
        self.assertNotIn(key, (self.public / 'index.html').read_text())
        rows = self.admin.call('data/news')[1]['data']
        rows[0]['images'].append(key)
        rows[0]['cover'] = key
        self.save('news', rows)
        self.assertIn(key, json.loads(saved_manifest.read_text()))
        for field in ('small', 'large', 'thumb', 'original'):
            self.assertTrue((self.public / variant[field]).is_file())
        # A later unreferenced historical upload is excluded even if in assets
        # and dist; pre-existing public files are deliberately not deleted.
        legacy_key = 'uploads/unreferenced-historical.webp'
        manifest = json.loads(saved_manifest.read_text())
        legacy = dict(variant, small='web/unreferenced-historical.webp')
        manifest[legacy_key] = legacy
        saved_manifest.write_text(json.dumps(manifest))
        for base in (self.root / 'assets', self.root / 'dist'):
            destination = base / legacy['small']
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'historical fixture')
        (self.public / 'web/preserved-history.webp').write_bytes(b'keep me')
        self.save('site')
        self.assertFalse((self.public / legacy['small']).exists())
        self.assertNotIn(legacy_key, (self.public / 'index.html').read_text())
        self.assertEqual((self.public / 'web/preserved-history.webp').read_bytes(), b'keep me')
        result = subprocess.run(['python3', str(self.root / 'admin/maintenance.py')], env=self.env, cwd=self.root, capture_output=True, text=True, check=True)
        outcome = json.loads(result.stdout.splitlines()[-1])
        self.assertTrue(outcome['protected_unchanged'])
        self.assertTrue(Path(outcome['public_backup']).is_file())

    def browser(self, checks):
        chrome = os.environ.get('ZQ_TEST_CHROME', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if not Path(chrome).is_file(): self.skipTest('Set ZQ_TEST_CHROME to an installed Chromium executable for DOM regression')
        page = self.public / 'dom-regression.html'
        instrumentation = '''<script>
(()=>{
try {
renderProg(''); renderProg('tour');
for(let i=0;i<5;i++){sailIdx=i;renderSails();}
CHECKS
document.body.setAttribute('data-zq-test', JSON.stringify({ok:true,xss:window.__reviewXss||0, home:document.querySelector('#home-feat').textContent,route:document.querySelector('#prog-body').textContent.length}));
} catch(e) {document.body.setAttribute('data-zq-test',JSON.stringify({ok:false,error:String(e)}));}
})();</script>'''.replace('CHECKS', checks)
        page.write_text((self.public / 'index.html').read_text().replace('</body>', instrumentation + '</body>'))
        # On a Mac without a local display Chrome can emit the completed DOM
        # while its display-link process stays alive. Read the DOM file and
        # terminate only our isolated browser process group after completion.
        output_path = self.root / 'browser-dom.txt'
        with output_path.open('w') as output_file, (self.root / 'browser.log').open('w') as log:
            process = subprocess.Popen([chrome, '--headless=new', '--disable-gpu', '--force-prefers-reduced-motion',
                '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
                '--user-data-dir=' + tempfile.mkdtemp(prefix='browser-profile-', dir=self.root),
                '--timeout=10000', '--dump-dom', page.as_uri()], stdout=output_file, stderr=log, start_new_session=True)
            try:
                for _ in range(150):
                    output = output_path.read_text()
                    if 'data-zq-test=' in output and '</html>' in output: break
                    if process.poll() is not None: break
                    time.sleep(.1)
                else: self.fail('Browser did not emit completed DOM')
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
        output = output_path.read_text()
        class Result(HTMLParser):
            value = None
            def handle_starttag(parser, tag, attrs):
                if tag == 'body': parser.value = dict(attrs).get('data-zq-test')
        parser = Result()
        parser.feed(output)
        self.assertIsNotNone(parser.value, 'Browser did not complete DOM checks')
        value = json.loads(parser.value)
        self.assertTrue(value['ok'], value)
        self.assertEqual(value['xss'], 0)
        self.assertGreater(value['route'], 0)
        return value

    def test_02_saved_xss_is_text_in_browser(self):
        payload = '<img src=x onerror="window.__reviewXss=1">'
        site = self.admin.call('data/site')[1]['data']
        for brand in site['brands'].values():
            for field in ('n', 'name', 'tag', 'desc', 'long'): brand[field] = payload
        site['sails'] = [[payload, payload] for _ in range(5)]
        self.save('site', site)
        self.browser('''if(document.querySelector('[onerror]'))throw Error('injected attribute');
if(!document.querySelector('#prog-body').textContent.includes('<img src=x'))throw Error('editable text lost');
if(!document.querySelector('#sail-txt').textContent.includes('<img src=x'))throw Error('sail text lost');''')
        site['brands']['tour']['cls'] = 'b1" onmouseover="window.__reviewXss=1'
        revision = self.admin.call('data/site')[1]['revision']
        self.assertEqual(self.admin.call('data/site', {'data': site, 'revision': revision})[0], 400)

    def test_03_empty_and_media_only_pages_work(self):
        rows = self.admin.call('data/news')[1]['data']
        for rows in ([r for r in rows if r['category'] == 'media'], []):
            self.save('news', rows)
            self.assertIn('暫無活動消息', self.browser('')['home'])

    def test_04_editor_success_cannot_reset_admin_or_ip_budget(self):
        token = self.admin.call('invites', {})[1]['token']
        guest = Client(self.base)
        self.assertEqual(guest.call('register', {'token': token, 'phone': '87654321', 'password': 'editor-123'})[0], 200)
        for _ in range(29):
            self.assertEqual(guest.call('login', {'account': 'qa-admin', 'password': 'wrong'})[0], 401)
        self.assertEqual(guest.call('login', {'account': '87654321', 'password': 'editor-123'})[0], 200)
        self.assertEqual(guest.call('login', {'account': 'qa-admin', 'password': 'wrong'})[0], 401)
        self.assertEqual(guest.call('login', {'account': 'qa-admin', 'password': 'wrong'})[0], 429)
        status = None
        for i in range(130):
            status = Client(self.base).call('login', {'account': 'other-' + str(i), 'password': 'wrong'})[0]
            if status == 429: break
        self.assertEqual(status, 429)
        self.assertEqual(guest.call('login', {'account': '87654321', 'password': 'editor-123'})[0], 429)


class InitializationTest(unittest.TestCase):
    def test_password_boundaries_and_existing_account_preserved(self):
        spec = importlib.util.spec_from_file_location('isolated_auth', ROOT / 'admin/auth.py')
        auth = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(auth)
        with tempfile.TemporaryDirectory(prefix='zq-init-') as directory:
            for n in (0, 1, 11, 1025):
                auth.DB = Path(directory) / ('bad-' + str(n) + '.sqlite3')
                with self.assertRaises(RuntimeError): auth.initialize('qa', 'a' * n)
                with auth.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 0)
            for n in (12, 1024):
                auth.DB = Path(directory) / ('good-' + str(n) + '.sqlite3')
                auth.initialize('qa', 'a' * n)
                before = auth.DB.read_bytes()
                auth.initialize('changed', 'x')
                self.assertEqual(auth.DB.read_bytes(), before)


if __name__ == '__main__': unittest.main()
