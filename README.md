# OPC UA Mock Server
Simple OPC UA mock server with REST API based on [opcua-asyncio](https://github.com/FreeOpcUa/opcua-asyncio). 
Configuration in a form of [yaml file](#configuration) can be easily written by hand or loaded directly from the 
mocked server. Requires Python 3.7 or higher.

## Installation
### Installation via pip
To be done...

### Manual installation
1) clone this repository
2) (optional) create and activate Python virtual environment
3) install dependencies by running `pip install -r requirements.txt`

## Configuration
The server is configured by a YAML configuration file. The file can be obtained by running the 
app in the [scanner mode](#default-app) or by creating it manually.

### Configuration file format

| Name | Type | Mandatory | Description | 
|---|---|---|---|
| server | structure | Yes | - | 
| server.endpoint | string | Yes | Listening IP and port of the OPC UA server | 
| server.name | string | Yes | Discovery name of the server |
| server.namespaces | list of strings | Yes | User defined server namespaces |
| server.security | structure | No | - |
| server.security.users | list of structures | No | List of users allowed to connect to the server |
| server.security.users[*].username | string | Yes, if the parent exists | Username in plaintext |
| server.security.users[*].password | string | Yes, if the parent exists | SHA256 hash of the user password | 
| server.security.policies | list of strings | No | Enabled [OPC UA policies](#supported-opc-ua-policies) |
| server.security.profiles | list of strings | No | Enabled [OPC UA profiles](#supported-opc-ua-profiles) |
| server.nodes | list of structures | Yes | - |
| server.nodes[*].nodeid | string | Yes | Valid NodeID formatted string |
| server.nodes[*].name | string | Yes | Browse name of the node |
| server.nodes[*].type | string | Yes | Type of the node - permitted values are variable and object |
| server.nodes[*].writable | bool | No | Default False. If True, OPC UA clients can write the variable. Ignored for objects. |
| server.nodes[*].samples | integer | No | Default 10. Number of values to historize. Ignored for objects. |
| server.nodes[*].value | any scalar value for type variable, structure for type object | Yes | If the type is variable default node value. If the type is object, recursive definition of the node is expected. |

For the documentation purposes, names of the structures within the configuration file are "flattened". For example, 
structure
```yaml
server: 
  namespaces:
    - ...
```
 translates to `server.namespaces`.

#### Supported OPC UA policies
 - NoSecurity
 - Basic256Sha256_Sign
 - Basic256Sha256_SignAndEncrypt
 - Basic256_SignAndEncrypt
 - Basic256_Sign
 - Basic128Rsa15_Sign
 - Basic128Rsa15_SignAndEncrypt

#### Supported OPC UA profiles
 - Anonymous - no authentication 
 - Username - username and password authentication

### Example configuration file
```yaml
server:
    endpoint: opc.tcp://0.0.0.0:4840
    name: My Test Server
    namespaces: # remember, only non-default namespaces are defined here
        - http://my.namespace  # ns=2
        - http://someother.namespace  # ns=3
nodes:
    - nodeid: ns=2;i=10000
      name: Var1
      value: 15
      type: variable
    - nodeid: ns=2;i=10001
      name: Var2
      value: 11
      type: variable
      writable: true
      samples: 15
    - nodeid: ns=2;i=10002
      name: Obj
      type: object
      value:
        - nodeid: ns=3;i=20001
          name: Var3
          value: 101
          type: variable
```


## Running
### Default app
After [installing](#installation) the app, it can be run by `python app/mockapp.py`. Script usage is
`mockapp.py [-h] [-s SCAN] -c CONFIG [-p [HTTP_PORT]]`, where
 - `--scan/-s opc.tcp://server-host-or-ip:4840` scans the server given by the URL and creates the configuration file
- `-p/--port` starts a server instance with the REST server on the given HTTP port
- `--config/-c file.yaml` creates the configuration file in case of the server scan or loads the configuration file in case of running the server

### Custom behavior
Users can define their own functions that can be called by a code or via the REST interface and also functions called
when a variable change occurs. Server can be also extended by a control loop that reacts to user inputs. 

File `example.py` shows how to define such functions. The server API
uses [asyncio](https://docs.python.org/3/library/asyncio.html), so all the functions must be treated that way. 

To interact with the server, object `MockServer` is used. Functions to be used by the user are `read`, `write`, 
`wait_for`, `on_change`, `on_call` and `call`. 

### Using REST
Via the REST API, user can call functions defined by `on_call`, read all the variables and list registered
functions and `on_change` callbacks. It can be accessed via http on the port chosen when starting the app.
Documentation of the API is hosted by the application itself on `/docs` endpoint (e.g., `http://localhost:8080/docs`) 
or by `openapi.json` file located at (e.g., `http://localhost:8080/openapi.json`). All the API functions are served 
on `/api/` endpoint. 

Currently, there is no front-end interface. Nevertheless, `/docs` endpoint can be used to execute queries.
