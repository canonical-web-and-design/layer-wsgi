# Core packages
import os
import socket
import subprocess
from time import sleep
from urllib.parse import urlunparse

# Third party packages
import yaml
from charmhelpers.core.hookenv import (
    log,
    relations_of_type,
    status_set,
    open_port,
    config
)
from charmhelpers.fetch import apt_install
from charmhelpers.core.templating import render
from charmhelpers.core.host import (
    service_reload,
    service_running,
    service_start,
)
from charms.reactive import hook, remove_state, set_state, when_all, all_states

# Local packages
from .lib.helpers import (
    build_url_host,
    get_user,
    delete_env_value,
    demote,
    is_port_open,
    get_env,
    set_env_values,
    variables_from_string,
)


# Read layer config, with defaults
layer_config = {
    'application_root': '/srv',
    'username': 'wsgi',
}
if os.path.exists('wsgi.yaml'):
    with open('wsgi.yaml') as config_yaml:
        layer_config.update(yaml.safe_load(config_yaml.read()))

# Store environment variables in the global environment file
env_file = "/etc/environment"


@hook('install', 'upgrade-charm')
def system_dependencies():
    """
    Install system dependencies
    """

    # Install system dependencies for this layer
    status_set('maintenance', '[wsgi] Setting up dependencies')
    log('[wsgi] Installing system dependencies')
    apt_install(['python3-pip', 'python-setuptools', 'circus', 'gunicorn3'])

    # Create user
    log('[wsgi] Ensuring the user {} exists'.format(layer_config['username']))
    get_user(layer_config['username'])

    set_state('wsgi.system.ready')


@hook('config-changed')
def configure_dependencies():
    """
    Install dependencies for the application
    """

    # Install custom dependencies
    status_set('maintenance', '[wsgi] Installing configured dependencies')
    extra_dependencies = config('apt_dependencies') or ""
    apt_install(extra_dependencies.split())

    # Globally set environment variables
    log('[wsgi] Setting environment variables in {}'.format(env_file))
    set_env_values(
        env_file,
        variables_from_string(config('environment_variables'))
    )

    set_state('wsgi.configured')


@hook('{mongo,postgres}-relation-{joined,changed,broken,departed}')
def database_attached():
    if all_states(
        'wsgi.configured', 'wsgi.source.available', 'wsgi.system.ready'
    ):
        start_application_service()


@when_all('wsgi.configured', 'wsgi.system.ready', 'wsgi.source.available')
def start_application_service():
    # Remove source.available to allow it to be re-triggered
    remove_state('wsgi.source.available')
    remove_state('wsgi.available')

    # Install application dependencies
    status_set('maintenance', '[wsgi] Installing application dependencies')

    cache_dir = config('pip_cache_dir')

    if os.path.isfile('requirements.txt'):
        if cache_dir:
            log('[wsgi] Installing pip dependencies from {}'.format(cache_dir))
            subprocess.check_call(
                [
                    'pip3', 'install',
                    '--no-index',
                    '--find-links', cache_dir,
                    '--requirement', 'requirements.txt',
                ],
                cwd=layer_config['application_root'],
                env=dict(LC_ALL='C.UTF-8', **get_env(env_file))
            )
        else:
            log('[wsgi] Installing pip dependencies from PyPi')
            subprocess.check_call(
                ['pip3', 'install', '--requirement', 'requirements.txt'],
                cwd=layer_config['application_root'],
                env=dict(LC_ALL='C.UTF-8', **get_env(env_file))
            )

    set_state('wsgi.ready')

    # Check for a database connection
    log('[wsgi] Checking for database connection')
    postgres_relations = relations_of_type('postgres')
    mongo_relations = relations_of_type('mongo')
    db_relation = None

    if postgres_relations:
        db_relation = postgres_relations[0]
        db_scheme = "postgresql"
    elif mongo_relations:
        db_relation = mongo_relations[0]
        db_scheme = "mongodb"

    if db_relation:
        db_host = db_relation.get('host') or db_relation.get('hostname')
        db_port = db_relation.get('port')
        log('[wsgi] Using database at {}:{}'.format(db_host, db_port))
        database_url = urlunparse(
            (
                db_scheme,
                build_url_host(
                    db_host, db_port,
                    db_relation.get('user'), db_relation.get('password')
                ),
                db_relation.get('database', ''),
                None,
                None,
                None
            )
        )
        set_env_values(env_file, {'DATABASE_URL': database_url})

        provision_command = layer_config.get('provision_command')

        if provision_command:
            status_set('maintenance', '[wsgi] Provisioning database')
            subprocess.check_call(
                provision_command.split(),
                cwd=layer_config['application_root'],
                env=get_env(env_file),
                preexec_fn=demote(get_user(layer_config['username']))
            )
    else:
        log('[wsgi] No database attached')
        delete_env_value(env_file, 'DATABASE_URL')

    # Open the port, ready
    status_set('maintenance', '[wsgi] Opening port {}'.format(config('port')))
    log('[wsgi] Opening port {}'.format(config('port')))
    open_port(config('port'))

    # Configure circus daemon to run gunicorn
    service_name = 'gunicorn3.service'
    service_file = '/etc/systemd/system/{}'.format(service_name)
    log('[wsgi] Writing systemd config to {}'.format(service_file))
    status_set('maintenance', '[wsgi] Preparing daemon')
    render(
        source='{}.j2'.format(service_name),
        target=service_file,
        perms=0o644,
        context={
            'application_root': layer_config['application_root'],
            'env_file': env_file,
            'wsgi_module': config('wsgi_module'),
            'user': layer_config['username'],
            'group': layer_config['username'],
            'port': config('port'),
            'env': get_env(env_file)
        }
    )
    subprocess.check_call(['systemctl', 'daemon-reload'])

    if service_running(service_name):
        log('[wsgi] Reloading {}'.format(service_name))
        service_reload(service_name)
    else:
        log('[wsgi] Starting {}'.format(service_name))
        service_start(service_name)

    # Try 5 times to check if the service started
    service_responding = False
    for attempt in range(0, 10):
        log('[wsgi] Waiting for service on port {} (attempt {})'.format(
            config('port'), attempt
        ))
        if service_running(service_name) and is_port_open(config('port')):
            service_responding = True
            break
        sleep(6)

    if service_responding:
        log('[wsgi] Service responded on port {}'.format(config('port')))
        status_set('active', '[wsgi] Service started on port {}'.format(
            config('port')
        ))
        set_state('wsgi.available')
    else:
        raise socket.error('Service not responding')


@when_all('website.available')
def send_port(http):
    http.configure(config('port'))
