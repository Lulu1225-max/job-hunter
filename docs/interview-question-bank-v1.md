# Interview Question Bank v1

The Question Bank is part of the existing Interviews page. Every query and mutation is scoped by the authenticated JWT `sub` user ID.

Questions are deduplicated per user with `trim + lowercase + collapse whitespace`. Saving an existing question increments `times_seen`. If the new save includes a different answer, the API returns `answer_conflict: true` and keeps the existing answer unless the caller explicitly sends `replace_answer: true`. Users can also edit the saved answer from the Question Bank tab.

Actual Interview saves include a client generated `request_id`. The service hashes that ID with each normalized question and stores only the opaque hash in `seen_keys`. Retrying the same save can create another Interview record under the existing Interview behavior, but it does not increment the Question Bank frequency twice.

Question and answer bodies stay in `interview_question_bank`. Analytics metadata contains only `source`, `category`, and the existing Demo marker.
