#!/usr/bin/env python

# WS client example

import sys
import time
import argparse
import asyncio
import threading
import websockets
import traceback
import pathlib
import ssl
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from websockets import ConnectionClosed

bin_path = pathlib.Path (__file__).parent

# Change these if/when necessary

arg_parser = argparse.ArgumentParser(description='the micronets websocket test client/proxy server')

arg_parser.add_argument ('--http-proxy-address', "-a", required=False, action='store', type=str,
                         default="localhost", help="specify the address to bind the proxy to")
arg_parser.add_argument ('--http-proxy-port', "-p", required=False, action='store', type=int,
                         default = 5001, help="specify the port to bind the proxy to")
arg_parser.add_argument ('--client-cert', "-cc", required=False, action='store', type=open,
                         default = bin_path.parent.joinpath ('lib/micronets-ws-test-client.pkeycert.pem'),
                         help="the client cert file")
arg_parser.add_argument ('--ca-cert', "-ca", required=False, action='store', type=open,
                         default = bin_path.parent.parent.joinpath ('lib/micronets-ws-root.cert.pem'),
                         help="the client cert file")
arg_parser.add_argument ("connect_uri", action='store', help="the uri for the server websocket")

args = arg_parser.parse_args ()

websocket = None
pending_requests = {}

async def init_connection(ssl_context, dest):
    scheme = 'wss' if ssl_context else 'ws'
    print (f"ws-test-client: Opening websocket to {dest}...")
    ws = await websockets.connect (dest, ssl=ssl_context)
    print (f"ws-test-client: Connected to {dest}.")
    print("ws-test-client: Sending HELLO message...")
    await send_hello_message (ws)
    print("ws-test-client: Waiting for HELLO message...")
    await wait_for_hello_message (ws)
    print("ws-test-client: HELLO handshake complete.")
    return ws

async def send_hello_message (websocket):
    global message_id
    message = json.dumps ( {'message': {'messageId': message_id, 
                                        'messageType': 'CONN:HELLO',
                                        'requiresResponse': False,
                                        'peerClass': 'micronets-ws-test-client',
                                        'peerId': '12345678' }} )
    message_id += 1
    print ("ws-test-client: > sending hello message: ", message)
    await websocket.send (message)

async def send_rest_message (websocket, message):
    global message_id
    message_id += 1
    print ("ws-test-client: > sending REST message: ", message)
    await websocket.send (message)

def check_message (message):
    message_body = check_json_field (message, 'message', dict, True)
    message_id = check_json_field (message_body, 'messageId', int, True)
    message_type = check_json_field (message_body, 'messageType', str, True)
    check_json_field (message_body, 'requiresResponse', bool, True)

async def wait_for_hello_message(websocket):
    raw_message = await websocket.recv ()
    message = json.loads (raw_message)
    print (f"ws-test-client: process_hello_messages: Received message: {message}")
    if not message:
        raise Exception("message does not appear to be json")
    check_message (message)

    message_type = message['message']['messageType']
    if message_type != "CONN:HELLO":
        raise Exception (f"Unexpected message while waiting for HELLO: {message_type}")

    print("ws-test-client: process_hello_messages: Received HELLO message")

async def receive (websocket):
    print ("ws-test-client: receive: starting...")
    global pending_requests
    while (True):
        message = await websocket.recv ()
        print (f"ws-test-client: < received: {message}")
        message_json = json.loads (message) ['message']
        if ('inResponseTo' in message_json):
            in_response_to_id = message_json ['inResponseTo']
            print (f"ws-test-client: ws_reader: Message {message_json['messageId']} "
                   f"is a response to {in_response_to_id} - signaling future #{in_response_to_id}")
            response_cond = pending_requests.pop (in_response_to_id)
            if (not response_cond or not isinstance (response_cond, threading.Condition)):
                print (f"ws-test-client: ws_reader: No condition found for message {in_response_to_id}!")
            else:
                with response_cond:
                    pending_requests [in_response_to_id] = message
                    response_cond.notify_all ()
        if (message_json ['messageType'] == 'REST:REQUEST'):
            print (f"ws-test-client: ws_reader: Found rest {message_json ['method']} request for {message_json ['path']}")
            await handle_rest_request (websocket, message_json)

