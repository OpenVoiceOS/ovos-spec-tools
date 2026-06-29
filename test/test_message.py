"""Conformance tests for the OVOS-MSG-1 :class:`Message` envelope.

Each test class targets one numbered section of the spec
(``architecture/message-object.md``). Test names are the ``MUST`` /
``SHOULD`` rule they pin so failures point at the spec sentence.
"""
import json

import pytest

from ovos_spec_tools import (
    DEFAULT_SESSION_ID,
    MalformedMessage,
    Message,
)


# --- §2 envelope ------------------------------------------------------------

class TestEnvelope:
    def test_constructs_with_only_msg_type(self):
        """§2: ``data`` and ``context`` MAY be empty."""
        m = Message("ovos.test")
        assert m.msg_type == "ovos.test"
        assert m.data == {}
        assert m.context == {}

    def test_constructs_with_data_and_context(self):
        m = Message("ovos.test", {"a": 1}, {"source": "x"})
        assert m.data == {"a": 1}
        assert m.context == {"source": "x"}

    def test_accepts_empty_msg_type_at_construction(self):
        """§2.1 (non-empty ``type``) gates the **wire** form, not
        intermediate objects. The ``Message("").forward(real_type)``
        pattern is widely used to build a routing scaffold before the
        real topic is known."""
        m = Message("")
        assert m.msg_type == ""

    def test_rejects_non_string_msg_type(self):
        with pytest.raises(MalformedMessage):
            Message(123)  # type: ignore[arg-type]

    def test_rejects_non_dict_data(self):
        """§2.2: ``data`` is a JSON object."""
        with pytest.raises(MalformedMessage):
            Message("ovos.test", "not a dict")  # type: ignore[arg-type]

    def test_rejects_non_dict_context(self):
        """§2.3: ``context`` is a JSON object."""
        with pytest.raises(MalformedMessage):
            Message("ovos.test", {}, "not a dict")  # type: ignore[arg-type]


# --- §6 serialization + deserialization round-trip --------------------------

