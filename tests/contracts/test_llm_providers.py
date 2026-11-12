"""Real HTTP client/provider envelopes, with a disposable local JSON service."""
import asyncio
from contextlib import contextmanager
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

import httpx
import pytest

from maicon_sim.sdk.llm import (
    FixtureLLM, HTTPLLM, LLMError, OpenAICompatibleLLM, build_llm, llm_environment,
)


@contextmanager
def endpoint(reply, delay=0.):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append({'body': value, 'authenticated': self.headers.get('Authorization') == 'Bearer test-only-provider-key'})
            if delay:
                time.sleep(delay)
            result = reply(value)
            blob = result if isinstance(result, bytes) else json.dumps(result).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1/chat/completions', received
    finally:
        server.shutdown()
        worker.join(2.)
        server.server_close()


def test_json_http_provider_real_client_sends_auth_and_validates_reports(caplog):
    def reply(body):
        return {'target': 'red_radar', 'search_sectors': ['r-s1', 'cm'], 'base': 'red_maintenance'} if body['task'] == 'parse_order' else {'ranking': ['R-3', 'R-1', 'R-2']}

    async def run(url):
        llm = HTTPLLM(url, 'local-test-model', key='test-only-provider-key')
        assert not llm.mock
        result = await llm.parse_order('레이더 시설', deadline=time.monotonic()+2.)
        assert result == {'target': 'RED_RADAR', 'search_sectors': ['R-S1', 'CM'], 'base': 'RED_MAINTENANCE'}
        assert await llm.rank_threat({'opposing_slots': ['R-1', 'R-2', 'R-3']}) == ['R-3', 'R-1', 'R-2']

    with endpoint(reply) as (url, received), caplog.at_level(logging.INFO):
        asyncio.run(run(url))
    assert len(received) == 2
    assert all(item['authenticated'] for item in received)
    assert received[0]['body']['model'] == 'local-test-model'
    assert 'test-only-provider-key' not in caplog.text


def test_openai_compatible_provider_real_chat_envelope_and_json_content():
    def reply(body):
        assert body['response_format'] == {'type': 'json_object'}
        payload = json.loads(body['messages'][1]['content'])
        result = {'base': 'RED_COMMAND_POST'} if payload['task'] == 'parse_order' else {'ranking': ['R-2', 'R-3', 'R-1']}
        return {'choices': [{'message': {'content': json.dumps(result)}}]}

    async def run(url):
        llm = OpenAICompatibleLLM(url, 'chat-model', key='test-only-provider-key')
        assert await llm.parse_order('후속 거점은 작전지휘소') == {'base': 'RED_COMMAND_POST'}
        assert await llm.rank_threat({'camp': 'BLUE'}) == ['R-2', 'R-3', 'R-1']

    with endpoint(reply) as (url, received):
        asyncio.run(run(url))
    assert received[0]['authenticated']
    assert received[0]['body']['messages'][0]['role'] == 'system'


@pytest.mark.parametrize('response', [
    b'{"ranking":["R-1","R-2","R-3"],"ranking":["R-3","R-2","R-1"]}',
    b'{"ranking":NaN}',
    b'```json\n{"ranking":["R-1","R-2","R-3"]}\n```',
    {'ranking': ['R-1', 'R-1', 'R-3']},
    {'ranking': ['R-1', 'B-2', 'R-3']},
    {'ranking': ['R-1', 'R-2']},
    {'ranking': ['R-1', 'R-2', 'R-3'], 'confidence': 1},
])
def test_provider_rejects_invalid_json_or_callsigns(response):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=response if isinstance(response, bytes) else json.dumps(response).encode()))) as client:
            llm = HTTPLLM('https://provider.test/model', 'model', client=client)
            with pytest.raises(LLMError):
                await llm.rank_threat({'camp': 'BLUE'})
    asyncio.run(run())


@pytest.mark.parametrize('result', [
    {'target': 3}, {'target': 'RADAR'}, {'search_sectors': ['CM', 'cm']},
    {'base': 'RED_MAINTENANCE', 'mission_code': 'NOPE0001'}, {},
])
def test_provider_rejects_interpretations_outside_public_schema(result):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=result))) as client:
            with pytest.raises(LLMError):
                await HTTPLLM('https://provider.test', 'model', client=client).parse_order('text')
    asyncio.run(run())


def test_expired_deadline_sends_no_http_and_no_automatic_retry():
    requests = []
    async def slow(request):
        requests.append(request.url.path)
        await asyncio.sleep(.2)
        return httpx.Response(200, json={'ranking': ['R-1', 'R-2', 'R-3']})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
            llm = HTTPLLM('https://provider.test', 'model', timeout_s=1., client=client)
            with pytest.raises(asyncio.TimeoutError):
                await llm.rank_threat({'camp': 'BLUE'}, deadline=time.monotonic()-1.)
            assert requests == []
            with pytest.raises(asyncio.TimeoutError):
                await llm.rank_threat({'camp': 'BLUE'}, deadline=time.monotonic()+.03)
            assert requests == ['/']
    asyncio.run(run())


def test_factory_is_explicit_and_does_not_fall_back_when_auth_is_missing():
    assert isinstance(build_llm(environ={}), FixtureLLM)
    with pytest.raises(ValueError, match='binding is missing'):
        build_llm(provider='openai-compatible', model='configured-model', environ={})
    with pytest.raises(ValueError, match='ENDPOINT'):
        build_llm(provider='json-http', model='configured-model', environ={})
    with pytest.raises(ValueError, match='provider'):
        build_llm(provider='typo', environ={})
    llm = build_llm(provider='json-http', endpoint='https://provider.test', model='configured-model', key_env='MY_LLM_KEY', environ={'MY_LLM_KEY': 'test-only-provider-key'})
    assert llm.provider_name == 'json-http' and not llm.mock


def test_only_explicit_llm_environment_and_named_credential_are_forwarded():
    inherited = {'GH_TOKEN': 'test-only-github-value', 'ADMIN_TOKEN': 'test-only-admin-value', 'MAICON_LLM_API_KEY': 'test-only-unused-value'}
    assert llm_environment(inherited) == {}
    assert llm_environment({**inherited, 'MAICON_LLM_PROVIDER': 'fixture'}) == {'MAICON_LLM_PROVIDER': 'fixture'}
    configured = {**inherited, 'MAICON_LLM_PROVIDER': 'json-http', 'MAICON_LLM_ENDPOINT': 'https://provider.test', 'MAICON_LLM_MODEL': 'configured-model', 'MAICON_LLM_API_KEY_ENV': 'MY_LLM_KEY', 'MY_LLM_KEY': 'test-only-provider-key'}
    forwarded = llm_environment(configured)
    assert set(forwarded) == {'MAICON_LLM_PROVIDER', 'MAICON_LLM_ENDPOINT', 'MAICON_LLM_MODEL', 'MAICON_LLM_API_KEY_ENV', 'MY_LLM_KEY'}
    assert 'GH_TOKEN' not in forwarded and 'ADMIN_TOKEN' not in forwarded


def test_fixture_rank_uses_visual_estimate_but_remains_marked_mock():
    provider = FixtureLLM('BLUE')
    assert provider.mock
    assert asyncio.run(provider.rank_threat({'opposing_slots': ['R-1', 'R-2', 'R-3'], 'estimated_ranking': ['R-3', 'R-2', 'R-1']})) == ['R-3', 'R-2', 'R-1']
