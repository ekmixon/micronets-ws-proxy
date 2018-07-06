# Micronets DHCP Test Readme

## Setting up the proxy


### Generating the shared root certificate used for websocket communication:

This will produce the root certificate and key for validating/generating
leaf certificates used by peers of the websocket proxy:

```
bin/gen-ocf-root-cert --cert-basename lib/micronets-ws-root \
    --subject-org-name "Micronets Websocket Root Cert" \
    --expiration-in-days 3650
```

The shared root cert will be the basis for trust for all the entities
communicating via the websocket proxy. The websocket proxy will only 
trust peers that present a cert (and can accept a challenge from) the
proxy.

The `micronets-ws-root.key.pem` file generated by this script should
only be retained for the purposes of generating new leaf certs for the
websocket peers.

### To generate the cert to be used for the Websocket Proxy:

```
bin/gen-ocf-leaf-cert --cert-basename lib/micronets-ws-proxy \
    --subject-org-name "Micronets Websocket Proxy Cert" \
    --expiration-in-days 3650 \
    --ca-certfile lib/micronets-ws-root.cert.pem \
    --ca-keyfile lib/micronets-ws-root.key.pem

cat lib/micronets-ws-proxy.cert.pem lib/micronets-ws-proxy.key.pem > lib/micronets-ws-proxy.pkeycert.pem
```

The `lib/micronets-ws-proxy.pkeycert.pem` file must be deployed with the 
Micronets websocket proxy and well-protected. The `lib/micronets-ws-root.cert.pem`
must be added to the Proxy's list of trusted CAs. (and should really be the only
CA enabled for the proxy)

### Generating the cert to be used for the Micronets Manager:

```
bin/gen-ocf-leaf-cert --cert-basename lib/micronets-manager \
    --subject-org-name "Micronets Manager Cert" \
    --expiration-in-days 3650 \
    --ca-certfile lib/micronets-ws-root.cert.pem \
    --ca-keyfile lib/micronets-ws-root.key.pem

cat lib/micronets-manager.cert.pem lib/micronets-manager.key.pem > lib/micronets-manager.pkeycert.pem
```

The `lib/micronets-manager.pkeycert.pem` file must be deployed with the 
Micronets Manager to connect to the websocket proxy and `lib/micronets-ws-root.cert.pem` 
must be added to the Micronet's Manager CA list.

### To generate the cert to be used for the Micronets DHCP Manager:

```
bin/gen-ocf-leaf-cert --cert-basename lib/micronets-dhcp-manager \
    --subject-org-name "Micronets DHCP Manager Cert" \
    --expiration-in-days 3650 \
    --ca-certfile lib/micronets-ws-root.cert.pem \
    --ca-keyfile lib/micronets-ws-root.key.pem

cat lib/micronets-dhcp-manager.cert.pem lib/micronets-dhcp-manager.key.pem > lib/micronets-dhcp-manager.pkeycert.pem
```

The `lib/micronets-manager.pkeycert.pem` file must be deployed with the 
Micronets Manager to connect to the websocket proxy and `lib/micronets-ws-root.cert.pem` 
must be added to the Micronet's Manager CA list.

### To generate the cert to be used by the test client:

```
bin/gen-ocf-leaf-cert --cert-basename lib/micronets-ws-test-client \
    --subject-org-name "Micronets Websocket Test Client Cert" \
    --expiration-in-days 3650 \
    --ca-certfile lib/micronets-ws-root.cert.pem \
    --ca-keyfile lib/micronets-ws-root.key.pem

cat lib/micronets-ws-test-client.cert.pem lib/micronets-ws-test-client.key.pem > lib/micronets-ws-test-client.pkeycert.pem
```

## Websocket message format:

### Base message definition:

All messages exchanged via the websocket channel must have these fields:

```
{
   “message”: {
      “messageId”: <client-supplied session-unique string>,
      “messageType”: <string identifying the message type>,
      “requiresResponse”: <boolean>
      “inResponseTo”: <id string of the originating message> (optional)
   }
}
```

### HELLO message definition:

```
{
    "message": {
        "messageId": 0,
        "messageType": "CONN:HELLO",
        "peerClass": <string identifying the type of peer connecting to the websocket>,
        "peerId": <string uniquely identifying the peer in the peer class>,
        "requiresResponse": false
    }
}
```

Example:

```
{
    "message": {
        "messageId": 0,
        "messageType": "CONN:HELLO",
        "requiresResponse": false,
        "peerClass": "micronets-ws-test-client",
        "peerId": "12345678"
    }
}
```

### REST Request definition:

This defines a REST Request message:

```
“message”: {
   “messageType”: “REST:REQUEST”,
   “requiresResponse”: true,
   “method”: <HEAD|GET|POST|PUT|DELETE|…>,
   “path”: <URI path>,
   “queryStrings”: [{“name”: <name string>, “value”: <val string>}, …],
   “headers”: [{“name”: <name string>, “value”: <val string>}, …],
   “dataFormat”: <mime data format for the messageBody>
   “messageBody”: <either a string encoded according to the mime type, base64 string if dataFormat is “application/octet-stream”, or JSON object if dataFormat is “application/json”>
```

Note that Content-Length, Content-Type, and Content-Encoding should not be communicated via the "headers" element as they are conveyed via the dataFormat and messageBody elements. If the request is handled by a HTTP processing system, these header elements may need to be derived from dataFormat and messageBody.

Example GET request:

