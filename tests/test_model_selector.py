import pytest
import httpx
from app import model_selector as selector
from conftest import create_job, upload, image_bytes


def assessment(**overrides):
    return selector.Assessment(**{**dict(naturalness=.95, context_match=.95, framing=.95,
                                        editability=.95, confidence=.95, reject=False, reason='Compatível com a peça'), **overrides})


def fake_search(query, per_page):
    offset = 0 if query == 'summer fashion' else 3
    return [{'id': i+offset, 'url': f'https://www.pexels.com/photo/{i+offset}',
             'photographer': 'Test', 'image_url': f'https://images.pexels.com/photos/{i+offset}/test.jpg'} for i in range(3)]


def setup(monkeypatch, scores):
    calls=[]
    def evaluate(prompt, images, schema):
        calls.append((prompt, len(images)))
        if schema is selector.Profile:
            return selector.Profile(garment='Shorts', context='Verão casual; pernas visíveis', queries=['summer fashion', 'casual outdoor shorts'])
        return scores.pop(0)
    monkeypatch.setattr(selector, 'vision', evaluate)
    monkeypatch.setattr(selector, 'search_models', fake_search)
    monkeypatch.setattr(selector, 'download_photo', lambda url: image_bytes())
    return calls


def test_winter_and_artificial_candidates_rejected_and_second_search_used(monkeypatch):
    calls=setup(monkeypatch,[assessment(context_match=.1, reason='Ambiente de inverno'),
                            assessment(naturalness=.2, reason='Artificial'), assessment(framing=.2),
                            assessment(editability=.3), assessment(), assessment(confidence=.2)])
    report, chosen=selector.select_model(image_bytes())
    assert report['status']=='SELECTED' and chosen[1]['id']==4
    assert len(report['candidates'])==6
    assert report['candidates'][0]['accepted'] is False
    assert report['rights_review_required'] is True
    assert calls[0][1]==1 and all(n==2 for _,n in calls[1:])


def test_all_bad_candidates_require_operator(monkeypatch):
    setup(monkeypatch,[assessment(reject=True) for _ in range(6)])
    report, chosen=selector.select_model(image_bytes())
    assert chosen is None and report['status']=='NEEDS_OPERATOR'


def test_best_candidate_selected_not_first_hit(monkeypatch):
    setup(monkeypatch,[assessment(naturalness=.81),assessment(),assessment(confidence=.1)])
    report, chosen=selector.select_model(image_bytes())
    assert chosen[1]['id']==1 and len(report['candidates'])==3


def test_duplicate_photos_not_evaluated_twice(monkeypatch):
    setup(monkeypatch,[assessment(reject=True) for _ in range(3)])
    monkeypatch.setattr(selector,'search_models',lambda q,per_page:fake_search('summer fashion',per_page))
    report,_=selector.select_model(image_bytes())
    assert len(report['candidates'])==3


@pytest.mark.parametrize('url',['http://images.pexels.com/photos/1/a.jpg','https://evil.test/photos/1/a.jpg',
                               'https://images.pexels.com.evil.test/photos/1/a.jpg','https://user@images.pexels.com/photos/1/a.jpg',
                               'https://images.pexels.com:8443/photos/1/a.jpg'])
def test_external_downloads_rejected(url):
    with pytest.raises(ValueError):
        selector.download_photo(url)


def test_api_saves_selected_model_with_provenance(operator,monkeypatch):
    setup(monkeypatch,[assessment(),assessment(),assessment()])
    job=create_job(operator)
    garment=upload(operator,job)
    result=operator.post(f'/jobs/{job}/select-model',json={'garment_asset_id':garment['id']})
    assert result.status_code==200,result.text
    selected=result.json()['selected_asset_id']
    assets=operator.get(f'/jobs/{job}/assets').json()
    asset=next(a for a in assets if a['id']==selected)
    assert asset['kind']=='model' and 'PENDENTE' in asset['rights_evidence']
    import json
    assert json.loads(asset['metadata'])['matched_garment_id']==garment['id']
    assert operator.get(f'/jobs/{job}/audit').json()[-1]['action']=='MODEL_SELECTION_COMPLETED'


def test_selection_missing_credentials_creates_no_fake_model(operator,monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('GEMINI_VISION_MODEL',raising=False)
    job=create_job(operator)
    garment=upload(operator,job)
    assert operator.post(f'/jobs/{job}/select-model',json={'garment_asset_id':garment['id']}).status_code==503
    assert len(operator.get(f'/jobs/{job}/assets').json())==1


def test_vision_contract(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','fixture')
    monkeypatch.setenv('GEMINI_VISION_MODEL','vision-test')
    client=httpx.Client
    def service(req):
        import json
        body=json.loads(req.content)
        assert body['generationConfig']['responseMimeType']=='application/json'
        assert len(body['contents'][0]['parts'])==3
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':assessment().model_dump_json()}]}}]})
    monkeypatch.setattr(httpx,'Client',lambda **kw:client(transport=httpx.MockTransport(service),**kw))
    assert selector.vision('compare',[image_bytes(),image_bytes()],selector.Assessment).context_match==.95
