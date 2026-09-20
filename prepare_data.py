#!/usr/bin/env python3
"""Prepare public NFL records. Standard library only; no credentials or league reads."""
import argparse, csv, hashlib, io, json, math, os, re, sys, unicodedata
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
ID_URL = 'https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv'
PLAYER_URL = 'https://api.sleeper.app/v1/players/nfl'
METRICS = ['attempts','completions','passing_yards','passing_tds','passing_interceptions','carries','rushing_yards','rushing_tds','targets','receptions','receiving_yards','receiving_tds','receiving_air_yards','receiving_yards_after_catch','target_share','air_yards_share','fantasy_points','fantasy_points_ppr']
SORTS = ['targets','carries','opportunities','receiving_air_yards','target_share','offense_snaps','offense_pct']
POSITIONS = {'QB','RB','WR','TE','FB','HB'}
EXTERNAL_IDS = ('gsis_id','rotowire_id','espn_id','sportradar_id')
COLS = ['name','position','week','game_id','team','opponent','gsis_id','pfr_id','sleeper_id','stats_present','snaps_present',*METRICS,'opportunities','offense_snaps','offense_pct']

def stamp(): return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def clean(v): return None if v is None or str(v) in ('','NA','NaN') else v
def number(v):
    if clean(v) is None: return None
    try:
        n=float(v)
        return (int(n) if n.is_integer() else n) if math.isfinite(n) else None
    except (ValueError,TypeError): return None
def norm(v): return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower())
def bucket(key):
    h=2166136261
    for c in key: h=((h ^ ord(c))*16777619) & 0xffffffff
    return h % 128
def encode(v): return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def fetch(url, maximum=64*1024*1024):
    with urlopen(Request(url,headers={'User-Agent':'FantasyHQ-personal-data/1.3','Accept':'application/json,text/csv,*/*'}),timeout=60) as r:
        data=r.read(maximum+1)
        if len(data)>maximum: raise ValueError('Public source exceeds size bound')
        modified=r.headers.get('Last-Modified')
        try: modified=parsedate_to_datetime(modified).astimezone(timezone.utc).isoformat().replace('+00:00','Z') if modified else None
        except (ValueError,TypeError): modified=None
        return data.decode('utf-8-sig'), {'url':url,'retrieved_at':stamp(),'file_modified_at':modified,'status':'AVAILABLE'}
def csv_rows(text, required):
    reader=csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames) or not set(required)<=set(reader.fieldnames): raise ValueError('CSV schema mismatch')
    for row in reader:
        if None in row or any(v is None for v in row.values()): raise ValueError('Malformed CSV row')
        yield {k:clean(v) for k,v in row.items()}

def crosswalk(text):
    rows=[]
    for r in csv_rows(text,['sleeper_id','gsis_id','pfr_id','name','position']):
        # Identity matching must not depend on a provider's potentially stale position.
        if any(r.get(k) for k in ('sleeper_id','gsis_id','pfr_id')):
            rows.append({k:r.get(k) for k in ['name','position','sleeper_id','gsis_id','pfr_id',*EXTERNAL_IDS]})
    if not rows: raise ValueError('Empty player crosswalk')
    return rows

def enrich_sleeper_ids(players, external_index):
    added=0;ambiguous=0
    claimed={p['sleeper_id'] for p in players if p.get('sleeper_id')}
    source_counts={}
    for p in players:
        for field in EXTERNAL_IDS:
            if p.get(field):
                key=field+':'+str(p[field]);source_counts[key]=source_counts.get(key,0)+1
    for p in players:
        if p.get('sleeper_id'): continue
        keys=[field+':'+str(p[field]) for field in EXTERNAL_IDS if p.get(field)]
        matched=[key for key in keys if external_index.get(key)]
        candidates={pid for key in matched for pid in external_index[key]}
        if not candidates:continue
        if len(candidates)!=1 or candidates&claimed or any(source_counts[key]!=1 or len(external_index[key])!=1 for key in matched):
            ambiguous+=1;continue
        p['sleeper_id']=next(iter(candidates));claimed.add(p['sleeper_id']);p['mapping_notes']=['Sleeper ID resolved through unique shared '+key.split(':',1)[0] for key in matched];added+=1
    return {'sleeper_ids_added':added,'ambiguous_candidates_not_joined':ambiguous,'basis':'Unique shared provider IDs only; no name-only joining.'}

