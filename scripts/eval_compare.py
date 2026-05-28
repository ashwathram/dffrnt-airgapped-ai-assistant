import json
import os
from collections import defaultdict

vo_path = 'artifacts/eval/vector_only/eval_recursive_vector_only_20260527_001231.json'
hy_path = 'artifacts/eval/hybrid/eval_recursive_hybrid_20260527_001232.json'

def load(p):
    with open(p,'r',encoding='utf-8') as f:
        return json.load(f)

def cat_from_filename(fn):
    n = fn.lower()
    if 'resume' in n or 'cv' in n:
        return 'resume'
    if 'proposal' in n:
        return 'proposal'
    if 'case' in n or 'case-study' in n or 'case_study' in n:
        return 'case study'
    if 'sales' in n or 'pitch' in n:
        return 'sales'
    if 'technical' in n or 'experience' in n or 'technicalproposal' in n:
        return 'technical/experience'
    return 'other'

vo = load(vo_path)
hy = load(hy_path)

results_vo = vo.get('results',[])
results_hy = hy.get('results',[])

n = min(len(results_vo), len(results_hy))

agg = {'vector_only':{'recall_at_k':0,'precision_at_k':0,'mrr':0,'coverage':0,'count':0},
       'hybrid':{'recall_at_k':0,'precision_at_k':0,'mrr':0,'coverage':0,'count':0},
       'by_category':defaultdict(lambda: {'vector_only':{'recall_at_k':0,'precision_at_k':0,'mrr':0,'coverage':0,'count':0}, 'hybrid':{'recall_at_k':0,'precision_at_k':0,'mrr':0,'coverage':0,'count':0}}),
       'failure_cases':{'vec_pass_hy_fail':[], 'hy_pass_vec_fail':[], 'both_failed':[]}
      }

for i in range(n):
    rvo = results_vo[i]
    rhy = results_hy[i]
    q = rvo.get('query')
    # assume expected source file first
    srcs = rvo.get('expected_source_files', [])
    base = os.path.basename(srcs[0]) if srcs else 'unknown'
    cat = cat_from_filename(base)

    mvo = rvo.get('metrics',{})
    mhy = rhy.get('metrics',{})

    for k in ['recall_at_k','precision_at_k','mrr','coverage']:
        agg['vector_only'][k] += mvo.get(k,0) or 0
        agg['hybrid'][k] += mhy.get(k,0) or 0
        agg['vector_only']['count'] += 1
        agg['hybrid']['count'] += 1
        agg['by_category'][cat]['vector_only'][k] += mvo.get(k,0) or 0
        agg['by_category'][cat]['hybrid'][k] += mhy.get(k,0) or 0
        agg['by_category'][cat]['vector_only']['count'] += 1
        agg['by_category'][cat]['hybrid']['count'] += 1

    # pass if recall_at_k > 0
    vec_pass = (mvo.get('recall_at_k',0) > 0)
    hy_pass = (mhy.get('recall_at_k',0) > 0)
    if vec_pass and not hy_pass:
        agg['failure_cases']['vec_pass_hy_fail'].append({'query':q,'source':base})
    if hy_pass and not vec_pass:
        agg['failure_cases']['hy_pass_vec_fail'].append({'query':q,'source':base})
    if (not hy_pass) and (not vec_pass):
        agg['failure_cases']['both_failed'].append({'query':q,'source':base})

# compute averages
for mode in ['vector_only','hybrid']:
    cnt = agg[mode]['count'] or 1
    for k in ['recall_at_k','precision_at_k','mrr','coverage']:
        agg[mode][k] = agg[mode][k] / cnt
    agg[mode].pop('count',None)

by_cat_out = {}
for cat,vals in agg['by_category'].items():
    out = {}
    for mode in ['vector_only','hybrid']:
        cnt = vals[mode]['count'] or 1
        out[mode] = {k: vals[mode][k]/cnt for k in ['recall_at_k','precision_at_k','mrr','coverage']}
    by_cat_out[cat]=out

summary = {
    'overall':{'vector_only':agg['vector_only'],'hybrid':agg['hybrid']},
    'by_category':by_cat_out,
    'failure_cases':agg['failure_cases'],
    'artifacts':{
        'vector_only': [f for f in os.listdir('artifacts/eval/vector_only') if f.startswith('eval_recursive')],
        'hybrid': [f for f in os.listdir('artifacts/eval/hybrid') if f.startswith('eval_recursive')]
    }
}

print(json.dumps(summary, indent=2))
