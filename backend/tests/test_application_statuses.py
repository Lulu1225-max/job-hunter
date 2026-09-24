from app.utils.normalization import canonical_status


def test_every_canonical_application_status_is_stable():
    statuses = (
        "saved",
        "applied",
        "oa",
        "interview",
        "final_interview",
        "offer",
        "rejected",
        "withdrawn",
    )

    assert {status: canonical_status(status) for status in statuses} == {
        status: status for status in statuses
    }
