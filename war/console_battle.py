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
        self.max_hp = self.base_hp
        self.base_dmg = 10
        self.dmg = self.base_dmg
        self.move_cd = random.randint(MOVE_INTERVAL_MIN, MOVE_INTERVAL_MAX)
        self.flash = 0  # frames to flash after attacking
        self.kills = 0
        self.xp = 0
        self.is_elite = False
        # Morale & supply
        self.morale = 100
        self.unsupplied = False
        self.is_commander = False  # set later for commander units

    def _reset_cd(self):
        global current_weather
        penalty = 2 if current_weather == 'rain' else 1
        base_interval = random.randint(MOVE_INTERVAL_MIN, MOVE_INTERVAL_MAX)
        if getattr(self, 'aura_bonus', False):
            base_interval = int(base_interval * 0.9)
        self.move_cd = base_interval * penalty

    def attempt_move(self, units):
        # Morale based hesitation and fleeing
        if self.morale < 20:
            # flee: move opposite direction of enemy HQ (along x axis)
            dx = -1 if self.team == 'blue' else 1
            target_x = self.x + dx
            if 0 <= target_x < WIDTH:
                trail[(self.x, self.y)] = TRAIL_FADE
                self.x = target_x
                self._reset_cd()
            return
        elif self.morale < 30 and random.random() < 0.5:
            # hesitation skip move
            return
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
                dmg = int(self.dmg * 1.25) if getattr(self, 'aura_bonus', False) else self.dmg
                u.hp -= dmg
                log.append(f"{self.describe()} attacked {u.describe()} for {dmg} dmg")
                self.flash = 2
                if u.hp <= 0:
                    log.append(f"{u.describe()} was destroyed")
                    units.remove(u)
                    apply_nearby_death_morale(u)
                    if u.is_commander:
                        log.append(f"Commander of {u.team.upper()} has fallen! Morale decreased.")
                        for ally in units:
                            if ally.team == u.team:
                                ally.morale = max(0, ally.morale - 30)
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
    # spawn at or near barracks
    bx, by = BARRACKS_POS[team]
    attempts = 20
    while attempts:
        attempts -= 1
        offset_choices = [(0,0),(1,0),(-1,0),(0,1),(0,-1)]
        dx, dy = random.choice(offset_choices)
        x, y = bx+dx, by+dy
        if not (0<=x<WIDTH and 0<=y<HEIGHT):
            continue
        if any(u.x==x and u.y==y for u in units):
            continue
        units.append(Unit(x,y,team))
        print('\a', end='')
        break

# initial spawns
for _ in range(5):
    spawn_unit('blue')
    spawn_unit('red')

# === Commanders and Barracks ===

def create_commander(team):
    bx, by = HQ_POS[team]
    cmd = Unit(bx, by, team, symbol='C')
    cmd.is_commander = True
    cmd.base_hp += 100
    cmd.hp = cmd.base_hp
    cmd.base_dmg += 5
    cmd.dmg = cmd.base_dmg
    units.append(cmd)

create_commander('blue')
create_commander('red')

# Barracks position near HQ
BARRACKS_POS = {
    'blue': (HQ_POS['blue'][0]+1, HQ_POS['blue'][1]),
    'red': (HQ_POS['red'][0]-1, HQ_POS['red'][1])
}

# Ensure terrain plain
for pos in BARRACKS_POS.values():
    terrain[pos[1]][pos[0]] = '.'

# === Neutral Special Buildings ===
BUILDINGS = []  # list of dicts: {'type': 'tower'/'factory', 'pos':(x,y), 'owner':None/'blue'/'red'}

def place_building(b_type, symbol):
    attempts = 100
    while attempts:
        attempts -= 1
        x = random.randint(2, WIDTH-3)
        y = random.randint(0, HEIGHT-1)
        if (x,y) in HQ_POS.values() or (x,y) in BARRACKS_POS.values():
            continue
        if any(b['pos']==(x,y) for b in BUILDINGS):
            continue
        if terrain[y][x] != '.':
            continue
        BUILDINGS.append({'type': b_type, 'pos':(x,y), 'owner': None, 'symbol': symbol, 'capture_timer':0, 'capture_team': None})
        break

# Place one tower and one factory
place_building('tower','T')
place_building('factory','F')

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

    # Factories give +1 res per sec
    for b in BUILDINGS:
        if b['type']=='factory' and b['owner']:
            resources[b['owner']]+=1

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

# ===================== WEATHER SYSTEM ==================================

WEATHER_EVENTS = ['rain', 'fog', 'storm']
current_weather = 'clear'
weather_timer = 0  # remaining frames for current event
next_weather_in = random.randint(FPS * 30, FPS * 60)  # frames until next event

def update_weather(frame, log):
    global current_weather, weather_timer, next_weather_in

    if current_weather == 'clear':
        if frame >= next_weather_in:
            current_weather = random.choice(WEATHER_EVENTS)
            weather_timer = FPS * 10  # 10 seconds
            next_weather_in = frame + random.randint(FPS * 30, FPS * 60)
            log.append(f"Weather changed to {current_weather.upper()}")
    else:
        weather_timer -= 1
        if weather_timer <= 0:
            log.append("Weather cleared")
            current_weather = 'clear'
            weather_timer = 0

# ===================== MORALE & SUPPLY ==================================

def adjacent_coords(x, y):
    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
        nx, ny = x+dx, y+dy
        if 0<=nx<WIDTH and 0<=ny<HEIGHT:
            yield nx, ny

