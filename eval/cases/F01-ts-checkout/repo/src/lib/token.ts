import jwt from "jsonwebtoken";

const SECRET = process.env.JWT_SECRET ?? "dev-secret";

export interface Claims {
  sub: string;
  role: string;
}

/** Read the caller's claims out of a bearer token. */
export function claimsFrom(header: string | undefined): Claims | null {
  if (!header) return null;
  const token = header.replace("Bearer ", "");
  try {
    return jwt.decode(token) as Claims;
  } catch (e) {
    return null;
  }
}
