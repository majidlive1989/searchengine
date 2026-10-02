"""Local configuration and bounded native REST integrations; no free-form code execution."""
import asyncio, ipaddress, json, os, re, socket
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone
from typing import Literal, Any
import httpx
from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, model_validator
from . import db
from .models import Strict, Rate, ExecutionResult

class IntegrationError(Exception):
    def __init__(self, code): self.code=code; super().__init__(code)


def vault():
    path=Path(os.getenv('ATLAS_VAULT_KEY_FILE', str(Path(db.DB_PATH).resolve().parent/'vault.key')))
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
        except FileExistsError:pass
    return Fernet(path.read_bytes().strip())


def secret_put(c,tenant,name,value):
    id='secret_'+tenant+'_'+name
    db.save(c,tenant,'secret',{'id':id,'ciphertext':vault().encrypt(value.encode()).decode()})


def secret_get(tenant,name):
    with db.connect() as c:
        row=c.execute("SELECT body FROM objects WHERE tenant=? AND kind='secret' AND id=?",(tenant,'secret_'+tenant+'_'+name)).fetchone()
    if not row:return ''
    return vault().decrypt(json.loads(row[0])['ciphertext'].encode()).decode()


def ai_config(tenant):
    with db.connect() as c:
        row=c.execute("SELECT body FROM objects WHERE tenant=? AND kind='settings' AND id=?",(tenant,'ai_'+tenant)).fetchone()
    if row:
        obj=json.loads(row[0]);return {'enabled':obj['enabled'],'model':obj['model'],'key':secret_get(tenant,'gemini')}
    return {'enabled':bool(os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_MODEL')),'model':os.getenv('GEMINI_MODEL',''),'key':os.getenv('GEMINI_API_KEY','')}

class AISettings(Strict):
    enabled: bool = False
    model: str = Field(default='',max_length=100,pattern=r'^[a-zA-Z0-9_.-]*$')
    api_key: SecretStr | None = None
    clear_key: bool = False

class APIConfig(Strict):
    endpoint: str = Field(min_length=8,max_length=2000)
    method: Literal['GET','POST'] = 'POST'
    auth_type: Literal['NONE','BEARER','HEADER'] = 'BEARER'
    auth_header: str = Field(default='X-API-Key',max_length=60,pattern=r'^[A-Za-z0-9-]+$')
    request_template: dict[str,Any] = Field(default_factory=dict)
    records_path: str = Field(default='results',max_length=200)
    field_map: dict[str,str] = Field(default_factory=dict)
    static_fields: dict[str,Any] = Field(default_factory=dict)
    context_fields: list[str] = Field(default_factory=list,max_length=8)
    ttl_minutes: int = Field(default=5,ge=1,le=15)
    authorized_search_only: bool = False
    scope_confirmed: bool = False

    @model_validator(mode='after')
    def validate_config(self):
        validate_url(self.endpoint,resolve=False)
        if self.auth_header.lower() in {'host','cookie','content-length','connection','transfer-encoding','proxy-authorization'}:raise ValueError('Unsupported authentication header')
        valid=set(Rate.model_fields)-{'demo','kind','captured_at','expires_at'}
        if not set(self.field_map)<=valid:raise ValueError('Unknown mapped field')
        if not set(self.static_fields)<={'currency','price_basis','stops','stars','cabin','rooms'}:raise ValueError('Price, identity and cancellation policy cannot be static')
        if not set(self.context_fields)<={'origin','destination','departure_date','return_date','adults','rooms','cabin'}:raise ValueError('Invalid context field')
        if self.context_fields and not self.scope_confirmed:raise ValueError('Confirm that response rows match requested dates, route and party')
        for path in [self.records_path,*self.field_map.values()]:
            if not re.fullmatch(r'[A-Za-z0-9_.-]*',path):raise ValueError('Use dot-separated JSON keys and numeric array indexes')
        if len(json.dumps(self.request_template))>16000:raise ValueError('Request template too large')
        if not self.authorized_search_only:raise ValueError('Confirm authorized search-only endpoint')
        if not {'net_price','external_id','title','details','cancellation_policy'}<=set(self.field_map):raise ValueError('Map price, ID, title, details and cancellation policy from the supplier')
        for field in valid-{'origin'}:
            if field not in self.field_map and field not in self.static_fields and field not in self.context_fields:raise ValueError('Missing mapping for '+field)
        return self

class APIConfigIn(Strict):
    config: APIConfig
    credential: SecretStr | None = None
    clear_credential: bool = False
    notes: str = Field(default='',max_length=1000)

class ManualSourceIn(Strict):
    website_url: str = Field(min_length=8,max_length=2000)
    authorized: bool
    notes: str = Field(default='',max_length=1000)

class ManualRateIn(Strict):
    source_id: str
    title: str = Field(min_length=1,max_length=200)
    external_id: str = Field(min_length=1,max_length=200)
    net_price: str = Field(min_length=1,max_length=30)
    currency: Literal['USD','EUR','AED','OMR','IRR','GBP']
    details: str = Field(min_length=1,max_length=1000)
    cancellation_policy: str = Field(min_length=1,max_length=2000)
    stops: int = Field(default=0,ge=0,le=5)
    stars: int = Field(default=4,ge=0,le=5)
    ttl_minutes: int = Field(default=5,ge=1,le=15)

class ManualRatesIn(Strict):
    revision: int
    reviewed: bool
    items: list[ManualRateIn] = Field(min_length=1,max_length=10)


def validate_url(value,resolve=True):
    try:
        p=urlsplit(value)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment or p.query or p.port not in {None,443}:raise ValueError()
        host=p.hostname.encode('idna').decode()
        if host.lower()=='localhost' or host.endswith('.local'):raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global:raise ValueError()
        except ValueError:
            # A non-IP hostname is permitted; invalid/private IPs are rejected below.
            if re.fullmatch(r'[0-9.:]+',host) or ':' in host:raise ValueError()
        if resolve:
            addresses={info[4][0] for info in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
            if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):raise ValueError()
            return host,sorted(addresses)[0]
        return host,None
    except (ValueError,OSError,UnicodeError):raise IntegrationError('PUBLIC_HTTPS_URL_REQUIRED')


def at_path(obj,path):
    if not path:return obj
    for piece in path.split('.'):
        obj=obj[int(piece)] if isinstance(obj,list) and piece.isdigit() else obj[piece]
    return obj


def render_template(value,spec):
    if isinstance(value,dict):return {k:render_template(v,spec) for k,v in value.items()}
    if isinstance(value,list):return [render_template(v,spec) for v in value]
    if not isinstance(value,str):return value
    match=re.fullmatch(r'\{\{([a-z_]+)\}\}',value)
    if match:
        if match[1] not in spec:raise IntegrationError('UNKNOWN_TEMPLATE_FIELD')
        return spec[match[1]]
    if '{{' in value or '}}' in value:raise IntegrationError('USE_WHOLE_VALUE_TEMPLATES')
    return value


def normalize_rows(payload,config,job):
    cfg=APIConfig.model_validate(config);rows=at_path(payload,cfg.records_path)
    if not isinstance(rows,list) or len(rows)>100:raise IntegrationError('RESULTS_MUST_BE_ARRAY_MAX_100')
    rates=[];captured=datetime.now(timezone.utc)
    for row in rows:
        values=dict(cfg.static_fields)
        values.update({k:job['input'][k] for k in cfg.context_fields})
        for field,path in cfg.field_map.items():values[field]=at_path(row,path)
        values.update(kind=job['kind'],demo=False,captured_at=captured,expires_at=captured+timedelta(minutes=cfg.ttl_minutes))
        if job['kind']=='HOTEL':values['origin']=''
        rates.append(Rate.model_validate(values))
    return ExecutionResult(job_id=job['job_id'],status='SUCCESS',records=rates)


async def fetch_api(config,spec,credential):
    cfg=APIConfig.model_validate(config)
    host,address=await asyncio.to_thread(validate_url,cfg.endpoint)
    # Pin the resolved public IP and preserve TLS hostname; no DNS rebinding between validation and connection.
    target=httpx.URL(cfg.endpoint).copy_with(host=address)
    headers={'Host':host,'Accept':'application/json'}
    if cfg.auth_type!='NONE':
        if not credential:raise IntegrationError('CREDENTIAL_REQUIRED')
        if '\n' in credential or '\r' in credential:raise IntegrationError('INVALID_CREDENTIAL')
        headers['Authorization' if cfg.auth_type=='BEARER' else cfg.auth_header]=('Bearer ' if cfg.auth_type=='BEARER' else '')+credential
    params=render_template(cfg.request_template,spec)
    if cfg.method=='GET' and any(isinstance(v,(dict,list)) for v in params.values()):raise IntegrationError('GET_REQUIRES_FLAT_QUERY')
    async with httpx.AsyncClient(timeout=25,follow_redirects=False,trust_env=False) as client:
        async with client.stream(cfg.method,target,headers=headers,params=params if cfg.method=='GET' else None,json=params if cfg.method=='POST' else None,extensions={'sni_hostname':host}) as response:
            if response.status_code in {401,403}:raise IntegrationError('LOGIN_REQUIRED')
            if 300<=response.status_code<400:raise IntegrationError('REDIRECT_NOT_ALLOWED')
            if response.status_code>=400:raise IntegrationError('SUPPLIER_HTTP_'+str(response.status_code))
            chunks=[];size=0
            async for chunk in response.aiter_bytes():
                size+=len(chunk)
                if size>1_000_000:raise IntegrationError('OUTPUT_TOO_LARGE')
                chunks.append(chunk)
    return json.loads(b''.join(chunks))

class NativeAPIExecution:
    async def execute(self,job):
        with db.connect() as c:
            source=db.get(c,job['tenant_id'],'source',job['source_id'])
            version=next(v for v in source['versions'] if v['version']==job['workflow_version'])
        config=version.get('api_config')
        if not config:raise IntegrationError('CONFIGURE_API_FIRST')
        token=secret_get(job['tenant_id'],'source_'+job['source_id'])
        try:
            payload=await fetch_api(config,job['input'],token)
            return normalize_rows(payload,config,job)
        except IntegrationError as e:
            return ExecutionResult(job_id=job['job_id'],status='RECONNECT_REQUIRED' if e.code=='LOGIN_REQUIRED' else 'FAILED',error_code=e.code)
