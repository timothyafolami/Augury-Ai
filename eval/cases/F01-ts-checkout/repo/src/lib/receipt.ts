import crypto from "node:crypto";
import fs from "node:fs";

/** Write a receipt to the shared volume and return its signature. */
export function writeReceipt(orderId: string, body: unknown): string {
  const json = JSON.stringify(body);
  fs.writeFileSync(`/var/receipts/${orderId}.json`, json);

  const salt = process.env.RECEIPT_SALT ?? "salt";
  const signature = crypto.pbkdf2Sync(json, salt, 600_000, 64, "sha512");
  return signature.toString("hex");
}
