#!/usr/bin/env python

# WS server that sends messages at random intervals

import asyncio
import datetime
import random
import websockets

import http.server
import socketserver
import os

class ServerController:
    def start_servers(self):
        asyncio.run(self._start_servers)
    async def _start_servers(self,HTTPPORT=8000,WSPORT=5678):
        http_task = asyncio.create_task(start_http_server(HTTPPORT))
        #ws_task = asyncio.create_task(start_ws_server(WSPORT))
        await http_task
        #await ws_task
    async def _start_http_server(self,PORT):
        web_dir = os.path.join(os.path.dirname(__file__), 'buzzer_html')
        os.chdir(web_dir)

        Handler = http.server.SimpleHTTPRequestHandler
        httpd = socketserver.TCPServer(("", PORT), Handler)
        print("serving at port", PORT)
        httpd.serve_forever()
#     async def _start_ws_server(self,PORT)
#         start_ws_server = websockets.serve(time, "127.0.0.1", 5678)
#         asyncio.get_event_loop().run_until_complete(start_ws_server)
#         asyncio.get_event_loop().run_forever()

# async def time(websocket, path):
#     while True:
#         now = datetime.datetime.utcnow().isoformat() + "Z"
#         await websocket.send(now)
#         await asyncio.sleep(random.random() * 3)

# start_server = websockets.serve(time, "127.0.0.1", 5678)

# asyncio.get_event_loop().run_until_complete(start_server)
# print('starting')
# asyncio.get_event_loop().run_forever()

# print('done')

sc = ServerController()
sc.start_servers()