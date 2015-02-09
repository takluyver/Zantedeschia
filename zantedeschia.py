import asyncio
from collections import deque
from errno import EAGAIN, EINTR
import zmq

class AsyncZMQSocket:
    """An asynchronous wrapper around a ZeroMQ socket.
    """
    _recv_callback = None

    def __init__(self, socket:zmq.Socket, loop=None):
        self.socket = socket
        self.loop = loop or asyncio.get_event_loop()
        self._connected_to_loop = False
        self._send_queue = deque() # [msg_parts], Future
        self._recv_queue = deque() # Future, multipart

    def _init_loop(self):
        if not self._connected_to_loop:
            fd = self.socket.getsockopt(zmq.FD)
            self.loop.add_reader(fd, self._wakeup)
            self._connected_to_loop = True

    def close(self, linger=None):
        if self._connected_to_loop:
            fd = self.socket.getsockopt(zmq.FD)
            self.loop.remove_reader(fd)
            self._connected_to_loop = False
        self.socket.close(linger)

    def _wakeup(self):
        """Check for any sending or receiving we can do.
        """
        events = self.socket.getsockopt(zmq.EVENTS)
        rescheduled = False

        if (events & zmq.POLLIN) and self._recv_waiting:
            # Check again until there's nothing more to receive.
            self._schedule()
            rescheduled = True
            self._recv_ready()

        if (events & zmq.POLLOUT) and self._send_queue:
            frames, fut, flags = self._send_queue.popleft()
            if self._send_queue and not rescheduled:
                # Check again if there's anything waiting to be sent
                self._schedule()
            try:
                self.socket.send_multipart(frames, flags & zmq.DONTWAIT)
            except zmq.ZMQError as e:
                if e.errno in (EAGAIN, EINTR):
                    # Reached SNDHWM, or interrupted - requeue
                    self._send_queue.appendleft((frames, fut))
                else:
                    fut.set_exception(e)
            except Exception as e:
                fut.set_exception(e)
            else:
                fut.set_result(None)
                # Schedule ourselves again to potentially send more messages
                self.loop.call_soon(self._wakeup)

    def _schedule(self):
        """Call this whenever we might be able to send/recv more messages.

        ZMQ fds are edge triggered, so they don't reliably tell us when the
        socket is ready to send/recv.
        """
        self.loop.call_soon(self._wakeup)

    @property
    def _recv_waiting(self):
        return (self._recv_callback is not None) or bool(self._recv_queue)

    def _recv_ready(self):
        if self._recv_callback is not None:
            try:
                parts = self.socket.recv_multipart(zmq.DONTWAIT)
            except zmq.ZMQError as e:
                if e.errno not in (EAGAIN, EINTR):
                    raise
            else:
                try:
                    self._recv_callback(parts)
                except:
                    raise

        else:
            # If we've reached here, then there should be single message
            # receivers waiting in the queue
            fut = self._recv_queue.popleft()
            try:
                res = self.socket.recv_multipart(zmq.DONTWAIT)
            except zmq.ZMQError as e:
                if e.errno in (EAGAIN, EINTR):
                    # Queue empty (somehow) or recv interrupted - requeue
                    self._recv_queue.appendleft(fut)
                else:
                    fut.set_exception(e)
            except Exception as e:
                fut.set_exception(e)
            else:
                fut.set_result(res)

    def recv_multipart(self):
        """Asynchronously receive a multipart message.

        Returns a future, the result of which will be a list of message parts
        (bytes objects).

        The normal way to use this is::

            msg_parts = yield from s.recv_multipart()

        Several coroutines may be waiting to receive at once; they will get
        incoming messages in the order in which they called recv_multipart().

        Mixing use of this method with the ``on_recv()`` callback interface
        is not supported.
        """
        self._init_loop()
        f = asyncio.Future()
        self._recv_queue.append(f)
        self._schedule()
        return f

    def on_recv(self, callback):
        """Arrange for callback to be called when the socket receives a message.

        The callback will be called with a single argument, a list of parts in
        a multipart message.

        Mixing this API with ``recv_multipart()`` is not supported.
        """
        self._recv_callback = callback
        self._init_loop()
        self._schedule()

    def send(self, data, flags=0):
        """Send a single message part.

        Typical use::

            yield from s.send(b'data')

        This returns a future, but the completion of that future doesn't mean
        that the message has been sent, only that it has gone to ZMQ's internal
        queue. Waiting on the future is useful for rate limiting: it will block
        if ZMQ's queue reaches the high water mark.
        """
        return self.send_multipart([data], flags=flags)

    def send_multipart(self, msg_parts, flags=0):
        """Send a multipart message.

        Typical use::

            yield from s.send_multipart([b'some', b'data'])

        This returns a future, but the completion of that future doesn't mean
        that the message has been sent, only that it has gone to ZMQ's internal
        queue. Waiting on the future is useful for rate limiting: it will block
        if ZMQ's queue reaches the high water mark.
        """
        self._init_loop()
        f = asyncio.Future()
        self._send_queue.append((msg_parts, f, flags))
        self._schedule()
        return f

