"""Offline restore to a new path only, including credential key and session revocation."""
import argparse,hashlib,os,sqlite3
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--backup',required=True);p.add_argument('--output',required=True);p.add_argument('--key-file');a=p.parse_args()
source=Path(a.backup).resolve();target=Path(a.output).resolve()
key=source.with_suffix(source.suffix+'.vault-key');key_target=Path(a.key_file or os.getenv('ATLAS_VAULT_KEY_FILE',str(target.parent/'vault.key')))
def checksum(file):
    sidecar=file.with_suffix(file.suffix+'.sha256')
    if not file.is_file() or not sidecar.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=sidecar.read_text().strip():raise SystemExit('Missing or invalid checksum for '+str(file))
if target.exists():raise SystemExit('Target exists. Restore requires a new database path.')
checksum(source)
with sqlite3.connect('file:'+source.as_posix()+'?mode=ro',uri=True) as src:
    if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Backup corrupt')
    has_secrets=src.execute("SELECT count(*) FROM objects WHERE kind='secret'").fetchone()[0]>0
    if has_secrets:
        checksum(key)
        if key_target.exists() and key_target.read_bytes()!=key.read_bytes():raise SystemExit('Different vault key exists. Restore into a separate folder; never overwrite an installation key.')
    target.parent.mkdir(parents=True,exist_ok=True)
    if has_secrets and not key_target.exists():
        key_target.parent.mkdir(parents=True,exist_ok=True)
        with open(key_target,'xb') as f:f.write(key.read_bytes())
        try:key_target.chmod(0o600)
        except OSError:pass
    with sqlite3.connect(target) as dst:
        src.backup(dst);dst.execute('DELETE FROM sessions');dst.commit()
try:target.chmod(0o600)
except OSError:pass
print('Restored:',target)
print('Stop the server before switching DATABASE_PATH. Sessions were revoked. Preserve the vault key.')
