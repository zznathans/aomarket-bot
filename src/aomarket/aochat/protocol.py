"""Raw AO chat socket framing: connect, read one packet, write one packet.

Port of the transport half of AoChat.php (read_data/get_packet's header
parsing, send_packet) -- no login/dispatch logic here, see client.py.
"""

import asyncio

from aomarket.aochat import packet


class AOChatConnection:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except ConnectionError:
                pass

    async def read_packet(self) -> packet.InboundPacket:
        assert self._reader is not None, "not connected"
        header = await self._reader.readexactly(4)
        ptype, plen = packet.decode_header(header)
        payload = await self._reader.readexactly(plen) if plen else b""
        return packet.decode_packet(ptype, payload)

    async def send_packet(self, packet_type: int, args: list) -> None:
        assert self._writer is not None, "not connected"
        self._writer.write(packet.encode_packet(packet_type, args))
        await self._writer.drain()
