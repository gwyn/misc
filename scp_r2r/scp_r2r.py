#!/usr/bin/python
#
# Secure copy between two remote hosts
#
# Copyright (c)2010-2022 by Gwyn Connor (gwyn.connor at googlemail.com)
# License: GNU Lesser General Public License
#          (http://www.gnu.org/copyleft/lesser.txt)
#
# This script allows to transfer files between two remote hosts. It uses a
# local SSH Agent and Agent Forwarding for authentication. Therefore, the
# private key files of the involved hosts never leave the machine this script
# runs on.
#
# Configuration:
#   Use the variables at the top of this script to set it up:
#     SSH_PATH           path to ssh
#     SSH_AGENT_PATH     path to ssh-agent
#     SSH_ADD_PATH       path to ssh-add
#     SSH_CONFIG_FILE    path to ssh client configuration file
#
#   All servers must be configured in your SSH client configuration file, see:
#     man 5 ssh_config
#
#   Example:
#     Host myserver1
#       User myremoteuser
#       Hostname myserver1.example.org
#       Port 2222
#       IdentityFile /path/to/id_rsa
#
# Notes for Microsoft Windows and PAGEANT users:
#   Install ssh-pageant
#     https://github.com/cuviper/ssh-pageant
#   Set global script variable SSH_AGENT_PATH to ssh-pageant path, e.g.:
#     SSH_AGENT_PATH = '/cygdrive/c/bin/ssh-pageant'
#
# References:
#   [1] A hack to copy files between two remote hosts using Python,
#         by Eliot, 2010-02-08
#         http://www.saltycrane.com/blog/2010/02/hack-copy-files-between-two-remote-hosts-using-python/
#   [2] An Illustrated Guide to SSH Agent Forwarding, by Steve Friedl
#         http://www.unixwiz.net/techtips/ssh-agent-forwarding.html#fwd
#   [3] SSH: The Secure Shell, The Definitive Guide, 2.5. The SSH Agent,
#         by Daniel J. Barrett and Richard E. Silverman
#         http://docstore.mik.ua/orelly/networking_2ndEd/ssh/ch02_05.htm

import sys
import os
import subprocess
import re
import fnmatch
import optparse

SSH_PATH = '/usr/bin/ssh'
#SSH_AGENT_PATH = '/usr/bin/ssh-agent'
SSH_AGENT_PATH = '/cygdrive/c/bin/ssh-pageant'
SSH_ADD_PATH = '/usr/bin/ssh-add'
SSH_CONFIG_FILE = os.path.expanduser('~/.ssh/config')

__version__ = '0.12.0106' # x.y.MMDD

class ScpError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)
 
def debug(message):
    global verbose
    if verbose:
        print message

class SSHConfig (object):
    """
    Extracted from the paramiko project, (C)2006-2007 Robey Pointer
       http://www.lag.net/paramiko/
       http://github.com/robey/paramiko/blob/master/paramiko/config.py
    License: GNU Lesser General Public License 2.1
             (http://www.gnu.org/licenses/lgpl-2.1.txt)
    """
    def __init__(self):
        self._config = [ { 'host': '*' } ]

    def parse(self, file_obj):
        configs = [self._config[0]]
        for line in file_obj:
            line = line.rstrip('\n').lstrip()
            if (line == '') or (line[0] == '#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip().lower()
            else:
                # find first whitespace, and split there
                i = 0
                while (i < len(line)) and not line[i].isspace():
                    i += 1
                if i == len(line):
                    raise Exception('Unparsable line: %r' % line)
                key = line[:i].lower()
                value = line[i:].lstrip()

            if key == 'host':
                del configs[:]
                # the value may be multiple hosts, space-delimited
                for host in value.split():
                    # do we have a pre-existing host config to append to?
                    matches = [c for c in self._config if c['host'] == host]
                    if len(matches) > 0:
                        configs.append(matches[0])
                    else:
                        config = { 'host': host }
                        self._config.append(config)
                        configs.append(config)
            else:
                for config in configs:
                    config[key] = value

    def lookup(self, hostname):
        matches = [x for x in self._config if fnmatch.fnmatch(hostname, x['host'])]
        # sort in order of shortest match (usually '*') to longest
        matches.sort(lambda x,y: cmp(len(x['host']), len(y['host'])))
        ret = {}
        for m in matches:
            ret.update(m)
        del ret['host']
        return ret

def read_ssh_config():
    sshconfig = SSHConfig()
    sshconfig.parse(open(SSH_CONFIG_FILE, 'r').readlines())
    return sshconfig

def run_command(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, env=os.environ):
    debug('Command: %s' % ' \\\n  '.join(command))
    try:
        process = subprocess.Popen(command,
            stdin=stdin, stdout=stdout, stderr=stderr, env=env)
        debug('Pid: %s' % process.pid)
        output = process.communicate()[0]
        ret = process.poll()
        if ret:
            raise ScpError('Process error %d' % ret)
        return output
    except OSError, e:
        raise ScpError('Cannot start process: %s, %s' % (command, e))

def get_ssh_agent():
    return {'SSH_AUTH_SOCK': os.environ.get('SSH_AUTH_SOCK')} \
        if os.environ.has_key('SSH_AUTH_SOCK') else None

def ssh_agent_start():
    debug('Starting ssh-agent')
    agent = {}
    output = run_command([SSH_AGENT_PATH])
    output_pattern = '(SSH_AUTH_SOCK|SSH_AGENT_PID|SSH_PAGEANT_PID)=([^;]+);'
    m = re.findall(output_pattern, output, re.DOTALL)
    if m:
        agent = dict((k, v.strip("'")) for (k, v) in m)
        debug('Agent sock: %s' % agent['SSH_AUTH_SOCK'])
        debug('Agent pid: %s' % get_ssh_agent_pid(agent))
    else:
        raise ScpError('Cannot determine agent data from output: %s' % output)
    return agent

def get_ssh_agent_pid(agent):
    return agent['SSH_AGENT_PID'] if agent.has_key('SSH_AGENT_PID') else \
        agent['SSH_PAGEANT_PID'] if agent.has_key('SSH_PAGEANT_PID') else \
        None

def get_ssh_agent_env(agent):
    env = os.environ
    env.update(agent)
    return env

def ssh_agent_load_keys(agent, identity_files):
    if not identity_files:
        return
    debug('Loading keys into ssh-agent')
    command = [SSH_ADD_PATH]
    command.extend(identity_files)
    env = get_ssh_agent_env(agent)
    run_command(command, stdin=sys.stdin, stdout=sys.stdout, env=env)

def ssh_agent_stop(agent):
    debug('Stopping ssh-agent')
    command = [SSH_AGENT_PATH, '-k']
    env = get_ssh_agent_env(agent)
    run_command(command, env=env)

def scp(agent, host1, host2, options):
    debug('Starting scp')
    if options.push:
        connect_host = host1
        remote_host = host2
        source = host1['path']
        target = '%s:%s' % (host2['config']['hostname'], host2['path'])
    else:
        connect_host = host2
        remote_host = host1
        source = '%s:%s' % (host1['config']['hostname'], host1['path'])
        target = host2['path'] if host2['path'] else '~'
    command = [SSH_PATH,
        '-A',
        '-t']
    if options.verbose:
        command.append('-v')
    command.extend([
        connect_host['name'],
        'scp',
        '-p'])
    if options.verbose:
        command.append('-v')
    if options.limit:
        command.extend(['-l', str(options.limit)])
    if options.recursive:
        command.append('-r')
    if options.compression:
        command.append('-C')
    command.extend(['-o%s=%s' % (option, value)
                       for option, value in remote_host['config'].items()
                       if option not in ['identityfile', 'hostname']])
    command.extend([
        source,
        target
    ])
    env = get_ssh_agent_env(agent)
    run_command(command, stdin=sys.stdin, stdout=sys.stdout, env=env)

def get_term_info():
    """ Returns terminal size as tuple (rows, columns) """
    import fcntl, struct, termios, sys
    term_info = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ,
        struct.pack("HH", 0, 0))
    return struct.unpack("HH", term_info)

