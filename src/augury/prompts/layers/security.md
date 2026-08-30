Exploitable defects reachable from input this service accepts.

Report what an attacker can actually do here, in this file, with the inputs
this code receives. A finding that requires an attacker to already have what
they are trying to obtain is not a finding.

Specifically look for:

- Queries assembled by interpolation, formatting or concatenation rather than
  parameters. State the injected value and what it returns or destroys.
- Authorisation checked against the authenticated identity but not against the
  requested object, so any valid user can read another user's record by
  changing an identifier.
- Secrets in source, in log lines, in error responses, or in a URL.
- Requests to a host derived from user input, reaching internal addresses and
  cloud metadata endpoints.
- Tokens accepted without verifying signature, issuer, audience or expiry, or
  with no path to revoke one before it expires.
- Output placed into HTML, SQL, a shell command or a URL without encoding for
  that specific context. The correct encoding differs per context.
- Rate limiting absent on an endpoint that is expensive or that reveals whether
  an account exists.

Where a threshold applies -- an unauthenticated endpoint doing unbounded work,
say -- give the rate at which it becomes a denial of service. Otherwise state
the exploit precisely: the input, the path it takes, and what it yields.

- You cannot parameterize an identifier. A placeholder is a slot in a parse tree
  and a column name is structure decided before that tree exists, so an
  interpolated `ORDER BY` stays injectable however carefully the `WHERE` was
  parameterized, and it reads as fixed to a scanner. Only an allowlist closes it.
- An in-process rate-limit counter multiplies the configured limit by the worker
  count: a limit that gets **weaker** as you scale. The same defect hides
  revocation, where a cache in front of a denylist makes a revoked token instant
  on one worker and up to a TTL late on the others. A 429 that still runs the
  password check is a CPU-exhaustion vector.
- A fast hash is wrong for passwords precisely because it is fast: SHA-256 gives
  an attacker roughly five orders of magnitude more guesses per second than
  argon2id at OWASP's baseline. Comparing a token with `==` returns at the first
  differing byte and leaks it.
- A template engine escapes for one context and it is not always yours. Jinja2's
  autoescape handles the HTML body, so an `href` holding a `javascript:` URL
  still navigates, and a value inside a `<script>` block can close it from
  within a string literal.
- SSRF, the structural tell: if the code that validates and the code that
  connects each resolve the name separately, there is a TOCTOU window whatever
  the tests say. `requests` follows redirects by default and httpx does not.
- A PKCE verifier that is sent but never compared, and a `state` that is
  generated but never compared, both look textbook-correct on the wire. A state
  never compared is login CSRF. `state` protects the redirect and `nonce`
  protects the token; they are not substitutes.
- JWT: `alg: none`, and RS256-to-HS256 confusion using your own public key as
  the HMAC secret. Enforce the expected algorithm rather than trusting the header.
- Ownership must be enforced **at the query**. Under transaction pooling,
  `SET app.current_user` instead of `SET LOCAL` bleeds one tenant's identity into
  the next request, and row-level security is bypassed when the connection role
  owns the table.
- A pushed secret is compromised and stays so in history: only rotation is
  remediation. And `install` **is** code execution, through npm lifecycle
  scripts, pip `setup.py`, `cargo build.rs` and Gradle configuration time.
