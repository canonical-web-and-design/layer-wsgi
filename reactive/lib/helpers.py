import os
import pwd
import re
import socket
import subprocess


# Helper functions
# ===
def demote(user):
    """
    A closure for demoting permissions to a specified user and group,
    usually for passing to subprocess's "preexec_fn" argument

    From: https://stackoverflow.com/a/6037494/613540
    """

    def demotion():
        os.setgid(user.pw_uid)
        os.setuid(user.pw_gid)
    return demotion


def is_port_open(port):
    """
    Check if a given local port responds
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(('127.0.0.1', port)) == 0


def get_user(username):
    """
    Get or create user
    """

    try:
        user = pwd.getpwnam(username)
    except KeyError:
        subprocess.check_call(['useradd', username])
        user = pwd.getpwnam(username)

    return user


def build_url_host(domain, port=None, username=None, password=None):
    """
    Build the host part of a URL from a domain, port, username and password

    > _build_url_host('example.com')
    'example.com'

    > _build_url_host('example.com', 8080)
    'example.com:8080'

    > _build_url_host('example.com', 8080, 'robin')
    'robin@example.com:8080'

    > _build_url_host('example.com', 8080, 'robin', 'mypassword')
    'robin:mypassword@example.com:8080'
    """

    host = domain

    if port:
        host = "{0}:{1}".format(domain, port)

    if username:
        credentials = username

        if password:
            credentials = "{0}:{1}".format(
                username, password
            )

        host = "{0}@{1}".format(credentials, host)

    return host


def variables_from_string(variables_string):
    """
    Split a string like:
    var1=val1 var2=val2
    """

    variables = {}

    for declaration in variables_string.split():
        variable_name, value = declaration.split('=')

        variables[variable_name] = value

    return variables


def get_env(filepath):
    """
    Read a file of environment variables, returning them as a dictionary
    """

    env_vars = {}

    with open(filepath) as env_file:
        for env_line in env_file.readlines():
            # Is this line a bash variable?
            if re.match(r"^[a-zA-Z_]+[a-zA-Z0-9_]*=", env_line):
                key, value = env_line.strip().split('=', 1)
                env_vars[key] = value

    return env_vars


def set_env_values(filepath, incoming_variables):
    """
    Update a value in a file containing environment variables
    """

    env_lines = []
    found = []

    with open(filepath) as env_file:
        for env_line in env_file.readlines():
            key = None
            if re.match(r"^[a-zA-Z_]+[a-zA-Z0-9_]*=", env_line):
                key, value = env_line.strip().split('=', 1)

            if key in incoming_variables:
                new_line = "{key}={value}\n".format(
                    key=key,
                    value=incoming_variables[key]
                )
                found.append(key)
                env_lines.append(new_line)
            else:
                env_lines.append(env_line)

    for key, value in incoming_variables.items():
        if key not in found:
            new_line = "{key}={value}\n".format(
                key=key,
                value=value
            )
            env_lines.append(new_line)

    with open(filepath, 'w') as env_file:
        env_file.writelines(env_lines)

    return env_lines


def delete_env_value(filepath, target_key):
    """
    Remove a value from an environment file
    """

    env_lines = []

    with open(filepath) as env_file:
        for env_line in env_file.readlines():
            if not env_line.startswith(target_key + '='):
                env_lines.append(env_line)

    with open(filepath, 'w') as env_file:
        env_file.writelines(env_lines)

    return env_lines
