# WSGI charm layer

A [charm layer](https://jujucharms.com/docs/2.1/developer-layers) for serving a Python 3 application as a [WSGI service](https://en.wikipedia.org/wiki/Web_Server_Gateway_Interface).

## Usage

To implement this layer, add `layer:wsgi` in [your `layer.yaml`](https://jujucharms.com/docs/2.0/reference-layer-yaml):

``` yaml
includes: ['layer:wsgi', ...]
```

### Layer configuration

By default the layer will look for the WSGI application in `/srv`, and will run the WSGI service as the `wsgi` user. These settings can be overridden by including a `wsgi.yaml` in the root of your charm:

``` yaml
application_root: '{path}'
username: '{username}'
```

### Config options

The layer will add the following config options to the charm:

``` yaml
port: 80  # The port where the WSGI service should listen
provision_command: ""  # A command to run in the application directory before running the WSGI application - e.g. for provisioning the database
pip_cache_dir: ""  # The name of a folder within the application from which to install pip dependencies
wsgi_module: "wsgi:application"  # The python path to the WSGI module and application
wsgi_logfile_path: "/var/log/wsgi.service.log"  # Where to store logs for the WSGI service
apt_dependencies: ""  # A space-separated list of apt dependencies for the WSGI application
environment_variables: ""  # A space-separated list of environment variables to pass to the application. E.g.: 'VAR1=val1 VAR2=val2'
```

You can override the defaults by including these config options in your charm's `config.yaml` explicitly, with a new default settings. E.g. to set a new location for the `wsgi_module`:

``` yaml
options:
  # Defaults for WSGI layer config options
  wsgi_module:
    default: "webapp.wsgi:application"
```

### Providing the application

The WSGI application source code must be provided in `application_root` (`/srv` by default). This folder should contain the WSGI function, at the location specified in the `wsgi_module` setting (`wsgi:application` by default). If this folder contains a `requirements.txt` file specifying python dependencies, then these dependencies will be installed.

You must then tell the WSGI layer when the WSGI application is in place by triggering the `wsgi.source.available` [reactive state](https://pythonhosted.org/charms.reactive/), e.g.:

``` python
from charms.reactive import remove_state, set_state

@when('resources.build.available')
def update():
    set_state('wsgi.source.available')
```

Once the service has been started, the `wsgi.active` state will be set, which you can then use to do any final actions, e.g.:

``` python
from charmhelpers.core.hookenv import status_set

@when('wsgi.available')
def wsgi_running():
    status_set('active', 'WSGI service running')
```

## Relations

The WSGI layer adds the following relations to the charm:

### Provides

- `website`: An implementation of [the `http` interface](http://interfaces.juju.solutions/interface/http/)). This could be used attaching an [HAProxy](https://jujucharms.com/haproxy) load-balancer, for example.

### accepts

- `postgres`: An implementation of [the `pgsql` interface](http://interfaces.juju.solutions/interface/pgsql/), for attaching a PostgreSQL database.
- `mongo`: An implementation of [the `mongodb` interface](http://interfaces.juju.solutions/interface/mongodb/), for attaching a Mongo database.

Attaching either database type will result in the WSGI application being run with a `DATABASE_URL` environment variables, which will contain information about the database, for use by the WSGI application:

``` bash
DATABASE_URL="[postgresql|mongodb]://{db_user}:{db_password}@{db_host}:{db_port}/{database_name}"
```

## Debugging

The WSGI application is run with [Gunicorn](http://gunicorn.org/). The service is run with [systemd](https://wiki.debian.org/systemd), and the configuration will be installed into `/etc/systemd/system/gunicorn3.service`. Logs from the gunicorn service are sent to the syslog and can be inspected with [journalctl](https://www.freedesktop.org/software/systemd/man/journalctl.html), e.g.:

``` bash
journalctl -u gunicorn3.service
```
