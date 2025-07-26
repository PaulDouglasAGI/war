import os
import random
import time
from collections import defaultdict

from colorama import init, Fore, Back, Style

# ============= INITIALISE COLORAMA (cross-platform colors) =============
init(autoreset=True)

# ===================== GAME CONFIGURATION ==============================
WIDTH, HEIGHT = 60, 30  # grid size (columns, rows)
FPS = 10                # console refresh rate (frames per second)

# Visual/animation tuning
ANIM_PERIOD = FPS * 3     # terrain animation toggle every 3 seconds

# Fog-of-war support (set to True to enable)
FOG_ENABLED = False
FOG_RADIUS = 8

# Unit trail persistence
TRAIL_FADE = 3  # frames

MOVE_INTERVAL_MIN = FPS // 2  # 0.5 seconds
MOVE_INTERVAL_MAX = FPS       # 1   second

LEFT_END = WIDTH // 3 - 1
MID_END = 2 * WIDTH // 3 - 1

# Terrain distribution probabilities
TERRAIN_PROBS = {
    '.': 0.82,  # plains
    '~': 0.05,  # water
    '#': 0.08,  # wall
    '*': 0.05,  # resource tile (decorative)
}
TERRAIN_LIST = [t for t, p in TERRAIN_PROBS.items() for _ in range(int(p * 100))]

TEAM_COLORS = {
    'blue': Fore.CYAN,
    'red': Fore.RED,
}

HEALTH_COLORS = {
    'high': Fore.GREEN,
    'med': Fore.YELLOW,
    'low': Fore.RED,
}

# Stats tracking
kills = {'blue': 0, 'red': 0}

# Unit trail map: (x,y) -> remaining_frames
trail = {}

# ===================== DATA CLASSES ====================================
class Unit:
    uid_counter = 0

    def __init__(self, x, y, team, symbol='A'):
        Unit.uid_counter += 1
        self.id = Unit.uid_counter
        self.x = x
        self.y = y
        self.team = team
        self.symbol = symbol
        self.base_hp = 100
        self.hp = self.base_hp
        self.base_dmg = 10
        self.dmg = self.base_dmg
        self.move_cd = random.randint(MOVE_INTERVAL_MIN, MOVE_INTERVAL_MAX)
        self.flash = 0  # frames to flash after attacking
        self.kills = 0
        self.xp = 0
        self.is_elite = False

    def _reset_cd(self):
        self.move_cd = random.randint(MOVE_INTERVAL_MIN, MOVE_INTERVAL_MAX)

    def attempt_move(self, units):
        if self.move_cd > 0:
            self.move_cd -= 1
            return
        enemies = [u for u in units if u.team != self.team]
        if not enemies:
            return
        target = min(enemies, key=lambda e: abs(e.x - self.x) + abs(e.y - self.y))

        # record trail before moving
        trail[(self.x, self.y)] = TRAIL_FADE
        # Simple movement
        if target.x > self.x:
            self.x += 1
        elif target.x < self.x:
            self.x -= 1
        if target.y > self.y:
            self.y += 1
        elif target.y < self.y:
            self.y -= 1
        # Clamp
        self.x = max(0, min(self.x, WIDTH - 1))
        self.y = max(0, min(self.y, HEIGHT - 1))
        self._reset_cd()

    def attempt_attack(self, units, log):
        for u in units:
            if u.team != self.team and u.x == self.x and u.y == self.y:
                dmg = self.dmg
                u.hp -= dmg
                log.append(f"{self.describe()} attacked {u.describe()} for {dmg} dmg")
                self.flash = 2
                if u.hp <= 0:
                    log.append(f"{u.describe()} was destroyed")
                    units.remove(u)
                    kills[self.team] += 1
                    print('\a', end='')  # beep on kill
                    # XP gain
                    self.kills += 1
                    self.xp += 1
                    if self.xp >= 3 and not self.is_elite:
                        self.become_elite(log)
                return

    def become_elite(self, log):
        self.is_elite = True
        self.symbol = 'E'
        self.max_hp = self.base_hp + 50
        self.hp += 50
        self.dmg = self.base_dmg + 5
        # slightly faster moves
        self.move_cd = max(self.move_cd - 1, MOVE_INTERVAL_MIN // 2)
        log.append(f"{self.describe()} has become ELITE!")

    def describe(self):
        return f"{self.team[0].upper()}{self.id}"

    def view_symbol(self):
        health_col = HEALTH_COLORS['high'] if self.hp > 66 else HEALTH_COLORS['med'] if self.hp > 33 else HEALTH_COLORS['low']
        base_col = TEAM_COLORS[self.team]
        color = Style.BRIGHT + base_col if self.is_elite else base_col
        if self.flash:
            # Extra bright flash when attacking
            color = Style.BRIGHT + Fore.WHITE
            self.flash -= 1
        return f"{color}{self.symbol}{Style.RESET_ALL}{health_col}"

# ===================== MAP & GAME SETUP ================================

def make_terrain():
    grid = [[random.choice(TERRAIN_LIST) for _ in range(WIDTH)] for _ in range(HEIGHT)]
    # Clear left/right spawn columns to plains so units/HQ spawn nicely
    for y in range(HEIGHT):
        for x in list(range(2)) + list(range(WIDTH-2, WIDTH)):
            grid[y][x] = '.'
    return grid

terrain = make_terrain()

# ======= Control map for territory capture ========
control_map = [[None for _ in range(WIDTH)] for _ in range(HEIGHT)]  # 'blue', 'red', or None
capture_team = [[None for _ in range(WIDTH)] for _ in range(HEIGHT)]
capture_timer = [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)]  # frames standing
vacate_timer = [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)]   # frames since friendly left

