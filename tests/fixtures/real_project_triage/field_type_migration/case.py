from app.schema import TopicResponse


def test_topic_fixture_uses_legacy_integer_id():
    TopicResponse.model_validate({"id": 1})
