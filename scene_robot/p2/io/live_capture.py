"""Bounded, disposable camera sessions with identity-preserving reconnect."""
import multiprocessing as mp
import os
import time
import cv2
import zmq
from p2.clock import now_ns
from p2.msgs import CameraFrame, Status, encode, decode
from p2.io.windows_cameras import enumerate_devices

BACKENDS = ('MSMF', 'DSHOW')


def matching(devices, selected):
    """Never reconnect to a different camera just because indices shifted."""
    identity = selected.get('device_id', '').casefold()
    exact = [d for d in devices if identity and d['device_id'].casefold() == identity]
    if exact:
        return exact[0]
    # Virtual drivers can expose different symbolic links across APIs. Only a
    # unique exact friendly name is an acceptable cross-backend fallback.
    names = [d for d in devices if d['name'] == selected.get('name')
             and (not identity or d['backend'] != selected.get('backend'))]
    return names[0] if len(names) == 1 else None


def capture_worker(pipe, backend, selected, probe):
    cap = None
    try:
        cv2.setNumThreads(1)
        devices = enumerate_devices(backend)  # fresh enumeration EVERY attempt
        pipe.send(('inventory', devices))
        if selected is None:
            return
        device = matching(devices, selected)
        if device is None:
            raise RuntimeError('Selected camera absent; will not substitute another index')
        cap = cv2.VideoCapture(device['index'], getattr(cv2, 'CAP_' + backend))
        if not cap.isOpened():
            raise RuntimeError('Camera failed to open')
        while True:
            ok, bgr = cap.read()
            timestamp = now_ns()  # host read complete, before IPC
            if not ok or bgr is None:
                raise RuntimeError('Camera read failed')
            pipe.send(('frame', timestamp, bgr, device, os.getpid()))
            if probe:
                return
            time.sleep(1 / 15)
    except Exception as exc:
        pipe.send(('error', repr(exc)))
    finally:
        if cap is not None:
            cap.release()
        pipe.close()


class ChildChannel:
    """Private transport still uses the project's msgpack/raw-buffer schemas."""
    def __init__(self, endpoint):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUSH)
        self.socket.setsockopt(zmq.SNDHWM, 2)
        self.socket.setsockopt(zmq.LINGER, 1000)
        self.socket.connect(endpoint)

    def send(self, event):
        if event[0] == 'frame':
            _, timestamp, bgr, device, pid = event
            metadata = Status(now_ns(), {'event': 'frame', 'device': device, 'pid': pid})
            frame = CameraFrame('real_phone', 0, timestamp, now_ns(), 'real', 'pinhole',
                                bgr.shape[1], bgr.shape[0], bgr[:, :, ::-1], None, 'none')
            parts = encode('capture/status', metadata) + encode('camera/real_phone', frame)
        else:
            parts = encode('capture/status', Status(now_ns(), {'event': event[0], 'value': event[1]}))
        self.socket.send_multipart(parts)

    def close(self):
        self.socket.close(); self.context.term()


def run_child(endpoint, backend, selected, probe, worker):
    worker(ChildChannel(endpoint), backend, selected, probe)


class Session:
    """Parent watchdog also kills a driver stuck inside open/read/release."""
    def __init__(self, backend, selected=None, probe=False, worker=capture_worker):
        ctx = mp.get_context('spawn')
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.setsockopt(zmq.RCVHWM, 2)
        self.socket.setsockopt(zmq.LINGER, 0)
        # OS-assigned loopback port: never one of the named 5600-5619 project
        # channels (5602 is the fusion publisher the UI binds at start-up).
        try:
            port = self.socket.bind_to_random_port('tcp://127.0.0.1', min_port=49152, max_port=65535, max_tries=200)
        except zmq.ZMQError:
            self.socket.close(); self.context.term()
            raise RuntimeError('No free loopback port for the camera-helper channel')
        endpoint = f'tcp://127.0.0.1:{port}'
        self.endpoint = endpoint
        self.process = ctx.Process(target=run_child, args=(endpoint, backend, selected, probe, worker), daemon=True)
        self.process.start()

    def receive(self, timeout):
        deadline = now_ns() + int(timeout * 1e9)
        while now_ns() < deadline:
            if self.socket.poll(min(50, max(1, int((deadline-now_ns())/1e6)))):
                parts = self.socket.recv_multipart()
                metadata = decode(parts[:2])[1].values
                if metadata['event'] == 'frame':
                    frame = decode(parts[2:])[1]
                    return ('frame', frame.t_capture_ns, frame.rgb[:, :, ::-1], metadata['device'], metadata['pid'])
                return (metadata['event'], metadata['value'])
            if not self.process.is_alive():
                raise EOFError(f'Camera child exited: {self.process.exitcode}')
        raise TimeoutError('Camera child open/read watchdog expired')

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.kill(); self.process.join(timeout=2)
        self.socket.close(); self.context.term()
        if self.process.is_alive():
            raise RuntimeError('Camera child did not terminate')


def cameras(probe=True, timeout=8):
    rows = []
    for backend in BACKENDS:
        session = Session(backend)
        try:
            event = session.receive(timeout)
            if event[0] != 'inventory':
                raise RuntimeError(str(event))
            devices = event[1]
        except (RuntimeError, TimeoutError, EOFError) as exc:
            print(f'{backend} enumeration failed: {exc}', flush=True); devices = []
        finally:
            session.close()
        for device in devices:
            row = dict(device, readable=False)
            if probe:
                session = Session(backend, device, True)
                try:
                    session.receive(timeout)  # inventory
                    event = session.receive(timeout)
                    if event[0] == 'frame':
                        row.update(readable=True, width=event[2].shape[1], height=event[2].shape[0])
                    else:
                        row['error'] = str(event)
                except (TimeoutError, EOFError) as exc:
                    row['error'] = str(exc)
                finally:
                    session.close()
            rows.append(row)
    return rows


def frames(selected, reconnect=True, seconds=0, session_factory=Session,
           sleep=time.sleep, clock=now_ns, log=print, timeout=8):
    start = clock(); failures = 0; attempt = 0
    while not seconds or (clock() - start) / 1e9 < seconds:
        # Primary on every cycle, fallback after primary failure. A good session
        # stays open; every subsequent attempt is a fresh process and inventory.
        backend = BACKENDS[attempt % len(BACKENDS)]; attempt += 1
        session = session_factory(backend, selected)
        got_frame = False
        log({'event': 'attempt', 'backend': backend, 't_ns': clock()})
        try:
            while not seconds or (clock() - start) / 1e9 < seconds:
                event = session.receive(timeout)
                if event[0] == 'inventory':
                    log({'event': 'inventory', 'backend': backend, 'devices': event[1]})
                elif event[0] == 'frame':
                    got_frame = True; failures = 0
                    yield event[1:]
                else:
                    raise RuntimeError(str(event))
        except (EOFError, OSError, RuntimeError, TimeoutError) as exc:
            log({'event': 'outage', 'error': str(exc), 'backend': backend, 't_ns': clock()})
        finally:
            session.close()
        if not reconnect and (got_frame or attempt >= len(BACKENDS)):
            break
        failures += 1
        delay = min(8., .5 * 2 ** min(failures - 1, 4))
        log({'event': 'backoff', 'seconds': delay})
        sleep(delay)
        if got_frame:
            attempt = 0  # after a working session dies, try MSMF first again
