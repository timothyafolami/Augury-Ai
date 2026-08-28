"""Which imported name implies which practice-lab concern, per runtime.

The same concern wears a different name in each language: a connection pool is
`sqlalchemy` in Python, `database/sql` in Go, `sqlx` in Rust and `java.sql` in
Java. The lab's argument is that the runtime is what makes the mechanism
visible; this table is that argument in a form the Cartographer can read.

Matched by prefix, so `java.util.concurrent.Executor` matches
`java.util.concurrent`.
"""

from __future__ import annotations

from augury.core.cartography.model import Signal

CONCURRENCY = frozenset({Signal.CONCURRENCY})
NETWORK = frozenset({Signal.NETWORK})
DATA = frozenset({Signal.DATA})
DISTRIBUTED = frozenset({Signal.DISTRIBUTED})
FAILURE = frozenset({Signal.FAILURE})
OBSERVABILITY = frozenset({Signal.OBSERVABILITY})
SECURITY = frozenset({Signal.SECURITY})
WEB = frozenset({Signal.ENTRYPOINT, Signal.NETWORK})

GO_SIGNALS: dict[str, frozenset[Signal]] = {
    "sync": CONCURRENCY,
    "context": CONCURRENCY,
    "runtime": CONCURRENCY,
    "golang.org/x/sync": CONCURRENCY,
    "net/http": NETWORK,
    "net": NETWORK,
    "database/sql": DATA,
    "gorm.io": DATA,
    "github.com/jackc/pgx": DATA,
    "github.com/redis/go-redis": DISTRIBUTED,
    "github.com/cenkalti/backoff": FAILURE,
    "log": OBSERVABILITY,
    "log/slog": OBSERVABILITY,
    "go.opentelemetry.io": OBSERVABILITY,
    "crypto": SECURITY,
    "os/exec": SECURITY,
    "github.com/golang-jwt": SECURITY,
    "github.com/gin-gonic/gin": WEB,
    "github.com/labstack/echo": WEB,
    "net/http/httptest": NETWORK,
}

RUST_SIGNALS: dict[str, frozenset[Signal]] = {
    "tokio": CONCURRENCY,
    "std::sync": CONCURRENCY,
    "std::thread": CONCURRENCY,
    "rayon": CONCURRENCY,
    "reqwest": NETWORK,
    "hyper": NETWORK,
    "std::net": NETWORK,
    "sqlx": DATA,
    "diesel": DATA,
    "tokio_postgres": DATA,
    "redis": DISTRIBUTED,
    "lapin": DISTRIBUTED,
    "backoff": FAILURE,
    "tracing": OBSERVABILITY,
    "log": OBSERVABILITY,
    "metrics": OBSERVABILITY,
    "jsonwebtoken": SECURITY,
    "ring": SECURITY,
    "std::process": SECURITY,
    "axum": WEB,
    "actix_web": WEB,
    "rocket": WEB,
}

JAVA_SIGNALS: dict[str, frozenset[Signal]] = {
    "java.util.concurrent": CONCURRENCY,
    "java.lang.Thread": CONCURRENCY,
    "java.sql": DATA,
    "javax.sql": DATA,
    "jakarta.persistence": DATA,
    "javax.persistence": DATA,
    "org.hibernate": DATA,
    "java.net": NETWORK,
    "java.net.http": NETWORK,
    "okhttp3": NETWORK,
    "org.apache.kafka": DISTRIBUTED,
    "io.lettuce": DISTRIBUTED,
    "io.github.resilience4j": FAILURE,
    "org.slf4j": OBSERVABILITY,
    "java.util.logging": OBSERVABILITY,
    "io.micrometer": OBSERVABILITY,
    "javax.crypto": SECURITY,
    "java.security": SECURITY,
    "io.jsonwebtoken": SECURITY,
    "org.springframework.web": WEB,
    "jakarta.ws.rs": WEB,
}

# Node builtins are written both bare and `node:`-prefixed; the adapter
# normalises the prefix away before matching, so one entry covers both.
TYPESCRIPT_SIGNALS: dict[str, frozenset[Signal]] = {
    "worker_threads": CONCURRENCY,
    "perf_hooks": OBSERVABILITY,
    "net": NETWORK,
    "dns": NETWORK,
    "tls": NETWORK,
    "crypto": SECURITY,
    "os": CONCURRENCY,
    "v8": CONCURRENCY,
    "cluster": CONCURRENCY,
    "async_hooks": CONCURRENCY,
    "axios": NETWORK,
    "node-fetch": NETWORK,
    "undici": NETWORK,
    "got": NETWORK,
    "http": NETWORK,
    "https": NETWORK,
    "pg": DATA,
    "mysql2": DATA,
    "typeorm": DATA,
    "prisma": DATA,
    "@prisma/client": DATA,
    "knex": DATA,
    "mongoose": DATA,
    "sequelize": DATA,
    "ioredis": DISTRIBUTED,
    "redis": DISTRIBUTED,
    "bullmq": DISTRIBUTED,
    "amqplib": DISTRIBUTED,
    "p-retry": FAILURE,
    "cockatiel": FAILURE,
    "winston": OBSERVABILITY,
    "pino": OBSERVABILITY,
    "@opentelemetry": OBSERVABILITY,
    "jsonwebtoken": SECURITY,
    "bcrypt": SECURITY,
    "child_process": SECURITY,
    "express": WEB,
    "fastify": WEB,
    "koa": WEB,
    "@nestjs/core": WEB,
    "next": WEB,
}

CPP_SIGNALS: dict[str, frozenset[Signal]] = {
    "thread": CONCURRENCY,
    "mutex": CONCURRENCY,
    "atomic": CONCURRENCY,
    "condition_variable": CONCURRENCY,
    "future": CONCURRENCY,
    "curl/curl.h": NETWORK,
    "asio.hpp": NETWORK,
    "sys/socket.h": NETWORK,
    "pqxx": DATA,
    "sqlite3.h": DATA,
    "spdlog": OBSERVABILITY,
    "openssl": SECURITY,
}
