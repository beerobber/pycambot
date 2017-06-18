import requests
import time

camctl = 'http://10.0.1.31/cgi-bin/ptzctrl.cgi?ptzcmd&'

#commands = ['posset&0', 'left&10&10', 'right&5&5', 'right&5&5', 'right&5&5', 'ptzstop&0&0', 'poscall&0']
commands = ['posset&0', 'up&2&6', 'p', 'left&9&1', 'p', 'ptzstop&1&1', 'poscall&0']

for command in commands:
    print command
    if command == 'p':
        time.sleep(2)
        continue
    url = camctl + command
    r = requests.get(url=url)
    print r.status_code

