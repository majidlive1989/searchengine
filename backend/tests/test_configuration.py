import asyncio,json,socket,sqlite3,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pytest
from test_workflows import client,post,spec,create,draft
from app import db,integrations,main
from app.integrations import APIConfig,IntegrationError,secret_get,ai_config,validate_url,render_template,normalize_rows


def config(kind='FLIGHT'):
    return {'endpoint':'https://supplier.example.com/search','method':'POST','auth_type':'BEARER','auth_header':'X-API-Key','request_template':{'from':'{{origin}}','to':'{{destination}}','pax':'{{adults}}'},'records_path':'results','field_map':{'external_id':'id','title':'name','net_price':'price','currency':'currency','details':'details','cancellation_policy':'policy',**({'stops':'stops'} if kind=='FLIGHT' else {'stars':'stars'})},'static_fields':{'price_basis':'TOTAL_PARTY_STAY_TAX_INCLUDED',**({'stars':0} if kind=='FLIGHT' else {'stops':0})},'context_fields':['origin','destination','departure_date','return_date','adults','rooms','cabin'],'ttl_minutes':5,'authorized_search_only':True,'scope_confirmed':True}

def native_source(client,kind='FLIGHT'):
    source=post(client,'/sources',{'name':'Configurable '+kind,'kind':kind,'provider':'JSON_API'}).json()
    r=client.put('/api/sources/'+source['id']+'/api-config',json={'config':config(kind),'credential':'private-supplier-token'})
    assert r.status_code==200,r.text
    return source

def test_ai_settings_encrypted_redacted_and_clear(client):
    r=client.put('/api/settings/ai',json={'enabled':True,'model':'gemini-test-model','api_key':'private-test-key'})
    assert r.status_code==200 and r.json()['has_key']
    assert 'private-test-key' not in r.text
    assert client.get('/api/settings').json()['ai_provider']=='GEMINI'
    assert ai_config('agency')['key']=='private-test-key'
    with db.connect() as c:
        assert 'private-test-key' not in str([tuple(row) for row in c.execute('SELECT * FROM objects')])
        assert 'private-test-key' not in str([tuple(row) for row in c.execute('SELECT * FROM audit')])
    assert client.put('/api/settings/ai',json={'enabled':False,'model':'gemini-test-model'}).status_code==200
    assert client.get('/api/settings').json()['ai_provider']=='OFFLINE_RULES'
    assert ai_config('agency')['key']=='private-test-key'
    assert client.put('/api/settings/ai',json={'enabled':False,'model':'','clear_key':True}).json()['has_key'] is False

def test_ai_enabled_requires_key(client):
    assert client.put('/api/settings/ai',json={'enabled':True,'model':'model'}).status_code==422

def test_native_api_config_versions_and_secret(client):
    source=native_source(client);id=source['id']
    data=client.get('/api/sources/'+id+'/api-config').json();assert data['version']==2 and data['has_credential']
    assert secret_get('agency','source_'+id)=='private-supplier-token'
    assert 'private-supplier-token' not in client.get('/api/sources').text
    changed=config();changed['endpoint']='https://different.example.com/search'
    assert client.put('/api/sources/'+id+'/api-config',json={'config':changed}).status_code==409
    assert post(client,'/sources/'+id+'/activate').status_code==409

def test_source_api_end_to_end_mocked_supplier(client,monkeypatch):
    async def fake_fetch(cfg,inp,credential):
        assert credential=='private-supplier-token'
        return {'results':[{'id':'fare-001','name':'Verified fixture airline','price':'123.45','currency':'USD','details':'Supplier-provided itinerary','policy':'Supplier-provided terms','stops':0}]}
    monkeypatch.setattr(integrations,'fetch_api',fake_fetch)
    source=native_source(client)
    for pax in [1,2,3]:
        r=post(client,'/sources/'+source['id']+'/test',{'spec':spec(intent='FLIGHT_SEARCH',adults=pax)})
        assert r.json()['success'],r.text
    assert post(client,'/sources/'+source['id']+'/activate').status_code==200
    req=post(client,'/requests',{'customer_name':'Live contract fixture','spec':spec(intent='FLIGHT_SEARCH')}).json()
    post(client,'/requests/'+req['id']+'/confirm',{'spec':req['spec'],'revision':1})
    r=post(client,'/requests/'+req['id']+'/search-runs',{'source_ids':[source['id']]});assert r.status_code==200,r.text
    import time
    for _ in range(100):
        d=client.get('/api/requests/'+req['id']).json()
        if d['status']!='SEARCHING':break
        time.sleep(.02)
    assert d['status']=='RESULTS_READY';assert d['results'][0]['net_price']=='123.45';assert not d['results'][0]['demo']
    offer=post(client,'/offers',{'request_id':req['id'],'result_ids':[d['results'][0]['id']],'markup':'10'}).json()
    assert offer['total']=='135.80'
    assert post(client,'/offers/'+offer['id']+'/approve').status_code==200

