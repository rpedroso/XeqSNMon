import os
from origamibot import OrigamiBot as Bot

# NODE_URL = 'http://localhost:9231'
NODE_URL = 'http://154.38.165.93:9231'

TOKEN = os.getenv('TOKEN')  # bot token
TO = os.getenv('TO')  # group chat id

if not TOKEN or not TO:
    raise ValueError('TOKEN and TO must be configured')

bot = Bot(TOKEN)
