"""Private loopback workout HTTP boundary; all hardware/state stays on the core loop."""
from __future__ import annotations
import asyncio
import json
import threading
import time
from http.server import SimpleHTTPRequestHandler
from urllib.parse import urlsplit


def _dns_label(value):
    return bool(value) and len(value) <= 63 and value[0].isalnum() and value[-1].isalnum() \
        and all(character.isalnum() or character == '-' for character in value)


def is_private_research_origin(value):
    """Accept the explicit loopback bench or HTTPS delivered inside a tailnet."""
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        return False
    if parsed.scheme == 'http' and parsed.hostname == '127.0.0.1':
        return parsed.port is not None
    hostname = (parsed.hostname or '').lower()
    labels = hostname.split('.')
    return parsed.scheme == 'https' and len(labels) >= 4 \
        and labels[-2:] == ['ts', 'net'] and all(_dns_label(label) for label in labels)


class WorkoutHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = {}

    def publish(self, service):
        values = {'status': service.snapshot(), 'imu': service.imu_window(),
                  'pose-test': service.pose_test_snapshot(), 'reference': service.reference_result,
                  'pose-result': service.pose_test_result, 'pose': service.pose_latest(),
                  'demo': service.demo_catalog() if service.demo is not None else None}
        with self.lock:
            self.data = json.loads(json.dumps(values, allow_nan=False))

    def snapshot(self, name):
        with self.lock:
            value = self.data.get(name)
        if name == 'pose' and value and value.get('pose'):
            age = time.monotonic_ns() - value['pose']['captured_monotonic_us'] * 1000
            value = {**value, 'age_ms': round(age / 1e6, 2)}
            if age < 0 or age > 500_000_000:
                value.update(state='stale', pose=None)
        return value


def allowed_mutation(headers, *, origins, person_test=False, demo=False):
    origin = headers.get('Origin')
    header = 'X-DS-Demo' if demo else 'X-DS-Person-Test' if person_test else 'X-DS-Workout'
    return origin in origins and headers.get(header) == '1'


def _require_demo_idle(service):
    if service.demo is None:
        raise ValueError('Demo inference is not enabled')
    if service.state != 'idle' or service.pose_test:
        raise ValueError('Stop the live session or pose test before demo inference')


async def execute_demo_start(service):
    """Start indication only; it cannot select or manufacture a model result."""
    _require_demo_idle(service)
    if getattr(service, 'feedback', None) is None:
        return {'enabled': False, 'cue': 'start', 'dispatched': False, 'warnings': []}
    return await service.feedback.demo_start()


async def execute_demo(service, request):
    """Run frozen inference first, then map its actual class to an optional cue."""
    _require_demo_idle(service)
    result = service.demo.predict(request)
    if getattr(service, 'feedback', None) is None:
        feedback = {'enabled': False, 'cue': 'bad' if result['predicted_class'] else 'good',
                    'dispatched': False, 'warnings': []}
    else:
        feedback = await service.feedback.demo_result(
            predicted_class=result['predicted_class'], final_rep=request['rep_id'] == 3)
    return {**result, 'actuators_enabled': feedback['enabled'], 'feedback': feedback}


def workout_handler(hub, service, loop, static_dir, *, origins):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)

        def respond(self, status, data):
            encoded = json.dumps(data, allow_nan=False, separators=(',', ':')).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            path = urlsplit(self.path).path
            routes = {'/api/workout/status': 'status', '/api/research/imu-window': 'imu',
                '/api/research/pose-latest': 'pose',
                '/api/research/demo': 'demo',
                '/api/research/person-pose-test': 'pose-test',
                '/api/research/person-pose-test/latest': 'pose-result',
                '/api/workout/model-check': 'reference'}
            if path in routes:
                value = hub.snapshot(routes[path])
                self.respond(200 if value is not None else 404, value or {'error': 'unavailable'})
            elif path == '/':
                self.send_response(302)
                self.send_header('Location', '/ui-preview/')
                self.end_headers()
            elif path.startswith('/api/'):
                self.respond(404, {'error': 'not_found'})
            else:
                super().do_GET()

        def do_POST(self):
            path = urlsplit(self.path).path
            person = path == '/api/research/person-pose-test'
            demo_predict = path == '/api/research/demo/predict'
            demo_start = path == '/api/research/demo/start'
            demo = demo_predict or demo_start
            if not allowed_mutation(self.headers, origins=origins, person_test=person, demo=demo):
                self.respond(403, {'error': 'private_origin_required'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 4096:
                    raise ValueError('request too large')
                if person:
                    if length:
                        raise ValueError('pose check takes no body')
                    async def execute():
                        result = service.start_pose_test()
                        hub.publish(service)
                        return result
                elif demo_start:
                    if length:
                        raise ValueError('demo start takes no body')
                    async def execute():
                        result = await execute_demo_start(service)
                        hub.publish(service)
                        return result
                else:
                    if path != '/api/workout/command' and not demo_predict:
                        self.respond(404, {'error': 'not_found'})
                        return
                    if self.headers.get_content_type() != 'application/json':
                        raise ValueError('JSON required')
                    request = json.loads(self.rfile.read(length))
                    if not demo and (not isinstance(request, dict) or set(request) != {'action', 'data'} or not isinstance(request['data'], dict)):
                        raise ValueError('invalid command')
                    async def execute():
                        result = await execute_demo(service, request) if demo_predict else await service.command(request['action'], request['data'])
                        hub.publish(service)
                        return result
                future = asyncio.run_coroutine_threadsafe(execute(), loop)
                try:
                    self.respond(200, future.result(timeout=10))
                except TimeoutError:
                    future.cancel()
                    self.respond(503, {'error': 'core_busy'})
            except (ValueError, TypeError, KeyError) as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                self.respond(503, {'error': 'workout_service_unavailable'})

        def log_message(self, *_args):
            pass
    return Handler
