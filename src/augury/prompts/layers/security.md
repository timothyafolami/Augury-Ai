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