def check_json_field (json_obj, field, field_type, required):
    '''Thrown an Exception of json_obj doesn't contain field and/or it isn't of type field_type'''
    if field not in json_obj:
        if required:
            raise Exception (f"message doesn't contain a '{field}' field")
        else:
            return None
    field_val = json_obj [field]
    if not isinstance (field_val, field_type):
        raise Exception (f"Field type for '{field}' field is not a {field_type}")
    return field_val

def get_websocket ():
    return websocket

class MyHTTPHandler (BaseHTTPRequestHandler):
    def do_HEAD (self):
        print ("Got HEAD request for", self.path)
    def do_GET (self):
        self.relay_message ()
    def do_POST (self):
        self.relay_message ()
    def do_PUT (self):
        self.relay_message ()
    def do_DELETE (self):
        self.relay_message ()

    def relay_message(self):
        global message_id
        websocket = get_websocket ()
        print (f"Got {self.command} request for {self.path}")

        if (not websocket): # And no HELLOACK received...
            self.send_error (503, message="The upstream websocket is not open")
            return

        request_id = message_id
        message_id += 1
        message = { 'messageId': request_id, 
                    'messageType': 'REST:REQUEST',
                    'requiresResponse': True,
                    'method': self.command,
                    'path': self.path}

        if content_length_val := self.headers['Content-Length']:
            content_length = int (content_length_val)
            del self.headers ['Content-Length']
            if (content_length > 0):
                if 'Content-Type' in self.headers:
                    data_format = self.headers ['Content-Type']
                    del self.headers ['Content-Type']
                else:
                    data_format = "application/json"
                if 'Content-Encoding' in self.headers:
                    del self.headers ['Content-Encoding']
                message_payload = self.rfile.read(content_length)
                print (f"  Payload: {message_payload}")
                message ['dataFormat'] = data_format
                if (data_format == "application/json"):
                    encoded_payload = json.loads (message_payload)
                else:
                    encoded_payload = message_payload.decode ('utf-8')
                message ['messageBody'] = encoded_payload

        if headers := [
            {'name': header_name, 'value': header_value}
            for header_name, header_value in self.headers.items()
        ]:
            message ['headers'] = headers
        message_json = json.dumps ({'message': message}, indent=2)

        print (f"ws-test-client: Relaying REST request to peer: {message_json}")
        request_future = asyncio.run_coroutine_threadsafe (send_rest_message (websocket, message_json), 
                                                           event_loop)
        print("ws-test-client: Waiting for send to complete...")
        request_future.result ()

        cond = threading.Condition ()
        pending_requests [request_id] = cond
        print (f"ws-test-client: Waiting for response to request #{request_id}...")
        with cond:
            cond.wait ()
        response = pending_requests.pop (request_id)
        print (f"ws-test-client: Received response to #{request_id}:", response)

        response_json = json.loads (response)
        response_message = response_json ['message']
        print (f"ws-test-client: response.json for #{request_id}:", json.dumps (response_message))
        if response_message['messageType'] != "REST:RESPONSE":
            raise Exception ("Response to message #{request_id} is not a REST:RESPONSE")
        self.send_response (response_message ['statusCode'])
        found_content_type = False
        found_content_length = False
        if ('headers' in response_message):
            for header in response_message ['headers']:
                header_name = header ['name']
                header_val = header ['val']
                print (f"ws-test-client: header {header_name} has value {header_val}")
                self.send_header (header_name, header_val)
                if (header_name == 'Content-Type'):
                    found_content_type = True
        message_body = None
        if ('messageBody' in response_message):
            data_format = response_message ['dataFormat']
            if (data_format == 'application/json'):
                message_body = json.dumps (response_message ['messageBody'], indent=2)
            else:
                message_body = response_message ['messageBody']
            print("ws-test-client: Found message body:", message_body)
            if not found_content_type:
                self.send_header ('Content-Type', data_format)
            self.send_header ('Content-Length', len (message_body))
        self.end_headers ()
        if (message_body):
            self.wfile.write (message_body.encode ('utf-8'))

        print (f"Done processing request for {self.path}")