```
{
  "message": {
    "messageId": 3,
    "messageType": "REST:REQUEST",
    "requiresResponse": true,
    "method": "GET",
    "path": "/micronets/v1/dhcp/subnets",
    "headers": [
      {
        "name": "Host",
        "value": "localhost:5001"
      },
      {
        "name": "User-Agent",
        "value": "curl/7.54.0"
      },
      {
        "name": "Accept",
        "value": "*/*"
      }
    ]
  }
}
```

Example POST request:

```
{
  "message": {
    "messageId": 1,
    "messageType": "REST:REQUEST",
    "requiresResponse": true,
    "method": "POST",
    "path": "/micronets/v1/dhcp/subnets",
    "headers": [
      {
        "name": "Host",
        "value": "localhost:5001"
      },
      {
        "name": "User-Agent",
        "value": "curl/7.54.0"
      },
      {
        "name": "Accept",
        "value": "*/*"
      }
    ],
    "dataFormat": "application/json",
    "messageBody": {
      "subnetId": "mocksubnet007",
      "ipv4Network": {
        "network": "192.168.1.0",
        "mask": "255.255.255.0",
        "gateway": "192.168.1.1"
      },
      "nameservers": [
        "1.2.3.4",
        "1.2.3.5"
      ]
    }
  }
}
```

Example PUT request:

```
{
    "message": {
        "messageId": 3,
        "messageType": "REST:REQUEST",
        "requiresResponse": true,
        "method": "PUT",
        "path": "/micronets/v1/dhcp/subnets/mocksubnet007",
        "dataFormat": "application/json",
        "headers": [
           {"name": "Host", "value": "localhost:5001"},
           {"name": "User-Agent", "value": "curl/7.54.0"},
           {"name": "Accept", "value": "*/*"}
        ],
        "messageBody": {
            "ipv4Network": {
                "gateway": "192.168.1.3"
            }
        }
    }
}
```

### REST Response definition:

This defines a REST Response message:

```
{
    “message”: {
        “messageType”: “REST:RESPONSE”,
        "inResponseTo": <integer message ID of the REST:REQUEST that generated the response>
        “requiresResponse”: false,
        “statusCode”: <HTTP integer status code>,
        “reasonPhrase”: <HTTP reason phrase string>,
        “headers”: [{“name”: <name string>, “value”: <val string>}, ],
        “dataFormat”: <mime data format for the messageBody>,
        “messageBody”: <either a string encoded according to the dataFormat, base64 string if dataFormat is         “application/octet-stream”, or JSON object if dataFormat is “application/json”>
 “application/octet-stream”, or JSON object if dataFormat is “application/json”>
    }
}
```

Note that Content-Length, Content-Type, and Content-Encoding should not be communicated via the "headers" element as they are conveyed via the dataFormat and messageBody elements. If the request is handled by a HTTP processing system, these header elements may need to be derived from dataFormat and messageBody.

Example GET response:
```
{
    "message": { 
        "messageId": 2,
        "inResponseTo": 3,
        "messageType": "REST:RESPONSE",
        "reasonPhrase": null,
        "requiresResponse": false, 
        "statusCode": 200,
        "dataFormat": "application/json", 
        "messageBody": {
            "subnets": [
                {
                    "ipv4Network": {
                        "gateway": "192.168.30.2",
                        "mask": "255.255.255.0",
                        "network": "192.168.30.0"
                    }, 
                    "subnetId": "wireless-network-1"
                }, 
                {
                    "ipv4Network": {
                        "gateway": "192.168.40.1",
                        "mask": "255.255.255.0",
                        "network": "192.168.40.0"
                    }, 
                    "subnetId": "wired-network-3"
                },
                {
                    "ipv4Network": {
                        "gateway": "10.40.0.1",
                        "mask": "255.255.255.0",
                        "network": "10.40.0.0"
                    }, 
                    "nameservers": ["10.40.0.1"],
                    "subnetId": "testsubnet001"
                }
            ]
        }
    }
}
```

Example POST response:

```
{
    "message": {
        "messageId": 2,
        "inResponseTo": 1,
        "messageType": "REST:RESPONSE",
        "requiresResponse": false,
        "statusCode": 201
        "dataFormat": "application/json",
        "messageBody": {
            "subnet": {
                "subnetId": "mocksubnet007",
                "ipv4Network": {
                    "gateway": "192.168.1.1",
                    "mask": "255.255.255.0",
                    "network": "192.168.1.0"
                }, 
                "nameservers": ["1.2.3.4", "1.2.3.5"]
            }
        }
    }
}
```

Example PUT response:
```
 {
     "message": {
         "messageId": 2,
         "inResponseTo": 3,
         "messageType": "REST:RESPONSE",
         "requiresResponse": false,
         "statusCode": 200,
         "dataFormat": "application/json",
         "messageBody": {
             "subnet": {
                 "ipv4Network": {
                     "gateway": "192.168.1.3",
                     "mask": "255.255.255.0",
                     "network": "192.168.1.0"
                 },
                 "nameservers": ["1.2.3.4", "1.2.3.5"],
                 "subnetId": "mocksubnet007"
             }
         }
     }
 }
```

Example DELETE response:
```
{
    "message": {
        "messageId": 3,
        "inResponseTo": 5,
        "messageType": "REST:RESPONSE",
        "requiresResponse": false,
        "statusCode": 200
    }
}
```

### Event Message definition:

```
{
    “message”: {
        “messageType”: “EVENT:<client-supplied event name>”,
        “requiresResponse”: False,
        “dataFormat”: <mime data format for the messageBody>,
        “messageBody”: <either a string encoded according to the mime type, base64 string if dataFormat is “application/octet-stream”, or JSON object if dataFormat is “application/json”>
    }
}
```
