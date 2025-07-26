import pygame
import random
import csv
import os
from collections import deque

# =============== CONFIGURATION ==================
WIDTH, HEIGHT = 800, 600
TILE_SIZE = 20
ROWS, COLS = HEIGHT // TILE_SIZE, WIDTH // TILE_SIZE

FPS = 60
FOG_RADIUS = 5            # Tiles
HQ_HP = 500

# Terrain types
OPEN, WALL, FOREST = 0, 1, 2
TERRAIN_COLORS = {
    OPEN: (50, 50, 50),
    WALL: (90, 90, 90),
    FOREST: (34, 85, 34),
}

# Unit definitions
UNIT_TYPES = {
    "Infantry": {"hp": 100, "dmg": 10, "speed": 1, "cost": 3},
    "Tank":     {"hp": 200, "dmg": 20, "speed": 1, "cost": 5},  # slow but strong
    "Scout":    {"hp": 60,  "dmg": 5,  "speed": 2, "cost": 2},  # fast but weak

    # Support units
    "Shieldbearer": {"hp": 120, "dmg": 6, "speed": 1, "cost": 4},
    "Medic":        {"hp": 80,  "dmg": 3, "speed": 1, "cost": 4},
    "BarrierEng":   {"hp": 90,  "dmg": 4, "speed": 1, "cost": 5},
    "RepairBot":    {"hp": 70,  "dmg": 2, "speed": 1, "cost": 4},
    "Spotter":      {"hp": 60,  "dmg": 4, "speed": 1, "cost": 3},
}

TEAM_COLORS = {
    "blue": (0, 120, 255),
    "red": (255, 80, 80),
}

LOG_FILE = "log.csv"
LOG_FIELDS = ["frame", "unit_id", "event", "unit_type", "team", "x", "y"]

# =============== INITIALISE PYGAME ==============
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Advanced Battle")
clock = pygame.time.Clock()
font_small = pygame.font.SysFont(None, 18)
font_big = pygame.font.SysFont(None, 32)

# =============== UTILITY FUNCTIONS ==============

def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def in_bounds(pos):
    x, y = pos
    return 0 <= x < COLS and 0 <= y < ROWS

def neighbors(pos):
    x, y = pos
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if in_bounds((nx, ny)):
            yield nx, ny

# =============== TERRAIN GENERATION =============

def generate_terrain():
    while True:
        grid = [[OPEN for _ in range(COLS)] for _ in range(ROWS)]
        # sprinkle walls and forests
        for y in range(ROWS):
            for x in range(COLS):
                r = random.random()
                if r < 0.05:
                    grid[y][x] = WALL
                elif r < 0.15:
                    grid[y][x] = FOREST
        # leave room for HQs (will carve later)
        if reachable(grid):
            return grid

