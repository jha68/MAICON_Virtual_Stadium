"""Decrypt the authenticated bootstrap without exposing values to logs."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--encrypted', required=True)
    parser.add_argument('--private-key', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    key = Path(args.private_key)
    if key.stat().st_mode & 0o077:
        raise ValueError('The session private key must have mode0600')
    result = subprocess.run(['openssl','cms','-decrypt','-binary','-inform','DER','-in',args.encrypted,
                             '-recip',str(root/'session-cert.pem'),'-inkey',str(key)],
                            check=True, capture_output=True)
    credentials = json.loads(result.stdout)
    settings = json.loads((root/'session.json').read_text())
    if credentials.get('session_id') != settings['session_id'] or credentials.get('domain') != settings['domain']:
        raise ValueError('Encrypted bootstrap belongs to a different session')
    if len(credentials.get('password','')) < 10 or len(credentials.get('token','')) < 32:
        raise ValueError('Invalid encrypted credentials')
    out = Path(args.out)
    out.mkdir(parents=True,mode=0o700,exist_ok=True)
    out.chmod(0o700)
    for name, value in [('credentials.json',json.dumps(credentials)), ('web.password',credentials['password']+'\n')]:
        path = out/name
        if path.exists():
            if path.read_text() != value:
                raise ValueError('Refusing to replace existing session credentials')
        else:
            fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as handle:
                handle.write(value)
    print('Existing operator password and relay credentials prepared in private files.')


if __name__ == '__main__':
    main()
