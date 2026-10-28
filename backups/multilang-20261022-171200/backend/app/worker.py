"""Independent review worker: persistent state makes restart recovery possible."""

import logging
import time

from . import queue
from .orchestrator import run_review
from .schemas import ReviewRequest
from .storage import Store
from .config import RULE_VERSION

log = logging.getLogger(__name__)

def run_once(store: Store, job_id: str) -> bool:
    if not store.claim(job_id):
        return False
    job = store.job_source(job_id)
    try:
        if job["rule_version"] != RULE_VERSION:
            raise ValueError("队列中的规则版本与当前 Worker 不一致")
        report = run_review(
            ReviewRequest(filename=job["filename"], source=job["source"]),
            lambda kind, detail: store.event(job_id, kind, detail),
            lambda round_number: store.set_round(job_id, round_number),
            task_id=job_id,
            initial_round=job["review_round"],
        )
        store.finish(job_id, report)
    except Exception:
        log.exception("Review job %s failed", job_id)
        store.fail(job_id, "审查执行失败；请联系管理员查看 Worker 日志")
    return True

def main():
    logging.basicConfig(level=logging.INFO)
    store = Store()
    for job_id in store.pending_jobs():
        if store.job_source(job_id)["status"] == "running":
            store.recover(job_id)
        queue.publish(job_id)
    while True:
        try:
            job_id = queue.receive()
            if job_id:
                run_once(store, job_id)
        except Exception:
            log.exception("Worker polling failed; retrying")
            time.sleep(3)

if __name__ == "__main__":
    main()