def columnize(list, display_width):
    """ Returns a columnized string of the given list """
    import math
    max_entry_width = sorted([len(entry) for entry in list])[-1]
    column_width = (max_entry_width + 2)
    columns = display_width / column_width
    rows = int(math.ceil(len(list) / float(columns)))
    result = ''
    for row in range(0, rows):
        for column in range(0, columns):
            list_index = column*rows + row
            if list_index < len(list):
                result += ('%-' + str(max_entry_width) + 's  ') \
                    % list[list_index]
        result += '\n'
    return result

def list_known_hosts(sshconfig):
    hosts = [entry['host'] for entry in sshconfig._config
                           if entry['host'] != '*']
    if hosts:
        print 'List of known hosts (%s):' % SSH_CONFIG_FILE
        print columnize(hosts, display_width=get_term_info()[1])

def main_transfer(host1, host2, options):
    sshconfig = read_ssh_config()
    try:
        host1['config'] = sshconfig.lookup(host1['name'])
        host2['config'] = sshconfig.lookup(host2['name'])
        if not host1['config']:
            list_known_hosts(sshconfig)
            raise ScpError('Unknown host "%s".\n' % host1['name']
                + 'Please add it to the SSH config file: %s' % SSH_CONFIG_FILE)
        if not host2['config']:
            list_known_hosts(sshconfig)
            raise ScpError('Unknown host "%s".\n' % host2['name']
                + 'Please add it to the SSH config file: %s' % SSH_CONFIG_FILE)

        agent = get_ssh_agent()
        agent_started = False
        if not agent:
            agent = ssh_agent_start()
            agent_started = True
        try:
            identity_files = []
            if host1['config'].has_key('identityfile'):
                identity_files.append(host1['config']['identityfile'])
            if host2['config'].has_key('identityfile'):
                identity_files.append(host2['config']['identityfile'])
            ssh_agent_load_keys(agent, identity_files)
            scp(agent, host1, host2, options)
        finally:
            if agent_started:
                ssh_agent_stop(agent)
    except ScpError, e:
        print 'Error: ', e.value
        sys.exit(2)

def main():
    global verbose

    usage = 'Usage: %prog [options] host1:path1 host2:path2'
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose',
        default=False, help='verbose mode')
    parser.add_option('--push', action='store_true', dest='push',
        default=True, help='connect to host1 and push data to host2 [default]')
    parser.add_option('--pull', action='store_false', dest='push',
        help='connect to host2 and pull data from host1')
    parser.add_option('-l', type='int', dest='limit',
        help='limits the used bandwidth, specified in kbit/s')
    parser.add_option('-r', action='store_true', dest='recursive',
        help='recursively copy entire directories')
    parser.add_option('-C', action='store_false', dest='compression',
        help='enable compression')
    (options, args) = parser.parse_args()
    if len(args) != 2:
        parser.error('please specify exactly two hosts')

    verbose = options.verbose
    host1 = {}
    host2 = {}
    try:
        host1['name'], host1['path'] = args[0].split(':')
        host2['name'], host2['path'] = args[1].split(':')
    except (IndexError, ValueError):
        parser.error('host arguments must be in the form "hostname:path"');

    main_transfer(host1, host2, options)

if __name__ == "__main__":
    main()