class TestSerialization:
    def test_round_trip_preserves_envelope(self):
        original = Message(
            "ovos.test", {"x": 1, "y": ["a", "b"]},
            {"source": "skill", "session": {"session_id": "s1"}})
        round_tripped = Message.deserialize(original.serialize())
        assert round_tripped == original

    def test_serialize_emits_a_single_json_object(self):
        m = Message("ovos.test")
        parsed = json.loads(m.serialize())
        assert isinstance(parsed, dict)
        assert set(parsed.keys()) == {"type", "data", "context"}

    def test_deserialize_rejects_unknown_top_level_keys(self):
        """§2: 'Other top-level keys MUST NOT appear; consumers MUST
        reject any Message with unknown top-level keys.'"""
        payload = json.dumps({
            "type": "ovos.test", "data": {}, "context": {},
            "extra": "field"})
        with pytest.raises(MalformedMessage):
            Message.deserialize(payload)

    def test_deserialize_rejects_missing_type(self):
        with pytest.raises(MalformedMessage):
            Message.deserialize(json.dumps({"data": {}, "context": {}}))

    def test_deserialize_rejects_unparsable_payload(self):
        with pytest.raises(MalformedMessage):
            Message.deserialize("not json {")

    def test_deserialize_rejects_non_object_root(self):
        """§2: 'A Message is a JSON object'."""
        with pytest.raises(MalformedMessage):
            Message.deserialize(json.dumps(["not", "an", "object"]))

    def test_deserialize_accepts_already_parsed_dict(self):
        m = Message.deserialize({"type": "ovos.test", "data": {}, "context": {}})
        assert m == Message("ovos.test")

    def test_deserialize_accepts_bytes(self):
        m = Message.deserialize(b'{"type": "ovos.test", "data": {}, "context": {}}')
        assert m.msg_type == "ovos.test"

    def test_serialize_forbids_nan_and_infinity(self):
        """§6: 'Numbers MUST be finite. NaN, +Infinity, -Infinity are
        forbidden.'"""
        m = Message("ovos.test", {"x": float("nan")})
        with pytest.raises(ValueError):
            m.serialize()

    def test_serialize_calls_dot_serialize_on_nested_objects(self):
        """Carrier objects (Session, nested Messages, …) exposing a
        ``.serialize()`` method are converted before JSON encoding so
        callers don't have to pre-dictify their context."""

        class _Carrier:
            def __init__(self, sid):
                self.sid = sid

            def serialize(self):
                return {"session_id": self.sid, "lang": "en-US"}

        m = Message("ovos.test", {}, {"session": _Carrier("s-42")})
        parsed = json.loads(m.serialize())
        assert parsed["context"]["session"] == {
            "session_id": "s-42", "lang": "en-US"}

    def test_serialize_walks_nested_lists_and_dicts(self):
        class _C:
            def serialize(self):
                return "C-payload"
        m = Message("ovos.test", {"items": [_C(), {"k": _C()}]})
        parsed = json.loads(m.serialize())
        assert parsed["data"]["items"] == ["C-payload", {"k": "C-payload"}]

    def test_serialize_data_can_be_empty(self):
        """§2.2: ``data`` MAY be empty (`{}`)."""
        parsed = json.loads(Message("ovos.test").serialize())
        assert parsed["data"] == {}
        assert parsed["context"] == {}

    def test_serialize_rejects_empty_type(self):
        """§2.1/§7 producer MUST: ``serialize`` is the conformance gate and
        MUST refuse to emit an empty ``type``."""
        with pytest.raises(MalformedMessage):
            Message("").serialize()

    def test_serialize_after_forward_from_empty_scaffold_ok(self):
        """The construct-then-forward scaffold becomes serializable once it
        has a real topic."""
        m = Message("").forward("ovos.real", {"k": "v"})
        parsed = json.loads(m.serialize())
        assert parsed["type"] == "ovos.real"

    def test_serialize_accepts_valid_type_syntax(self):
        """§2.1: ASCII letters, digits, ``.`` ``:`` ``_`` ``-`` are all valid
        topic characters; a dot/colon-segmented topic serializes unchanged."""
        m = Message("assistant.intent.register.keyword")
        assert json.loads(m.serialize())["type"] == \
            "assistant.intent.register.keyword"
        # the full permitted charset, including the colon separator and a digit
        assert json.loads(Message("Foo_bar-1:Baz").serialize())["type"] == \
            "Foo_bar-1:Baz"

    def test_serialize_rejects_type_with_whitespace(self):
        """§2.1 producer MUST: a topic carries no whitespace, so an embedded
        space MUST be rejected at the wire gate rather than emitted."""
        with pytest.raises(MalformedMessage):
            Message("a b").serialize()

    def test_serialize_rejects_type_with_illegal_char(self):
        """§2.1: characters outside [A-Za-z0-9.:_-] (here a slash) are not
        permitted in a topic."""
        with pytest.raises(MalformedMessage):
            Message("ovos/test").serialize()

    def test_deserialize_rejects_wrong_type_data(self):
        """§2.2/§6: a present-but-non-object ``data`` MUST be rejected, not
        silently coerced to ``{}``."""
        for bad in ([], 0, False, "x"):
            with pytest.raises(MalformedMessage):
                Message.deserialize({"type": "ovos.test", "data": bad})

    def test_deserialize_rejects_wrong_type_context(self):
        """§2.3/§6: a present-but-non-object ``context`` MUST be rejected."""
        for bad in ([], 0, False, "x"):
            with pytest.raises(MalformedMessage):
                Message.deserialize({"type": "ovos.test", "context": bad})

    def test_deserialize_absent_or_null_data_defaults_to_empty(self):
        """§2.2/§2.3: an absent (or explicit null) ``data``/``context`` is
        equivalent to ``{}`` — that is still allowed."""
        m = Message.deserialize({"type": "ovos.test"})
        assert m.data == {} and m.context == {}
        m2 = Message.deserialize({"type": "ovos.test", "data": None,
                                  "context": None})
        assert m2.data == {} and m2.context == {}

    def test_deserialize_preserves_empty_dict_data(self):
        m = Message.deserialize({"type": "ovos.test", "data": {}})
        assert m.data == {}


# --- §5.1 forward -----------------------------------------------------------

class TestForward:
    def test_preserves_context_unchanged(self):
        """§5.1: ``context = C`` (preserved unchanged, including
        ``source``, ``destination``, and ``session``)."""
        m = Message("ovos.a", {}, {"source": "x", "destination": "y",
                                    "session": {"session_id": "s1"}})
        f = m.forward("ovos.b", {"k": "v"})
        assert f.msg_type == "ovos.b"
        assert f.data == {"k": "v"}
        assert f.context == {"source": "x", "destination": "y",
                             "session": {"session_id": "s1"}}

    def test_forwarder_does_not_become_new_source(self):
        """§5.1: 'The forwarder does not become the new source — the
        original producer remains named.'"""
        m = Message("ovos.a", {}, {"source": "original-producer"})
        assert m.forward("ovos.b").context["source"] == "original-producer"

    def test_forward_context_is_deep_copied(self):
        """Mutating the source context after forward MUST NOT affect
        the forwarded Message. Uses a named id the registry never folded, so
        the session is carried verbatim (a session without a session_id would
        normalize to the default per §4.3)."""
        m = Message("ovos.a", {}, {"source": "x",
                                   "session": {"session_id": "relay-deepcopy",
                                               "lang": "en-US"}})
        f = m.forward("ovos.b")
        m.context["session"]["lang"] = "MUTATED"
        assert f.context["session"]["lang"] == "en-US"

    def test_forward_omits_data_defaults_to_empty(self):
        m = Message("ovos.a", {"k": "v"})
        assert m.forward("ovos.b").data == {}


