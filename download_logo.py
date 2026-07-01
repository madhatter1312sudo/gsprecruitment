#!/usr/bin/env python3
"""Download GSP logo from Gmail attachments"""
import json, urllib.request, urllib.parse, base64, os, sys

# Read from .env - more reliable than hardcoding
env_path = os.path.expanduser("/home/og/projects/gsp-recruitment/talent-os/.env")
env = {}
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k] = v

CLIENT_ID = env.get('GOOGLE_CLIENT_ID', '').strip()
CLIENT_SECRET = env.get('GOOGLE_CLIENT_SECRET', '').strip()
REFRESH_TOKEN = env.get('GOOGLE_REFRESH_TOKEN', '').strip()

print(f"CLIENT_ID: {CLIENT_ID[:30]}...")
print(f"CLIENT_SECRET: {CLIENT_SECRET[:10]}...")
print(f"REFRESH_TOKEN: {REFRESH_TOKEN[:20]}...")

if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    print("❌ Missing credentials")
    sys.exit(1)

# Get access token
data = urllib.parse.urlencode({
    'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
    'refresh_token': REFRESH_TOKEN, 'grant_type': 'refresh_token'
}).encode()
req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
token = json.loads(urllib.request.urlopen(req).read())['access_token']
headers = {'Authorization': f'Bearer {token}'}
print("✅ Access token obtained")

logo_dir = "/home/og/projects/gsp-recruitment/website/assets"
os.makedirs(logo_dir, exist_ok=True)

def save_attachment(msg_id, att_id, filename, path):
    att_req = urllib.request.Request(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/attachments/{att_id}", headers=headers)
    att_data = json.loads(urllib.request.urlopen(att_req).read())
    b64data = att_data.get('data', '')
    if b64data:
        file_bytes = base64.urlsafe_b64decode(b64data + '==')
        with open(path, 'wb') as f:
            f.write(file_bytes)
        return len(file_bytes)
    return 0

# 1. Get the Logo_file.eps from spganesh
print("\n--- Searching for GSP Logo from spganesh ---")
params = urllib.parse.urlencode({'maxResults': 5, 'q': 'from:spganesh@gsprecruitment.nl has:attachment Logo_file'})
req = urllib.request.Request(f'https://gmail.googleapis.com/gmail/v1/users/me/messages?{params}', headers=headers)
resp = json.loads(urllib.request.urlopen(req).read())

if resp.get('messages'):
    msg_id = resp['messages'][0]['id']
    req = urllib.request.Request(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=full", headers=headers)
    msg = json.loads(urllib.request.urlopen(req).read())
    
    hdrs = msg.get('payload', {}).get('headers', [])
    subj = next((h['value'] for h in hdrs if h['name'] == 'Subject'), '(no subject)')
    date = next((h['value'] for h in hdrs if h['name'] == 'Date'), '?')
    print(f"Email: {subj} - {date}")
    
    parts = msg.get('payload', {}).get('parts', [])
    for p in parts:
        fn = p.get('filename', '')
        if fn and p.get('body', {}).get('attachmentId'):
            clean_fn = fn.replace(' ', '_')
            path = os.path.join(logo_dir, clean_fn)
            size = save_attachment(msg_id, p['body']['attachmentId'], fn, path)
            print(f"  ✅ Saved: {path} ({size} bytes)")
else:
    print("❌ No email found from spganesh with Logo_file.eps")

# 2. Also get the "Logo sr engineering" email with all variants
print("\n--- Searching for 'Logo sr engineering' email ---")
params2 = urllib.parse.urlencode({'maxResults': 5, 'q': '"Logo sr engineering"'})
req2 = urllib.request.Request(f'https://gmail.googleapis.com/gmail/v1/users/me/messages?{params2}', headers=headers)
resp2 = json.loads(urllib.request.urlopen(req2).read())

if resp2.get('messages'):
    msg_id2 = resp2['messages'][0]['id']
    req2 = urllib.request.Request(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id2}?format=full", headers=headers)
    msg2 = json.loads(urllib.request.urlopen(req2).read())
    
    hdrs2 = msg2.get('payload', {}).get('headers', [])
    subj2 = next((h['value'] for h in hdrs2 if h['name'] == 'Subject'), '(no subject)')
    sender2 = next((h['value'] for h in hdrs2 if h['name'] == 'From'), '?')
    print(f"Email: {subj2} - From: {sender2}")
    
    def walk_parts(parts_list):
        count = 0
        for p in parts_list:
            fn = p.get('filename', '')
            if fn and p.get('body', {}).get('attachmentId'):
                clean_fn = fn.replace(' ', '_').replace('(', '').replace(')', '')
                path = os.path.join(logo_dir, clean_fn)
                size = save_attachment(msg_id2, p['body']['attachmentId'], fn, path)
                print(f"  ✅ Saved: {path} ({size} bytes)")
                count += 1
            if p.get('parts'):
                count += walk_parts(p['parts'])
        return count
    
    walk_parts(msg2.get('payload', {}).get('parts', []))
else:
    print("❌ No 'Logo sr engineering' email found")

print(f"\n\n📁 All logo files in {logo_dir}/:")
for f in sorted(os.listdir(logo_dir)):
    fp = os.path.join(logo_dir, f)
    size = os.path.getsize(fp)
    print(f"  {f:55s} {size:>8} bytes")