def test_native_missing_price_fails_closed(client,monkeypatch):
    async def fake(*args):return {'results':[{'id':'x','name':'bad response'}]}
    monkeypatch.setattr(integrations,'fetch_api',fake)
    source=native_source(client)
    assert post(client,'/sources/'+source['id']+'/test',{'spec':spec(intent='FLIGHT_SEARCH')}).json()['success'] is False

def test_api_mapping_cannot_hardcode_price_or_skip_attestation():
    cfg=config();cfg['static_fields']['net_price']='99'
    with pytest.raises(ValueError):APIConfig.model_validate(cfg)
    cfg=config();cfg['authorized_search_only']=False
    with pytest.raises(ValueError):APIConfig.model_validate(cfg)
    cfg=config();cfg['scope_confirmed']=False
    with pytest.raises(ValueError):APIConfig.model_validate(cfg)

def test_ssrf_url_and_dns_restrictions(monkeypatch):
    for url in ['http://example.com/search','https://localhost/search','https://127.0.0.1/search','https://169.254.169.254/latest','https://[::1]/','https://user:pass@example.com/','https://example.com:9000/','https://example.com/?key=secret']:
        with pytest.raises(IntegrationError):validate_url(url,resolve=False)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))])
    with pytest.raises(IntegrationError):validate_url('https://supplier.example.com/search')

def test_request_template_typed_and_no_arbitrary_code():
    assert render_template({'pax':'{{adults}}'},spec())=={'pax':2}
    with pytest.raises(IntegrationError):render_template('{{password}}',spec())
    with pytest.raises(IntegrationError):render_template('prefix {{origin}}',spec())

def manual_source(client,kind):
    source=post(client,'/sources',{'name':'Manual '+kind,'kind':kind,'provider':'MANUAL'}).json()
    r=client.put('/api/sources/'+source['id']+'/manual-config',json={'website_url':'https://supplier.example.com','authorized':True})
    assert r.status_code==200,r.text
    return source

def manual_item(source):
    return {'source_id':source['id'],'title':'Agent-verified '+source['kind'],'external_id':'ref-'+source['kind'],'net_price':'250.50','currency':'USD','details':'Exact itinerary / room description','cancellation_policy':'Supplier terms entered by agent','stops':0,'stars':4,'ttl_minutes':5}

def test_manual_supplier_request_to_offer(client):
    flight=manual_source(client,'FLIGHT');hotel=manual_source(client,'HOTEL');req=create(client)
    r=post(client,'/requests/'+req['id']+'/confirm',{'spec':req['spec'],'revision':1}).json()
    payload={'revision':r['revision'],'reviewed':True,'items':[manual_item(flight),manual_item(hotel)]}
    saved=post(client,'/requests/'+req['id']+'/manual-results',payload,'same-manual-key');assert saved.status_code==200,saved.text
    repeated=post(client,'/requests/'+req['id']+'/manual-results',payload,'same-manual-key');assert repeated.json()['id']==saved.json()['id']
    req=client.get('/api/requests/'+req['id']).json();assert len(req['results'])==2
    assert all(r['capture_mode']=='MANUAL' and not r['demo'] for r in req['results'])
    offer=draft(client,req).json();assert offer['total']=='563.63'
    assert post(client,'/offers/'+offer['id']+'/approve').status_code==200

