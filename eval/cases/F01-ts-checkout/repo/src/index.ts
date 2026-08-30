import express from "express";

import { orders } from "./routes/orders.js";

const app = express();
app.use(express.json());
app.use(orders);

app.get("/healthz", (_req, res) => {
  res.status(200).send("ok");
});

app.listen(3000, () => {
  console.log("listening on :3000");
});
