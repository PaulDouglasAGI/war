import pygame
import random

# Basic settings
WIDTH, HEIGHT = 800, 600
TILE_SIZE = 20
ROWS, COLS = HEIGHT // TILE_SIZE, WIDTH // TILE_SIZE

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

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
            if target.x > self.x: self.x += 1
            elif target.x < self.x: self.x -= 1
            if target.y > self.y: self.y += 1
            elif target.y < self.y: self.y -= 1

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
    if frame % 60 == 0:  # Spawn new unit every second
        spawn_unit("blue")
        spawn_unit("red")

    for u in units[:]:
        if u.hp <= 0:
            units.remove(u)
            continue
        u.move(units)
        u.attack(units)
        u.draw()

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