def test_manual_validation_and_atomicity(client):
    flight=manual_source(client,'FLIGHT');hotel=manual_source(client,'HOTEL');req=create(client)
    r=post(client,'/requests/'+req['id']+'/confirm',{'spec':req['spec'],'revision':1}).json()
    payload={'revision':r['revision'],'reviewed':False,'items':[manual_item(flight),manual_item(hotel)]}
    path='/requests/'+req['id']+'/manual-results'
    assert post(client,path,payload).status_code==422
    payload['reviewed']=True;payload['items'][1]['net_price']='-5'
    assert post(client,path,payload).status_code==422
    assert client.get('/api/requests/'+req['id']).json()['results']==[]
    payload['items'][1]['net_price']='200';payload['revision']=99
    assert post(client,path,payload).status_code==409
    assert post(client,'/requests/'+req['id']+'/search-runs',{'source_ids':[flight['id'],hotel['id']]}).status_code==409

def test_config_admin_only(client):
    source=native_source(client)
    post(client,'/users',{'name':'Agent','email':'agent@agency.local','password':'agent-password-123','role':'AGENT'})
    post(client,'/auth/logout');post(client,'/auth/login',{'email':'agent@agency.local','password':'agent-password-123'})
    assert client.get('/api/settings/ai').status_code==403
    assert client.put('/api/settings/ai',json={'enabled':False}).status_code==403
    assert client.get('/api/sources/'+source['id']+'/api-config').status_code==403
    assert 'api_config' not in client.get('/api/sources').text


def test_api_config_invalid_url_returns_safe_error(client):
    source=post(client,'/sources',{'name':'Source','kind':'FLIGHT','provider':'JSON_API'}).json()
    cfg=config();cfg['endpoint']='https://localhost/'
    r=client.put('/api/sources/'+source['id']+'/api-config',json={'config':cfg,'credential':'secret-that-must-not-echo'})
    assert r.status_code==422 and 'secret-that-must-not-echo' not in r.text

def test_backup_restore_includes_encrypted_credentials(client,tmp_path,monkeypatch):
    client.put('/api/settings/ai',json={'enabled':True,'model':'test-model','api_key':'recover-this-test-key'})
    root=Path(__file__).resolve().parents[2];backup=tmp_path/'saved.db';restored=tmp_path/'restored-installation'/'copilot.db'
    subprocess.run([sys.executable,str(root/'scripts/backup.py'),'--database',db.DB_PATH,'--output',str(backup)],check=True,capture_output=True)
    assert backup.with_suffix('.db.vault-key').is_file()
    subprocess.run([sys.executable,str(root/'scripts/restore.py'),'--backup',str(backup),'--output',str(restored)],check=True,capture_output=True)
    monkeypatch.setattr(db,'DB_PATH',str(restored))
    assert ai_config('agency')['key']=='recover-this-test-key'
    with sqlite3.connect(restored) as c:assert c.execute('SELECT count(*) FROM sessions').fetchone()[0]==0

@pytest.mark.parametrize('status,expected',[(200,None),(302,'REDIRECT_NOT_ALLOWED'),(401,'LOGIN_REQUIRED'),(503,'SUPPLIER_HTTP_503')])
def test_native_transport_pins_host_and_rejects_redirects(monkeypatch,status,expected):
    import httpx
    original=httpx.AsyncClient
    seen=[]
    def handler(req):
        seen.append(req)
        return httpx.Response(status,json={'results':[]},headers={'Location':'https://other.example.com/'})
    monkeypatch.setattr(integrations,'validate_url',lambda *a,**k:('supplier.example.com','93.184.216.34'))
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(handler)))
    async def call():return await integrations.fetch_api(config(),spec(),'test-secret')
    if expected:
        with pytest.raises(IntegrationError,match=expected):asyncio.run(call())
    else:assert asyncio.run(call())=={'results':[]}
    assert len(seen)==1
    assert seen[0].url.host=='93.184.216.34'
    assert seen[0].headers['host']=='supplier.example.com'
    assert seen[0].extensions['sni_hostname']=='supplier.example.com'
    assert seen[0].headers['authorization']=='Bearer test-secret'
    assert json.loads(seen[0].content)['pax']==2
