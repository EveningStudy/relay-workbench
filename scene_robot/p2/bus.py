"""Local ZeroMQ pub/sub with bounded socket buffers."""
import zmq
import msgpack
from p2.clock import now_ns
from p2.msgs import encode, decode

DATA = "tcp://127.0.0.1:5600"
COMMANDS = "tcp://127.0.0.1:5601"


class Publisher:
    def __init__(self, address=DATA):
        self.socket = zmq.Context.instance().socket(zmq.PUB)
        self.socket.setsockopt(zmq.SNDHWM, 8)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.bind(address)

    def send(self, topic, message):
        parts=encode(topic, message)
        if getattr(message,'timing',None):
            message.timing['t_encode_ns']=now_ns()
            message.t_send_ns=now_ns()
            header=msgpack.unpackb(parts[1],raw=False)
            header['fields']['timing']=message.timing
            header['fields']['t_send_ns']=message.t_send_ns
            parts[1]=msgpack.packb(header,use_bin_type=True)
        self.socket.send_multipart(parts)

    def close(self):
        self.socket.close()


class Subscriber:
    def __init__(self, topic, address=DATA,hwm=8):
        self.socket = zmq.Context.instance().socket(zmq.SUB)
        self.socket.setsockopt(zmq.RCVHWM, hwm)
        self.socket.setsockopt(zmq.LINGER, 0)
        for prefix in ([topic] if isinstance(topic,str) else topic):self.socket.setsockopt(zmq.SUBSCRIBE,prefix.encode())
        self.socket.connect(address)

    def recv(self, timeout_ms=20):
        if self.socket.poll(timeout_ms):
            return decode(self.socket.recv_multipart())
        return None

    def close(self):
        self.socket.close()
