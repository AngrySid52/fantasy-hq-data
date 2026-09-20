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

if __name__=='__main__': unittest.main()