def update_morale():
    # For each unit compute morale adjustments
    unit_at = defaultdict(list)
    for u in units:
        unit_at[(u.x, u.y)].append(u)

    for u in units:
        delta = 0
        allies_adj = 0
        enemies_adj = 0
        for nx, ny in adjacent_coords(u.x, u.y):
            for other in unit_at.get((nx, ny), []):
                if other.team == u.team:
                    allies_adj += 1
                else:
                    enemies_adj += 1
        delta += allies_adj * 5
        delta -= enemies_adj * 3
        # cap
        if u.unsupplied:
            delta = min(delta, 0)  # cannot gain morale while unsupplied
        if delta:
            u.morale = max(0, min(100, u.morale + delta))

        # hesitation/flee flags handled in movement

def apply_nearby_death_morale(dead_unit):
    for u in units:
        if abs(u.x - dead_unit.x) + abs(u.y - dead_unit.y) == 1 and u.team == dead_unit.team:
            u.morale = max(0, u.morale - 10)

def update_supply_status(frame):
    # BFS from HQs through owned tiles or units to mark supplied
    supplied_tiles = {'blue': set(), 'red': set()}

    for team in ('blue','red'):
        hq_pos = HQ_POS[team]
        queue=[hq_pos]
        visited = set(queue)
        while queue:
            cx, cy = queue.pop()
            supplied_tiles[team].add((cx, cy))
            for nx, ny in adjacent_coords(cx, cy):
                if (nx, ny) in visited:
                    continue
                # allowed traverse if tile controlled by team OR has friendly unit
                if control_map[ny][nx]==team or any(u.x==nx and u.y==ny and u.team==team for u in units):
                    visited.add((nx, ny))
                    queue.append((nx, ny))

    # Mark units
    for u in units:
        if (u.x, u.y) in supplied_tiles[u.team]:
            u.unsupplied=False
        else:
            u.unsupplied=True
            # attrition once per second
            if frame % FPS ==0:
                u.hp -= 1

# ===================== COMMANDER AURA ==================================

def update_commander_aura():
    commanders = [u for u in units if u.is_commander]
    for u in units:
        u.aura_bonus = False
    for cmd in commanders:
        for u in units:
            if u.team == cmd.team and abs(u.x - cmd.x)+abs(u.y - cmd.y) <=2 and not u.is_commander:
                u.aura_bonus = True

# ===================== BUILDINGS CAPTURE & EFFECTS =====================

def update_buildings(frame):
    for b in BUILDINGS:
        x,y = b['pos']
        occupiers = [u for u in units if u.x==x and u.y==y]
        if occupiers:
            team = occupiers[0].team
            if b['capture_team']==team:
                b['capture_timer'] +=1
            else:
                b['capture_team']=team
                b['capture_timer']=1
            if b['owner']!=team and b['capture_timer']>=CAPTURE_FRAMES:
                b['owner']=team
                attack_log.append(f"{team.upper()} captured a {b['type'].upper()}!")
        else:
            b['capture_timer']=0
            b['capture_team']=None

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

    # Weather status line
    if current_weather == 'clear':
        weather_str = 'Clear'
    else:
        icon = {'rain':'🌧','fog':'🌫','storm':'🌩'}.get(current_weather,'?')
        weather_str = f"{icon} {current_weather.capitalize()} ({weather_timer//FPS}s remaining)"
    print(f"WEATHER: {weather_str}")

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

    # Place Barracks
    for team, (bx, by) in BARRACKS_POS.items():
        cell_strings[by][bx] = TEAM_COLORS[team] + 'B' + Style.RESET_ALL

    # Place special buildings
    for b in BUILDINGS:
        x,y = b['pos']
        color = TEAM_COLORS[b['owner']] if b['owner'] else Fore.WHITE
        cell_strings[y][x] = color + b['symbol'] + Style.RESET_ALL

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
                if resources[team] >= 3 and current_weather != 'storm':
                    spawn_unit(team)
                    resources[team] -= 3
        # === unit logic ===
        for u in units[:]:
            u.attempt_move(units)
            u.attempt_attack(units, attack_log)

        # === systems ===
        update_control_map(frame)
        award_control_resources(frame)
        update_weather(frame, attack_log) # Update weather
        update_morale() # Update morale
        update_supply_status(frame) # Update supply status
        update_commander_aura() # Update commander aura
        update_buildings(frame) # Update buildings

        for u in units[:]:
            if u.hp <= 0:
                attack_log.append(f"{u.describe()} died from attrition")
                units.remove(u)
                apply_nearby_death_morale(u)
                kills[('red' if u.team=='blue' else 'blue')] += 1
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
                radius = FOG_RADIUS - 2 if current_weather == 'fog' else FOG_RADIUS
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        if abs(dx) + abs(dy) <= radius:
                            vx, vy = u.x + dx, u.y + dy
                            if 0 <= vx < WIDTH and 0 <= vy < HEIGHT:
                                visible.add((vx, vy))
            # add tower vision
            for b in BUILDINGS:
                if b['type']=='tower' and b['owner']:
                    if b['owner'] in ('blue','red'):
                        bx, by = b['pos']
                        for dx in range(-5,6):
                            for dy in range(-5,6):
                                if abs(dx)+abs(dy)<=5:
                                    vx, vy = bx+dx, by+dy
                                    if 0<=vx<WIDTH and 0<=vy<HEIGHT:
                                        visible.add((vx,vy))
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