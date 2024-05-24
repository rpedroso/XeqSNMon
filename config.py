import os
from origamibot import OrigamiBot as Bot

NODE_URL = 'http://localhost:9231/json_rpc'
# NODE_URL = 'http://154.38.165.93:9231/json_rpc'

TOKEN = os.getenv('TOKEN')  # bot token
TO = os.getenv('TO')  # group chat id

if not TOKEN or not TO:
    raise ValueError('Need env vars TOKEN and TO')


class FakeBot:
    def __init__(self, *args):
        pass

    def send_message(self, chat_id, message, **kwargs):
        print('_' * 60)
        print(message)
        print('_' * 60)


bot = FakeBot(TOKEN)