def identities(players):
    shards=[{} for _ in range(128)]
    for p in players:
        identity={k:p.get(k) for k in ['name','position','sleeper_id','gsis_id','pfr_id']}
        if p.get('mapping_notes'):identity['mapping_notes']=p['mapping_notes']
        for prefix,field in [('s','sleeper_id'),('g','gsis_id'),('p','pfr_id'),('n','name')]:
            value=norm(p[field]) if prefix=='n' else p.get(field)
            if value:
                key=prefix+':'+value
                shards[bucket(key)].setdefault(key,[]).append(identity)
    return [{'schema':1,'keys':s} for s in shards]

def parse_stats(text, season):
    out=[]
    for r in csv_rows(text,['player_id','player_display_name','season','season_type','week','game_id','position','team',*METRICS]):
        if r['season_type']!='REG' or number(r['season'])!=season or r['position'] not in POSITIONS: continue
        week=number(r['week'])
        if not isinstance(week,int) or not 1<=week<=18 or not r['player_id'] or not r['game_id']: raise ValueError('Invalid stats identity/week')
        x={'gsis_id':r['player_id'],'name':r['player_display_name'],'position':'RB' if r['position'] in ('FB','HB') else r['position'],'week':week,'game_id':r['game_id'],'team':r['team'],'opponent':r.get('opponent_team')}
        x.update({k:number(r[k]) for k in METRICS})
        x['opportunities']=None if x['carries'] is None or x['targets'] is None else x['carries']+x['targets']
        out.append(x)
    if not out: raise ValueError('Source has no usable stats records')
    return out

def parse_snaps(text, season):
    out=[]
    for r in csv_rows(text,['pfr_player_id','player','season','game_type','week','game_id','position','team','offense_snaps','offense_pct']):
        if r['game_type']!='REG' or number(r['season'])!=season or r['position'] not in POSITIONS: continue
        week=number(r['week']); pct=number(r['offense_pct'])
        if not isinstance(week,int) or not 1<=week<=18 or not r['pfr_player_id'] or not r['game_id']: raise ValueError('Invalid snap identity/week')
        if pct is not None and not 0<=pct<=1: raise ValueError('Invalid snap percentage scale')
        out.append({'pfr_id':r['pfr_player_id'],'name':r['player'],'position':'RB' if r['position'] in ('FB','HB') else r['position'],'week':week,'game_id':r['game_id'],'team':r['team'],'opponent':r.get('opponent'),'offense_snaps':number(r['offense_snaps']),'offense_pct':pct})
    if not out: raise ValueError('Source has no usable snap records')
    return out

def join(players, stats, snaps):
    maps={k:{} for k in ('gsis_id','pfr_id')}
    for p in players:
        for k in maps:
            if p[k]: maps[k].setdefault(p[k],[]).append(p)
    def unique(k,v):
        ps=maps[k].get(v,[])
        return ps[0] if len(ps)==1 else {}
    joined={}; seen=set()
    for r in stats:
        key=('g',r['gsis_id'],r['week']); p=unique('gsis_id',r['gsis_id'])
        if key in joined: raise ValueError('Duplicate stats identity/week')
        joined[key]={**r,'sleeper_id':p.get('sleeper_id'),'pfr_id':p.get('pfr_id'),'stats_present':True,'snaps_present':False,'offense_snaps':None,'offense_pct':None}
    for r in snaps:
        sk=(r['pfr_id'],r['week'])
        if sk in seen: raise ValueError('Duplicate snap identity/week')
        seen.add(sk); p=unique('pfr_id',r['pfr_id'])
        key=('g',p['gsis_id'],r['week']) if p.get('gsis_id') else ('p',r['pfr_id'],r['week'])
        if key in joined:
            if joined[key]['game_id']!=r['game_id']: raise ValueError('Stats/snap game mismatch')
            joined[key].update({'snaps_present':True,'offense_snaps':r['offense_snaps'],'offense_pct':r['offense_pct']})
        else: joined[key]={**dict.fromkeys([*METRICS,'opportunities']),**r,'gsis_id':p.get('gsis_id'),'sleeper_id':p.get('sleeper_id'),'stats_present':False,'snaps_present':True}
    return list(joined.values())