# --- §5.2 reply -------------------------------------------------------------

class TestReply:
    def test_swaps_source_and_destination(self):
        """§5.2: routing keys reversed."""
        m = Message("ovos.req", {}, {"source": "A", "destination": "B"})
        r = m.reply("ovos.ack")
        assert r.context["source"] == "B"
        assert r.context["destination"] == "A"

    def test_preserves_session_unchanged(self):
        """§5.2 (3): 'All other ``context`` keys, including ``session``,
        are preserved unchanged.'"""
        sess = {"session_id": "s1", "lang": "en-US"}
        m = Message("ovos.req", {}, {"source": "A", "destination": "B",
                                      "session": sess})
        r = m.reply("ovos.ack")
        assert r.context["session"] == sess

    def test_destination_array_picks_one_for_source(self):
        """§5.2 (2): array form — implementation chooses; consumers
        MUST NOT rely on a particular member being chosen."""
        m = Message("ovos.req", {}, {"source": "A",
                                     "destination": ["B", "C"]})
        r = m.reply("ovos.ack")
        # the exact choice is implementation-defined; ours is index 0
        assert r.context["source"] in ("B", "C")
        assert r.context["destination"] == "A"

    def test_provided_context_keys_are_swapped_too(self):
        """``context`` overlays land before the §5.2 swap (matches the
        historical ``ovos_bus_client.Message.reply`` behaviour); routing
        keys passed in get swapped along with everything else."""
        m = Message("ovos.req", {}, {"source": "A", "destination": "B"})
        r = m.reply("ovos.ack",
                    context={"source": "C", "destination": "D"})
        # overlay sets src=C, dst=D — then the swap flips them
        assert r.context["source"] == "D"
        assert r.context["destination"] == "C"

    def test_provided_non_routing_context_keys_pass_through(self):
        """Keys that are not ``source`` / ``destination`` overlay
        without being swapped — handy for custom session shapes or
        tracing identifiers."""
        m = Message("ovos.req", {}, {"source": "A", "destination": "B"})
        r = m.reply("ovos.ack", context={"trace_id": "abc"})
        assert r.context["trace_id"] == "abc"
        assert r.context["source"] == "B"
        assert r.context["destination"] == "A"


# --- §5.3 response ----------------------------------------------------------

class TestResponse:
    def test_topic_is_source_plus_dot_response(self):
        """§5.3: 'A ``response`` is a ``reply`` whose topic is the source
        topic suffixed with ``.response``.'"""
        m = Message("ovos.intent.list", {}, {"source": "A", "destination": "B"})
        r = m.response({"intents": []})
        assert r.msg_type == "ovos.intent.list.response"

    def test_response_swaps_routing_like_reply(self):
        m = Message("ovos.intent.list", {}, {"source": "A", "destination": "B"})
        r = m.response()
        assert r.context["source"] == "B"
        assert r.context["destination"] == "A"


# --- §4 session carrier -----------------------------------------------------

class TestSessionCarrier:
    def test_default_session_id_constant_matches_spec(self):
        """§4.1: 'The value "default" is reserved...'"""
        assert DEFAULT_SESSION_ID == "default"

    def test_absent_session_is_well_formed(self):
        """§4.3 / §7: 'a Message without [session] is well-formed'."""
        m = Message("ovos.test")
        assert "session" not in m.context

    def test_context_session_is_opaque_dict(self):
        """§4: 'session is mostly opaque under this specification.' The
        envelope does not parse it — any dict shape conforms."""
        m = Message("ovos.test", {},
                    {"session": {"weird": "shape", "session_id": "s1"}})
        round_tripped = Message.deserialize(m.serialize())
        assert round_tripped.context["session"]["weird"] == "shape"


# --- §3 routing key opacity -------------------------------------------------

class TestRoutingOpacity:
    def test_source_and_destination_can_be_arbitrary_strings(self):
        """§3.4: 'source and destination are opaque strings.'"""
        m = Message("ovos.test", {},
                    {"source": "anything-goes-here",
                     "destination": ["a@b", "c#d"]})
        assert Message.deserialize(m.serialize()) == m


