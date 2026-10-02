from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException,Header
from pydantic import ValidationError
from . import db
from .security import admin,current_user
from .integrations import *
from .providers import GeminiUnderstanding,validate_result
from .models import TravelSpec

router=APIRouter(prefix='/api')

@router.get('/settings/ai')
def get_ai(u=Depends(admin)):
    cfg=ai_config(u['tenant'])
    return {'enabled':cfg['enabled'],'model':cfg['model'],'has_key':bool(cfg['key'])}

@router.put('/settings/ai')
def update_ai(body:AISettings,u=Depends(admin)):
    cfg=ai_config(u['tenant']);newkey=body.api_key.get_secret_value() if body.api_key else ''
    if len(newkey)>500:raise HTTPException(422,'API key too long')
    key='' if body.clear_key else newkey or cfg['key']
    if body.enabled and (not body.model or not key):raise HTTPException(422,'Enable AI only after entering a model and key')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        secret_put(c,u['tenant'],'gemini',key)
        db.save(c,u['tenant'],'settings',{'id':'ai_'+u['tenant'],'enabled':body.enabled,'model':body.model})
        db.audit(c,u,'settings','AI_SETTINGS_UPDATED',{'enabled':body.enabled,'model':body.model})
    return get_ai(u)

@router.post('/settings/ai/test')
async def test_ai(u=Depends(admin)):
    cfg=ai_config(u['tenant'])
    if not cfg['key'] or not cfg['model']:raise HTTPException(409,'Save a model and API key first')
    try:
        result=await GeminiUnderstanding(u['tenant']).generate([{'text':'Return only the word OK.'}])
        if 'OK' not in result.upper():raise ValueError()
    except Exception:raise HTTPException(502,'Gemini connection test failed. Check the key, model access and network. Secret values are not returned.')
    with db.connect() as c:db.audit(c,u,'settings','AI_CONNECTION_TESTED')
    return {'ok':True,'message':'Model responded. Travel extraction and voice still require your review.'}

@router.get('/sources/{id}/api-config')
def get_api_config(id:str,u=Depends(admin)):
    with db.connect() as c:s=db.get(c,u['tenant'],'source',id)
    if s['provider']!='JSON_API':raise HTTPException(409,'Not a native JSON API source')
    latest=next(v for v in s['versions'] if v['version']==s['version'])
    return {'config':latest.get('api_config'),'has_credential':bool(secret_get(u['tenant'],'source_'+id)),'version':s['version']}

@router.put('/sources/{id}/api-config')
def put_api_config(id:str,body:APIConfigIn,u=Depends(admin)):
    cfg=body.config.model_dump(mode='json')
    # Validate shape here; resolve and pin public DNS only when a test/search explicitly executes.
    token=body.credential.get_secret_value() if body.credential else ''
    if len(token)>4000:raise HTTPException(422,'Credential too long')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');s=db.get(c,u['tenant'],'source',id)
        if s['provider']!='JSON_API':raise HTTPException(409,'Not a JSON API source')
        # Changing the endpoint must never silently send a previous source credential elsewhere.
        previous=s['versions'][-1].get('api_config',{})
        if previous and previous.get('endpoint')!=cfg['endpoint'] and not token:
            if cfg['auth_type']!='NONE':raise HTTPException(409,'Re-enter the credential when changing the endpoint')
            body.clear_credential=True
        if body.clear_credential:secret_put(c,u['tenant'],'source_'+id,'')
        elif token:secret_put(c,u['tenant'],'source_'+id,token)
        s['version']+=1;s['status']='DRAFT';s['active_version']=None
        s['versions'].append({'version':s['version'],'mapping_version':'native-api-v'+str(s['version']),'notes':body.notes,'api_config':cfg,'created_at':db.now()})
        db.save(c,u['tenant'],'source',s);db.audit(c,u,id,'API_CONFIG_VERSION_SAVED',{'version':s['version']})
    return get_api_config(id,u)

