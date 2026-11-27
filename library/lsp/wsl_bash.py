"""Start bash-language-server without indexing Windows drive mounts for shell completions."""
import os
import re
import shutil
import sys


def server_environment(env):
    if env.get('SAGE_BASH_LSP_FULL_PATH') == '1':
        return env
    entries = env.get('PATH', '').split(os.pathsep)
    native = (path for path in entries if not re.match(r'^/mnt/[a-zA-Z](?:/|$)', path))
    return {**env, 'PATH': os.pathsep.join(dict.fromkeys(native))}


if __name__ == '__main__':
    binary = shutil.which('bash-language-server')
    if not binary:
        sys.exit('bash-language-server is missing from PATH')
    env = server_environment(os.environ)
    if not shutil.which('node', path=env['PATH']) and shutil.which('node'):
        env = os.environ
    os.execve(binary, [binary, *sys.argv[1:]], env)
