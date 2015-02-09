Zantedeschia is an experimental alternative integration between asyncio and
ZeroMQ sockets.

I started trying to use `aiozmq <https://github.com/aio-libs/aiozmq>`_, but I
objected to some of the design decisions. I borrowed ideas from that code, but
did a few things differently:

1. ``aiozmq`` is built around asyncio's protocol and transport APIs, which I
   find hard to use; even the simplest examples involve subclassing
   ``ZmqProtocol``. Zantedeschia uses a single AsyncZMQSocket wrapper class,
   with simple semantics.
2. Zantedeschia does not include an RPC framework.
3. Zantedeschia expects the user to create and connect ZMQ sockets using PyZMQ,
   then wrap them in an AsyncZMQSocket object.

*Zantedeschia* is a genus of flowers. Asyncio itself was originally codenamed
'tulip', and a tradition developed of naming asyncio libraries after flowers.

Use this at your own risk. MinRK, the author of PyZMQ, told me that I definitely
shouldn't rely on the ZMQ file descriptors for an event loop, but I'm doing
exactly that.

Ping server example:

.. code:: python

    import asyncio, zmq, zantedeschia

    ctx = zmq.Context()
    s = ctx.socket(zmq.REP)
    s.bind('tcp://127.0.0.1:8123')
    async_sock = zantedeschia.AsyncZMQSocket(s)

    def pong():
        while True:
            msg_parts = yield from async_sock.recv_multipart()
            yield from async_sock.send_multipart(msg_parts)

    asyncio.get_event_loop().run_until_complete(pong())

Using the ``on_recv`` API instead:

.. code:: python

    import asyncio, zmq, zantedeschia

    ctx = zmq.Context()
    s = ctx.socket(zmq.REP)
    s.bind('tcp://127.0.0.1:8123')
    async_sock = zantedeschia.AsyncZMQSocket(s)

    @async_sock.on_recv
    def pong(msg_parts):
        async_sock.send_multipart(msg_parts)

    asyncio.get_event_loop().run_forever()
