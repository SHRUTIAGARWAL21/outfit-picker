"""The two kinds of failure a worker can hit (PRD 6.3).

The difference decides what the worker does next:

- A TransientError is bad luck — a timeout, a rate limit, a 5xx from the model.
  Trying again later will probably work. The worker retries with a growing delay.

- A PermanentError will never work — a corrupt file, a photo with no clothing in
  it, content the model refuses. Retrying only wastes money. The worker marks the
  garment FAILED, stores the reason, and stops.
"""


class TransientError(Exception):
    """A temporary problem. Retry it."""


class PermanentError(Exception):
    """A problem that will never clear. Do not retry."""