@router.put('/sources/{id}/manual-config')
def manual_config(id:str,body:ManualSourceIn,u=Depends(admin)):
    validate_url(body.website_url,resolve=False)
    if not body.authorized:raise HTTPException(422,'Confirm your agency is authorized to use this supplier')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE');s=db.get(c,u['tenant'],'source',id)
        if s['provider']!='MANUAL':raise HTTPException(409,'Not a manual supplier')
        s['version']+=1;s['active_version']=s['version'];s['status']='ACTIVE';s['website_url']=body.website_url;s['notes']=body.notes
        s['versions'].append({'version':s['version'],'mapping_version':'manual-v'+str(s['version']),'notes':'Human-reviewed supplier rate entry','created_at':db.now()})
        db.save(c,u['tenant'],'source',s);db.audit(c,u,id,'MANUAL_SOURCE_ACTIVATED',{'version':s['version']})
    return s

@router.post('/requests/{id}/manual-results')
def manual_rates(id:str,body:ManualRatesIn,u=Depends(current_user),idempotency_key:str|None=Header(default=None)):
    from .main import request_get,mutation,make_job,TERMINAL
    if not body.reviewed:raise HTTPException(422,'Verify exact supplier prices, route, dates, party, taxes and terms first')
    with db.connect() as c:
        def op():
            req=request_get(c,u,id);spec=TravelSpec.model_validate(req['spec'])
            if req['revision']!=body.revision or req['confirmed_revision']!=req['revision'] or spec.issues() or req['status'] in TERMINAL or req['status']=='SEARCHING':raise HTTPException(409,'Confirm current travel details and finish any running search first')
            run={'id':db.uid('run'),'request_id':id,'revision':req['revision'],'spec':req['spec'],'status':'SUCCESS','created_at':db.now(),'completed_at':db.now(),'jobs':[],'capture_mode':'MANUAL'}
            kinds=set();seen=set()
            for item in body.items:
                source=db.get(c,u['tenant'],'source',item.source_id)
                if source['provider']!='MANUAL' or source['status']!='ACTIVE':raise HTTPException(409,'Select an active manual supplier')
                key=(item.source_id,item.external_id)
                if key in seen:raise HTTPException(422,'Duplicate supplier rate ID')
                seen.add(key);kinds.add(source['kind']);now=datetime.now(timezone.utc)
                values={k:req['spec'][k] for k in ['origin','destination','departure_date','return_date','adults','rooms','cabin']}
                values.update(item.model_dump(exclude={'source_id','ttl_minutes'}));values.update(kind=source['kind'],price_basis='TOTAL_PARTY_STAY_TAX_INCLUDED',captured_at=now,expires_at=now+timedelta(minutes=item.ttl_minutes),demo=False)
                if source['kind']=='HOTEL':values['origin']=''
                try:rate=Rate.model_validate(values)
                except ValidationError:raise HTTPException(422,'Invalid rate: use a positive decimal total and complete supplier fields')
                job=make_job(source,req['spec'],u['tenant'],run['id'],req['revision'])
                try:validate_result(ExecutionResult(job_id=job['job_id'],status='SUCCESS',records=[rate]),job)
                except ValueError:raise HTTPException(422,'Rate does not match requested directness, stars or other confirmed details')
                job.update(status='SUCCESS',source_name=source['name'],duration_ms=0);run['jobs'].append(job)
                obj={'id':db.uid('rate'),**rate.model_dump(mode='json'),'source_id':source['id'],'source_name':source['name'],'run_id':run['id'],'request_id':id,'workflow_version':source['active_version'],'created_at':db.now(),'entered_by':u['id'],'capture_mode':'MANUAL'}
                db.save(c,u['tenant'],'result',obj)
            expected={'FLIGHT','HOTEL'} if spec.intent=='PACKAGE_SEARCH' else {'FLIGHT'} if spec.intent=='FLIGHT_SEARCH' else {'HOTEL'}
            if kinds!=expected:raise HTTPException(422,'Enter at least one rate for every requested service, with no extra service')
            req.update(status='RESULTS_READY',active_run_id=run['id'],updated_at=db.now());db.save(c,u['tenant'],'request',req);db.save(c,u['tenant'],'run',run)
            db.audit(c,u,id,'MANUAL_RATES_VERIFIED',{'run_id':run['id'],'count':len(body.items)});return run
        return mutation(c,u,'manual/'+id,idempotency_key,body.model_dump(mode='json'),op)[0]