class MyHTTPServerThread (threading.Thread):
    def __init__ (self):
        self.lock = threading.Lock ()
        try:
            self.lock.acquire ()
            self.httpd = None
            self.state = "ready"
            print ("MyHTTPServerThread.__init__(): state:", self.state)
            threading.Thread.__init__ (self)
        finally:
            self.lock.release ()

    def run (self):
        try:
            self.lock.acquire ()
            if (self.state == "ready"):
                server_address = (args.http_proxy_address, args.http_proxy_port)
                self.httpd = HTTPServer (server_address, MyHTTPHandler)
                self.state = "running"
                print (f"MyHTTPServerThread: Starting HTTP server on {args.http_proxy_address} port {args.http_proxy_port}...")
        finally:
            self.lock.release ()
        self.httpd.serve_forever ()

    def shutdown (self):
        try:
            self.lock.acquire ()
            if (self.state == "running"):
                print ("MyHTTPServerThread: Shutting down HTTP server...")
                self.httpd.shutdown ()
            self.state = "stopped"
        finally:
            self.lock.release ()

class ConsoleThread (threading.Thread):
    def __init__ (self):
        print ("ConsoleThread.__init__()")
        threading.Thread.__init__ (self)

    def run (self):
        time.sleep(1)
        print("ConsoleThread.run())")
        while (True):
            try:
                print ("Enter json message to send via websocket or \"quit\": ")
                # https://docs.python.org/3.6/library/json.html#module-json
                line = sys.stdin.readline()
                if line.startswith("quit"):
                    stop_everything()
                message = json.loads(line)
                check_message(message)
                print (f"sending message: {json.dumps(message, indent=4)}")
                ws = get_websocket()
                request_future = asyncio.run_coroutine_threadsafe(ws.send(line), event_loop)
                request_future.result()
            except Exception as ex:
                print(f"ConsoleThread: Caught exception: {ex}")

    def shutdown (self):
        print("ConsoleThread.shutdown()")

print ("Startup...")

message_id = 0

ssl_context = ssl.SSLContext (ssl.PROTOCOL_TLS_CLIENT)

# Setup the client's cert
print ("Loading test client certificate from", args.client_cert.name)
ssl_context.load_cert_chain (args.client_cert.name)

# Verify peer certs using the websocket root as the CA
print ("Loading CA certificate from", args.ca_cert.name)

ssl_context.load_verify_locations (cafile = args.ca_cert.name)
ssl_context.verify_mode = ssl.VerifyMode.CERT_REQUIRED
ssl_context.check_hostname = False

event_loop = asyncio.get_event_loop ()
my_http_thread = None
console_thread = None
try:
    websocket = event_loop.run_until_complete (asyncio.ensure_future (init_connection (ssl_context,
                                                                                       args.connect_uri)))
    my_http_thread = MyHTTPServerThread ()
    my_http_thread.start ()
    console_thread = ConsoleThread ()
    console_thread.start ()
    print("ws-test-client: Starting event loop...")
    event_loop.run_until_complete (receive (websocket))
except ConnectionClosed or IncompleteReadError as ex:
    print (f"ws-test-client: connection to {args.connect_uri} closed")
except Exception as Ex:
    print (f"ws-test-client: Caught an exception on connection to {args.connect_uri}: {Ex}")
    traceback.print_exc (file=sys.stdout)
finally:
    event_loop.close ()
    if (my_http_thread):
        my_http_thread.shutdown ()
    if (console_thread):
        console_thread.shutdown ()
