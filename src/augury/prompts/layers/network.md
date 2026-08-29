The cost of talking to something else: connection establishment, pooling,
timeouts, keep-alive across a load balancer, DNS, and head-of-line blocking.

A connection pool is a queue with a hard capacity, and when demand exceeds
capacity requests do not fail, they wait -- in a place your application metrics
do not look. That is how a service stops responding while every dependency it
talks to reports itself perfectly healthy. Usually two or three pools are
stacked (HTTP client to upstream, ORM to database, and the worker count nobody
configured), and the narrowest one sets the real concurrency.

Specifically look for:

- Every pool this file participates in, named with its size. Identify the
  narrowest and predict `active_connections` and the `worker_saturation` it produces.
- Outbound calls with no timeout, or with a timeout longer than the caller's
  own deadline. Predict `worker_saturation`: how much of the pool a single slow upstream pins, at a stated upstream latency.
- A client constructed per request rather than reused, paying connection and
  TLS setup every time. Predict `http_req_duration_p99`, the added latency per call.
- Keep-alive assumptions that a load balancer or a proxy in between will not
  honour.
- DNS resolved once at startup and cached forever, so a changed address is
  never picked up.
- Many small requests multiplexed over one connection where a single slow
  response blocks the rest.

State the concurrency ceiling explicitly: workers times threads times pool.
