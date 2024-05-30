# How to using XeqSNMon


## Intall requirements
```
$ pip install -r requirements.txt
```

## Run

copy config.py to config_local.py and change:
```
NODE_URL = <node to get info from>
```
then run:

```
$ TOKEN=<Bot token> TO=<Telegran chat id> python xeqsnmon.py
```

or copy config.py to config_local.py and change:

```
NODE_URL = <node to get info from>
TOKEN =  <Telegram bot token>
TO = <Group id to send notifications>
```

then run:
```
$ python xeqsnmon.py
```