def add_week_identities(week, identity_shards):
    # Copy globally authoritative matches, including ambiguity outside this week.
    # A week-local unique ID/name alone is not sufficient identity evidence.
    keys=set(week['by_id'])
    ni=week['columns'].index('name')
    keys.update('n:'+norm(r[ni]) for r in week['rows'] if r[ni])
    for key in list(keys):
        for p in identity_shards[bucket(key)]['keys'].get(key,[]):
            if p.get('name'):keys.add('n:'+norm(p['name']))
    columns=['name','position','sleeper_id','gsis_id','pfr_id','mapping_notes']
    rows=[]; index={}; seen={}
    for key in sorted(keys):
        matches=[]
        for p in identity_shards[bucket(key)]['keys'].get(key,[]):
            row=[p.get(k,[] if k=='mapping_notes' else None) for k in columns]
            packed=encode(row)
            if packed not in seen:seen[packed]=len(rows);rows.append(row)
            matches.append(seen[packed])
        # Do not deduplicate matches: duplicate crosswalk entries remain ambiguous.
        index[key]=matches
    week['identity_lookup']={'columns':columns,'rows':rows,'by_key':index}
    return week

def week_file(rows, season, week, stats, snaps, identity_shards=None):
    selected=[r for r in rows if r['week']==week]
    # Stable sorting and complete rows, including unmapped identities. No player cap.
    selected.sort(key=lambda r:(r['name'] or '',r.get('gsis_id') or r.get('pfr_id') or ''))
    by_id={}
    for i,r in enumerate(selected):
        for p,k in [('s','sleeper_id'),('g','gsis_id'),('p','pfr_id')]:
            if r.get(k): by_id.setdefault(p+':'+r[k],[]).append(i)
    orders={k:sorted([i for i,r in enumerate(selected) if r.get(k) is not None],key=lambda i:(-selected[i][k],selected[i]['name'] or '',selected[i].get('gsis_id') or selected[i].get('pfr_id') or '')) for k in SORTS}
    result={'schema':1,'season':season,'week':week,'columns':COLS,'rows':[[r.get(k) for k in COLS] for r in selected],'by_id':by_id,'orders':orders,'coverage':{'week':week,'stats_games_seen':len({r['game_id'] for r in stats if r['week']==week}),'snap_games_seen':len({r['game_id'] for r in snaps if r['week']==week}),'week_complete_verified':False}}
    return add_week_identities(result,identity_shards) if identity_shards is not None else result

