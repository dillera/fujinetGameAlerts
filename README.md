README For GAS - Game Alert System

# Design
More info coming...


# System Setup
More info coming...


# Installation
More info coming...


# Deployment and Operation

### Using the supplied `create_service.bash` script

$ ~/fujinetGameAlerts$ deploy/create_service.bash gas 5100

$ ~/fujinetGameAlerts$ deploy/create_service.bash gasui 5101

### Issues
If you have not set the required env variables you will see this:

```
/fujinetGameAlerts$ deploy/create_service.bash gasui 5101
Error: Environment variable FA_SECRET_KEY is not set.
Error: Environment variable TWILIO_ACCT_SID is not set.
Error: Environment variable TWILIO_AUTH_TOKEN is not set.
Error: Environment variable TWILIO_TN is not set.
Error: Environment variable DISCORD_WEBHOOK is not set.
Error: Environment variable WORKING_DIRECTORY is not set.
Error: Environment variable PYTHON_ENV_PATH is not set.
```

Properly set the variables in your env and re-run the script.


### Monitoring Service

After Service is created:

In one window run:
$ journalctl -u gas -f &
$ journalctl -u gasui -f &

Then:
$ sudo systemctl restart gas.service
$ sudo systemctl restart gasui.service

$ sudo systemctl stop gas
$ sudo systemctl start gas

And watch the output. Fix any errors, if it's error free you should see:

```
Nov 01 systemd[1]: Started gas.
Nov 01 gunicorn[3789]:  [3789] [INFO] Starting gunicorn 21.2.0
Nov 01 gunicorn[3789]:  [3789] [INFO] Listening at: http://0.0.0.0:5100 (3789)
Nov 01 gunicorn[3789]:  [3789] [INFO] Using worker: sync
Nov 01 gunicorn[3789]:  [3807] [INFO] Booting worker with pid: 3807
Nov 01 gunicorn[3789]:  [3812] [INFO] Booting worker with pid: 3812
Nov 01 gunicorn[3789]:  [3813] [INFO] Booting worker with pid: 3813
Nov 01 gunicorn[3789]:  [3814] [INFO] Booting worker with pid: 3814
```

which indicates the service started up the flask application fronted with gunicorn. Errors will be obvious.

Then you can watch the logs:

~/fujinetGameAlerts$ tail -f logs/gas.log






# Managing Lobby Server

### Starting up:
cd ~/code/servers/lobby
$ ./lobbyPersist -evtaddr http://gas.6502.fun/fuji/game

### Stopping lobby:
# ps -ef |grep lobby
[process]
$ kill 143910


### Testing code in QA:

git commit -am 'andy updates for fga and gas qa'
git fetch
git rebase main
[check code]

Check Lobby:

Current Servers/Players:
http://fgs.qa.6502.fun:8080/

http://fgs.qa.6502.fun:8080/version
http://fgs.qa.6502.fun:8080/docs



# Setup 5 Card Stud QAServer  to point to our GAS server


root@ubuntu-s-1vcpu-1gb-nyc3-01:~/code/servers-fujinet/5cardstud/server/mock-server# diff lobbyClient.go ~/code/servers_tracking_andy/5cardstud/server/mock-server/lobbyClient.go 
15c15
<  LOBBY_ENDPOINT_UPSERT = "http://fujinet.online:8080/server"
---
>  LOBBY_ENDPOINT_UPSERT = "http://localhost:8080/server"
25c25
<  Serverurl: "https://5card.carr-designs.com/",
---
>  Serverurl: "http://lobby-qa.6502.fun:8081/",





# end