# Permanently set HQ tiles ownership
for team, (hx, hy) in {'blue': (1, HEIGHT // 2), 'red': (WIDTH - 2, HEIGHT // 2)}.items():
    control_map[hy][hx] = team

units = []
resources = {'blue': 10, 'red': 10}

HQ_POS = {'blue': (1, HEIGHT // 2), 'red': (WIDTH - 2, HEIGHT // 2)}

# Headquarters health
HQ_MAX_HP = 300
hq_hp = {'blue': HQ_MAX_HP, 'red': HQ_MAX_HP}

def spawn_unit(team):
    # spawn in left/right third depending on team, avoid occupied tiles
    attempts = 20
    while attempts:
        attempts -= 1
        if team == 'blue':
            x = random.randint(0, LEFT_END)
        else:
            x = random.randint(MID_END + 1, WIDTH - 1)
        y = random.randint(0, HEIGHT - 1)
        if any(u.x == x and u.y == y for u in units):
            continue
        units.append(Unit(x, y, team))
        print('\a', end='')  # beep on spawn
        break

# initial spawns
for _ in range(5):
    spawn_unit('blue')
    spawn_unit('red')

attack_log = []  # rolling log
MAX_LOG_LINES = 5

# ===================== SYSTEMS =========================================

CAPTURE_FRAMES = FPS * 3      # 3 seconds to capture
VACATE_FRAMES = FPS * 10      # 10 seconds to lose control
RESOURCE_INTERVAL = FPS * 5   # resources from captured tiles

def update_control_map(frame):
    """Handle tile capture and decay"""
    # 1. Build quick lookup of units per tile
    unit_lookup = defaultdict(list)
    for u in units:
        unit_lookup[(u.x, u.y)].append(u)

    for y in range(HEIGHT):
        for x in range(WIDTH):
            # Skip HQ tiles (permanent)
            if (x, y) in HQ_POS.values():
                continue

            units_here = unit_lookup.get((x, y))

            if units_here:
                team_here = units_here[0].team
                # reset vacate timer because friendly present
                vacate_timer[y][x] = 0
                if capture_team[y][x] == team_here:
                    capture_timer[y][x] += 1
                else:
                    capture_team[y][x] = team_here
                    capture_timer[y][x] = 1

                # complete capture
                if capture_timer[y][x] >= CAPTURE_FRAMES:
                    control_map[y][x] = team_here
            else:
                # no unit; reset capture progress
                capture_timer[y][x] = 0
                capture_team[y][x] = None

                # track vacate for controlled tile
                if control_map[y][x] is not None:
                    vacate_timer[y][x] += 1
                    if vacate_timer[y][x] >= VACATE_FRAMES:
                        control_map[y][x] = None
                        vacate_timer[y][x] = 0

def award_control_resources(frame):
    if frame % RESOURCE_INTERVAL != 0:
        return
    # count tiles per team
    count = {'blue': 0, 'red': 0}
    for row in control_map:
        for owner in row:
            if owner in count:
                count[owner] += 1
    for team in ('blue', 'red'):
        resources[team] += count[team]

def check_hq_status(frame, log):
    # Attack HQ once per second
    if frame % FPS != 0:
        return False  # not game over
    for u in units:
        for enemy_team, pos in HQ_POS.items():
            if enemy_team != u.team and (u.x, u.y) == pos:
                hq_hp[enemy_team] -= u.dmg
                log.append(f"{u.describe()} hit {enemy_team.upper()} HQ for {u.dmg} dmg")
                print('\a', end='')
                if hq_hp[enemy_team] <= 0:
                    return True
    return False

# ===================== RENDERING =======================================

def clear_screen():
    print('\033[H\033[J', end='')

TOP_BORDER = '┌' + '─' * (LEFT_END) + '┬' + '─' * (MID_END - LEFT_END) + '┬' + '─' * (WIDTH - MID_END - 1) + '┐'
MID_LABELS = (
    '│' + 'TEAM A'.center(LEFT_END) + '│' +
    "NO MAN'S LAND".center(MID_END - LEFT_END) + '│' +
    'TEAM B'.center(WIDTH - MID_END - 1) + '│'
)
BOTTOM_BORDER = '└' + '─' * (LEFT_END) + '┴' + '─' * (MID_END - LEFT_END) + '┴' + '─' * (WIDTH - MID_END - 1) + '┘'


def render(frame):
    clear_screen()
    print(TOP_BORDER)
    print(MID_LABELS)

    # Build grid lines
    cell_strings = [[' ' for _ in range(WIDTH)] for _ in range(HEIGHT)]
    # Place terrain with simple animation
    anim_toggle = (frame // (ANIM_PERIOD // 2)) % 2 == 0
    for y in range(HEIGHT):
        for x in range(WIDTH):
            t = terrain[y][x]
            if t == '*':  # resource twinkle
                sym = '*' if anim_toggle else '+'
                cell_strings[y][x] = (Style.BRIGHT + Fore.YELLOW + sym + Style.RESET_ALL)
            elif t == '~':
                color = Fore.BLUE if anim_toggle else Style.DIM + Fore.BLUE
                cell_strings[y][x] = color + '~' + Style.RESET_ALL
            else:
                if control_map[y][x] == 'blue':
                    cell_strings[y][x] = Back.BLUE + t + Style.RESET_ALL
                elif control_map[y][x] == 'red':
                    cell_strings[y][x] = Back.RED + t + Style.RESET_ALL
                else:
                    cell_strings[y][x] = t
    # Place HQs
    for team, (hx, hy) in HQ_POS.items():
        icon = ('⛩' if team == 'blue' else '⚑')
        cell_strings[hy][hx] = TEAM_COLORS[team] + icon + Style.RESET_ALL
    # Place unit trails (fade)
    for (tx, ty), remaining in list(trail.items()):
        if remaining <= 0:
            del trail[(tx, ty)]
            continue
        if cell_strings[ty][tx] == ' ':
            cell_strings[ty][tx] = Style.DIM + '.' + Style.RESET_ALL
        trail[(tx, ty)] = remaining - 1

    # Place units
    for u in units:
        cell_strings[u.y][u.x] = u.view_symbol()
    # Print rows with separators between regions
    for y in range(HEIGHT):
        row_str = '│'
        for x in range(WIDTH):
            if x == LEFT_END + 1 or x == MID_END + 1:
                # boundary already has cell after print
                pass
            row_str += cell_strings[y][x]
            if x == LEFT_END or x == MID_END:
                row_str += '│'
        row_str += '│'
        print(row_str)
    print(BOTTOM_BORDER)

    # Scoreboard
    blue_cnt = sum(1 for u in units if u.team == 'blue')
    red_cnt = sum(1 for u in units if u.team == 'red')
    print(f"{Fore.CYAN}TEAM A{Style.RESET_ALL}: {blue_cnt} units | {resources['blue']} res | Kills: {kills['blue']}")
    print(f"{Fore.RED}TEAM B{Style.RESET_ALL}: {red_cnt} units | {resources['red']} res | Kills: {kills['red']}")
    print(f"Frame: {frame}")

    # HQ health display
    print(f"{Fore.CYAN}BLUE HQ{Style.RESET_ALL}: {hq_hp['blue']} HP      {Fore.RED}RED HQ{Style.RESET_ALL}: {hq_hp['red']} HP")

    # Log lines
    for line in attack_log[-MAX_LOG_LINES:]:
        print(line)

# ===================== MAIN LOOP =======================================
start_time = time.time()
frame = 0

try:
    while True:
        # === resource gain and spawn (once per second) ===
        if frame % FPS == 0 and frame != 0:
            for team in ('blue', 'red'):
                resources[team] += 1
                if resources[team] >= 3:
                    spawn_unit(team)
                    resources[team] -= 3
        # === unit logic ===
        for u in units[:]:
            u.attempt_move(units)
            u.attempt_attack(units, attack_log)

        # === systems ===
        update_control_map(frame)
        award_control_resources(frame)
        game_over = check_hq_status(frame, attack_log)
        if game_over:
            winner = 'TEAM A' if hq_hp['red'] <= 0 else 'TEAM B'
            print('\a')
            print(f"\n{Style.BRIGHT}{Fore.YELLOW}{winner} DESTROYED THE ENEMY HQ!{Style.RESET_ALL}")
            break
        # === render ===
        if FOG_ENABLED:
            # Compute visibility for fog (viewer perspective = both teams for now)
            visible = set()
            for u in units:
                for dx in range(-FOG_RADIUS, FOG_RADIUS + 1):
                    for dy in range(-FOG_RADIUS, FOG_RADIUS + 1):
                        if abs(dx) + abs(dy) <= FOG_RADIUS:
                            vx, vy = u.x + dx, u.y + dy
                            if 0 <= vx < WIDTH and 0 <= vy < HEIGHT:
                                visible.add((vx, vy))
            # hide unseen unit positions by temporarily clearing their cell before render
            hidden_units = []
            for u in units:
                if (u.x, u.y) not in visible:
                    hidden_units.append(u)
            for hu in hidden_units:
                units.remove(hu)
            render(frame)
            units.extend(hidden_units)
        else:
            render(frame)
        # trim logs
        if len(attack_log) > 100:
            attack_log[:] = attack_log[-100:]
        # recompute unit counts for win check
        blue_cnt = sum(1 for u in units if u.team == 'blue')
        red_cnt = sum(1 for u in units if u.team == 'red')
        # === win check ===
        if blue_cnt == 0 or red_cnt == 0:
            winner = 'TEAM B' if blue_cnt == 0 else 'TEAM A'
            print('\a')  # victory beep
            print(f"\n{Style.BRIGHT}{Fore.YELLOW}{winner} WINS!{Style.RESET_ALL}")
            break

        # === wait ===
        frame += 1
        time.sleep(1 / FPS)
except KeyboardInterrupt:
    print("\nExiting...")