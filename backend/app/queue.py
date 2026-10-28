"""Redis notification queue. The database remains the durable job ledger."""

import os

import redis

QUEUE_KEY = "codesentinel:reviews:v1"

def client():
    return redis.Redis.from_url(os.getenv("CODESENTINEL_REDIS_URL", "redis://localhost:6379/0"),
                              decode_responses=True, socket_connect_timeout=2, socket_timeout=10)

def publish(job_id: str):
    client().lpush(QUEUE_KEY, job_id)

def receive(timeout: int = 5) -> str | None:
    item = client().brpop(QUEUE_KEY, timeout=timeout)
    return item[1] if item else None
