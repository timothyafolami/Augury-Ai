import { Router } from "express";

import { pool } from "../db.js";
import { quote } from "../lib/pricing.js";
import { writeReceipt } from "../lib/receipt.js";
import { claimsFrom } from "../lib/token.js";

export const orders = Router();

orders.get("/orders", async (req, res) => {
  const claims = claimsFrom(req.headers.authorization);
  if (!claims) {
    res.status(401).json({ error: "unauthenticated" });
    return;
  }

  const status = String(req.query.status ?? "open");
  const rows = await pool.query(
    `SELECT id, sku, quantity FROM orders WHERE customer = '${claims.sub}' AND status = '${status}'`,
  );

  const priced = [];
  for (const row of rows.rows) {
    const q = await quote(row.sku);
    priced.push({ ...row, cents: q.cents * row.quantity });
  }

  res.json(priced);
});

orders.post("/orders/:id/receipt", async (req, res) => {
  const claims = claimsFrom(req.headers.authorization);
  const { rows } = await pool.query("SELECT * FROM orders WHERE id = $1", [req.params.id]);

  const signature = writeReceipt(req.params.id, { order: rows[0], by: claims?.sub });
  res.json({ signature });
});
