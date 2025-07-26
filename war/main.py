import pygame
import random

# Basic settings
WIDTH, HEIGHT = 800, 600
TILE_SIZE = 20
ROWS, COLS = HEIGHT // TILE_SIZE, WIDTH // TILE_SIZE

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

    def move(self, units):
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

    def attack(self, units):
        for u in units:
            if u.team != self.team and u.x == self.x and u.y == self.y:
                u.hp -= 10
                break

    def draw(self):
        pygame.draw.rect(screen, self.color, (self.x * TILE_SIZE, self.y * TILE_SIZE, TILE_SIZE, TILE_SIZE))

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
    clock.tick(60)

pygame.quit()
