from procurepilot_api.shared.mailer import FakeMailer


def test_fake_mailer_returns_message_id() -> None:
    mailer = FakeMailer()
    result = mailer.send(
        to="supplier@example.com",
        subject="RFQ 123",
        body="Please quote.",
        headers={"In-Reply-To": "foo"},
    )
    assert result.message_id is not None
    assert result.message_id.startswith("fake-")