# --- subclass-friendliness --------------------------------------------------

class TestSubclassDerivations:
    """Derivations and ``deserialize`` must return instances of the
    runtime class so ``ovos-bus-client``'s subclass propagates naturally
    through forward / reply / response chains."""

    class _BusClientMessage(Message):
        pass

    def test_forward_returns_subclass(self):
        m = self._BusClientMessage("ovos.a")
        assert isinstance(m.forward("ovos.b"), self._BusClientMessage)

    def test_reply_returns_subclass(self):
        m = self._BusClientMessage("ovos.a", {}, {"source": "x", "destination": "y"})
        assert isinstance(m.reply("ovos.b"), self._BusClientMessage)

    def test_response_returns_subclass(self):
        m = self._BusClientMessage("ovos.a", {}, {"source": "x", "destination": "y"})
        assert isinstance(m.response(), self._BusClientMessage)

    def test_deserialize_returns_subclass(self):
        payload = '{"type": "ovos.a", "data": {}, "context": {}}'
        assert isinstance(
            self._BusClientMessage.deserialize(payload),
            self._BusClientMessage)


def test_malformed_message_is_catchable_as_assertion_error():
    """Legacy ``ovos_bus_client.Message`` raised ``AssertionError`` from
    bare ``assert`` constructor checks; downstream code that catches
    that type must keep working through the migration."""
    with pytest.raises(AssertionError):
        Message("ok", data="not a dict")


# --- as_dict ----------------------------------------------------------------

def test_as_dict_returns_envelope_as_dict():
    m = Message("ovos.test", {"a": 1}, {"source": "skill"})
    d = m.as_dict
    assert isinstance(d, dict)
    assert d == {"type": "ovos.test", "data": {"a": 1},
                 "context": {"source": "skill"}}


def test_as_dict_walks_carrier_serialize_protocol():
    """``as_dict`` round-trips through ``serialize`` so nested objects
    with a ``.serialize()`` method are converted, same as on the wire."""

    class _Carrier:
        def serialize(self):
            return {"session_id": "s-7"}

    m = Message("ovos.test", {}, {"session": _Carrier()})
    assert m.as_dict["context"]["session"] == {"session_id": "s-7"}


# --- hashability (library-usefulness; not a spec rule) ----------------------

class TestHashable:
    def test_equal_messages_hash_equal(self):
        a = Message("ovos.test", {"x": 1}, {"source": "skills"})
        b = Message("ovos.test", {"x": 1}, {"source": "skills"})
        assert a == b
        assert hash(a) == hash(b)

    def test_usable_as_dict_key_and_set_member(self):
        a = Message("ovos.test", {"x": 1})
        b = Message("ovos.test", {"x": 1})
        c = Message("ovos.other", {"x": 1})
        d = {a: "value"}
        assert d[b] == "value"          # equal key hits the same bucket
        assert len({a, b, c}) == 2      # a and b collapse, c distinct

    def test_usable_in_lru_cache(self):
        import functools

        calls = []

        @functools.lru_cache(maxsize=None)
        def handler(msg):
            calls.append(msg.msg_type)
            return msg.msg_type.upper()

        m1 = Message("ovos.test", {"x": 1}, {"source": "a"})
        m2 = Message("ovos.test", {"x": 1}, {"source": "a"})  # equal to m1
        assert handler(m1) == "OVOS.TEST"
        assert handler(m2) == "OVOS.TEST"
        assert calls == ["ovos.test"]   # cached: only one underlying call

    def test_nested_dict_and_list_data_hashes(self):
        m = Message("ovos.test",
                    {"items": [1, 2, {"k": "v"}], "meta": {"a": [3, 4]}},
                    {"session": {"session_id": "s", "langs": ["en", "pt"]}})
        # must not raise, and must be stable across repeated calls
        assert hash(m) == hash(m)

    def test_int_and_float_data_hash_equal(self):
        # value-equality invariant: {"x": 1} == {"x": 1.0} so they MUST
        # hash equal (a json.dumps digest would break this).
        a = Message("ovos.test", {"x": 1})
        b = Message("ovos.test", {"x": 1.0})
        assert a == b
        assert hash(a) == hash(b)

    def test_mutation_then_rehash_changes_hash(self):
        # documented behavior: the hash is a point-in-time snapshot of the
        # mutable payload; mutating data after hashing changes the hash.
        m = Message("ovos.test", {"x": 1})
        h1 = hash(m)
        m.data["x"] = 2
        assert hash(m) != h1
