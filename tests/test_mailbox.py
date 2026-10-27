"""Conformance observations: wire bytes, public results and backend side effects."""

import json
from pathlib import Path
import random
import re
import struct
import unittest
import zlib

from tools.mailbox.backend import (BUFFER, CONN_STATE, EXISTS, INV_PARAM, LARGE_DGRAM,
                                   NO_CONN, NO_DATA, NO_FREE, OK)
from tools.mailbox.codec import (Call, FormatError, Frame, Header, HELLO_LIMITS,
                                 Kind, MAX_FRAME)
from tools.mailbox.device import (ACTIVE, CONTROL, CONTROL_BUSY, DATA, FAULT, READY,
                                  REPLY_HELD, RESET, REWIND, RX_COUNT, SIGNATURE,
                                  STATUS, TX_FREE, Mailbox)
from tools.mailbox.host import Budget, Host, TransportError

ROOT = Path(__file__).resolve().parents[1]


def raw_frame(payload, *, session=1, sequence=1, opcode=17, kind=1, status=0):
    """Independent constructor, also permits intentionally invalid call records."""
    packet = struct.pack("<2sBBIIBBH", b"N4", 1, kind, session, sequence,
                         opcode, status, len(payload)) + payload
    return packet + struct.pack("<I", zlib.crc32(packet))


