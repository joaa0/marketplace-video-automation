from app import config
"""Optional Telegram long-polling approval interface. Never publishes videos."""
import json
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.db import connect, init_db
from app.main import approve_render, ApprovalInput


def telegram_call(method: str, params: dict):
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN não configurado')
    data = urlencode(params).encode()
    request = Request(f'https://api.telegram.org/bot{token}/{method}', data=data)
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('Telegram rejeitou a operação')
    return result['result']


def handle_message(message: dict):
    chat_id = message['chat']['id']
    allowed = os.getenv('TELEGRAM_ALLOWED_CHAT_ID', '').strip()
    if not allowed or str(chat_id) != allowed:
        return  # deny by default; do not disclose data
    text = message.get('text', '').strip()
    if text == '/start' or text == '/ajuda':
        answer = ('Comandos:\n/jobs — tarefas recentes\n/aprovar ID CONFIRMO — confirma vídeo, SKU, direitos, legenda, preço e estoque\n'
                  'A publicação automática está desativada.')
    elif text == '/jobs':
        with connect() as db:
            rows = db.execute('SELECT id,status FROM jobs ORDER BY created_at DESC LIMIT 10').fetchall()
        answer = '\n'.join(f'{r["id"]}: {r["status"]}' for r in rows) or 'Nenhuma tarefa.'
    elif text.startswith('/aprovar '):
        arguments = text.split()
        if len(arguments) != 3 or arguments[2] != 'CONFIRMO':
            telegram_call('sendMessage', {'chat_id': chat_id, 'text': 'Revise o vídeo pela API autenticada e confirme SKU, direitos, legenda, preço e estoque. Depois: /aprovar ID CONFIRMO'})
            return
        render_id = arguments[1]
        try:
            result = approve_render(render_id, ApprovalInput(reviewer=f'telegram:{chat_id}', sku_verified=True, rights_verified=True, caption_verified=True, price_availability_verified=True))
            answer = f'Aprovação registrada: {result["approval_id"]}. Publicação automática desativada.'
        except Exception:
            answer = 'Não foi possível aprovar. Verifique ID, versão e integridade do arquivo.'
    else:
        answer = 'Comando desconhecido. Use /ajuda.'
    telegram_call('sendMessage', {'chat_id': chat_id, 'text': answer[:3900]})


def run():
    init_db()
    if not os.getenv('TELEGRAM_ALLOWED_CHAT_ID'):
        raise RuntimeError('Configure TELEGRAM_ALLOWED_CHAT_ID antes de iniciar')
    with connect() as db:
        row = db.execute("SELECT value FROM bot_state WHERE key='telegram_offset'").fetchone()
    offset = int(row['value']) if row else None
    while True:
        try:
            params = {'timeout': 25, 'allowed_updates': json.dumps(['message'])}
            if offset is not None:
                params['offset'] = offset
            for update in telegram_call('getUpdates', params):
                if 'message' in update:
                    handle_message(update['message'])
                offset = update['update_id'] + 1
                with connect() as db:
                    db.execute("INSERT INTO bot_state VALUES ('telegram_offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(offset),))
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f'Falha temporária no Telegram: {type(exc).__name__}; nova tentativa em 5s')
            time.sleep(5)


if __name__ == '__main__':
    run()
