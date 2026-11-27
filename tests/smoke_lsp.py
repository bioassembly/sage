"""Exercise the selected language servers in an empty workspace over LSP stdio."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from library import profiles
from library.lsp.provision import native_command


async def exercise(name, command, project):
    binary = shutil.which(command[0])
    if not binary:
        raise ValueError(f'{name}: missing {command[0]} on PATH')
    proc = await asyncio.create_subprocess_exec(binary, *command[1:], cwd=project,
        env={**os.environ, 'XDG_CACHE_HOME': str(project / '.cache')},
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)

    def send(message):
        data = json.dumps({'jsonrpc': '2.0', **message}).encode()
        proc.stdin.write(f'Content-Length: {len(data)}\r\n\r\n'.encode() + data)

    async def response(identifier):
        while True:
            header = await proc.stdout.readuntil(b'\r\n\r\n')
            fields = dict(line.lower().split(b':', 1) for line in header.strip().splitlines())
            reply = json.loads(await proc.stdout.readexactly(int(fields[b'content-length'])))
            if 'method' in reply and 'id' in reply:
                result = [{} for _ in reply.get('params', {}).get('items', [])] if reply['method'] == 'workspace/configuration' else None
                send({'id': reply['id'], 'result': result})
            elif reply.get('id') == identifier:
                if 'error' in reply:
                    raise ValueError(f'{name}: {reply["error"]["message"]}')
                return reply['result']

    async def request(identifier, method, params):
        message = {'id': identifier, 'method': method}
        if params is not None:
            message['params'] = params
        send(message)
        try:
            return await asyncio.wait_for(response(identifier), timeout=30)
        except (TimeoutError, asyncio.IncompleteReadError) as error:
            raise ValueError(f'{name} failed to answer {method}') from error

    try:
        result = await request(1, 'initialize', {'processId': os.getpid(), 'rootUri': project.as_uri(),
            'rootPath': str(project), 'workspaceFolders': [{'uri': project.as_uri(), 'name': 'fixture'}], 'capabilities': {}})
        if not result.get('capabilities'):
            raise ValueError(f'{name} advertised no capabilities')
        send({'method': 'initialized', 'params': {}})
        if name == 'typescript':
            doc = project / 'answer.ts'
            uri = doc.as_uri()
            send({'method': 'textDocument/didOpen', 'params': {'textDocument': {
                'uri': uri, 'languageId': 'typescript', 'version': 1, 'text': doc.read_text()}}})
            hover = await request(2, 'textDocument/hover', {'textDocument': {'uri': uri}, 'position': {'line': 0, 'character': 7}})
            if not hover or 'answer' not in json.dumps(hover['contents']):
                raise ValueError('TypeScript did not resolve the fixture symbol')
        await request(3, 'shutdown', None)
        send({'method': 'exit'})
        print(f'{name}: native LSP passed', flush=True)
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), 3)
        except TimeoutError:
            proc.kill()
            await proc.wait()


async def main(client):
    catalog = profiles.read(ROOT / 'library/lsp/servers.json')
    with tempfile.TemporaryDirectory(prefix='sage-lsp-') as directory:
        project = Path(directory)
        (project / 'tsconfig.json').write_text('{}')
        (project / 'answer.ts').write_text('const answer = 42;\n')
        for name in profiles.profile(client)['lsp']:
            command = catalog[name]['command']
            await exercise(name, native_command(command) if client == 'opencode' else command, project)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client', choices=profiles.CLIENTS)
    asyncio.run(main(parser.parse_args().client))
