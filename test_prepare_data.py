import unittest, json
from prepare_data import *

class PreparationTests(unittest.TestCase):
    def test_catalog_retains_every_identity(self):
        c=sleeper_catalog({'old':{'full_name':'Retired Name','position':'RB','team':None,'active':True,'search_rank':1},'new':{'full_name':'Rookie','position':'WR','team':'BAL','search_rank':10},'idp':{'full_name':'Defender','position':'LB'},'a':{'full_name':'Same Name'},'b':{'full_name':'Same Name'}},stamp())
        self.assertEqual(c['source_count'],5)
        self.assertEqual(set(c['ordered_ids']),set(c['players']))
        self.assertEqual(c['name_index']['samename'],['a','b'])
        self.assertEqual(c['players']['idp'][2],['LB'])
        self.assertNotIn('injury_status',c['players']['new'])
    def test_join_uses_ids_and_keeps_missing(self):
        ids=[{'name':'A','position':'WR','sleeper_id':'1','gsis_id':'g1','pfr_id':'p1'}]
        stats=[{'name':'A','gsis_id':'g1','week':1,'game_id':'game','position':'WR','targets':0}]
        snaps=[{'name':'Different','pfr_id':'p1','week':1,'game_id':'game','position':'WR','offense_snaps':25,'offense_pct':.5},{'name':'Unmapped','pfr_id':'p2','week':1,'game_id':'game','position':'WR','offense_snaps':4,'offense_pct':.08}]
        out=join(ids,stats,snaps)
        self.assertEqual(len(out),2);self.assertEqual(out[0]['targets'],0)
        self.assertEqual(out[0]['offense_snaps'],25);self.assertIsNone(out[1]['targets']);self.assertIsNone(out[1]['sleeper_id'])
        w=week_file(out,2026,1,stats,snaps)
        self.assertEqual(len(w['orders']['offense_snaps']),2);self.assertEqual(len(w['orders']['targets']),1)
        self.assertFalse(w['coverage']['week_complete_verified'])
        with self.assertRaises(ValueError): join(ids,stats,stats and [dict(snaps[0],game_id='other')])
        with self.assertRaises(ValueError): join(ids,stats+stats,snaps)
    def test_identity_ambiguity_and_hash(self):
        ps=[{'name':'Same Name','position':'WR','sleeper_id':str(i),'gsis_id':None,'pfr_id':None} for i in (1,2)]
        shards=identities(ps);self.assertEqual(len(shards[bucket('n:samename')]['keys']['n:samename']),2)
        self.assertEqual(norm('Tre’ Harris'),'treharris')
        self.assertEqual(bucket('s:8228'),bucket('s:8228'))
    def test_csv_schema_failure_is_explicit(self):
        with self.assertRaises(ValueError): list(csv_rows('wrong\n1\n',['expected']))
        with self.assertRaises(ValueError): list(csv_rows('a,b\n1\n',['a','b']))
        self.assertEqual(list(csv_rows('a,b\n1,"two,three"\n',['a','b']))[0]['b'],'two,three')
    def test_partial_and_empty_weeks(self):
        w=week_file([],2026,2,[],[])
        self.assertEqual(w['rows'],[]);self.assertEqual(w['coverage']['stats_games_seen'],0)
    def test_week_identity_index_keeps_global_ambiguity_and_notes(self):
        ps=[{'name':'Same Name','position':'WR','sleeper_id':'1','gsis_id':'g1','pfr_id':'p1','mapping_notes':['verified provider ID']},
            {'name':'Same Name','position':'WR','sleeper_id':'2','gsis_id':'g2','pfr_id':'p2'},
            {'name':'Conflicting ID','position':'TE','sleeper_id':'1','gsis_id':'g3','pfr_id':'p3'}]
        w={'columns':['name'],'rows':[['Same Name']],'by_id':{'s:1':[0],'g:missing':[0]}}
        add_week_identities(w,identities(ps));idx=w['identity_lookup']
        self.assertEqual(len(idx['by_key']['n:samename']),2)
        self.assertEqual(len(idx['by_key']['s:1']),2)
        self.assertEqual(idx['by_key']['g:missing'],[])
        p=dict(zip(idx['columns'],idx['rows'][idx['by_key']['s:1'][0]]))
        self.assertEqual(p['mapping_notes'],['verified provider ID'])
        # Even byte-identical crosswalk duplicates remain ambiguous.
        w2={'columns':['name'],'rows':[['Same Name']],'by_id':{'s:1':[0]}}
        add_week_identities(w2,identities([ps[0],ps[0]]))
        self.assertEqual(len(w2['identity_lookup']['by_key']['s:1']),2)
    def test_halfback_snaps_and_stale_crosswalk_position(self):
        ids=crosswalk('sleeper_id,gsis_id,pfr_id,name,position\n1,g1,p1,Converted Player,LB\n')
        self.assertEqual(len(ids),1)
        snaps=parse_snaps('pfr_player_id,player,season,game_type,week,game_id,position,team,offense_snaps,offense_pct\np1,Converted Player,2026,REG,1,game,HB,CIN,46,0.72\n',2026)
        self.assertEqual(snaps[0]['position'],'RB')
        rows=join(ids,[{'name':'Converted Player','gsis_id':'g1','week':1,'game_id':'game','position':'RB','targets':0}],snaps)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['offense_snaps'],46);self.assertEqual(rows[0]['sleeper_id'],'1')
    def test_external_id_bridges_are_unique_and_never_name_only(self):
        players=[{'name':'Matthew Example','sleeper_id':None,'gsis_id':'g1','rotowire_id':'77'}, {'name':'Same Exact Name','sleeper_id':None,'gsis_id':'g2'}, {'name':'Ambiguous','sleeper_id':None,'gsis_id':'g3','rotowire_id':'88'}]
        catalog=sleeper_catalog({'s1':{'full_name':'Matt Example','rotowire_id':77},'s2':{'full_name':'Same Exact Name'},'s3':{'full_name':'Other','rotowire_id':88},'s4':{'full_name':'Other2','rotowire_id':88}},stamp())
        report=enrich_sleeper_ids(players,catalog['external_index'])
        self.assertEqual(players[0]['sleeper_id'],'s1');self.assertIsNone(players[1]['sleeper_id']);self.assertIsNone(players[2]['sleeper_id'])
        self.assertEqual(report['sleeper_ids_added'],1);self.assertEqual(report['ambiguous_candidates_not_joined'],1)
        conflict=[{'sleeper_id':'existing','rotowire_id':'11'},{'sleeper_id':None,'rotowire_id':'12'}]
        self.assertEqual(enrich_sleeper_ids(conflict,{'rotowire_id:12':['existing']})['sleeper_ids_added'],0)

if __name__=='__main__': unittest.main()
