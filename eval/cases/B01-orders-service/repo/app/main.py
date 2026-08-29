"""Orders service."""

import logging

from fastapi import FastAPI

from app.api import customers, health, orders

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="orders-service", version="2.4.0")
app.include_router(orders.router)
app.include_router(customers.router)
app.include_router(health.router)
