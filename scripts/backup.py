"""Consistent SQLite backup, including the optional local vault key sidecar."""
import argparse,hashlib,os,sqlite3
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--database',default='data/copilot.db');p.add_argument('--output',required=True);p.add_argument('--key-file');a=p.parse_args()
source=Path(a.database).resolve();dest=Path(a.output).resolve()
key=Path(a.key_file or os.getenv('ATLAS_VAULT_KEY_FILE',str(source.parent/'vault.key')))
key_out=dest.with_suffix(dest.suffix+'.vault-key')
if not source.is_file():raise SystemExit('Database not found')
if any(x.exists() for x in [dest,dest.with_suffix(dest.suffix+'.sha256'),key_out,key_out.with_suffix(key_out.suffix+'.sha256')]):raise SystemExit('Refusing to overwrite backup files')
dest.parent.mkdir(parents=True,exist_ok=True)
with sqlite3.connect('file:'+source.as_posix()+'?mode=ro',uri=True) as src,sqlite3.connect(dest) as dst:
    src.backup(dst)
    if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Backup integrity check failed')
    has_secrets=dst.execute("SELECT count(*) FROM objects WHERE kind='secret'").fetchone()[0]>0
if has_secrets:
    if not key.is_file():
        dest.unlink();raise SystemExit('Vault key missing. Restore the key before backing up encrypted credentials.')
    key_out.write_bytes(key.read_bytes())
    key_out.with_suffix(key_out.suffix+'.sha256').write_text(hashlib.sha256(key_out.read_bytes()).hexdigest()+'\n')
for file in [dest]+([key_out] if has_secrets else []):
    try:file.chmod(0o600)
    except OSError:pass
dest.with_suffix(dest.suffix+'.sha256').write_text(hashlib.sha256(dest.read_bytes()).hexdigest()+'\n')
print('Backup complete:',dest)
print('Vault key included:',has_secrets)
print('Store ALL sidecars together on encrypted, access-controlled storage. The archive is not encrypted by this script.')
