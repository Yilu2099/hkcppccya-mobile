"""Run against an isolated copy of the CMS; never touches production data."""
import concurrent.futures
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


class Client:
    def __init__(self, base):
        self.base, self.csrf = base, ''
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, body=None, csrf=None):
        req = urllib.request.Request(self.base + '/cms/api/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json', 'X-CSRF': self.csrf if csrf is None else csrf})
        try:
            with self.opener.open(req) as r: status, value = r.status, json.load(r)
        except urllib.error.HTTPError as error:
            status, value = error.code, json.load(error)
        if status == 200 and isinstance(value, dict) and value.get('csrf'): self.csrf = value['csrf']
        return status, value


class AccountsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='zq-account-test-')
        cls.root = Path(cls.temp.name)
        shutil.copytree(ROOT/'admin', cls.root/'admin', ignore=shutil.ignore_patterns('private','backups','__pycache__'))
        shutil.copytree(ROOT/'assets', cls.root/'assets', ignore=lambda path,names:[n for n in names if not n.endswith('.json')])
        cls.base = 'http://127.0.0.1:8791'
        cls.env = dict(os.environ, ZQ_CMS_PORT='8791', ZQ_CMS_ACCOUNT='qa-admin', ZQ_CMS_PASSWORD='qa-password-123', ZQ_CMS_AUTH_DB=str(cls.root/'admin/private/accounts.sqlite3'))
        cls.process = subprocess.Popen(['python3',str(cls.root/'admin/server.py')],env=cls.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                Client(cls.base).call('session');break
            except OSError: time.sleep(.1)

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait();cls.temp.cleanup()

    def test_complete_flow(self):
        admin = Client(self.base)
        self.assertEqual(admin.call('login',{'password':'qa-password-123'})[0],401)
        self.assertEqual(admin.call('login',{'account':'qa-admin','password':'wrong'})[0],401)
        self.assertEqual(admin.call('login',{'account':'qa-admin','password':'qa-password-123'})[0],200)
        self.assertEqual(admin.call('session')[1]['user']['role'],'admin')
        self.assertEqual(admin.call('invites',{},csrf='bad')[0],403)
        token=admin.call('invites',{})[1]['token']
        guest=Client(self.base)
        self.assertEqual(guest.call('invites',{})[0],401)
        self.assertEqual(guest.call('invite-check',{'token':token})[0],200)
        for phone,password in [('1234567','12345678'),('123456789','12345678'),('abcdefgh','12345678'),('１２３４５６７８','12345678'),('12345678','1234567')]:
            self.assertEqual(guest.call('register',{'token':token,'phone':phone,'password':password})[0],400)
        self.assertEqual(guest.call('register',{'token':token,'phone':'12345678','password':'12345678','role':'admin'})[0],200)
        self.assertEqual(guest.call('session')[1]['user']['role'],'editor')
        self.assertEqual(guest.call('data/news')[0],200)
        self.assertEqual(guest.call('invites')[0],403)
        self.assertEqual(guest.call('invites',{})[0],403)
        self.assertEqual(guest.call('invite-check',{'token':token})[0],400)
        self.assertEqual(guest.call('logout',{})[0],200)
        self.assertEqual(guest.call('session')[1]['loggedIn'],False)
        self.assertEqual(guest.call('login',{'account':'12345678','password':'12345678'})[0],200)
        other=admin.call('invites',{})[1]
        self.assertEqual(guest.call('register',{'token':other['token'],'phone':'12345678','password':'12345678'})[0],400)
        self.assertEqual(guest.call('invite-check',{'token':other['token']})[0],200)
        self.assertEqual(guest.call('register',{'token':other['token'],'phone':'13800138000','password':'abcdefgh'})[0],200)
        cancelled=admin.call('invites',{})[1]
        admin.call('invites/revoke',{'id':cancelled['id']})
        self.assertEqual(guest.call('register',{'token':cancelled['token'],'phone':'87654321','password':'12345678'})[0],400)
        race=admin.call('invites',{})[1]
        def register(phone): return Client(self.base).call('register',{'token':race['token'],'phone':phone,'password':'12345678'})[0]
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(register,['87654321','87654322'])),[200,400])
        import sqlite3
        with sqlite3.connect(self.env['ZQ_CMS_AUTH_DB']) as db:
            expired=admin.call('invites',{})[1]
            db.execute('UPDATE invites SET expires=0 WHERE id=?',(expired['id'],))
        self.assertEqual(guest.call('invite-check',{'token':expired['token']})[0],400)
        # Restart must preserve identities and valid sessions.
        self.process.terminate();self.process.wait()
        type(self).process=subprocess.Popen(['python3',str(self.root/'admin/server.py')],env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                status,session=guest.call('session');break
            except OSError:time.sleep(.1)
        self.assertTrue(session['loggedIn'])
        with sqlite3.connect(self.env['ZQ_CMS_AUTH_DB']) as db:
            stored=db.execute('SELECT password FROM users').fetchall()
            self.assertTrue(all(':' in row[0] and len(row[0])==97 for row in stored))


if __name__=='__main__':unittest.main()