class WireTests(unittest.TestCase):
    def test_published_handshake_vectors(self):
        fixtures = json.loads((ROOT / "tests/fixtures/mailbox-v1.json").read_text())
        for fixture in fixtures:
            with self.subTest(fixture=fixture["name"]):
                wire = bytes.fromhex(fixture["wire"])
                decoded = Frame.decode(wire)
                self.assertEqual(decoded.header.kind, fixture["kind"])
                self.assertEqual(decoded.header.session, 1)
                self.assertEqual(decoded.header.sequence, 0)
                self.assertEqual(decoded.header.opcode, 255)
                body = HELLO_LIMITS if fixture["kind"] == 2 else b""
                self.assertEqual(decoded.payload, body)
                self.assertEqual(Frame.make(Kind(fixture["kind"]), 1, 0, 255, body).encode(), wire)
        document = (ROOT / "docs/MAILBOX-PROTOCOL.md").read_text()
        section = document.split("### Handshake wire examples", 1)[1].split("## Network semantics", 1)[0]
        examples = re.findall(r"```text\n(.*?)\n```", section, re.S)
        self.assertEqual([bytes.fromhex(s) for s in examples],
                         [bytes.fromhex(f["wire"]) for f in fixtures])

    def test_call_register_order_and_endianness(self):
        # Register H precedes L in the record; IX, auxiliary port and lengths are LE.
        packet = bytes.fromhex("0000123456789abc3412000008000300")
        packet += bytes.fromhex("c000020150002211") + b"\0" * 8 + b"abc"
        call = Call.decode(packet)
        self.assertEqual((call.bc, call.de, call.hl, call.ix), (0x1234, 0x5678, 0x9ABC, 0x1234))
        self.assertEqual(call.aux, bytes.fromhex("c000020150002211"))
        self.assertEqual(call.encode(), packet)

    def test_frame_and_call_length_limits(self):
        payload = Call.make(17, b=1, hl=2048, data=b"a" * 2048).encode()
        self.assertEqual(len(payload), 2080)
        self.assertEqual(len(raw_frame(payload)), MAX_FRAME)
        for size in (0, 31, 2081):
            with self.subTest(size=size), self.assertRaises(FormatError):
                Call.decode(b"\0" * size)
        self.assertEqual(Call.decode(b"\0" * 32), Call(0))
        with self.assertRaises(FormatError):
            Call(17, data=b"a" * 2049).encode()
        with self.assertRaises(FormatError):
            Frame.decode(raw_frame(b"a" * 2081))

    def test_encoder_rejects_out_of_range_fields(self):
        for header in (Header(Kind.REQUEST, 0, 1, 17), Header(Kind.REQUEST, 1, 0xFFFFFFFF, 17),
                       Header(Kind.REQUEST, 1, 1, 256), Header(Kind.REQUEST, 1, 1, 17, 1)):
            with self.subTest(header=header), self.assertRaises(FormatError):
                header.encode()


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.bus = Mailbox()
        self.host = Host(self.bus)
        self.host.connect()
        self.backend = self.bus.backend

    def pump(self, predicate, limit=10000):
        for _ in range(limit):
            if predicate():
                return
            self.bus.tick()
        self.fail("model did not reach expected state within bounded visits")

    def feed(self, wire):
        try:
            self.host.send(wire, Budget(20000), require_active=self.bus.active)
        except TransportError:
            if not self.bus.fault:
                raise
        self.pump(lambda: not self.bus.tx or self.bus.fault)

    def request(self, call):
        return Frame.make(Kind.REQUEST, self.host.session, self.host.sequence, call.a, call.encode())

    def held(self, call):
        request = self.request(call)
        self.feed(request.encode())
        self.pump(lambda: self.bus.reply_held or self.bus.fault)
        self.assertEqual(self.bus.fault, 0)
        return request

    def read_reply(self):
        return self.host.receive(Budget(20000), require_active=self.bus.active)

    def ack(self, request):
        self.host.acknowledge(request, Budget(20000), require_active=self.bus.active)
        self.host.sequence = request.header.sequence + 1

    def tcp(self, resident=False):
        params = b"\xc0\x00\x02\x02" + struct.pack("<HHHB", 80, 65535, 0, 2 if resident else 0)
        result = self.host.call(Call(13, aux=params))
        self.assertEqual(result.a, OK)
        self.backend.establish(result.b)
        return result.b

    def udp(self, resident=False):
        result = self.host.call(Call.make(8, b=int(resident), hl=65535))
        self.assertEqual(result.a, OK)
        return result.b

    def test_boot_and_handshake_ack_gate(self):
        self.bus.write(CONTROL, RESET)
        self.assertEqual(self.bus.read(SIGNATURE), 0x4E)
        self.assertFalse(self.bus.read(STATUS) & (READY | ACTIVE))
        self.assertEqual((self.bus.read(TX_FREE), self.bus.read(RX_COUNT)), (0, 0))
        self.bus.write(DATA, 42)
        self.assertFalse(self.bus.tx)
        self.bus.tick()
        hello = Frame.make(Kind.HELLO, 123, 0, 255)
        self.feed(hello.encode())
        self.assertFalse(self.bus.active)
        self.assertEqual(self.read_reply().payload, HELLO_LIMITS)
        self.assertFalse(self.bus.active)  # Reading the final byte is not acknowledgment.
        self.ack(hello)
        self.assertTrue(self.bus.active)

    def test_duplicate_hello_does_not_reset_backend_or_cursor(self):
        self.bus.write(CONTROL, RESET)
        self.bus.tick()
        hello = Frame.make(Kind.HELLO, 42, 0, 255)
        self.feed(hello.encode())
        self.read_reply()
        count = self.backend.reset_count
        self.feed(hello.encode())
        self.assertEqual(self.backend.reset_count, count)
        self.assertEqual(self.bus.read(RX_COUNT), 0)
        self.bus.write(CONTROL, REWIND)
        self.bus.tick()
        self.assertEqual(self.read_reply().payload, HELLO_LIMITS)

    def test_fifo_capacity_and_overflow_latch(self):
        self.assertEqual(self.bus.read(TX_FREE), 16)
        for value in range(16):
            self.bus.write(DATA, value)
            self.assertEqual(self.bus.read(TX_FREE), 15 - value)
        before = tuple(self.bus.tx)
        self.bus.write(DATA, 16)
        self.assertEqual(self.bus.read(FAULT), 1)
        self.assertEqual(tuple(self.bus.tx), before)
        self.bus.write(CONTROL, 99)
        self.assertEqual(self.bus.read(FAULT), 1)
        self.bus.write(CONTROL, RESET)
        self.bus.tick()
        self.assertEqual(self.bus.read(FAULT), 0)

    def test_empty_read_and_invalid_control(self):
        self.assertEqual(self.bus.read(DATA), 255)
        self.assertEqual(self.bus.fault, 1)
        self.host.connect()
        self.bus.write(CONTROL, REWIND)
        self.assertEqual(self.bus.fault, 5)

    def test_reserved_writes_ignored(self):
        for offset in (0, 2, 3, 5, 6, 7):
            self.bus.write(offset, 255)
        self.assertEqual(self.bus.fault, 0)
        self.assertEqual(self.bus.read(SIGNATURE), 0x4E)

    def test_partial_frame_never_executes(self):
        for prefix in (1, 15, 16, 31, 51):
            with self.subTest(prefix=prefix):
                self.host.connect()
                request = self.request(Call.make(8, hl=1234)).encode()
                before = self.backend.effects["open"]
                self.feed(request[:prefix])
                for _ in range(250):
                    self.bus.tick()
                    self.bus.assert_bounds()
                self.assertEqual(self.backend.effects["open"], before)
                self.assertFalse(self.backend.sockets)
                self.feed(request[prefix:])
                self.pump(lambda: self.bus.reply_held)
                self.assertEqual(self.backend.effects["open"], before + 1)

    def test_malformed_frames_cannot_open_socket(self):
        valid = bytearray(Call.make(8, hl=1234).encode())
        malformed = [b"", bytes(31)]
        for position, value in ((0, 17), (1, 1), (8, 1), (10, 1), (12, 17),
                                (13, 1), (14, 1), (16, 1), (4, 1)):
            body = valid.copy()
            body[position] = value
            malformed.append(bytes(body))
        for payload in malformed:
            with self.subTest(payload=payload.hex()):
                self.host.connect()
                before = sum(self.backend.executions.values())
                self.feed(raw_frame(payload, session=self.host.session, opcode=8))
                self.assertEqual(self.bus.fault, 2)
                self.assertEqual(sum(self.backend.executions.values()), before)

    def test_bad_header_and_crc_rejected_without_execution(self):
        for field, value in ((0, 0), (2, 2), (3, 9), (13, 1), (14, 0x1F), (15, 9), (-1, 0)):
            with self.subTest(field=field):
                self.host.connect()
                packet = bytearray(self.request(Call.make(8, hl=1234)).encode())
                packet[field] = value if field != -1 else packet[-1] ^ 1
                before = sum(self.backend.executions.values())
                self.feed(bytes(packet))
                self.assertEqual(self.bus.fault, 2)
                self.assertEqual(sum(self.backend.executions.values()), before)

    def test_oversized_header_rejected_before_body(self):
        header = struct.pack("<2sBBIIBBH", b"N4", 1, 1, self.host.session, 1, 17, 0, 2081)
        self.feed(header)
        self.assertEqual(self.bus.fault, 2)
        self.assertEqual(self.bus.request_len, 0)

    def test_wrong_session_future_sequence_and_host_response(self):
        for session, sequence, kind, fault in ((999, 1, 1, 3), (1, 2, 1, 3), (1, 1, 2, 2)):
            with self.subTest(session=session, sequence=sequence, kind=kind):
                bus = Mailbox()
                host = Host(bus)
                host.connect()
                wire = raw_frame(Call.make(8, hl=1234).encode(), session=session,
                                 sequence=sequence, kind=kind, opcode=8)
                try:
                    host.send(wire, Budget(20000))
                except TransportError:
                    pass
                for _ in range(100):
                    bus.tick()
                self.assertEqual(bus.fault, fault)
                self.assertFalse(bus.backend.sockets)

    def test_duplicate_during_execution_and_after_reply(self):
        self.bus.execution_delay = 80
        request = self.request(Call.make(8, hl=1234))
        self.feed(request.encode())
        self.assertTrue(self.bus.executing)
        self.feed(request.encode())
        self.pump(lambda: self.bus.reply_held)
        first = self.read_reply()
        self.feed(request.encode())
        self.assertEqual(self.bus.read(RX_COUNT), 0)
        self.bus.write(CONTROL, REWIND)
        self.bus.tick()
        self.assertEqual(self.read_reply(), first)
        self.assertEqual(self.backend.executions[8], 1)
        self.assertEqual(self.backend.effects["open"], 1)

    def test_conflicting_duplicate_does_not_execute(self):
        request = self.held(Call.make(8, hl=1234))
        other = Frame.make(Kind.REQUEST, request.header.session, request.header.sequence,
                           8, Call.make(8, hl=4321).encode())
        self.feed(other.encode())
        self.assertEqual(self.bus.fault, 4)
        self.assertEqual(self.backend.effects["open"], 1)

    def test_crc_collision_is_still_a_conflicting_duplicate(self):
        handle = self.tcp()
        fixture = json.loads((ROOT / "tests/fixtures/mailbox-crc-collision.json").read_text())
        first_data = bytes.fromhex(fixture["first_data"])
        second_data = bytes.fromhex(fixture["second_data"])
        self.assertNotEqual(first_data, second_data)
        golden = raw_frame(Call.make(17, b=1, hl=8, data=first_data).encode())
        self.assertEqual(int.from_bytes(golden[-4:], "little"),
                         int(fixture["session_1_sequence_1_handle_1_frame_crc"], 16))
        first = self.held(Call.make(17, b=handle, hl=8, data=first_data))
        second = self.request(Call.make(17, b=handle, hl=8, data=second_data))
        self.assertEqual(first.encode()[-4:], second.encode()[-4:])
        self.feed(second.encode())
        self.assertEqual(self.bus.fault, 4)
        self.assertEqual(self.backend.effects["tcp_send"], 1)
        self.assertEqual(self.backend.sockets[handle].tx.peek(8), first_data)

    def test_maximum_request_duplicate_uses_no_third_frame_buffer(self):
        handle = self.tcp()
        data = bytes(range(256)) * 8
        request = self.held(Call.make(17, b=handle, hl=2048, data=data))
        retained = bytes(self.bus.request)
        response = bytes(self.bus.response)
        self.assertEqual(len(request.encode()), 2100)
        for _ in range(3):
            self.feed(request.encode())
            self.bus.assert_bounds()
            self.assertEqual(bytes(self.bus.request), retained)
            self.assertEqual(bytes(self.bus.response), response)
        self.assertEqual(self.backend.effects["tcp_send"], 1)
        self.assertEqual(len(self.bus.scratch), 16)

    def test_ack_works_with_full_rx_and_clears_stale_tail(self):
        request = self.held(Call.make(8, hl=1234))
        self.pump(lambda: self.bus.read(RX_COUNT) == 16)
        self.ack(request)
        self.assertEqual(self.bus.read(RX_COUNT), 0)
        self.assertFalse(self.bus.reply_held)
        result = self.host.call(Call(9, b=1))
        self.assertEqual(result.a, OK)

    def test_repeated_ack_does_not_disturb_new_reply(self):
        first = self.held(Call.make(8, hl=1234))
        self.read_reply()
        self.ack(first)
        second = self.held(Call.make(8, hl=4321))
        ack = Frame.make(Kind.ACK, first.header.session, first.header.sequence, 8)
        self.feed(ack.encode())
        result = Call.decode(self.read_reply().payload)
        self.assertEqual((result.a, result.b), (OK, 2))
        self.assertEqual(self.bus.current.sequence, second.header.sequence)
        self.assertEqual(self.backend.effects["open"], 2)

    def test_old_ack_during_execution_and_ack_opcode_mismatch(self):
        first = self.held(Call.make(8, hl=1234))
        self.read_reply()
        self.ack(first)
        self.bus.execution_delay = 80
        second = self.request(Call.make(8, hl=4321))
        self.feed(second.encode())
        old_ack = Frame.make(Kind.ACK, first.header.session, first.header.sequence, 8)
        self.feed(old_ack.encode())
        self.assertTrue(self.bus.executing)
        self.pump(lambda: self.bus.reply_held)
        self.assertEqual(Call.decode(self.read_reply().payload).b, 2)
        wrong_ack = Frame.make(Kind.ACK, second.header.session, second.header.sequence, 9)
        self.feed(wrong_ack.encode())
        self.assertEqual(self.bus.fault, 3)
        self.assertTrue(self.bus.reply_held)

    def test_old_request_after_ack_rejected(self):
        request = self.held(Call.make(8, hl=1234))
        self.read_reply()
        self.ack(request)
        self.feed(request.encode())
        self.assertEqual(self.bus.fault, 3)
        self.assertEqual(self.backend.effects["open"], 1)

    def test_partial_or_corrupt_ack_keeps_response(self):
        request = self.held(Call.make(8, hl=1234))
        saved = bytes(self.bus.response[:self.bus.response_len])
        ack = Frame.make(Kind.ACK, request.header.session, request.header.sequence, 8).encode()
        self.feed(ack[:19])
        self.assertTrue(self.bus.reply_held)
        self.feed(bytes((ack[19] ^ 1,)))
        self.assertEqual(self.bus.fault, 2)
        self.assertTrue(self.bus.reply_held)
        self.assertEqual(bytes(self.bus.response[:self.bus.response_len]), saved)

    def test_host_pause_preserves_reply_while_services_progress(self):
        self.held(Call.make(8, hl=1234))
        saved = bytes(self.bus.response[:self.bus.response_len])
        steps = self.backend.service_steps
        for _ in range(1000):
            self.bus.tick()
            self.bus.assert_bounds()
        self.assertEqual(self.bus.read(RX_COUNT), 16)
        self.assertEqual(self.backend.service_steps, steps + 1000)
        self.assertEqual(bytes(self.bus.response[:self.bus.response_len]), saved)
        self.assertEqual(self.backend.effects["open"], 1)

    def test_reset_during_each_exchange_phase(self):
        for phase in ("collect", "execute", "committed", "reply", "rewind", "ack"):
            with self.subTest(phase=phase):
                self.host.connect()
                handle = self.tcp(resident=True)
                request = self.request(Call.make(17, b=handle, hl=3, data=b"abc"))
                before = self.backend.effects["tcp_send"]
                if phase == "collect":
                    self.feed(request.encode()[:30])
                else:
                    self.feed(request.encode())
                    if phase != "execute":
                        self.pump(lambda: self.bus.committed)
                    if phase in ("reply", "rewind", "ack"):
                        self.pump(lambda: self.bus.reply_held)
                    if phase == "rewind":
                        self.bus.write(CONTROL, REWIND)
                        self.assertTrue(self.bus.read(STATUS) & CONTROL_BUSY)
                    if phase == "ack":
                        ack = Frame.make(Kind.ACK, self.host.session, self.host.sequence, 17)
                        self.feed(ack.encode()[:19])
                self.bus.write(CONTROL, RESET)
                self.assertFalse(self.bus.active)
                self.assertEqual((len(self.bus.tx), len(self.bus.rx)), (0, 0))
                self.bus.tick()
                self.assertFalse(self.backend.sockets)
                delta = 0 if phase in ("collect", "execute") else 1
                self.assertEqual(self.backend.effects["tcp_send"], before + delta)
                self.assertFalse(self.bus.reply_held)

    def test_host_restart_and_stale_session_frames(self):
        handle = self.tcp()
        old = self.request(Call.make(17, b=handle, hl=1, data=b"x"))
        self.held(Call.make(17, b=handle, hl=1, data=b"x"))
        self.host.connect()
        self.assertFalse(self.backend.sockets)
        self.feed(old.encode())
        self.assertEqual(self.bus.fault, 3)
        # A completely new driver may restart its counter only after RESET.
        restarted = Host(self.bus)
        restarted.connect()
        self.assertEqual(restarted.session, 1)
        self.assertFalse(self.backend.sockets)
        self.assertEqual(self.backend.effects["tcp_send"], 1)

    def test_sequence_and_session_counters_do_not_wrap(self):
        self.host.sequence = self.bus.expected = 0xFFFFFFFE
        self.assertEqual(self.host.call(Call.make(8, hl=1234)).a, OK)
        with self.assertRaisesRegex(TransportError, "sequence exhausted"):
            self.host.call(Call.make(8, hl=4321))
        self.assertFalse(self.host.connected)
        self.assertTrue(self.bus.reset_pending)
        self.assertEqual(self.backend.effects["open"], 1)
        self.host.session = 0xFFFFFFFF
        with self.assertRaisesRegex(TransportError, "session counter"):
            self.host.connect()
        self.assertEqual(self.host.session, 0xFFFFFFFF)

    def test_unknown_opcode_gets_transport_status_and_is_acknowledged(self):
        response = self.host.exchange(Call(250))
        self.assertEqual((response.header.status, response.payload), (1, b""))
        self.assertFalse(self.bus.reply_held)
        self.assertEqual(self.host.call(Call.make(8, hl=1234)).a, OK)

    def test_backend_failure_and_stuck_execution_require_reset(self):
        for stuck in (False, True):
            with self.subTest(stuck=stuck):
                self.host.connect()
                if stuck:
                    self.bus.execution_delay = None
                else:
                    self.backend.fail_next = True
                self.feed(self.request(Call.make(8, hl=1234)).encode())
                self.pump(lambda: self.bus.fault, limit=200)
                self.assertEqual(self.bus.fault, 6)
                self.assertFalse(self.backend.sockets)
                self.bus.write(CONTROL, RESET)
                self.bus.tick()
                self.assertEqual(self.bus.fault, 0)

    def test_tcp_atomic_send_capacity_and_zero_length(self):
        for size in (0, 512, 2048, 2049):
            with self.subTest(size=size):
                self.host.connect()
                handle = self.tcp()
                data = bytes(i % 256 for i in range(size))
                if size > 2048:
                    # Cannot fit a legal frame; exercise backend capacity independently.
                    result = self.backend.tcp_send(handle, data)
                else:
                    result = self.host.call(Call.make(17, b=handle, hl=size, data=data))
                self.assertEqual(result.a, BUFFER if size > 2048 else OK)
                ring = self.backend.sockets[handle].tx
                self.assertEqual(ring.peek(ring.used), b"" if size > 2048 else data)
                if size == 2048:
                    rejected = self.host.call(Call.make(17, b=handle, hl=1, data=b"!"))
                    self.assertEqual(rejected.a, BUFFER)
                    self.assertEqual(ring.peek(ring.used), data)

    def test_tcp_flags_and_connection_state(self):
        handle = self.tcp()
        socket = self.backend.sockets[handle]
        socket.state = 2
        self.assertEqual(self.host.call(Call.make(17, b=handle, hl=1, data=b"x")).a, CONN_STATE)
        self.assertEqual(self.host.call(Call(17, b=handle)).a, OK)
        socket.state = 7
        self.assertEqual(self.host.call(Call.make(17, b=handle, c=4, hl=1, data=b"x")).a, INV_PARAM)
        self.assertEqual(self.host.call(Call.make(17, b=handle, c=3, hl=1, data=b"x")).a, OK)

    def test_tcp_state_and_graceful_close_follow_peer_events(self):
        params = b"\xc0\x00\x02\x02" + struct.pack("<HHHB", 80, 1234, 0, 0)
        handle = self.host.call(Call(13, aux=params)).b
        self.assertEqual(self.host.call(Call(16, b=handle)).b, 2)
        self.backend.establish(handle)
        self.host.call(Call.make(17, b=handle, hl=512, data=b"x" * 512))
        state = self.host.call(Call(16, b=handle))
        self.assertEqual((state.b, state.ix, state.aux), (4, 1536, params[:8]))
        self.host.call(Call(14, b=handle))
        self.assertEqual(self.host.call(Call(16, b=handle)).b, 5)
        self.backend.peer_fin(handle)
        self.assertEqual(self.host.call(Call(16, b=handle)).a, NO_CONN)

    def test_tcp_receive_wrap_and_replay(self):
        handle = self.tcp()
        ring = self.backend.sockets[handle].rx
        ring.write(b"-" * 2047)
        ring.consume(2047)
        self.assertTrue(self.backend.inject_tcp(handle, b"abcde"))
        request = self.held(Call.make(18, b=handle, hl=3))
        first = self.read_reply()
        self.assertEqual(Call.decode(first.payload).data, b"abc")
        self.assertEqual(ring.peek(ring.used), b"de")
        self.bus.write(CONTROL, REWIND)
        self.bus.tick()
        self.assertEqual(self.read_reply(), first)
        self.assertEqual(self.backend.effects["tcp_receive"], 1)
        self.ack(request)
        result = self.host.call(Call.make(18, b=handle, hl=65535))
        self.assertEqual((result.bc, result.data), (2, b"de"))
        empty = self.host.call(Call.make(18, b=handle, hl=512))
        self.assertEqual((empty.a, empty.bc, empty.data), (OK, 0, b""))

    def test_tcp_receive_snapshot_excludes_later_arrivals(self):
        handle = self.tcp()
        self.backend.inject_tcp(handle, b"before")
        request = self.request(Call.make(18, b=handle, hl=65535))
        self.feed(request.encode())
        self.pump(lambda: self.bus.committed)
        self.backend.inject_tcp(handle, b"after")
        self.pump(lambda: self.bus.reply_held)
        self.assertEqual(Call.decode(self.read_reply().payload).data, b"before")
        self.ack(request)
        self.assertEqual(self.host.call(Call.make(18, b=handle, hl=65535)).data, b"after")

    def test_udp_zero_short_full_and_truncated_replay(self):
        for limit in (0, 2, 65535):
            with self.subTest(limit=limit):
                self.host.connect()
                handle = self.udp()
                self.backend.inject_udp(handle, b"first", ip=b"\x01\x02\x03\x04", port=0x1234)
                self.backend.inject_udp(handle, b"second")
                request = self.held(Call.make(12, b=handle, de=limit))
                first = self.read_reply()
                result = Call.decode(first.payload)
                self.assertEqual((result.a, result.bc, result.data), (OK, 5, b"first"[:limit]))
                self.assertEqual((result.l, result.h, result.e, result.d, result.ix), (1, 2, 3, 4, 0x1234))
                effects = self.backend.effects["udp_receive"]
                self.bus.write(CONTROL, REWIND)
                self.bus.tick()
                self.assertEqual(self.read_reply(), first)
                self.assertEqual(self.backend.effects["udp_receive"], effects)
                self.ack(request)
                result = self.host.call(Call.make(12, b=handle, de=65535))
                self.assertEqual(result.data, b"second")
                self.assertEqual(self.host.call(Call.make(12, b=handle, de=65535)).a, NO_DATA)

    def test_udp_header_and_payload_wrap(self):
        for start in (2045, 2038):
            with self.subTest(start=start):
                self.host.connect()
                handle = self.udp()
                ring = self.backend.sockets[handle].rx
                ring.write(b"-" * start)
                ring.consume(start)
                self.backend.inject_udp(handle, b"payload-wrap", port=4000)
                result = self.host.call(Call.make(12, b=handle, de=65535))
                self.assertEqual((result.a, result.data, result.ix), (OK, b"payload-wrap", 4000))
                self.assertEqual(ring.used, 0)

    def test_udp_state_distinguishes_empty_datagram_from_no_datagram(self):
        handle = self.udp()
        self.assertEqual(self.host.call(Call(10, b=handle)).b, 0)
        self.backend.inject_udp(handle, b"")
        state = self.host.call(Call(10, b=handle))
        self.assertEqual((state.b, state.de), (1, 0))
        received = self.host.call(Call.make(12, b=handle, de=0))
        self.assertEqual((received.a, received.bc, received.data), (OK, 0, b""))
        self.assertEqual(self.host.call(Call(10, b=handle)).b, 0)

    def test_udp_send_and_receive_size_boundaries(self):
        handle = self.udp()
        for size in (0, 1, 1472, 1473):
            with self.subTest(size=size):
                data = b"x" * size
                aux = b"\xc0\x00\x02\x02" + struct.pack("<HH", 1234, size)
                before = self.backend.effects["udp_send"]
                result = self.host.call(Call(11, b=handle, aux=aux, data=data))
                self.assertEqual(result.a, LARGE_DGRAM if size > 1472 else OK)
                self.assertEqual(self.backend.effects["udp_send"], before + (size <= 1472))
                self.assertEqual(self.backend.inject_udp(handle, data), size <= 1472)
                result = self.host.call(Call.make(12, b=handle, de=65535))
                if size <= 1472:
                    self.assertEqual((result.a, result.bc, result.data), (OK, size, data))
                else:
                    self.assertEqual(result.a, NO_DATA)

    def test_udp_ring_exhaustion_and_malformed_record_recovery(self):
        handle = self.udp()
        self.assertTrue(self.backend.inject_udp(handle, b"a" * 1472))
        self.assertFalse(self.backend.inject_udp(handle, b"b" * 600))
        self.assertEqual(self.host.call(Call.make(12, b=handle, de=65535)).data, b"a" * 1472)
        ring = self.backend.sockets[handle].rx
        ring.write(bytes.fromhex("0102030400500801"))  # Claims 2,049 bytes; only header exists.
        self.feed(self.request(Call.make(12, b=handle, de=65535)).encode())
        self.pump(lambda: self.bus.fault)
        self.assertEqual(self.bus.fault, 6)
        self.assertEqual(ring.used, 8)
        self.host.connect()
        self.assertFalse(self.backend.sockets)

    def test_three_shared_application_sockets_and_lifetime(self):
        tcp = self.tcp()
        resident = self.tcp(resident=True)
        udp = self.udp()
        self.assertEqual({tcp, resident, udp}, {1, 2, 3})
        self.assertEqual(self.host.call(Call.make(8, hl=4321)).a, NO_FREE)
        self.assertEqual(self.host.call(Call(9, b=4)).a, NO_CONN)
        self.host.call(Call(14, b=0))
        self.assertEqual(self.backend.sockets[tcp].state, 5)
        self.assertEqual(self.backend.sockets[resident].state, 4)
        self.assertEqual(len(self.backend.sockets), 3)
        self.host.call(Call(15, b=0))
        self.assertEqual(set(self.backend.sockets), {resident, udp})
        self.host.call(Call(9, b=0))
        self.assertEqual(set(self.backend.sockets), {resident})
        self.host.connect()
        self.assertFalse(self.backend.sockets)  # Session reset closes resident handles too.

    def test_udp_port_validation_and_duplicate_port(self):
        for port in (0, 65520, 65534):
            self.assertEqual(self.host.call(Call.make(8, hl=port)).a, INV_PARAM)
        self.assertEqual(self.host.call(Call.make(8, b=2, hl=1234)).a, INV_PARAM)
        self.assertEqual(self.host.call(Call.make(8, hl=1234)).a, OK)
        self.assertEqual(self.host.call(Call.make(8, hl=1234)).a, EXISTS)

    def test_randomized_producer_consumer_pauses(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                self.host.connect()
                handle = self.tcp()
                data = bytes(range(256)) * 8
                request = self.request(Call.make(17, b=handle, hl=2048, data=data)).encode()
                rng = random.Random(seed)
                sent = 0
                reply = bytearray()
                before = self.backend.effects["tcp_send"]
                for _ in range(20000):
                    if rng.randrange(3):
                        self.bus.tick()
                    if rng.randrange(2):
                        count = min(rng.randrange(17), self.bus.read(TX_FREE), len(request) - sent)
                        for value in request[sent:sent + count]:
                            self.bus.write(DATA, value)
                        sent += count
                    if rng.randrange(2):
                        count = min(rng.randrange(17), self.bus.read(RX_COUNT))
                        reply.extend(self.bus.read(DATA) for _ in range(count))
                    self.bus.assert_bounds()
                    self.assertEqual(self.bus.fault, 0)
                    if len(reply) == 52:
                        break
                else:
                    self.fail("bounded random schedule did not complete")
                self.assertEqual(Call.decode(Frame.decode(bytes(reply)).payload).a, OK)
                self.assertEqual(self.backend.effects["tcp_send"], before + 1)
                self.assertEqual(self.backend.sockets[handle].tx.peek(2048), data)


class HostRecoveryTests(unittest.TestCase):
    class CorruptingBus:
        def __init__(self, device, *, corrupt_reads=1, corrupt_at=0):
            self.device = device
            self.remaining = corrupt_reads
            self.rewinds = 0
            self.corrupt_at = corrupt_at
            self.read_count = 0

        def tick(self):
            self.device.tick()

        def read(self, offset):
            value = self.device.read(offset)
            if offset == DATA:
                position = self.read_count
                self.read_count += 1
                if self.remaining and position >= self.corrupt_at:
                    if self.remaining > 0:
                        self.remaining -= 1
                    return value ^ 1
            return value

        def write(self, offset, value):
            if offset == CONTROL and value == REWIND:
                self.rewinds += 1
            self.device.write(offset, value)

    def test_corrupt_reply_rewinds_without_duplicate_open(self):
        device = Mailbox()
        host = Host(device)
        host.connect()
        bus = self.CorruptingBus(device)
        host.bus = bus
        result = host.call(Call.make(8, hl=1234))
        self.assertEqual((result.a, result.b), (OK, 1))
        self.assertEqual(device.backend.effects["open"], 1)
        self.assertEqual(bus.rewinds, 1)

    def test_payload_crc_failure_replays_consumed_udp_record(self):
        device = Mailbox()
        host = Host(device)
        host.connect()
        handle = host.call(Call.make(8, hl=1234)).b
        device.backend.inject_udp(handle, b"first")
        device.backend.inject_udp(handle, b"second")
        bus = self.CorruptingBus(device, corrupt_at=49)
        host.bus = bus
        result = host.call(Call.make(12, b=handle, de=3))
        self.assertEqual((result.a, result.bc, result.data), (OK, 5, b"fir"))
        self.assertEqual(device.backend.effects["udp_receive"], 1)
        self.assertEqual(bus.rewinds, 1)
        self.assertEqual(host.call(Call.make(12, b=handle, de=65535)).data, b"second")

    def test_lost_or_truncated_response_is_rewound_without_resubmitting(self):
        for lose_all in (False, True):
            with self.subTest(lose_all=lose_all):
                device = Mailbox()
                host = Host(device)
                host.connect()
                original_tick = device.tick
                dropping = True

                def lose_response_bytes():
                    nonlocal dropping
                    original_tick()
                    if dropping and device.reply_held:
                        if lose_all or device.cursor == device.response_len:
                            device.rx.clear()  # Simulate bytes lost after leaving the Pico.
                        if device.cursor == device.response_len:
                            dropping = False

                device.tick = lose_response_bytes
                bus = self.CorruptingBus(device, corrupt_reads=0)
                host.bus = bus
                result = host.call(Call.make(8, hl=1234))
                self.assertEqual((result.a, result.b), (OK, 1))
                self.assertEqual(bus.rewinds, 1)
                self.assertEqual(device.backend.executions[8], 1)

    def test_valid_crc_wrong_response_identity_is_not_acknowledged(self):
        device = Mailbox()
        host = Host(device)
        host.connect()
        original_tick = device.tick
        replaced = False

        def substitute_wire_response():
            nonlocal replaced
            original_tick()
            if device.reply_held and not replaced:
                # Fault injection after publication; first emitted byte is unchanged.
                reply = Frame.decode(bytes(device.response[:device.response_len]))
                wire = Frame.make(Kind.RESPONSE, host.session + 1, host.sequence,
                                  reply.header.opcode, reply.payload).encode()
                device.response[:len(wire)] = wire
                replaced = True

        device.tick = substitute_wire_response
        with self.assertRaisesRegex(TransportError, "identity"):
            host.call(Call.make(8, hl=1234))
        self.assertTrue(device.reset_pending)
        self.assertFalse(host.connected)
        self.assertEqual(device.backend.effects["open"], 1)

    def test_inconsistent_receive_metadata_is_not_accepted_or_reexecuted(self):
        device = Mailbox()
        host = Host(device)
        host.connect()
        handle = host.call(Call.make(8, hl=1234)).b
        device.backend.inject_udp(handle, b"first")
        execute = device.backend.execute

        def corrupt_metadata(call):
            result = execute(call)
            if call.a == 12:
                # Valid framing/CRC, but original length is smaller than copied data.
                return Call.make(OK, bc=1, data=result.data)
            return result

        device.backend.execute = corrupt_metadata
        with self.assertRaisesRegex(FormatError, "UDP result length"):
            host.call(Call.make(12, b=handle, de=3))
        self.assertFalse(host.connected)
        self.assertTrue(device.reset_pending)
        self.assertEqual(device.backend.effects["udp_receive"], 1)

    def test_persistent_corruption_stops_after_three_reads(self):
        device = Mailbox()
        host = Host(device)
        host.connect()
        bus = self.CorruptingBus(device, corrupt_reads=-1)
        host.bus = bus
        with self.assertRaises(TransportError):
            host.call(Call.make(8, hl=1234))
        self.assertEqual(bus.rewinds, 2)
        self.assertFalse(host.connected)
        self.assertTrue(device.reset_pending)
        self.assertEqual(device.backend.effects["open"], 1)

    def test_shared_poll_budget_exhaustion_does_not_restart_recovery(self):
        device = Mailbox()
        host = Host(device)
        host.connect()
        device.execution_delay = None
        device.execution_limit = 100000
        host.poll_limit = 200
        with self.assertRaisesRegex(TransportError, "budget"):
            host.call(Call.make(8, hl=1234))
        self.assertEqual(host.last_budget.remaining, 0)
        self.assertFalse(host.connected)
        self.assertTrue(device.reset_pending)
        self.assertEqual(device.backend.effects["open"], 0)

    def test_invalid_fifo_count_is_rejected_before_data_access(self):
        for register in (TX_FREE, RX_COUNT):
            with self.subTest(register=register):
                device = Mailbox()
                host = Host(device)
                host.connect()
                original_read = device.read

                def bad_count(offset):
                    return 17 if offset == register else original_read(offset)

                device.read = bad_count
                with self.assertRaisesRegex(TransportError, "FIFO count"):
                    host.call(Call.make(8, hl=1234))
                self.assertTrue(device.reset_pending)
                self.assertFalse(host.connected)
                self.assertEqual(device.backend.effects["open"], 0)

    def test_reset_during_host_wait_is_terminal(self):
        device = Mailbox()
        host = Host(device)
        host.connect()
        original_tick = device.tick

        def reset_after_commit():
            original_tick()
            if device.committed:
                device.write(CONTROL, RESET)

        device.tick = reset_after_commit
        with self.assertRaisesRegex(TransportError, "session lost"):
            host.call(Call.make(8, hl=1234))
        self.assertEqual(device.backend.effects["open"], 1)
        self.assertFalse(host.connected)


if __name__ == "__main__":
    unittest.main()
