"""Create review-only dependency PRs using this repository's short-lived token."""
import base64,datetime,fnmatch,hashlib,json,os,pathlib,re,subprocess,tempfile,time,urllib.error,urllib.parse,urllib.request

VERSION='44.164.10'
INTEGRITY='00SwO80VhvAKMvn3NHD3yQTq9Fo0NhhpGgRkmRlh+6GS/GgH7AHwNsAnueU3gjTtoPAyj8igBQZvVqfmcG3mew=='
SERVER=os.environ['PERSONAL_GITEA_SERVER']
assert SERVER==os.environ['GITHUB_SERVER_URL']
assert urllib.parse.urlsplit(SERVER).scheme=='http'and urllib.parse.urlsplit(SERVER).port==3000
REPOSITORY='hallyaus/australian-fire-watch'
BRANCH='main'
PREFIX='renovate/personal-'
STATUS_CONTEXT='personal-dependency-checks'
phase_state={'phase':'context'}

def main():
    assert os.environ['GITHUB_SERVER_URL']==SERVER and os.environ['GITHUB_REPOSITORY']==REPOSITORY
    assert os.environ['GITHUB_REF']=='refs/heads/'+BRANCH
    assert os.environ['GITHUB_EVENT_NAME']in('push','schedule','workflow_dispatch')
    source=os.environ['GITHUB_SHA'];run=os.environ['GITHUB_RUN_ID']
    assert re.fullmatch('[0-9a-f]{40}',source) and run.isdigit()
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
    token=os.environ.pop('DEPENDENCY_JOB_TOKEN');assert token
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise RuntimeError('Unexpected authenticated redirect')
    opener=urllib.request.build_opener(NoRedirect)
    def api(path,method='GET',body=None):
        request=urllib.request.Request(SERVER+'/api/v1'+path,method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization':'token '+token,'Content-Type':'application/json'})
        with opener.open(request,timeout=30)as response:
            raw=response.read(2*1024*1024+1);assert len(raw)<=2*1024*1024
            return json.loads(raw)if raw else None
    phase_state['phase']='owner-only-default-policy'
    base='/repos/'+REPOSITORY
    user=api('/user');assert user['login']=='gitea-actions'
    repo=api(base);assert repo['private']and repo['owner']['login']=='hallyaus'and repo['default_branch']==BRANCH
    protected=api(base+'/branches/'+BRANCH)
    assert protected['protected']and protected['commit']['id']==source
    assert protected['user_can_push']is False and protected['user_can_merge']is False
    node=json.loads(subprocess.check_output(['node','-p','JSON.stringify(process.versions)'],text=True))['node']
    assert int(node.split('.')[0])==24 and int(node.split('.')[1])>=11
    report={'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'repository':REPOSITORY,'source':source,'run':run,'version':VERSION,'node':node,
        'default_push_and_merge_denied_to_job':True,'automerge':False,'persistent_credentials_created':False,
        'credential_values_recorded':False,'source_production_runtime_or_device_changed':False}
    phase_state['phase']='official-updater-install'
    with tempfile.TemporaryDirectory(prefix='personal-dependency-updates-')as directory:
        work=pathlib.Path(directory);archive=work/'renovate.tgz';digest=hashlib.sha512();size=0
        with urllib.request.urlopen('https://registry.npmjs.org/renovate/-/renovate-'+VERSION+'.tgz',timeout=45)as response,archive.open('wb')as output:
            while chunk:=response.read(1024*1024):
                size+=len(chunk);assert size<=64*1024*1024
                digest.update(chunk);output.write(chunk)
        assert base64.b64encode(digest.digest()).decode()==INTEGRITY
        report['official_package_integrity_verified']=True
        for name in ['npm-user','npm-global']:(work/name).write_text('')
        environment={k:os.environ[k]for k in ['PATH','LANG','TMPDIR','SYSTEMROOT']if k in os.environ}
        environment.update(NPM_CONFIG_USERCONFIG=str(work/'npm-user'),NPM_CONFIG_GLOBALCONFIG=str(work/'npm-global'),
            NPM_CONFIG_CACHE=str(work/'npm-cache'),NPM_CONFIG_REGISTRY='https://registry.npmjs.org/',
            NPM_CONFIG_IGNORE_SCRIPTS='true',GIT_TERMINAL_PROMPT='0',GIT_CONFIG_NOSYSTEM='1',
            GIT_CONFIG_GLOBAL='/dev/null',NODE_OPTIONS='--max-old-space-size=2048')
        install=subprocess.run(['npm','install','--prefix',str(work/'runtime'),'--ignore-scripts',
            '--no-audit','--no-fund','--package-lock=false','--no-save',str(archive)],
            env=environment,text=True,capture_output=True,timeout=480)
        assert install.returncode==0,'Official updater installation refused; raw output withheld'
        config={'platform':'gitea','endpoint':SERVER+'/api/v1/','repositories':[REPOSITORY],
            'autodiscover':False,'onboarding':False,'requireConfig':'ignored','baseBranches':[BRANCH],
            'username':'gitea-actions','gitAuthor':'Personal Gitea Maintenance <gitea-actions@personal.invalid>',
            'ignorePrAuthor':True,'branchPrefix':PREFIX,
            'baseDir':str(work/'repositories'),'cacheDir':str(work/'cache'),'repositoryCache':'disabled',
            'enabledManagers':['github-actions'],
            'includePaths':['.gitea/workflows/**'],
            'ignorePaths':['**/.github/workflows/**'],
            'packageRules':[{'matchManagers': ['github-actions'], 'groupName': 'ci-dependencies'}, {'matchDatasources': ['docker'], 'matchPackageNames': ['python'], 'matchCurrentValue': '/^3\\.13\\-bookworm$/', 'allowedVersions': '/^3\\.13\\-bookworm$/'}, {'matchDatasources': ['docker'], 'matchPackageNames': ['python'], 'matchCurrentValue': '/^3\\.14\\-bookworm$/', 'allowedVersions': '/^3\\.14\\-bookworm$/'}, {'matchDatasources': ['docker'], 'matchPackageNames': ['node'], 'matchCurrentValue': '/^24\\-bookworm$/', 'allowedVersions': '/^24\\-bookworm$/'}],
            'dependencyDashboard':False,'automerge':False,'platformAutomerge':False,
            'binarySource':'global','allowScripts':False,'allowPlugins':False,'allowedCommands':[],
            'fetchReleaseNotes':'off','prConcurrentLimit':5,'prHourlyLimit':5,
            'pruneStaleBranches':False,'rebaseWhen':'never'}
        config_path=work/'config.json';config_path.write_text(json.dumps(config))
        environment.update(RENOVATE_TOKEN=token,RENOVATE_CONFIG_FILE=str(config_path),LOG_FORMAT='json',LOG_LEVEL='info')
        command=work/'runtime/node_modules/renovate/dist/renovate.js';assert command.is_file()
        phase_state['phase']='updater'
        result=subprocess.run(['node',str(command)],env=environment,text=True,capture_output=True,timeout=600)
        assert len(result.stdout)+len(result.stderr)<=8*1024*1024
        messages=[];finished=[];extractions=[];errors=[]
        def safe(value):
            text=str(value).replace(token,'[redacted]')
            return re.sub(r'(https?://)[^/\s@]+@',r'\1[redacted]@',text)[:400]
        for line in(result.stdout+'\n'+result.stderr).splitlines():
            try:item=json.loads(line)
            except json.JSONDecodeError:continue
            if not isinstance(item,dict):continue
            message=item.get('msg','');messages.append(safe(message))
            if message=='Repository finished':finished.append({k:item.get(k)for k in ['repository','result','status']})
            if message=='Dependency extraction complete':extractions.append(item.get('stats',{}))
            if item.get('level',0)>=50:errors.append({'message':safe(message),'error':safe((item.get('err')or{}).get('message',''))})
        report.update(updater_exit=result.returncode,messages=messages,repository_finished=finished,
            extraction_statistics=extractions,errors=errors)
        phase_state['phase']='review-branch-file-boundary'
        pulls=api(base+'/pulls?state=open&limit=50')
        candidates=[]
        for pull in pulls:
            if not pull['head']['ref'].startswith(PREFIX):continue
            assert pull['user']['login']=='gitea-actions'and pull['base']['ref']==BRANCH
            assert pull['head']['repo']['id']==repo['id']
            files=api(base+'/pulls/'+str(pull['number'])+'/files?limit=100')
            names=[f['filename']for f in files];assert names and len(names)<100
            assert all(fnmatch.fnmatchcase(n,'.gitea/workflows/*.yml')or fnmatch.fnmatchcase(n,'.gitea/workflows/*.yaml')for n in names)
            candidates.append({'number':pull['number'],'url':pull['html_url'],'source':pull['head']['sha'],
                'branch':pull['head']['ref'],'changed_files':names,'merged':False})
        phase_state['phase']='unchanged-default-source'
        phase_state['phase']='exact-proposal-validation-dispatch'
        dispatches=[];holds=[];base_merges=[]
        for candidate in candidates:
            sha=candidate['source'];assert re.fullmatch('[0-9a-f]{40}',sha)
            file=api(base+'/contents/.gitea/workflows/ci.yml?ref='+sha)
            content=base64.b64decode(file['content']).decode()
            if 'PERSONAL_DEPENDENCY_STATUS_V2'not in content:
                # Bring the controlled validator into our earlier review branches by
                # a normal merge. Preserve both histories; never rebase or force-push.
                number=str(candidate['number'])
                original=api(base+'/pulls/'+number)
                assert original['user']['login']=='gitea-actions'and original['base']['ref']==BRANCH
                assert original['head']['repo']['id']==repo['id']and original['head']['sha']==sha
                assert original['head']['ref']==candidate['branch']and original['state']=='open'
                assert api(base+'/branches/'+BRANCH)['commit']['id']==source
                try:
                    api(base+'/pulls/'+number+'/update?style=merge','POST')
                except urllib.error.HTTPError as error:
                    if error.code!=409:raise
                    holds.append({'number':candidate['number'],'source':sha,'reason':'Normal base-into-proposal merge conflicts; owner review required'})
                    continue
                for attempt in range(10):
                    updated=api(base+'/pulls/'+number)
                    if updated['head']['sha']!=sha:break
                    time.sleep(1)
                else:raise RuntimeError('Proposal merge did not produce its new head')
                merged_sha=updated['head']['sha'];assert re.fullmatch('[0-9a-f]{40}',merged_sha)
                commit=api(base+'/git/commits/'+merged_sha+'?stat=false&verification=false&files=false')
                parents=[p['sha']for p in commit['parents']]
                assert len(parents)==2 and set(parents)=={sha,source}
                base_merges.append({'number':candidate['number'],'old_proposal':sha,'new_proposal':merged_sha,
                    'preserved_parents':parents,'normal_merge_only':True})
                sha=merged_sha;candidate['source']=sha
                file=api(base+'/contents/.gitea/workflows/ci.yml?ref='+sha)
                content=base64.b64decode(file['content']).decode()
                assert 'PERSONAL_DEPENDENCY_STATUS_V2'in content
            statuses=api(base+'/statuses/'+sha+'?limit=100')
            matching=[s for s in statuses if s['context']==STATUS_CONTEXT]
            latest=max(matching,key=lambda s:s['id'])if matching else None
            if latest and latest['status']in('success','failure','error'):
                dispatches.append({'number':candidate['number'],'source':sha,'previous_result':latest['status'],'unchanged_source_not_retested':True})
                continue
            runs=api(base+'/actions/runs?'+urllib.parse.urlencode({'head_sha':sha,'limit':100}))['workflow_runs']
            matching_runs=[r for r in runs if str(r['path']).split('@')[0].rsplit('/',1)[-1]=='ci.yml'and r['head_sha']==sha]
            active=[r for r in matching_runs if r['status']in('queued','in_progress','waiting','requested','pending')]
            if active:
                dispatches.append({'number':candidate['number'],'source':sha,'existing_live_run_ids':[r['id']for r in active]})
                continue
            if matching_runs:
                holds.append({'number':candidate['number'],'source':sha,'reason':'Existing exact-source CI finished without its controlled status; inspect it before retrying'})
                continue
            current=api(base+'/branches/'+urllib.parse.quote(candidate['branch'],safe=''))
            assert current['commit']['id']==sha
            api(base+'/statuses/'+sha,'POST',{'state':'pending','context':STATUS_CONTEXT,
                'description':'Queued exact-source tests, typing, coverage and hassfest','target_url':candidate['url']})
            dispatched=api(base+'/actions/workflows/ci.yml/dispatches?return_run_details=true',
                'POST',{'ref':'refs/heads/'+candidate['branch']})
            assert dispatched and dispatched['workflow_run_id']>0
            dispatches.append({'number':candidate['number'],'source':sha,'run_id':dispatched['workflow_run_id'],
                'run_url':dispatched['html_url'],'explicit_dispatch_avoids_bot_event_suppression':True})
        report['proposal_validation_dispatches']=dispatches;report['proposal_validation_holds']=holds
        report['proposal_base_merges']=base_merges
        after=api(base+'/branches/'+BRANCH)
        assert after['commit']['id']==source and not after['user_can_push']and not after['user_can_merge']
        report['default_source_unchanged']=True;report['review_pull_requests']=candidates
        report['updater_complete']=result.returncode==0 and len(finished)==1 and finished[0]['result']=='done'and not errors
        print(json.dumps({'personal_dependency_updates':report}))
        assert report['updater_complete'],'Dependency writer did not complete'
        environment.pop('RENOVATE_TOKEN',None)
    token=None

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'personal_dependency_updates_complete':False,'error_type':type(error).__name__,**phase_state}))
        raise SystemExit(1)
