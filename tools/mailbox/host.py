"""Bounded test host. Models transport, not MSX slots or the full UNAPI ABI."""

from .codec import (Call, FIFO_DEPTH, FormatError, Frame, Header, HELLO_LIMITS,
                    Kind, validate_response)
from .device import (ACTIVE, CONTROL, CONTROL_BUSY, DATA, FAULTED, READY,
                     REPLY_HELD, RESET, REWIND, RX_COUNT, STATUS, TX_FREE)


class TransportError(RuntimeError):
    pass


class ReadStalled(TransportError):
    """A retained response stopped making progress; rewind may recover it."""


class Budget:
    def __init__(self, polls):
        self.remaining = polls

    def spend(self):
        if self.remaining <= 0:
            raise TransportError("poll budget exhausted")
        self.remaining -= 1


class Host:
    def __init__(self, bus, poll_limit=1_048_576, reply_idle_limit=128):
        self.bus = bus
        self.poll_limit = poll_limit
        self.reply_idle_limit = reply_idle_limit  # Model visits, not milliseconds.
        self.session = 0
        self.sequence = 1
        self.connected = False
        self.last_budget = None

    def _budget(self):
        self.last_budget = Budget(self.poll_limit)
        return self.last_budget

    def _status(self, budget, *, require_active=True):
        budget.spend()
        self.bus.tick()
        status = self.bus.read(STATUS)
        if status & FAULTED:
            raise TransportError("device fault")
        if require_active and not status & ACTIVE:
            raise TransportError("session lost")
        return status

    def _abort(self):
        self.connected = False
        self.bus.write(CONTROL, RESET)

    def _count(self, offset, budget):
        budget.spend()
        count = self.bus.read(offset)
        if not 0 <= count <= FIFO_DEPTH:
            raise TransportError("invalid FIFO count")
        return count

    def send(self, wire, budget, *, require_active=True):
        offset = 0
        while offset < len(wire):
            status = self._status(budget, require_active=require_active)
            if status & CONTROL_BUSY or not status & READY:
                continue
            count = min(self._count(TX_FREE, budget), len(wire) - offset)
            for value in wire[offset:offset + count]:
                self.bus.write(DATA, value)
            offset += count

    def _read(self, count, budget, *, require_active=True):
        data = bytearray()
        idle = 0
        while len(data) < count:
            status = self._status(budget, require_active=require_active)
            if status & CONTROL_BUSY:
                continue
            amount = min(self._count(RX_COUNT, budget), count - len(data))
            data.extend(self.bus.read(DATA) for _ in range(amount))
            if amount:
                idle = 0
            elif status & REPLY_HELD:
                idle += 1
                if idle >= self.reply_idle_limit:
                    raise ReadStalled("retained reply made no progress")
        return bytes(data)

    def receive(self, budget, *, require_active=True):
        header = self._read(16, budget, require_active=require_active)
        size = Header.decode(header).length
        rest = self._read(size + 4, budget, require_active=require_active)
        return Frame.decode(header + rest)

    def _reply(self, request, budget, *, require_active=True):
        for attempt in range(3):
            try:
                reply = self.receive(budget, require_active=require_active)
            except (FormatError, ReadStalled):
                if attempt == 2:
                    raise TransportError("reply unreadable after three attempts")
                status = self._status(budget, require_active=require_active)
                if not status & REPLY_HELD:
                    raise TransportError("no retained response")
                self.bus.write(CONTROL, REWIND)
                while self._status(budget, require_active=require_active) & CONTROL_BUSY:
                    pass
                continue
            h, expected = reply.header, request.header
            if (h.kind != Kind.RESPONSE or (h.session, h.sequence, h.opcode) !=
                    (expected.session, expected.sequence, expected.opcode)):
                raise TransportError("response identity mismatch")
            if expected.kind == Kind.HELLO:
                if h.status or reply.payload != HELLO_LIMITS:
                    raise TransportError("incompatible HELLO limits")
            elif h.status == 0:
                validate_response(Call.decode(request.payload), Call.decode(reply.payload))
            elif reply.payload:
                raise TransportError("error response must be empty")
            return reply
        raise AssertionError("retry bound")

    def acknowledge(self, request, budget, *, require_active=True):
        h = request.header
        ack = Frame.make(Kind.ACK, h.session, h.sequence, h.opcode)
        self.send(ack.encode(), budget, require_active=require_active)
        while self._status(budget, require_active=require_active) & REPLY_HELD:
            pass

    def connect(self):
        budget = self._budget()
        self._abort()
        try:
            if self.session == 0xFFFFFFFF:
                raise TransportError("session counter exhausted")
            while not self._status(budget, require_active=False) & READY:
                pass
            self.session += 1
            hello = Frame.make(Kind.HELLO, self.session, 0, 255)
            self.send(hello.encode(), budget, require_active=False)
            self._reply(hello, budget, require_active=False)
            self.acknowledge(hello, budget, require_active=False)
            if not self.bus.read(STATUS) & ACTIVE:
                raise TransportError("HELLO not acknowledged")
            self.sequence = 1
            self.connected = True
        except (TransportError, FormatError):
            self._abort()
            raise

    def exchange(self, call):
        if not self.connected:
            raise TransportError("host offline")
        if self.sequence >= 0xFFFFFFFF:
            self._abort()
            raise TransportError("sequence exhausted; start a new session")
        # Local encoding errors cannot start a network action.
        request = Frame.make(Kind.REQUEST, self.session, self.sequence, call.a, call.encode())
        wire = request.encode()
        budget = self._budget()
        try:
            self.send(wire, budget)
            response = self._reply(request, budget)
            self.acknowledge(request, budget)
            self.sequence += 1
            return response
        except (TransportError, FormatError):
            self._abort()
            raise

    def call(self, call):
        response = self.exchange(call)
        if response.header.status:
            raise TransportError("opcode not modeled")
        return Call.decode(response.payload)
