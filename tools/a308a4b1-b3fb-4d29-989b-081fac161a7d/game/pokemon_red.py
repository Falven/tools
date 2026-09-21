"""Pokémon Red-specific read-only interpretation and finite input macros.

Profile: the pret/pokered English Red image, SHA-1 ea9b...8b9a, not a filename
claim of "Rev-A". The reference reader is NousResearch/pokemon-agent at
f8a03e4a8bc58f1d9dda6d677a7436cc832a57a9 (MIT; see README notices).
RAM layout / record format reference: pret/pokered at
a1a22aaf84d1675bcdbaeb194592379d586d838e. No raw memory reaches the controller.

This module owns menu interpretation, not strategy. Navigation is limited to
visible tiles; the controller chooses each direction/interaction. An unknown
screen stays unknown and receives explicit exploratory button choices.
"""

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha1, sha256
from re import fullmatch

# Immutable mapping constants, never mutable run state.
ROM_SHA1 = "ea9bcae617fdf159b045185467ae58b2e4a48b9a"
ROM_LENGTH = 1048576
TILE_MAP = 0xC3A0
PARTY_COUNT, PARTY_DATA, PARTY_NAMES = 0xD163, 0xD16B, 0xD2B5
IS_BATTLE, ACTIVE_PARTY = 0xD057, 0xCC2F
MAP_ID, PLAYER_Y, PLAYER_X = 0xD35E, 0xD361, 0xD362
BADGES, BAG_COUNT, BAG_DATA, MONEY = 0xD356, 0xD31D, 0xD31E, 0xD347
MENU_Y, MENU_X, MENU_INDEX, MENU_MAX, LIST_OFFSET = 0xCC24, 0xCC25, 0xCC26, 0xCC28, 0xCC36
TILESET_BANK, TILESET_COLLISION = 0xD52B, 0xD530
HOF_COUNT, HOF_MAP, HOF_SRAM, HOF_TEAM_BYTES = 0xD5A2, 0x76, 0xA598, 96

ReadMemory = Callable[..., bytes]
# (button, held frames, released frames), interpreted only by the emulator.
Pulse = tuple[str | None, int, int]


@dataclass(frozen=True)
class Move:
    slot: int
    name: str
    pp: int
    kind: str
    power: int


@dataclass(frozen=True)
class PartyMon:
    species_id: int
    species: str
    name: str
    name_bytes: bytes
    level: int
    hp: int
    max_hp: int
    status: str
    moves: tuple[Move, ...]


@dataclass(frozen=True)
class MenuEntry:
    label: str
    row: int
    column: int
    index: int


@dataclass(frozen=True)
class Observation:
    mode: str
    map_id: int
    location: str
    x: int
    y: int
    facing: str
    text: tuple[str, ...]
    menu: tuple[MenuEntry, ...]
    cursor: tuple[int, int] | None
    party: tuple[PartyMon, ...]
    active_slot: int
    battle: str
    enemy: str
    badges: int
    bag: tuple[tuple[int, str, int], ...]
    money: int
    terrain: tuple[str, ...]
    neighbors: tuple[tuple[str, str], ...]
    objects: tuple[str, ...]
    hof_count: int
    frame: int

    def progress_key(self) -> tuple:
        return (self.mode, self.map_id, self.x, self.y, self.badges,
                tuple((p.species_id, p.level, p.hp) for p in self.party),
                self.bag, self.text, self.cursor, self.enemy)

    def summary(self) -> str:
        return (f"{self.location} ({self.x}, {self.y}) · {self.mode.replace('_', ' ')}"
                f" · {self.badges.bit_count()}/8 badges · {len(self.party)} Pokémon")


@dataclass(frozen=True)
class LegalAction:
    identifier: str
    description: str
    pulses: tuple[Pulse, ...]
    # A menu target is re-observed before the final A press, not assumed reached.
    target: tuple[int, int] | None = None
    menu_mode: str | None = None


@dataclass(frozen=True)
class Completion:
    team: tuple[str, ...]
    record_sha256: str
    observed_frame: int
    evidence: str = "First complete Hall-of-Fame SRAM team, stable across emulated frames"


