from app import telegram_bot
from conftest import CHECKS, create_job, upload, queue_render, finish


def test_telegram_denies_other_chats_and_requires_explicit_checks(operator, monkeypatch):
    monkeypatch.setenv('TELEGRAM_ALLOWED_CHAT_ID', '42')
    sent = []
    monkeypatch.setattr(telegram_bot, 'telegram_call', lambda method, params: sent.append((method, params)))
    telegram_bot.handle_message({'chat': {'id': 41}, 'text': '/jobs'})
    assert not sent
    job = create_job(operator)
    asset = upload(operator, job)
    render_id = finish(operator, queue_render(operator, job, asset['id']))
    telegram_bot.handle_message({'chat': {'id': 42}, 'text': '/aprovar ' + render_id})
    assert 'CONFIRMO' in sent[-1][1]['text']
    assert operator.get(f'/renders/{render_id}/export').status_code == 409
    telegram_bot.handle_message({'chat': {'id': 42}, 'text': '/aprovar ' + render_id + ' CONFIRMO'})
    assert 'Aprovação registrada' in sent[-1][1]['text']
    telegram_bot.handle_message({'chat': {'id': 42}, 'text': '/aprovar ' + render_id + ' CONFIRMO'})
    assert 'Não foi possível' in sent[-1][1]['text']  # replay never duplicates approval
