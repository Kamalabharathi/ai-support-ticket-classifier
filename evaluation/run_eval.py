import json
from pathlib import Path
from app.model import get_classifier
from app.workflow import make_graph


def main():
    classifier = get_classifier()
    graph = make_graph(classifier)
    cases = [json.loads(line) for line in (Path(__file__).parent / 'benchmark.jsonl').read_text().splitlines() if line.strip()]
    matches_category = matches_team = 0
    errors = 0
    for case in cases:
        result = graph.invoke({'raw_ticket': case['text']})
        got = (result.get('classification') or {}).get('issue_category')
        team = result.get('assigned_team')
        matches_category += got == case['expected_category']
        matches_team += team == case['expected_team']
        errors += result.get('outcome') != 'classified'
        print(json.dumps({'text': case['text'], 'expected': case['expected_category'], 'predicted': got, 'team': team, 'outcome': result.get('outcome')}))
    print(json.dumps({'provider': type(classifier).__name__, 'cases': len(cases),
                      'category_accuracy': matches_category/len(cases),
                      'team_accuracy': matches_team/len(cases), 'failures': errors}, indent=2))
    print('Note: six examples are a smoke benchmark, not a validated production evaluation.')

if __name__ == '__main__':
    main()