def decode_text(data: bytes) -> str:
    result = []
    for value in data:
        if value == 0x50:
            break
        if 0x80 <= value <= 0x99:
            result.append(chr(65 + value - 0x80))
        elif 0xA0 <= value <= 0xB9:
            result.append(chr(97 + value - 0xA0))
        elif 0xF6 <= value <= 0xFF:
            result.append(str(value - 0xF6))
        else:
            result.append({
                0x7F: " ", 0x9A: "(", 0x9B: ")", 0x9C: ":", 0x9D: ";",
                0x9E: "[", 0x9F: "]", 0xBA: "é", 0xBB: "'d", 0xBC: "'l",
                0xBD: "'s", 0xBE: "'t", 0xBF: "'v", 0xE0: "'", 0xE3: "-",
                0xE6: "?", 0xE7: "!", 0xE8: ".", 0xEF: "♂", 0xF5: "♀",
                0xF0: "$", 0xF1: "×", 0xF2: ".", 0xF3: "/", 0xF4: ",",
                0xED: ">", 0xEC: ">", 0xE1: "PK", 0xE2: "MN",
            }.get(value, " "))
    return "".join(result).strip()


def _encode(text: str) -> bytes:
    return bytes(0x7F if c == " " else ord(c) - 65 + 0x80 for c in text)


def validate_rom(rom: bytes, configured_sha256: str) -> None:
    """Require both operator integrity and an independently identified mapping."""
    if not fullmatch(r"[0-9a-fA-F]{64}", configured_sha256):
        raise ValueError("POKEMON_RED_ROM_SHA256 must contain 64 hexadecimal digits.")
    if len(rom) != ROM_LENGTH:
        raise ValueError("The supported English Pokémon Red ROM must be exactly 1 MiB.")
    if sha256(rom).hexdigest() != configured_sha256.lower():
        raise ValueError("ROM does not match POKEMON_RED_ROM_SHA256.")
    if sha1(rom, usedforsecurity=False).hexdigest() != ROM_SHA1:
        raise ValueError("Unsupported ROM revision. Requires the pret English Red fingerprint, not a renamed or patched ROM.")
    if not rom[0x134:0x144].startswith(b"POKEMON RED"):
        raise ValueError("Cartridge header does not identify Pokémon Red.")


def _location(map_id: int) -> str:
    towns = ("Pallet Town", "Viridian City", "Pewter City", "Cerulean City",
             "Lavender Town", "Vermilion City", "Celadon City", "Fuchsia City",
             "Cinnabar Island", "Indigo Plateau", "Saffron City")
    if 0 <= map_id < len(towns):
        return towns[map_id]
    if 12 <= map_id <= 36:
        return f"Route {map_id - 11}"
    return {
        37: "Red's house 1F", 38: "Red's room", 39: "Rival's house",
        40: "Oak's lab", 41: "Viridian Pokémon Center", 42: "Viridian Mart",
        45: "Viridian Gym", 50: "Viridian Forest", 53: "Pewter Gym",
        57: "Pewter Pokémon Center", 58: "Mt. Moon 1F", 59: "Mt. Moon B1F",
        60: "Mt. Moon B2F", 63: "Cerulean Pokémon Center", 64: "Cerulean Gym",
        118: "Hall of Fame",
    }.get(map_id, f"Map {map_id}")


def _type_name(value: int) -> str:
    return {0: "Normal", 1: "Fighting", 2: "Flying", 3: "Poison",
            4: "Ground", 5: "Rock", 7: "Bug", 8: "Ghost", 20: "Fire",
            21: "Water", 22: "Grass", 23: "Electric", 24: "Psychic",
            25: "Ice", 26: "Dragon"}.get(value, "?")


