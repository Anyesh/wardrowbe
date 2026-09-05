TAGGING_QUEUE = "arq:tagging"
IMAGE_QUEUE = "arq:images"

# Kinds whose jobs live on IMAGE_QUEUE. Anything that looks up a job by
# ai_job_id (cancel, abort, the stale sweep) has to pick the queue from the
# item's processing_kind, because arq scopes job ids per queue and a lookup on
# the wrong queue reports not_found for a job that is very much alive.
IMAGE_PROCESSING_KINDS = frozenset({"rotate", "background_removal"})


def queue_for_kind(processing_kind: str | None) -> str:
    if processing_kind in IMAGE_PROCESSING_KINDS:
        return IMAGE_QUEUE
    return TAGGING_QUEUE
