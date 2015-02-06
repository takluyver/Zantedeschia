import functools
import time
import unittest
import asyncio
from zantedeschia import AsyncZMQSocket
import zmq

def coroutinetest(method):
    method = asyncio.coroutine(method)
    @functools.wraps(method)
    def wrapper(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(method(self))
    return wrapper

class PubSubTestCase(unittest.TestCase):
    def setUp(self):
        self.ctx = zmq.Context()
        self.sender = AsyncZMQSocket(self.ctx.socket(zmq.PUB))
        pub = self.sender.socket
        port = pub.bind_to_random_port('tcp://127.0.0.1')
        self.receiver = AsyncZMQSocket(self.ctx.socket(zmq.SUB))
        sub = self.receiver.socket
        sub.connect('tcp://127.0.0.1:%d' % port)
        sub.setsockopt(zmq.SUBSCRIBE, b'')
        time.sleep(0.2)  # Try to avoid race conditions

    def tearDown(self):
        self.sender.close()
        self.receiver.close()

    @coroutinetest
    def test_send_recv(self):
        yield from self.sender.send(b'123')
        msg = yield from self.receiver.recv_multipart()
        self.assertEqual(msg[0], b'123')

    @coroutinetest
    def test_send_recv_seq(self):
        msgs = [b'a', b'b', b'cdef', b'ghi', b'z']
        for msg in msgs:
            yield from self.sender.send(msg)

        for expected in msgs:
            received = yield from self.receiver.recv_multipart()
            self.assertEqual(received[0], expected)

    @coroutinetest
    def test_send_recv_alternating(self):
        msgs = [b'a', b'b', b'cdef', b'ghi', b'z']
        for msg in msgs:
            yield from self.sender.send(msg)
            received = yield from self.receiver.recv_multipart()
            self.assertEqual(received[0], msg)

    @coroutinetest
    def test_multipart(self):
        msg_parts = [b'a', b'b', b'cdef', b'ghi', b'z']
        yield from self.sender.send_multipart(msg_parts)
        received = yield from self.receiver.recv_multipart()
        self.assertEqual(received, msg_parts)

    @coroutinetest
    def test_on_recv(self):
        msgs = [[b'a', b'b'], [b'cdef', b'ghi'], [b'z']]
        received = []
        got_all = asyncio.Future()
        def receive(m):
            received.append(m)
            if len(received) == len(msgs):
                got_all.set_result(None)
        self.receiver.on_recv(receive)

        for msg in msgs:
            yield from self.sender.send_multipart(msg)

        yield from asyncio.wait_for(got_all, 10)
        self.assertEqual(received, msgs)

    @coroutinetest
    def test_recv_waiting(self):
        msgs = [[b'a', b'b'], [b'cdef', b'ghi'], [b'z']]
        receipts = [self.receiver.recv_multipart() for _ in msgs]

        yield from asyncio.sleep(0.01) # Let the event loop go round

        for msg in msgs:
            yield from self.sender.send_multipart(msg)

        received = yield from asyncio.gather(*receipts)
        self.assertEqual(received, msgs)

class PushPullTest(unittest.TestCase):
    def setUp(self):
        self.ctx = zmq.Context()
        self.sender = AsyncZMQSocket(self.ctx.socket(zmq.PUSH))
        self.receiver = AsyncZMQSocket(self.ctx.socket(zmq.PULL))
        # Not connecting them yet to test blocking on send

    @coroutinetest
    def test_blocked_send(self):
        msgs = [[b'a', b'b'], [b'cdef', b'ghi'], [b'z']]
        send_futures = [self.sender.send_multipart(m) for m in msgs]

        yield from asyncio.sleep(0.01)  # Let the event loop go round

        port = self.sender.socket.bind_to_random_port('tcp://127.0.0.1')
        self.receiver.socket.connect('tcp://127.0.0.1:%d' % port)

        for msg in msgs:
            received = yield from self.receiver.recv_multipart()
            self.assertEqual(received, msg)

        for f in send_futures:
            f.result()  # Will raise an exception if the future didn't succeed