class PokemonRed:
    def __init__(self, rom: bytes) -> None:
        # Constructed only after the full ROM fingerprint check, not on import.
        self._rom = rom
        self._species = self._species_names()
        self._move_names = self._terminated_table("POUND", "KARATE CHOP", 165)
        self._item_names = self._terminated_table("MASTER BALL", "ULTRA BALL", 83)
        move_anchor = bytes((1, 0, 40, 0, 255, 35, 2, 0, 50, 0, 255, 25))
        self._move_data = self._unique_offset(move_anchor)
        self._hof_baseline: bytes | None = None
        self._hof_zero_seen = False
        self._hof_candidate: tuple[bytes, int] | None = None
        self._selection_context = ""

    def _unique_offset(self, anchor: bytes) -> int:
        offset = self._rom.find(anchor)
        if offset < 0 or self._rom.find(anchor, offset + 1) >= 0:
            raise ValueError("ROM data-table signature does not match the supported mapping.")
        return offset

    def _species_names(self) -> tuple[str, ...]:
        anchor = _encode("RHYDON") + bytes((0x50,)) * 4 + _encode("KANGASKHAN")
        offset = self._unique_offset(anchor)
        return ("",) + tuple(decode_text(self._rom[offset + i * 10:offset + (i + 1) * 10])
                             for i in range(190))

    def _terminated_table(self, first: str, second: str, count: int) -> tuple[str, ...]:
        anchor = _encode(first) + b"\x50" + _encode(second) + b"\x50"
        offset = self._unique_offset(anchor)
        names = self._rom[offset:offset + count * 24].split(b"\x50", count)
        if len(names) <= count:
            raise ValueError("ROM name table is incomplete.")
        return ("",) + tuple(decode_text(value) for value in names[:count])

    def _species_name(self, value: int) -> str:
        return self._species[value] if 0 < value < len(self._species) else f"Species {value}"

    def _item_name(self, value: int) -> str:
        if 196 <= value <= 200:
            return f"HM{value - 195:02}"
        if 201 <= value <= 250:
            return f"TM{value - 200:02}"
        return self._item_names[value] if 0 < value < len(self._item_names) else f"Item {value}"

    def _moves(self, data: bytes, pp: bytes) -> tuple[Move, ...]:
        moves = []
        for slot, move_id in enumerate(data):
            if 1 <= move_id <= 165:
                offset = self._move_data + (move_id - 1) * 6
                moves.append(Move(slot, self._move_names[move_id], pp[slot] & 63,
                                  _type_name(self._rom[offset + 3]),
                                  self._rom[offset + 2]))
        return tuple(moves)

    def _party(self, read: ReadMemory) -> tuple[PartyMon, ...]:
        count = read(PARTY_COUNT)[0]
        if count > 6:
            return ()  # Uninitialized intro RAM is not a corrupt team.
        result = []
        for index in range(count):
            data = read(PARTY_DATA + index * 44, 44)
            nick = read(PARTY_NAMES + index * 11, 11)
            level, hp, maximum = data[33], int.from_bytes(data[1:3], "big"), int.from_bytes(data[34:36], "big")
            if not 1 <= level <= 100 or not 1 <= maximum <= 999 or hp > maximum:
                return ()  # Do not present transient party construction as facts.
            status = data[4]
            status_text = ("fainted" if hp == 0 else "sleep" if status & 7 else
                           "poison" if status & 8 else "burn" if status & 16 else
                           "freeze" if status & 32 else "paralysis" if status & 64 else "OK")
            result.append(PartyMon(data[0], self._species_name(data[0]),
                                   decode_text(nick), nick, level, hp, maximum,
                                   status_text, self._moves(data[8:12], data[29:33])))
        return tuple(result)

    def _screen(self, read: ReadMemory) -> tuple[bytes, tuple[str, ...], tuple[int, int] | None]:
        tiles = read(TILE_MAP, 360)
        # Retain column positions; decode_text otherwise strips them.
        lines = tuple("".join(decode_text(bytes((t,))) or " " for t in tiles[row * 20:(row + 1) * 20])
                      for row in range(18))
        cursors = [(index // 20, index % 20) for index, t in enumerate(tiles) if t == 0xED]
        cursor = cursors[-1] if cursors else None
        return tiles, lines, cursor

    def _menu(self, read: ReadMemory, lines: tuple[str, ...],
              cursor: tuple[int, int] | None) -> tuple[MenuEntry, ...]:
        if cursor is None:
            return ()
        # Two-dimensional battle command menu is not the ordinary vertical menu.
        if any("FIGHT" in line for line in lines):
            result = []
            for label in ("FIGHT", "PKMN", "ITEM", "RUN"):
                for row, line in enumerate(lines):
                    column = line.find(label)
                    if column >= 0:
                        result.append(MenuEntry(label, row, max(0, column - 1), len(result)))
            if len(result) == 4:
                return tuple(result)
        top_y, top_x = read(MENU_Y)[0], read(MENU_X)[0]
        current, maximum = read(MENU_INDEX)[0], read(MENU_MAX)[0]
        if not (maximum <= 8 and current <= maximum and top_y + 2 * maximum < 18
                and top_x < 19 and cursor == (top_y + 2 * current, top_x)):
            return ()
        entries = []
        for index in range(maximum + 1):
            row = top_y + index * 2
            label = lines[row][top_x + 1:].replace(">", "").strip()
            if label:
                entries.append(MenuEntry(label[:24], row, top_x, index))
        return tuple(entries)

    def _navigation(self, read: ReadMemory, tiles: bytes, mode: str) -> tuple:
        if mode != "overworld":
            return (), (), ()
        bank = read(TILESET_BANK)[0]
        pointer = int.from_bytes(read(TILESET_COLLISION, 2), "little")
        allowed: set[int] = set()
        if 0 < bank < 64 and 0x4000 <= pointer < 0x8000:
            offset = bank * 0x4000 + pointer - 0x4000
            allowed = set(self._rom[offset:offset + 256].split(b"\xff", 1)[0])
        rows = []
        for row in range(9):
            rows.append("".join("." if tiles[(row * 2 + 1) * 20 + col * 2] in allowed
                                else "#" if allowed else "?" for col in range(10)))
        # Player is centered in cell (4,4). Only rendered sprites are described.
        objects = []
        player = read(0xC100, 16)
        occupied = set()
        for index in range(1, 16):
            sprite = read(0xC100 + index * 16, 16)
            if sprite[0] == 0 or sprite[2] == 0xFF or not (0 < sprite[6] < 160 and 0 < sprite[4] < 144):
                continue
            dx, dy = (sprite[6] - player[6]) // 16, (sprite[4] - player[4]) // 16
            if -4 <= dx <= 5 and -4 <= dy <= 4:
                occupied.add((4 + dx, 4 + dy))
                objects.append(f"object {index} dx{dx:+} dy{dy:+}")
        neighbors = []
        for direction, dx, dy in (("up", 0, -1), ("down", 0, 1), ("left", -1, 0), ("right", 1, 0)):
            cell = rows[4 + dy][4 + dx]
            label = "object" if (4 + dx, 4 + dy) in occupied else "clear" if cell == "." else "blocked/edge" if cell == "#" else "unknown"
            neighbors.append((direction, label))
        rows[4] = rows[4][:4] + "@" + rows[4][5:]
        return tuple(rows), tuple(neighbors), tuple(objects[:6])

    def observe(self, read: ReadMemory, frame: int) -> Observation:
        party = self._party(read)
        battle_raw = read(IS_BATTLE)[0]
        battle = {1: "wild", 2: "trainer"}.get(battle_raw, "")
        tiles, lines, cursor = self._screen(read)
        menu = self._menu(read, lines, cursor)
        joined = " ".join(line.strip() for line in lines)
        labels = " ".join(entry.label for entry in menu)
        has_box = 0x79 in tiles and 0x7A in tiles and 0x7C in tiles
        # A uniform/fading background must not disclose hidden dark-cave tiles.
        bgp = read(0xFF47)[0]
        visible_palette = len({(bgp >> (2 * i)) & 3 for i in range(4)}) >= 3
        if not read(0xFF40)[0] & 0x80 or not visible_palette:
            mode = "animation"
        elif menu and "FIGHT" in labels and "RUN" in labels:
            mode = "battle_command"
        elif menu and battle and ("PP" in joined or any(m.name in labels for p in party for m in p.moves)):
            mode = "battle_moves"
        elif menu and party and any(p.name and p.name in labels for p in party):
            mode = "party_menu"
        elif menu and ("NEW GAME" in labels or "CONTINUE" in labels):
            mode = "main_menu"
        elif menu:
            mode = "menu"
        elif ("NAME" in joined and "END" in joined and any("ABCDE" in line.replace(" ", "") for line in lines)):
            mode = "naming"
        elif has_box:
            mode = "battle_text" if battle else "dialogue"
        elif battle:
            mode = "battle_animation"
        elif 0 < read(0xD368)[0] <= 128 and 0 < read(0xD369)[0] <= 128:
            mode = "overworld"
        else:
            mode = "intro"
        count = read(BAG_COUNT)[0]
        bag = ()
        if count <= 20:
            data = read(BAG_DATA, 40)
            bag = tuple((data[i * 2], self._item_name(data[i * 2]), data[i * 2 + 1])
                        for i in range(count) if data[i * 2] not in (0, 255))
        money_bytes = read(MONEY, 3)
        money = sum(((v >> 4) * 10 + (v & 15)) * 100**(2 - i) for i, v in enumerate(money_bytes))
        active_slot = read(ACTIVE_PARTY)[0]
        if active_slot >= len(party):
            active_slot = 0
        if battle and party:
            # Battle PP/HP change before the party's out-of-battle copy is updated.
            from dataclasses import replace
            own = read(0xD014, 29)
            hp, maximum = int.from_bytes(own[1:3], "big"), int.from_bytes(own[15:17], "big")
            if maximum and hp <= maximum and own[0] == party[active_slot].species_id:
                updated = list(party)
                updated[active_slot] = replace(party[active_slot], hp=hp, max_hp=maximum,
                                               moves=self._moves(own[8:12], own[25:29]))
                party = tuple(updated)
        enemy = ""
        if battle:
            data = read(0xCFE5, 17)
            hp, maximum = int.from_bytes(data[1:3], "big"), int.from_bytes(data[15:17], "big")
            if maximum and hp <= maximum and 1 <= data[14] <= 100:
                # Only displayed species/level and bar granularity, not exact
                # enemy HP, move list, PP, types, stats, or unrevealed trainer team.
                bar = min(48, max(1 if hp else 0, hp * 48 // maximum))
                enemy = f"{self._species_name(data[0])} L{data[14]} HP bar {bar}/48"
        terrain, neighbors, objects = self._navigation(read, tiles, mode)
        text = tuple(line.strip() for line in lines if line.strip()) if mode not in ("overworld", "animation", "battle_animation") else ()
        facing = {0: "down", 4: "up", 8: "left", 12: "right"}.get(read(0xC109)[0], "?")
        if not battle:
            self._selection_context = ""
        return Observation(mode, read(MAP_ID)[0], _location(read(MAP_ID)[0]),
                           read(PLAYER_X)[0], read(PLAYER_Y)[0], facing, text,
                           menu, cursor, party, active_slot, battle, enemy,
                           read(BADGES)[0], bag, money, terrain, neighbors,
                           objects, read(HOF_COUNT)[0], frame)

    def _select(self, entry: MenuEntry, observation: Observation,
                identifier: str, description: str) -> LegalAction:
        row, column = observation.cursor or (entry.row, entry.column)
        pulses = []
        if entry.column != column:
            pulses.append(("right" if entry.column > column else "left", 4, 8))
        vertical = (entry.row - row) // 2
        pulses.extend(("down" if vertical > 0 else "up", 4, 8) for _ in range(abs(vertical)))
        pulses.append(("a", 4, 20))
        return LegalAction(identifier, description[:72], tuple(pulses),
                           (entry.row, entry.column), observation.mode)

    def legal_actions(self, observation: Observation) -> tuple[LegalAction, ...]:
        o = observation
        wait = LegalAction("wait", "Wait for animation/text", ((None, 0, 60),))
        back = LegalAction("back", "Back/cancel", (("b", 4, 20),))
        if o.mode in ("animation", "battle_animation"):
            return (wait,)
        if o.menu:
            choices = []
            active = o.party[o.active_slot] if o.party else None
            for entry in o.menu:
                label = entry.label
                if o.mode == "battle_command" and o.battle == "trainer" and label == "RUN":
                    continue
                if o.mode == "battle_moves" and active:
                    move = next((m for m in active.moves if m.name in label), None)
                    if move is None or move.pp == 0:
                        continue
                    description = f"{move.name} {move.kind} power{move.power} PP{move.pp}"
                elif o.mode == "party_menu":
                    mon = next((p for p in o.party if p.name and p.name in label), None)
                    if mon and self._selection_context == "switch" and mon.hp == 0:
                        continue
                    description = f"{label} L{mon.level} HP{mon.hp}/{mon.max_hp}" if mon else label
                else:
                    description = label
                choices.append(self._select(entry, o, f"pick_{entry.index}", description))
            # Visible page only. Scrolls are decisions, never hidden auto-paging.
            choices.extend((LegalAction("scroll_up", "Scroll/menu up", (("up", 4, 8),)),
                            LegalAction("scroll_down", "Scroll/menu down", (("down", 4, 8),)),
                            back))
            return tuple(choices[:12])
        if o.mode == "overworld":
            choices = [LegalAction(direction, f"Walk {direction}: {terrain}", ((direction, 8, 16),))
                       for direction, terrain in o.neighbors]
            choices.extend((LegalAction("interact", "Talk/read/use facing object", (("a", 4, 20),)),
                            LegalAction("menu", "Open party/items/field moves", (("start", 4, 20),)),
                            wait))
            return tuple(choices)
        if o.mode == "naming":
            return tuple(LegalAction(key, label, ((button, 4, 12),)) for key, label, button in (
                ("name_up", "Name cursor up", "up"), ("name_down", "Name cursor down", "down"),
                ("name_left", "Name cursor left", "left"), ("name_right", "Name cursor right", "right"),
                ("name_char", "Enter selected name character", "a"),
                ("name_done", "Finish name", "start"), ("name_erase", "Erase name character", "b")))
        if o.mode in ("dialogue", "battle_text"):
            return (LegalAction("continue", "Advance/read dialogue", (("a", 4, 30),)), wait, back)
        # Honest unknown/intro interface; no preprogrammed name/starter/walkthrough.
        return (LegalAction("start", "Begin/confirm title", (("start", 4, 24),)),
                LegalAction("confirm", "Confirm visible selection", (("a", 4, 24),)),
                wait, back)

    def note_action(self, action: LegalAction, observation: Observation) -> None:
        if observation.mode == "battle_command":
            self._selection_context = "switch" if "PKMN" in action.description else "item" if "ITEM" in action.description else ""

    def verify_target(self, action: LegalAction, current: Observation) -> None:
        if action.target is not None and (current.mode != action.menu_mode or current.cursor != action.target):
            raise RuntimeError("Menu changed before confirmation; unsafe macro was stopped.")

    def completion(self, read: ReadMemory, observation: Observation) -> Completion | None:
        """Validate an entire first recorded team, not a flag or model assertion.

        HOF entries occupy 16 bytes: internal species, level, 11-byte nickname,
        and padding. Check every real party member against SRAM bank 0. Require
        a pristine-run zero counter and unchanged full 96-byte record at least
        two *emulated* frames apart after a candidate first appears. The SRAM
        copy is a bounded synchronous CopyData, not a dialogue-driven write.
        This rejects observing the counter increment before the recording.
        """
        record = read(HOF_SRAM, HOF_TEAM_BYTES, 0)
        if self._hof_baseline is None:
            self._hof_baseline = record
        if observation.hof_count == 0:
            self._hof_zero_seen = True
        eligible = (self._hof_zero_seen and observation.hof_count == 1
                    and observation.map_id == HOF_MAP and observation.badges == 255
                    and not observation.battle and bool(observation.party)
                    and record != self._hof_baseline)
        if not eligible:
            self._hof_candidate = None
            return None
        for index, mon in enumerate(observation.party):
            if not 1 <= mon.species_id <= 190 or "MISSINGNO" in mon.species:
                self._hof_candidate = None
                return None
            entry = record[index * 16:(index + 1) * 16]
            if entry[:2] != bytes((mon.species_id, mon.level)) or entry[2:13] != mon.name_bytes:
                self._hof_candidate = None
                return None
        candidate = self._hof_candidate
        self._hof_candidate = (record, observation.frame)
        if candidate is None or candidate[0] != record or observation.frame - candidate[1] < 2:
            return None
        return Completion(tuple(f"{p.name} ({p.species}) L{p.level}" for p in observation.party),
                          sha256(record).hexdigest(), observation.frame)