def reachable(grid):
    """Ensure path between tentative HQ zones"""
    start = (2, ROWS // 2)
    goal = (COLS - 3, ROWS // 2)
    q = deque([start])
    seen = {start}
    while q:
        cx, cy = q.popleft()
        if (cx, cy) == goal:
            return True
        for nx, ny in neighbors((cx, cy)):
            if (nx, ny) not in seen and grid[ny][nx] != WALL:
                seen.add((nx, ny))
                q.append((nx, ny))
    return False

terrain = generate_terrain()

# =============== EVENT LOGGER ===================

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        writer.writeheader()

def log_event(frame, unit, event):
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        writer.writerow({
            "frame": frame,
            "unit_id": getattr(unit, "uid", "-"),
            "event": event,
            "unit_type": getattr(unit, "u_type", "-"),
            "team": getattr(unit, "team", "-"),
            "x": getattr(unit, "x", "-"),
            "y": getattr(unit, "y", "-"),
        })

# =============== HQ CLASS =======================
class HQ:
    def __init__(self, team, x, y):
        self.team = team
        self.x, self.y = x, y  # top-left corner of 2x2 HQ
        self.hp = HQ_HP
        self.color = TEAM_COLORS[team]

    def tiles(self):
        for dy in range(2):
            for dx in range(2):
                yield self.x + dx, self.y + dy

    def draw(self):
        for tx, ty in self.tiles():
            pygame.draw.rect(screen, self.color, (tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        # Health bar above HQ
        bar_w = 2 * TILE_SIZE
        health_ratio = self.hp / HQ_HP
        pygame.draw.rect(screen, (200, 0, 0), (self.x * TILE_SIZE, (self.y - 0.3) * TILE_SIZE, bar_w, 4))
        pygame.draw.rect(screen, (0, 200, 0), (self.x * TILE_SIZE, (self.y - 0.3) * TILE_SIZE, bar_w * health_ratio, 4))

# =============== UNIT CLASS =====================
uid_counter = 0
class Unit:
    def __init__(self, team, x, y, u_type):
        global uid_counter
        uid_counter += 1
        self.uid = uid_counter
        self.team = team
        self.x = x
        self.y = y
        self.u_type = u_type
        self.color = TEAM_COLORS[team]
        self.max_hp = UNIT_TYPES[u_type]["hp"]
        self.hp = self.max_hp
        self.dmg = UNIT_TYPES[u_type]["dmg"]
        self.speed = UNIT_TYPES[u_type]["speed"]
        self.cost = UNIT_TYPES[u_type]["cost"]
        # Special mechanics flags
        self.dmg_reduction = 0.0  # set by Shieldbearer aura
        self.last_heal_frame = 0  # for Medic
        self.barrier_cd = FPS * 5 # for Barrier Engineer

        # Movement timing (spawn delay and pacing)
        self.move_cd = random.randint(10, 20)  # initial delay 10-20 frames

        # Siege counter for HQ capture
        self.hq_counter = 0

        # Attack cooldown
        self.attack_cd = 0

    # ---------- Pathfinding ---------------
    def bfs(self, goals, units):
        """Simple BFS avoiding walls and other units. goals is set of (x,y). Returns next step or None"""
        start = (self.x, self.y)
        q = deque([start])
        came = {start: None}
        occupied_start = {(u.x, u.y) for u in units if u is not self}
        while q:
            cur = q.popleft()
            if cur in goals:
                # reconstruct path back to start
                if cur == start:
                    return None  # already at goal; no movement needed
                # walk back until we reach the tile adjacent to start
                while came[cur] is not None and came[cur] != start:
                    cur = came[cur]
                return cur  # first step (may be directly the goal if adjacent)
            for nx, ny in neighbors(cur):
                if (nx, ny) in came:
                    continue
                if terrain[ny][nx] == WALL:
                    continue
                # Only block occupied tiles if they would be our immediate next step
                if cur == start and (nx, ny) in occupied_start:
                    continue
                came[(nx, ny)] = cur
                q.append((nx, ny))
        # No path found
        return start

    # ---------- Behavior Tree -------------
    def decide_target(self, units, visible_enemies, hqs, team_units):
        enemy_hq = hqs["red" if self.team == "blue" else "blue"]
        own_hq = hqs[self.team]
        # 1. Defend HQ if enemy within 4 tiles of HQ
        close_enemies = [e for e in visible_enemies if min(manhattan((tx, ty), (e.x, e.y)) for tx, ty in own_hq.tiles()) <= 4]
        if close_enemies:
            return random.choice(close_enemies)
        # 2. Regroup if isolated and team small (<3)
        if len(team_units) < 3:
            nearest_ally = None
            min_d = 999
            for ally in team_units:
                if ally is self:
                    continue
                d = manhattan((self.x, self.y), (ally.x, ally.y))
                if d < min_d:
                    min_d = d
                    nearest_ally = ally
            if nearest_ally and min_d > 4:
                return nearest_ally
        # 3. If enough forces, advance into enemy territory (towards enemy HQ)
        if len(team_units) >= 5:
            return enemy_hq
        # Default: hold position near HQ
        return own_hq

    # ---------- Update per frame -----------
    def update(self, frame, units, hqs, visible_map):
        # Global movement cooldown pacing
        if self.attack_cd > 0:
            self.attack_cd -= 1
        if self.move_cd > 0:
            self.move_cd -= 1
            # Even while waiting we can still attack if someone stands on us
            self.attack(units, hqs, frame)
            return
        if self.cooldown > 0:
            self.cooldown -= 1
            return
        # Determine visible enemies (within FOG_RADIUS) provided they are visible on map
        visible_enemies = [u for u in units if u.team != self.team and (u.x, u.y) in visible_map[self.team]]
        team_units = [u for u in units if u.team == self.team]

        # Priority: engage enemy within 5 tiles if any visible
        close_enemies = [e for e in visible_enemies if manhattan((self.x,self.y),(e.x,e.y))<=5]
        if close_enemies:
            target_obj = min(close_enemies, key=lambda e: manhattan((self.x,self.y),(e.x,e.y)))
        else:
            target_obj = self.decide_target(units, visible_enemies, hqs, team_units)

        if isinstance(target_obj, Unit):
            target_pos = {(target_obj.x, target_obj.y)}
        else:  # HQ
            target_pos = set(target_obj.tiles())

        # Pathfinding / movement
        for _ in range(self.speed):  # Scouts move twice
            step = self.bfs(target_pos, units)
            if step and step != (self.x, self.y):
                if any(u.x == step[0] and u.y == step[1] for u in units):
                    # Next tile is occupied; wait this turn
                    # Optional debug
                    # print(f"[{self.team}] Unit at {(self.x,self.y)} path blocked at {step}")
                    break
                self.move_to(*step, frame)
                print(f"[{self.team}] Unit {self.uid} moved to {(self.x,self.y)} cd reset")
                self.move_cd = random.randint(10,20)
            # Attack if on same tile
            attacked = self.attack(units, hqs, frame)
            if attacked:
                break  # stop after attack

        # ===== Support abilities =====
        if self.u_type == "Shieldbearer":
            for ally in units:
                if ally.team == self.team and ally is not self and manhattan((ally.x,ally.y),(self.x,self.y))<=2:
                    ally.dmg_reduction = max(ally.dmg_reduction, 0.5)

        elif self.u_type == "Medic":
            if frame - self.last_heal_frame >= FPS:  # heal every second (60 frames)
                for ally in units:
                    if ally.team == self.team and ally.hp < ally.max_hp and manhattan((ally.x,ally.y),(self.x,self.y))<=2:
                        ally.hp = min(ally.max_hp, ally.hp+1)
                        print(f"Medic {self.uid} healed {ally.uid} to {ally.hp}")
                self.last_heal_frame = frame

        elif self.u_type == "BarrierEng":
            if frame % (FPS*5) == 0:
                # pick adjacent tile towards enemy side
                dirs = [(-1,0),(1,0),(0,-1),(0,1)]
                random.shuffle(dirs)
                for dx,dy in dirs:
                    tx,ty = self.x+dx, self.y+dy
                    if in_bounds((tx,ty)) and terrain[ty][tx]==OPEN and not any(u.x==tx and u.y==ty for u in units):
                        terrain[ty][tx]=WALL
                        print(f"Barrier Engineer {self.uid} placed wall at {(tx,ty)}")
                        break

        elif self.u_type == "RepairBot":
            if frame % FPS ==0:
                for hq in hqs.values():
                    if manhattan((hq.x,hq.y),(self.x,self.y))<=2:
                        hq.hp = min(HQ_HP, hq.hp+2)
                        print(f"RepairBot {self.uid} repairs HQ {hq.team} to {hq.hp}")

        elif self.u_type == "Spotter":
            # extra vision handled in visibility phase: add position to visible map of team
            pass

    def move_to(self, nx, ny, frame):
        # Forest slows by 1 turn after entering
        if terrain[ny][nx] == FOREST:
            self.cooldown = 1
        log_event(frame, self, "move")
        self.x, self.y = nx, ny

    def attack(self, units, hqs, frame):
        # Attack adjacent (Manhattan distance <=1), subject to cooldown
        if self.attack_cd > 0:
            return False

        for u in units[:]:
            if u.team == self.team:
                continue
            if abs(u.x - self.x) + abs(u.y - self.y) <= 1:
                eff = int(self.dmg * (1 - getattr(u, 'dmg_reduction', 0)))
                u.hp -= eff
                print(f"Unit {self.uid} attacks {u.uid} for {eff} (raw {self.dmg})")
                log_event(frame, self, "attack")
                self.attack_cd = 5  # cooldown frames
                if u.hp <= 0:
                    print(f"Unit {u.uid} has been defeated.")
                    log_event(frame, u, "death")
                    if u in units:
                        units.remove(u)
                    else:
                        print(f"Attempted double-remove of unit {u.uid}")
                return True
        # Attack HQ
        enemy_hq = hqs["red" if self.team == "blue" else "blue"]
        if (self.x, self.y) in enemy_hq.tiles():
            self.hq_counter += 1
            print(f"[{self.team}] Unit {self.uid} sieging HQ {self.hq_counter}/3")
            if self.hq_counter >= 3:
                enemy_hq.hp -= self.dmg
                self.hq_counter = 0
                print(f"[{self.team}] Unit {self.uid} damaged enemy HQ for {self.dmg}")
                log_event(frame, self, "attack_hq")
        else:
            self.hq_counter = 0
        return False

    def draw(self):
        # Shape varies by unit type
        px, py = self.x * TILE_SIZE, self.y * TILE_SIZE
        rect = pygame.Rect(px, py, TILE_SIZE, TILE_SIZE)
        if self.u_type == "Infantry":
            pygame.draw.rect(screen, self.color, rect)
        elif self.u_type == "Tank":
            pygame.draw.rect(screen, self.color, rect.inflate(4, 4))
        else:  # Scout
            pygame.draw.circle(screen, self.color, rect.center, TILE_SIZE // 2)
        # Health bar
        ratio = self.hp / self.max_hp
        bar_w = TILE_SIZE
        pygame.draw.rect(screen, (200, 0, 0), (px, py - 4, bar_w, 3))
        pygame.draw.rect(screen, (0, 200, 0), (px, py - 4, bar_w * ratio, 3))

# =============== GAME STATE SETUP ===============

# Place HQs (ensure open terrain)
blue_hq = HQ("blue", 1, ROWS // 2 - 1)
red_hq = HQ("red", COLS - 3, ROWS // 2 - 1)
for tx, ty in list(blue_hq.tiles()) + list(red_hq.tiles()):
    terrain[ty][tx] = OPEN  # clear walls

hqs = {"blue": blue_hq, "red": red_hq}

units = []
resources = {"blue": 10, "red": 10}

# Initial spawns
for _ in range(3):
    def spawn_initial(team):
        hx, hy = (blue_hq.x, blue_hq.y) if team == "blue" else (red_hq.x, red_hq.y)
        sx = random.randint(hx - 1, hx + 2)
        sy = random.randint(hy - 1, hy + 2)
        if in_bounds((sx, sy)) and terrain[sy][sx] != WALL:
            u_type = random.choice(list(UNIT_TYPES))
            units.append(Unit(team, sx, sy, u_type))
    spawn_initial("blue")
    spawn_initial("red")

# Floating texts
floating_texts = []  # list of (text, x, y, lifetime)

def add_floating(text, x, y, color=(255, 255, 0)):
    floating_texts.append([font_small.render(text, True, color), x * TILE_SIZE, y * TILE_SIZE, 60])

# =============== MAIN LOOP ======================
frame = 0
running = True

while running:
    screen.fill((0, 0, 0))
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    frame += 1

    # ==== Resource accumulation and spawning ====
    if frame % FPS == 0:
        for team in ("blue", "red"):
            resources[team] += 1
            affordable = [t for t, v in UNIT_TYPES.items() if v["cost"] <= resources[team]]
            if affordable:
                u_type = random.choice(affordable)
                # attempt spawn near HQ within 2 tiles
                hq = hqs[team]
                spawn_candidates = []
                for dx in range(-2, 4):
                    for dy in range(-2, 4):
                        sx, sy = hq.x + dx, hq.y + dy
                        if not in_bounds((sx, sy)):
                            continue
                        if terrain[sy][sx] == WALL:
                            continue
                        if any(u.x == sx and u.y == sy for u in units):
                            continue
                        spawn_candidates.append((sx, sy))
                if spawn_candidates:
                    sx, sy = random.choice(spawn_candidates)
                    unit = Unit(team, sx, sy, u_type)
                    units.append(unit)
                    resources[team] -= UNIT_TYPES[u_type]["cost"]
                    log_event(frame, unit, "spawn")

    # ==== Visibility (fog of war) ===============
    visible = {"blue": set(), "red": set()}
    for team in ("blue", "red"):
        for u in units + [hqs[team]]:
            if getattr(u, "team", team) != team:
                continue
            origin = (u.x, u.y)
            if isinstance(u, Unit) and u.u_type == "Spotter":
                vrad = FOG_RADIUS + 2
            else:
                vrad = FOG_RADIUS
            for x in range(origin[0] - vrad, origin[0] + vrad + 1):
                for y in range(origin[1] - vrad, origin[1] + vrad + 1):
                    if in_bounds((x, y)) and manhattan(origin, (x, y)) <= vrad:
                        visible[team].add((x, y))

    # ==== Update units ==========================
    for u in units:
        u.dmg_reduction = 0.0  # reset shield effect each frame

    for u in units[:]:
        u.update(frame, units, hqs, visible)
        if u.hp <= 0:
            add_floating("Unit Destroyed", u.x, u.y)
            if u in units:
                units.remove(u)
            else:
                print(f"Attempted double-remove of unit {u.uid}")
            log_event(frame, u, "death")

    # ==== Check HQ destruction ==================
    for team, hq in list(hqs.items()):
        if hq.hp <= 0:
            winner = "Red" if team == "blue" else "Blue"
            msg = font_big.render(f"{winner} Wins!", True, (255, 255, 0))
            screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2))
            pygame.display.flip()
            pygame.time.delay(3000)
            running = False

    # ==== DRAW TERRAIN ==========================
    for y in range(ROWS):
        for x in range(COLS):
            col = TERRAIN_COLORS[terrain[y][x]]
            rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
            pygame.draw.rect(screen, col, rect)
    # Overlay fog (darken unseen tiles)
    fog_surface = pygame.Surface((TILE_SIZE, TILE_SIZE))
    fog_surface.set_alpha(120)
    fog_surface.fill((0, 0, 0))
    # viewer sees all, but we visualize combined visibility
    combined_visible = visible["blue"].union(visible["red"])
    for y in range(ROWS):
        for x in range(COLS):
            if (x, y) not in combined_visible:
                screen.blit(fog_surface, (x * TILE_SIZE, y * TILE_SIZE))

    # ==== DRAW HQs & Units ======================
    blue_hq.draw()
    red_hq.draw()
    for u in units:
        u.draw()

    # ==== Floating texts ========================
    for ft in floating_texts[:]:
        surf, fx, fy, life = ft
        screen.blit(surf, (fx, fy - (60 - life)))
        ft[3] -= 1
        if ft[3] <= 0:
            floating_texts.remove(ft)

    # ==== HUD ==================================
    blue_cnt = sum(1 for u in units if u.team == "blue")
    red_cnt = sum(1 for u in units if u.team == "red")
    hud = font_small.render(f"Blue: {blue_cnt}  Res: {resources['blue']}    |    Red: {red_cnt}  Res: {resources['red']}", True, (255, 255, 255))
    screen.blit(hud, (WIDTH // 2 - hud.get_width() // 2, 5))

    # ==== Hover info ===========================
    mx, my = pygame.mouse.get_pos()
    gx, gy = mx // TILE_SIZE, my // TILE_SIZE
    for u in units:
        if u.x == gx and u.y == gy:
            hover = font_small.render(f"{u.u_type} ({u.hp}/{u.max_hp})", True, (255, 255, 255))
            screen.blit(hover, (mx + 10, my + 10))
            break

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()