def sleeper_catalog(raw, retrieved):
    if not isinstance(raw,dict) or not raw: raise ValueError('Invalid Sleeper directory')
    players={}; names={};external_index={}
    for pid,p in raw.items():
        if not isinstance(p,dict): raise ValueError('Invalid player directory entry')
        name=p.get('full_name') or ' '.join(filter(None,[p.get('first_name'),p.get('last_name')])) or None
        players[pid]={'id':pid,'name':name,'position':p.get('position'),'fantasy_positions':p.get('fantasy_positions') or ([p['position']] if p.get('position') else []),'team':p.get('team'),'active':p.get('active'),'status':p.get('status'),**{k:number(p.get(k)) for k in ('search_rank','age','years_exp')}}
        if norm(name): names.setdefault(norm(name),[]).append(pid)
        for field in EXTERNAL_IDS:
            if clean(p.get(field)) is not None:external_index.setdefault(field+':'+str(p[field]),[]).append(pid)
    ordered=sorted(players,key=lambda pid:(players[pid]['search_rank'] if players[pid]['search_rank'] is not None and players[pid]['search_rank']>0 else math.inf,pid))
    return {'schema':1,'encoding':'player-tuples-v1','fetched_at':retrieved,'source_count':len(raw),'players':{pid:[p[k] for k in ['name','position','fantasy_positions','team','active','status','search_rank','age','years_exp']] for pid,p in players.items()},'name_index':names,'ordered_ids':ordered,'external_index':external_index}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default=str(ROOT/'data'));ap.add_argument('--season',type=int);ap.add_argument('--fixtures',type=Path);args=ap.parse_args()
    dest=Path(args.output);(dest/'objects').mkdir(parents=True,exist_ok=True);now=stamp();files=[]
    def put(data):
        body=encode(data);sha=hashlib.sha256(body).hexdigest();path='objects/'+sha+'.json';(dest/path).write_bytes(body);files.append(path)
        return {'path':path,'sha256':sha,'bytes':len(body)}
    previous={}
    if (dest/'manifest.json').exists(): previous=json.loads((dest/'manifest.json').read_text())
    def get(url,fixture):
        if args.fixtures: return (args.fixtures/fixture).read_text(),{'url':url,'retrieved_at':now,'file_modified_at':None,'status':'AVAILABLE'}
        return fetch(url)
    season=args.season
    if not season:
        state,_=fetch('https://api.sleeper.app/v1/state/nfl');season=int(json.loads(state)['season'])
    if not 2025<=season<=datetime.now(timezone.utc).year: raise ValueError('Invalid current season')
    id_text,id_meta=get(ID_URL,'ids.csv');ids=crosswalk(id_text)
    manifest={'schema':1,'generated_at':now,'current_season':season,'sources':{'ids':id_meta},'identities':[],'preparer_version':'1.3.2','seasons':{},'fixture_data':bool(args.fixtures)}
    def put_catalog(c):
        fields=['name','position','fantasy_positions','team','active','status','search_rank','age','years_exp']
        tuples=c['players'] if c.get('encoding')=='player-tuples-v1' else {pid:[p.get(k) for k in fields] for pid,p in c['players'].items()}
        teams=set('ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split())
        positions=['QB','RB','WR','TE','K','DEF'];shards=[{} for _ in range(16)];core={};pool=[]
        for pid in c['ordered_ids']:
            r=tuples[pid];shards[bucket(pid)%16][pid]=r
            mask=sum(1<<i for i,k in enumerate(positions) if k in (r[2] or []))
            if mask:
                assigned=r[3] in teams;pool.append([pid,mask,assigned,r[1]])
                if assigned:core[pid]=r
        return put({'schema':1,'encoding':'split-player-tuples-v1','fetched_at':c['fetched_at'],'source_count':c['source_count'],'core':core,'names':put({'schema':1,'index':c['name_index']}),'pool':put({'schema':1,'rows':pool}),'external_ids':put({'schema':1,'index':c['external_index']}),'shards':[put({'schema':1,'players':rows}) for rows in shards]})
    old=previous.get('sleeper',{});old_age=math.inf
    try: old_age=(datetime.now(timezone.utc)-datetime.fromisoformat(old['fetched_at'].replace('Z','+00:00'))).total_seconds()
    except (KeyError,ValueError): pass
    cached=None
    if not args.fixtures and 0<=old_age<86400 and (dest/old['catalog']['path']).exists():cached=json.loads((dest/old['catalog']['path']).read_text())
    if cached and cached.get('encoding')=='split-player-tuples-v1' and cached.get('external_ids') and (dest/cached['external_ids']['path']).exists():
        manifest['sleeper']=old
        files.extend([old['catalog']['path'],cached['names']['path'],cached['pool']['path'],cached['external_ids']['path'],*[x['path'] for x in cached['shards']]])
    else:
        raw,meta=get(PLAYER_URL,'sleeper.json');catalog=sleeper_catalog(json.loads(raw),meta['retrieved_at'])
        if not args.fixtures and catalog['source_count']<1000: raise ValueError('Unexpectedly small player directory')
        if old.get('source_count',0)>catalog['source_count']/0.75: raise ValueError('Player directory shrank by over 25%; refusing silent coverage loss')
        manifest['sleeper']={'catalog':put_catalog(catalog),'fetched_at':meta['retrieved_at'],'source_count':catalog['source_count'],'url':PLAYER_URL}
    catalog_meta=json.loads((dest/manifest['sleeper']['catalog']['path']).read_text())
    external_index=json.loads((dest/catalog_meta['external_ids']['path']).read_text())['index']
    manifest['identity_enrichment']=enrich_sleeper_ids(ids,external_index)
    manifest['sources']['sleeper_identity_links']={'url':PLAYER_URL,'retrieved_at':manifest['sleeper']['fetched_at'],'file_modified_at':None,'status':'AVAILABLE'}
    identity_shards=identities(ids)
    manifest['identities']=[put(x) for x in identity_shards]
    # Prepare the current and previous season.
    for year in sorted({season,max(2025,season-1)}):
        values={};sources={};warnings=[]
        for kind,folder,filename,parser in [('stats','stats_player',f'stats_player_week_{year}.csv',parse_stats),('snaps','snap_counts',f'snap_counts_{year}.csv',parse_snaps)]:
            url=f'https://github.com/nflverse/nflverse-data/releases/download/{folder}/{filename}'
            try:
                text,meta=get(url,f'{kind}.csv' if args.fixtures else filename);values[kind]=parser(text,year);sources[kind]=meta
            except Exception as e:
                values[kind]=[];sources[kind]={'url':url,'status':'UNAVAILABLE','retrieved_at':now};warnings.append(kind+': '+str(e)[:180])
        if not values['stats'] and not values['snaps']:
            manifest['seasons'][str(year)]={'status':'UNAVAILABLE','sources':sources,'warnings':warnings};continue
        rows=join(ids,values['stats'],values['snaps'])
        manifest['seasons'][str(year)]={'status':'AVAILABLE','sources':sources,'warnings':warnings,'weeks':{str(w):put(week_file(rows,year,w,values['stats'],values['snaps'],identity_shards)) for w in range(1,19)}}
    if manifest['seasons'][str(season)]['status']!='AVAILABLE': raise ValueError('Current-season workload unavailable; previous publication retained')
    # Keep 48 hours of immutable objects so cached manifests cannot mix generations.
    history=[]
    if (dest/'history.json').exists(): history=json.loads((dest/'history.json').read_text())
    cutoff=(datetime.now(timezone.utc)-timedelta(hours=48)).isoformat().replace('+00:00','Z')
    history=[h for h in history if h['generated_at']>=cutoff];history.append({'generated_at':now,'files':sorted(set(files))})
    keep={f for h in history for f in h['files']}
    for f in (dest/'objects').glob('*.json'):
        if 'objects/'+f.name not in keep: f.unlink()
    (dest/'history.json').write_bytes(encode(history));(dest/'manifest.json').write_bytes(encode(manifest))
    print(json.dumps({'prepared_at':now,'season':season,'identity_records':len(ids),'sleeper_players':manifest['sleeper']['source_count'],'weeks':{y:len(v.get('weeks',{})) for y,v in manifest['seasons'].items()},'immutable_objects':len(keep),'fixture_data':bool(args.fixtures)}))

if __name__=='__main__': main()
