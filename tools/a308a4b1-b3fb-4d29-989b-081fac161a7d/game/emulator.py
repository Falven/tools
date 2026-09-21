"""The small PyBoy boundary: explicit ticks, read-only memory, RAM-only media.

No MCP, model, identity, game strategy, file saves, or autonomous work here.
The owning session must serialize every method, including close().
"""

from base64 import b64encode
from importlib.metadata import version
from io import BytesIO
from time import monotonic


class RedEmulator:
    def __init__(self) -> None:
        self._pyboy = None
        self._rom_stream: BytesIO | None = None
        self._ram_stream: BytesIO | None = None
        self._rtc_stream: BytesIO | None = None
        self._held: str | None = None

    def open(self, rom: bytes) -> None:
        """Power on once from a supplied, already validated ROM and blank RAM."""
        if self._pyboy is not None:
            raise RuntimeError("An emulator is already open.")
        if version("pyboy") != "2.7.0":
            raise RuntimeError("Install the pinned PyBoy 2.7.0 dependency.")
        from pyboy import PyBoy

        # A file-like ROM has no adjacent .ram/.rtc/.state pathname. These streams
        # are explicit as well: a previous host save can never seed a fresh run.
        self._rom_stream = BytesIO(rom)
        self._ram_stream = BytesIO(bytes(32768))
        self._rtc_stream = BytesIO()
        try:
            self._pyboy = PyBoy(
                self._rom_stream, ram_file=self._ram_stream,
                rtc_file=self._rtc_stream, window="null", cgb=False,
                sound_emulated=False, sound_volume=0, log_level="ERROR",
                color_palette=(0xE0E8CC, 0xA8B878, 0x507048, 0x182820),
            )
            self._pyboy.set_emulation_speed(0)
            # One standard initial frame; no scripted intro or game-wrapper reset.
            if not self._pyboy.tick(1, True, False):
                raise RuntimeError("PyBoy stopped during power-on.")
        except Exception:
            self.close()
            raise

    @property
    def frame_count(self) -> int:
        if self._pyboy is None:
            raise RuntimeError("Emulator is not initialized.")
        return int(self._pyboy.frame_count)

    def read(self, address: int, length: int = 1, bank: int | None = None) -> bytes:
        """Read a bounded detached memory slice; never expose a writable view."""
        if self._pyboy is None:
            raise RuntimeError("Emulator is not initialized.")
        if not 0 <= address <= 0xFFFF or not 1 <= length <= 8192:
            raise ValueError("Invalid bounded memory read.")
        if address + length > 0x10000:
            raise ValueError("Memory read crosses the address space.")
        if bank is None:
            return bytes(self._pyboy.memory[address:address + length])
        if bank != 0 or not 0xA000 <= address < address + length <= 0xC000:
            raise ValueError("Only cartridge RAM bank zero is exposed.")
        return bytes(self._pyboy.memory[bank, address:address + length])

    def execute(self, button: str | None, held_frames: int,
                released_frames: int, deadline: float) -> int:
        """One ordinary press/release or animation wait, at most 120 frames.

        The session supplies a monotonic deadline. No tick follows deadline
        expiry. A failure can leave partial actual progress; it is not rolled back.
        """
        if self._pyboy is None:
            raise RuntimeError("Emulator is not initialized.")
        if button not in (None, "up", "down", "left", "right", "a", "b", "start"):
            raise ValueError("Button is not permitted.")
        total = held_frames + released_frames
        if (not 0 <= held_frames <= 16 or not 0 <= released_frames <= 120
                or not 1 <= total <= 120):
            raise ValueError("Action frame bound exceeded.")
        advanced = 0
        try:
            if button is not None:
                self._held = button
                self._pyboy.button_press(button)
            for _ in range(held_frames):
                if monotonic() >= deadline:
                    raise TimeoutError("Emulator batch exceeded its budget.")
                if not self._pyboy.tick(1, True, False):
                    raise RuntimeError("Emulator stopped during a batch.")
                advanced += 1
            self.release()
            for _ in range(released_frames):
                if monotonic() >= deadline:
                    raise TimeoutError("Emulator batch exceeded its budget.")
                if not self._pyboy.tick(1, True, False):
                    raise RuntimeError("Emulator stopped during a batch.")
                advanced += 1
        finally:
            self.release()
        return advanced

    def release(self) -> None:
        if self._held is not None and self._pyboy is not None:
            self._pyboy.button_release(self._held)
            self._held = None

    def capture(self) -> dict:
        """Encode the actual 160×144 display once into a detached PNG value."""
        if self._pyboy is None:
            raise RuntimeError("Emulator is not initialized.")
        from PIL.Image import Image
        source = self._pyboy.screen.image
        if not isinstance(source, Image):
            raise TypeError("PyBoy did not provide a Pillow screen image.")
        image = source.copy()
        if image.size != (160, 144):
            raise RuntimeError("Unexpected emulator screen dimensions.")
        stream = BytesIO()
        image.save(stream, format="PNG", optimize=False)
        return {"width": 160, "height": 144, "format": "png",
                "emulator_frame": self.frame_count,
                "png": b64encode(stream.getvalue()).decode("ascii")}

    def close(self) -> None:
        """Dispose without saving cartridge RAM. No destructor/background tick."""
        emulator, self._pyboy = self._pyboy, None
        self._held = None
        try:
            if emulator is not None:
                emulator.stop(save=False)
        finally:
            for stream in (self._rom_stream, self._ram_stream, self._rtc_stream):
                if stream is not None:
                    stream.close()
            self._rom_stream = self._ram_stream = self._rtc_stream = None
