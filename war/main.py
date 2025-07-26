import pygame
import random

# Basic settings
WIDTH, HEIGHT = 800, 600
TILE_SIZE = 20
ROWS, COLS = HEIGHT // TILE_SIZE, WIDTH // TILE_SIZE

# Game timing
FPS = 30  # ticks per second (controls global speed)
# Units will attempt to move every MOVE_INTERVAL_MIN to MOVE_INTERVAL_MAX frames
MOVE_INTERVAL_MIN = FPS // 2   # 0.5 s
MOVE_INTERVAL_MAX = FPS       # 1   s

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 24)  # For scoreboard and win message

# Simple resource system: each side gains 1 point / second and spends 3 points per spawn
resources = {"blue": 0, "red": 0}

class Unit:
    def __init__(self, x, y, color, team):
        self.x = x
        self.y = y
        self.color = color
        self.hp = 100
        self.team = team
        # Movement cooldown so units move slower & at varied cadence
        self.move_cooldown = random.randint(MOVE_INTERVAL_MIN, MOVE_INTERVAL_MAX)
        # Flash timer used when this unit just attacked
        self.attack_flash = 0

    def _reset_cooldown(self):
        self.move_cooldown = random.randint(MOVE_INTERVAL_MIN, MOVE_INTERVAL_MAX)

    def move(self, units):
        # Throttle movement speed
        if self.move_cooldown > 0:
            self.move_cooldown -= 1
            return

        # Find enemy
        enemies = [u for u in units if u.team != self.team]
        if enemies:
            target = min(enemies, key=lambda e: abs(e.x - self.x) + abs(e.y - self.y))

            # Determine whether this unit should push into enemy territory
            blue_count = sum(1 for u in units if u.team == "blue")
            red_count = sum(1 for u in units if u.team == "red")
            push_mode = (blue_count >= 5 and self.team == "blue") or (red_count >= 5 and self.team == "red")

            # Move towards the target (simple Manhattan heuristic)
            if target.x > self.x: self.x += 1
            elif target.x < self.x: self.x -= 1
            if target.y > self.y: self.y += 1
            elif target.y < self.y: self.y -= 1

            # If not in push mode, do not cross the midline
            midline = COLS // 2
            if not push_mode:
                if self.team == "blue":
                    self.x = min(self.x, midline - 1)
                else:  # red team
                    self.x = max(self.x, midline)

            # Clamp to board limits
            self.x = max(0, min(self.x, COLS - 1))
            self.y = max(0, min(self.y, ROWS - 1))

        # Reset movement cooldown after attempting a move
        self._reset_cooldown()

    def attack(self, units):
        for u in units:
            if u.team != self.team and u.x == self.x and u.y == self.y:
                u.hp -= 10
                # Trigger flash so we can highlight attacker
                self.attack_flash = 5  # frames to highlight
                break

    def draw(self):
        # Draw unit with optional flash highlight
        draw_color = self.color
        if self.attack_flash > 0:
            # Lighten color for a brief moment to indicate attack
            draw_color = tuple(min(255, c + 100) for c in self.color)
            self.attack_flash -= 1

        rect = pygame.Rect(self.x * TILE_SIZE, self.y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        pygame.draw.rect(screen, draw_color, rect)

        # Health bar
        hp_ratio = self.hp / 100
        bar_width = TILE_SIZE
        pygame.draw.rect(screen, (150, 0, 0), (rect.x, rect.y - 4, bar_width, 3))
        pygame.draw.rect(screen, (0, 200, 0), (rect.x, rect.y - 4, bar_width * hp_ratio, 3))

        # Optional letter to show unit type (all same type here, show 'I')
        label = font.render('U', True, (255, 255, 255))
        label_rect = label.get_rect(center=rect.center)
        screen.blit(label, label_rect)

units = []

def spawn_unit(team):
    x = random.randint(0, COLS//2 - 1) if team == "blue" else random.randint(COLS//2, COLS - 1)
    y = random.randint(0, ROWS - 1)
    color = (0, 0, 255) if team == "blue" else (255, 0, 0)
    units.append(Unit(x, y, color, team))

# Initial spawns
for _ in range(10):
    spawn_unit("blue")
    spawn_unit("red")

frame = 0
running = True
while running:
    screen.fill((30, 30, 30))
    # === Draw grid ===
    grid_color = (60, 60, 60)
    for x in range(COLS + 1):
        pygame.draw.line(screen, grid_color, (x * TILE_SIZE, 0), (x * TILE_SIZE, HEIGHT))
    for y in range(ROWS + 1):
        pygame.draw.line(screen, grid_color, (0, y * TILE_SIZE), (WIDTH, y * TILE_SIZE))

    # Midline divider
    pygame.draw.line(screen, (200, 200, 200), (WIDTH // 2, 0), (WIDTH // 2, HEIGHT), 3)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    frame += 1
    # === Per-second updates ===
    if frame % 60 == 0:
        # Resource gain
        resources["blue"] += 1
        resources["red"] += 1

        # Attempt to spawn units if enough resources
        for team in ("blue", "red"):
            if resources[team] >= 3:
                spawn_unit(team)
                resources[team] -= 3

    for u in units[:]:
        if u.hp <= 0:
            units.remove(u)
            continue
        u.move(units)
        u.attack(units)
        u.draw()

    # === Scoreboard ===
    blue_count = sum(1 for u in units if u.team == "blue")
    red_count = sum(1 for u in units if u.team == "red")

    score_surf = font.render(f"Blue: {blue_count} (Res {resources['blue']})  |  Red: {red_count} (Res {resources['red']})", True, (255, 255, 255))
    screen.blit(score_surf, (10, 10))

    # === Win condition ===
    if blue_count == 0 or red_count == 0:
        winner = "Red" if blue_count == 0 else "Blue"
        win_surf = font.render(f"{winner} team wins!", True, (255, 255, 0))
        screen.blit(win_surf, (WIDTH // 2 - win_surf.get_width() // 2, HEIGHT // 2))
        pygame.display.flip()
        pygame.time.delay(3000)
        running = False

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
