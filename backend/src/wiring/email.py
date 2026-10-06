"""The sender the account emails go out through.

Hand-maintained until the generator exists: imports and literals only. It is its own
module because ``hooks`` reaches features that import the accounts feature back.
"""

from crudauth import EmailSender

from ..infrastructure.taskiq.email import queued_sender

EMAIL_SENDER: EmailSender = queued_sender
