from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
from OpenGL.GLUT import glutBitmapCharacter, GLUT_BITMAP_HELVETICA_18
import random
import math
import time

# Globals / Game parameters
camera_pos = (0, 500, 500)
fovY = 60
GRID_LENGTH = 600
MARGIN = 120  # minimum distance from edge
TROOP_RADIUS = 8
TANK_RADIUS = 20

# Mode selection (1 gun, 2 battle drive, 3 survival)
GAME_MODE = None  # will be set in main() via input()

# Entities stored as dicts in lists
troops = []   # human infantry: dict {id, x,y,z, vx,vy,hp,side,ammo,alive, last_fire}
tanks = []    # vehicle: dict {id, x,y,z, vx,vy, hp, side, alive, last_fire}
bullets = []  # dict {x,y,z, dx,dy,dz, speed, owner_side, damage, ttl}
bombs = []    # dict {x,y,z, owner_side, radius, timer, exploded}
powerups = [] # dict {x,y,z, type, spawn_time}
obstacles = [] # dict {x1,y1,x2,y2,height} axis-aligned boxes on ground
grass = []  # dict {x, y, z, height}

# Player is always a troop or tank on side 'A' (left) for input control
player_is_tank = False
player_id = None
player_side = "A"

# Game state
game_start_time = time.time()
last_power_spawn = time.time()
power_spawn_interval = 4.0  # seconds between spawn attempts
score = {"A": 0, "B": 0}
game_over = False
winner = None

# Cheats
cheat_unlimited_ammo = False
cheat_freeze_until = 0.0
cheat_autotarget = False

# Movement & timing
PLAYER_SPEED = 6.0
ENTITY_SPEED = 0.2
BULLET_SPEED = 50.0
BULLET_TTL = 3.5

# Camera control globals
cam_angle = 0.0      # rotation around Z axis (left/right)
cam_height = 500.0   # Z height
cam_distance = 500.0 # distance from origin
cam_x_offset = 0.0   # offset along X for up/down

# IDs
_next_id = 1
def _nextid():
    global _next_id
    i = _next_id
    _next_id += 1
    return i

# Misc
rand_var = 423

# Utility functions (kept inline, not as new top-level defs)

def draw_text(x, y, text, font=GLUT_BITMAP_HELVETICA_18):
    glColor3f(1,1,1)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, 1000, 0, 800)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

def draw_shapes():
    # placeholder shapes (keeps original intent)
    glPushMatrix()
    glColor3f(1, 0, 0)
    glTranslatef(0, 0, 0)
    glutSolidCube(60)
    glTranslatef(0, 0, 100)
    glColor3f(0, 1, 0)
    glutSolidCube(60)
    glColor3f(1, 1, 0)
    glScalef(2,2,2)
    gluCylinder(gluNewQuadric(), 40, 5, 150, 10, 10)
    glPopMatrix()

# Game mechanics within provided functions

#zoom in/out limit
def clamp(v, a, b): return max(a,min(b,v))

# avoiding moving over obstacles
def point_in_obstacle(x, y, z=0, radius=8):
    for ob in obstacles:
        if ob['shape'] in ['cube', 'cylinder']:
            if (ob['x1'] - radius <= x <= ob['x2'] + radius and
                ob['y1'] - radius <= y <= ob['y2'] + radius and
                -radius <= z <= ob['height'] + radius):
                return True
        elif ob['shape'] in ['rock', 'tree']:
            cx, cy = (ob['x1']+ob['x2'])/2, (ob['y1']+ob['y2'])/2
            r = max(ob['x2']-ob['x1'], ob['y2']-ob['y1'])/2 + radius
            if (math.hypot(x-cx, y-cy) <= r and
                -radius <= z <= ob['height'] + radius):
                return True
    return False

def keyboardListener(key, x, y):
    global cheat_unlimited_ammo, cheat_autotarget, cheat_freeze_until
    global game_over, score, player_is_tank, player_id, player_side, GAME_MODE
    global cam_height, cam_x_offset, cam_angle
    k = key.decode('utf-8').lower()

    # Cheats
    if k == 'u':
        cheat_unlimited_ammo = not cheat_unlimited_ammo
    if k == 'f':
        cheat_freeze_until = time.time() + 5.0
    if k == 't':
        cheat_autotarget = not cheat_autotarget
    if k == 'r':
        reset_game()

    # Camera vertical movement
    if k == 'z':       # move camera up
        cam_height += 12.0
        cam_height = clamp(cam_height, 0, 700.0)
    if k == 'x':       # move camera down
        cam_height -= 12.0
        cam_height = clamp(cam_height, 0, 700.0)
    # Camera rotation around center
    if k == 'c':       # rotate left
        cam_angle -= 6
    if k == 'v':       # rotate right
        cam_angle += 6

    # Rotate all troops and tanks
    if k == 'j':       # rotate left
        for s in troops:
            if s['alive']:
                s['rot'] -= 5
        for t in tanks:
            if t['alive']:
                t['rot'] -= 5
    if k == 'k':       # rotate right
        for s in troops:
            if s['alive']:
                s['rot'] += 5
        for t in tanks:
            if t['alive']:
                t['rot'] += 5

def specialKeyListener(key, x, y):
    global camera_pos, player_id, player_is_tank
    # Move player entity with arrow keys (left/right/up/down)
    if player_id is None:
        return
    dx = dy = 0.0
    if key == GLUT_KEY_LEFT:
        dx = -1
    elif key == GLUT_KEY_RIGHT:
        dx = 1
    elif key == GLUT_KEY_UP:
        dy = 1
    elif key == GLUT_KEY_DOWN:
        dy = -1
    # apply to controlled entity (player)

    for t in tanks:
            if t['alive'] and t['side'] == player_side:
                new_tx = t['x'] + dx * PLAYER_SPEED
                new_ty = t['y'] + dy * PLAYER_SPEED
                new_tx = max(-GRID_LENGTH+20, min(GRID_LENGTH-20, new_tx))
                new_ty = max(-GRID_LENGTH+20, min(GRID_LENGTH-20, new_ty))
                # Only move if not inside an obstacle
                if point_in_obstacle(new_tx, new_ty, 8, TANK_RADIUS):
                    continue

                # Check for overlap with other tanks
                overlap = False
                for other_t in tanks:
                    if other_t is t or not other_t['alive']:
                        continue
                    dist_t = math.hypot(new_tx - other_t['x'], new_ty - other_t['y'])
                    if dist_t < TANK_RADIUS * 2:  # Minimum separation for tanks
                        overlap = True
                        # Push the other_t tank away from the moving tank
                        push_dx_t = other_t['x'] - new_tx
                        push_dy_t = other_t['y'] - new_ty
                        push_dist_t = math.hypot(push_dx_t, push_dy_t)
                        if push_dist_t == 0:
                            # If exactly same position, push in a random direction
                            push_dx_t, push_dy_t = random.uniform(-1,1), random.uniform(-1,1)
                            push_dist_t = math.hypot(push_dx_t, push_dy_t)
                        # Normalize and push by a small amount
                        push_amount_t = 12  # You can adjust this value for tanks
                        other_t['x'] += (push_dx_t / push_dist_t) * push_amount_t
                        other_t['y'] += (push_dy_t / push_dist_t) * push_amount_t
                        # Clamp pushed tank to grid
                        other_t['x'] = max(-GRID_LENGTH+20, min(GRID_LENGTH-20, other_t['x']))
                        other_t['y'] = max(-GRID_LENGTH+20, min(GRID_LENGTH-20, other_t['y']))
                
                # Move the tank if not overlapping, or after pushing
                if not overlap:
                    t['x'] = new_tx
                    t['y'] = new_ty
                else:
                    t['x'] = new_tx
                    t['y'] = new_ty

    for s in troops:
        if s['alive'] and s['side'] == player_side:
            new_x = s['x'] + dx * PLAYER_SPEED
            new_y = s['y'] + dy * PLAYER_SPEED
            # Clamp to grid
            new_x = max(-GRID_LENGTH+10, min(GRID_LENGTH-10, new_x))
            new_y = max(-GRID_LENGTH+10, min(GRID_LENGTH-10, new_y))

            # Only move if not inside an obstacle
            if point_in_obstacle(new_x, new_y, 0):
               continue 

            # Check for overlap with other troops
            overlap = False
            for other in troops:
                if other is s or not other['alive']:
                    continue
                dist = math.hypot(new_x - other['x'], new_y - other['y'])
                if dist < 18:  # 18 is minimum separation
                    overlap = True
                    # Push the other troop away from the moving troop
                    push_dx = other['x'] - new_x
                    push_dy = other['y'] - new_y
                    push_dist = math.hypot(push_dx, push_dy)
                    if push_dist == 0:
                        # If exactly same position, push in a random direction
                        push_dx, push_dy = random.uniform(-1,1), random.uniform(-1,1)
                        push_dist = math.hypot(push_dx, push_dy)
                    # Normalize and push by a small amount
                    push_amount = 8  # You can adjust this value
                    other['x'] += (push_dx / push_dist) * push_amount
                    other['y'] += (push_dy / push_dist) * push_amount
                    # Clamp pushed troop to grid
                    other['x'] = max(-GRID_LENGTH+10, min(GRID_LENGTH-10, other['x']))
                    other['y'] = max(-GRID_LENGTH+10, min(GRID_LENGTH-10, other['y']))
            # Move the troop if not overlapping, or after pushing
            if not overlap:
                s['x'] = new_x
                s['y'] = new_y
            else:
                s['x'] = new_x
                s['y'] = new_y

def mouseListener(button, state, x, y):
    global bullets, bombs, cheat_unlimited_ammo, cheat_autotarget

    if button == GLUT_LEFT_BUTTON and state == GLUT_DOWN:
        for ent in troops + tanks:
            if not ent['alive'] or ent['side'] != player_side:
                continue

            sx, sy, sz = ent['x'], ent['y'], 8 if ent in troops else 12
            if ent.get('ammo', 0) <= 0 and not cheat_unlimited_ammo:
                continue
            if not cheat_unlimited_ammo:
                ent['ammo'] -= 1

            # Determine bullet/bomb direction
            if cheat_autotarget:
                target = find_nearest_enemy(ent['side'], sx, sy)
                if target:
                    dx = target['x'] - sx
                    dy = target['y'] - sy
                    angle_rad = math.atan2(dy, dx)
                else:
                    angle_rad = math.radians(ent.get('rot', 0))
            else:
                angle_rad = math.radians(ent.get('rot', 0))

            fire_offset = 20
            spawn_x = sx + math.cos(angle_rad) * fire_offset
            spawn_y = sy + math.sin(angle_rad) * fire_offset


            # Mode-based firing rules
            if GAME_MODE in (2, 3) and ent in tanks:
                # Tanks fire bombs
                BOMB_SPEED = 80
                bombs.append({
                    'x': spawn_x,
                    'y': spawn_y,
                    'dx': math.cos(angle_rad) * BOMB_SPEED,
                    'dy': math.sin(angle_rad) * BOMB_SPEED,
                    'owner': ent['side'],
                    'radius': 60,
                    'timer': 0.7,
                    'exploded': False
                })
            else:
                # Troops (any mode) and tanks in Mode 1 fire bullets
                bullets.append({
                    'x': spawn_x,
                    'y': spawn_y,
                    'z': sz,
                    'dx': math.cos(angle_rad),
                    'dy': math.sin(angle_rad),
                    'dz': 0,
                    'speed': BULLET_SPEED * 1.5,
                    'owner': ent['side'],
                    'damage': 10 if ent in troops else 18,
                    'ttl': BULLET_TTL * 3
                })

# Core helpers implemented as inline code we call from showScreen/idle
# (We are *not* adding top-level functions beyond those in template.)
def setupCamera():
    global cam_angle, cam_height, cam_distance, cam_x_offset
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(fovY, 1.25, 0.1, 1500)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    
    # Compute camera position in polar coordinates
    rad = math.radians(cam_angle)
    cam_x = cam_distance * math.sin(rad) + cam_x_offset
    cam_y = cam_distance * math.cos(rad)
    cam_z = cam_height

    # Look at center (0,0,0)
    gluLookAt(cam_x, cam_y, cam_z, 0, 0, 0, 0, 0, 1)

def idle():
    glutPostRedisplay()

#  Inline helpers used by showScreen 
# These are placed here for clarity but are executed inside showScreen or keyboardListener etc.

def find_nearest_enemy(side, x, y):
    # returns dict reference to nearest enemy entity (troop or tank) alive
    best = None
    bestd = 1e9
    enemy_side = "B" if side == "A" else "A"
    for t in troops + tanks:
        if t.get('alive') and t.get('side') == enemy_side:
            dx = t['x'] - x; dy = t['y'] - y
            d = math.hypot(dx, dy)
            if d < bestd:
                bestd = d; best = t
    return best

def line_intersects_obstacle(x1,y1,x2,y2):
    # simple check whether the segment intersects any obstacle's 2D box
    for ob in obstacles:
        ox1, oy1, ox2, oy2 = ob['x1'], ob['y1'], ob['x2'], ob['y2']
        # axis-aligned box intersection: sample a point along line and check if it passes through box
        # we'll discretely sample a few points along the line
        steps = 6
        for i in range(steps+1):
            t = i/steps
            sx = x1 + (x2-x1)*t
            sy = y1 + (y2-y1)*t
            if ox1 <= sx <= ox2 and oy1 <= sy <= oy2:
                return True
    return False

def reset_game():
    global troops, tanks, bullets, bombs, powerups, obstacles
    global score, game_over, winner, player_id, player_is_tank, game_start_time
    global last_power_spawn, cheat_unlimited_ammo, cheat_autotarget, cheat_freeze_until
    troops = []
    tanks = []
    bullets = []
    bombs = []
    powerups = []
    obstacles = []
    score = {"A": 0, "B": 0}
    game_over = False
    winner = None
    cheat_unlimited_ammo = False
    cheat_freeze_until = 0.0
    cheat_autotarget = False
    # recreate arena content
    init_arena(GAME_MODE)

def obstacle_overlaps(new_ob, existing_obs, min_gap=8):
    """Check if new_ob (dict with x1,y1,x2,y2) overlaps/touches any in existing_obs."""
    for ob in existing_obs:
        # Axis-aligned bounding box overlap with a minimum gap
        if (new_ob['x1'] - min_gap < ob['x2'] + min_gap and
            new_ob['x2'] + min_gap > ob['x1'] - min_gap and
            new_ob['y1'] - min_gap < ob['y2'] + min_gap and
            new_ob['y2'] + min_gap > ob['y1'] - min_gap):
            return True
    return False


def init_arena(mode):
    global troops, tanks, obstacles, player_id, player_is_tank, game_start_time, last_power_spawn, MARGIN
    game_start_time = time.time()
    last_power_spawn = time.time()
    # create obstacles randomly
    obstacles.clear()
    num_obstacles = 10
    max_attempts = 50  # Max tries to place each obstacle

    for i in range(num_obstacles):
        for attempt in range(max_attempts):
            shape = random.choice(['cube', 'cylinder', 'rock', 'tree'])
            cx = random.uniform(-GRID_LENGTH + MARGIN, GRID_LENGTH - MARGIN)
            cy = random.uniform(-GRID_LENGTH + MARGIN, GRID_LENGTH - MARGIN)

            if shape == 'cube':
                w = random.uniform(40, 70)
                h = random.uniform(40, 70)
                height = random.uniform(30, 80)
                new_ob = {
                    'x1': cx - w/2,
                    'y1': cy - h/2,
                    'x2': cx + w/2,
                    'y2': cy + h/2,
                    'height': height,
                    'shape': shape
                }
            elif shape == 'cylinder':
                w = random.uniform(30, 50)
                h = random.uniform(30, 50)
                height = random.uniform(60, 120)
                bark_line_count = random.randint(8, 12)
                bark_lines = []
                for j in range(bark_line_count):
                    z_offset = (j / (bark_line_count - 1)) * height
                    bark_radius = min(w, h) / 2 + random.uniform(-0.5, 0.5)
                    bark_color = (
                        random.uniform(0.6, 0.9),
                        random.uniform(0.3, 0.5),
                        random.uniform(0.1, 0.3)
                    )
                    bark_lines.append({'z': z_offset, 'radius': bark_radius, 'color': bark_color})
                new_ob = {
                    'x1': cx - w/2,
                    'y1': cy - h/2,
                    'x2': cx + w/2,
                    'y2': cy + h/2,
                    'height': height,
                    'shape': shape,
                    'bark_lines': bark_lines
                }
            elif shape == 'rock':
                w = random.uniform(50, 100)
                h = random.uniform(50, 100)
                height = random.uniform(20, 40)
                rock_color = (random.uniform(0.3, 0.7), random.uniform(0.3, 0.7), random.uniform(0.3, 0.7))
                gravel_count = random.randint(5, 10)
                gravels = []
                for _ in range(gravel_count):
                    gravel_radius = max(w, h) / 2 + random.uniform(5, 15)
                    angle = random.uniform(0, 2 * math.pi)
                    gravel_x = gravel_radius * math.cos(angle)
                    gravel_y = gravel_radius * math.sin(angle)
                    gravel_size = random.uniform(2, 5)
                    gravel_color = (random.uniform(0.3, 0.5), random.uniform(0.3, 0.5), random.uniform(0.3, 0.5))
                    gravels.append({'x': gravel_x, 'y': gravel_y, 'size': gravel_size, 'color': gravel_color})
                new_ob = {
                    'x1': cx - w/2,
                    'y1': cy - h/2,
                    'x2': cx + w/2,
                    'y2': cy + h/2,
                    'height': height,
                    'shape': shape,
                    'rock_color': rock_color,
                    'gravels': gravels
                }
            elif shape == 'tree':
                w = random.uniform(20, 40)
                h = random.uniform(20, 40)
                height = random.uniform(80, 160)
                new_ob = {
                    'x1': cx - w/2,
                    'y1': cy - h/2,
                    'x2': cx + w/2,
                    'y2': cy + h/2,
                    'height': height,
                    'shape': shape
                }
            else:
                w = h = height = 0
                new_ob = {
                    'x1': cx,
                    'y1': cy,
                    'x2': cx,
                    'y2': cy,
                    'height': height,
                    'shape': shape
                }

            # Check for overlap with existing obstacles
            if not obstacle_overlaps(new_ob, obstacles, min_gap=8):
                obstacles.append(new_ob)
                break  # Successfully placed this obstacle
        # If max_attempts is reached, skip this obstacle

    
    # spawn symmetric troops/tanks
    left_x = -GRID_LENGTH + 80
    right_x = GRID_LENGTH - 80
    n = 6

    # Spawn grass
    grass.clear()
    num_grass = 150
    max_attempts = 50
    grass_radius = 3
    grass_margin = MARGIN
    for _ in range(num_grass):
        for _ in range(max_attempts):
            x = random.uniform(-GRID_LENGTH + grass_margin, GRID_LENGTH - grass_margin)
            y = random.uniform(-GRID_LENGTH + grass_margin, GRID_LENGTH - grass_margin)
            base_height = random.uniform(8, 16)
            num_blades = random.randint(2, 3)
            blades = []
            for _ in range(num_blades):
                angle = random.uniform(0, 360)
                height_offset = random.uniform(-2, 2)
                blades.append({'angle': angle, 'height_offset': height_offset})
            if not point_in_obstacle(x, y, 0, grass_radius):
                grass.append({'x': x, 'y': y, 'z': 0, 'height': base_height, 'blades': blades})
                break
    
    # Gun combat: troops only
    if mode == 1:
        for i in range(n):
            troops.append({'id': _nextid(), 'x': left_x + random.uniform(-60,60), 'y': -200 + i*40, 'z': 0,
                           'vx':0,'vy':0,'hp':30,'side':'A','ammo':30,'alive':True,'last_fire':0,'rot':0})
            troops.append({'id': _nextid(), 'x': right_x + random.uniform(-60,60), 'y': 200 - i*40, 'z': 0,
                           'vx':0,'vy':0,'hp':30,'side':'B','ammo':30,'alive':True,'last_fire':0,'rot':0})
    
    # Battle drive: tanks only
    elif mode == 2:
        for i in range(n):
            tanks.append({'id': _nextid(), 'x': left_x + random.uniform(-60,60), 'y': -200 + i*40, 'z': 0,
                           'vx':0,'vy':0,'hp':80,'side':'A','alive':True,'last_fire':0,'ammo':8,'rot':0})
            tanks.append({'id': _nextid(), 'x': right_x + random.uniform(-60,60), 'y': 200 - i*40, 'z': 0,
                           'vx':0,'vy':0,'hp':80,'side':'B','alive':True,'last_fire':0,'ammo':8,'rot':0})
    
    # Survival mode: mixed
    else:
        for i in range(n):
            troops.append({'id': _nextid(), 'x': left_x + random.uniform(-60,60), 'y': -200 + i*40, 'z': 0,
                           'vx':0,'vy':0,'hp':30,'side':'A','ammo':25,'alive':True,'last_fire':0,'rot':0})
            tanks.append({'id': _nextid(), 'x': left_x + random.uniform(-60,60), 'y': -240 + i*20, 'z': 0,
                           'vx':0,'vy':0,'hp':75,'side':'A','alive':True,'last_fire':0,'ammo':6,'rot':0})
            troops.append({'id': _nextid(), 'x': right_x + random.uniform(-60,60), 'y': 200 - i*40, 'z': 0,
                           'vx':0,'vy':0,'hp':30,'side':'B','ammo':25,'alive':True,'last_fire':0,'rot':0})
            tanks.append({'id': _nextid(), 'x': right_x + random.uniform(-60,60), 'y': 240 - i*20, 'z': 0,
                           'vx':0,'vy':0,'hp':75,'side':'B','alive':True,'last_fire':0,'ammo':6,'rot':0})
    
    # assign player to first left troop/tank depending on mode
    global player_id, player_is_tank
    player_id = None
    player_is_tank = False
    if mode == 2:
        if tanks:
            player_is_tank = True
            player_id = tanks[0]['id']
    else:
        if troops:
            player_is_tank = False
            player_id = troops[0]['id']

# Main render & update
def showScreen():
    global bullets, bombs, powerups, troops, tanks, score, game_over, winner
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()
    glViewport(0, 0, 1000, 800)
    setupCamera()

    # Draw textured floor
    glBegin(GL_QUADS)
    for i in range(-GRID_LENGTH, GRID_LENGTH, 10):
        for j in range(-GRID_LENGTH, GRID_LENGTH, 10):
            # shade = 0.55 + 0.05 * random.random()  # subtle random shading
            # glColor3f(shade, shade, shade)
            glColor3f(random.uniform(0.1, 0.15), random.uniform(0.2, 0.3), random.uniform(0.06, 0.09))  # solid green
            glVertex3f(i, j, 0)
            glVertex3f(i+10, j, 0)
            glVertex3f(i+10, j+10, 0)
            glVertex3f(i, j+10, 0)
    glEnd()

    # Draw grid border with wooden logs
    log_radius = 6
    log_height = 32
    log_gap = 2
    log_color = (0.55, 0.27, 0.07)  # brown

    # Left and right borders
    for y in range(-GRID_LENGTH, GRID_LENGTH, int(2*log_radius + log_gap)):
        for x in [-GRID_LENGTH, GRID_LENGTH]:
            glPushMatrix()
            glTranslatef(x, y, 0)
            glColor3f(*log_color)
            glRotatef(90, 0, 0, 1)  # Stand upright
            gluCylinder(gluNewQuadric(), log_radius, log_radius, log_height, 12, 2)
            glPopMatrix()

    # Top and bottom borders
    for x in range(-GRID_LENGTH, GRID_LENGTH, int(2*log_radius + log_gap)):
        for y in [-GRID_LENGTH, GRID_LENGTH]:
            glPushMatrix()
            glTranslatef(x, y, 0)
            glColor3f(*log_color)
            glRotatef(90, 0, 0, 1)  # Stand upright
            gluCylinder(gluNewQuadric(), log_radius, log_radius, log_height, 12, 2)
            glPopMatrix()

    # Draw grass tuft
    for g in grass:
        glPushMatrix()
        glTranslatef(g['x'], g['y'], g['z'])
        blade_width = 1.5
        base_height = g['height']
        for blade in g['blades']:
            glPushMatrix()
            glRotatef(blade['angle'], 0, 0, 1)
            tilt_angle = random.uniform(10, 20)
            glRotatef(tilt_angle, 0, 1, 0)
            glColor3f(0.1, random.uniform(0.5, 0.7), 0.1)
            blade_height = base_height + blade['height_offset']
            glBegin(GL_QUADS)
            glVertex3f(-blade_width/2, 0, 0)
            glVertex3f(blade_width/2, 0, 0)
            glVertex3f(blade_width/2, 0, blade_height)
            glVertex3f(-blade_width/2, 0, blade_height)
            glEnd()
            glPopMatrix()
        glPopMatrix()

    # Draw obstacles (random shapes)
    for ob in obstacles:
        ox1, oy1, ox2, oy2 = ob['x1'], ob['y1'], ob['x2'], ob['y2']
        h = ob['height']
        center_x, center_y = (ox1 + ox2) / 2, (oy1 + oy2) / 2
        sx, sy = (ox2 - ox1), (oy2 - oy1)
        shape = ob['shape']  # Use the shape assigned at creation

        glPushMatrix()
        glTranslatef(center_x, center_y, 0)
        
        if shape == 'cube':
            # Draw the main building
            glColor3f(0.7, 0.7, 0.7)
            glTranslatef(0, 0, h/2)  # Move cube up so it sits on ground
            glScalef(sx, sy, h)
            glutSolidCube(1.0)

            # Draw windows on the four sides
            # Undo the scaling for window placement
            glScalef(1.0/sx, 1.0/sy, 1.0/h)
            glTranslatef(0, 0, -h/2)  # Back to cube center at ground level

            window_color = (0.2, 0.4, 0.8)
            window_width = 0.15 * sx
            window_height = 0.2 * h
            window_zs = [0.2 * h, 0.5 * h, 0.8 * h]  # Three rows of windows

            # Front (+y) and back (-y)
            for y_sign in [1, -1]:
                for wx in [-0.25 * sx, 0.25 * sx]:
                    for wz in window_zs:
                        glColor3f(*window_color)
                        glBegin(GL_QUADS)
                        glVertex3f(wx - window_width/2, y_sign*sy/2 + 0.01*y_sign, wz - window_height/2)
                        glVertex3f(wx + window_width/2, y_sign*sy/2 + 0.01*y_sign, wz - window_height/2)
                        glVertex3f(wx + window_width/2, y_sign*sy/2 + 0.01*y_sign, wz + window_height/2)
                        glVertex3f(wx - window_width/2, y_sign*sy/2 + 0.01*y_sign, wz + window_height/2)
                        glEnd()

            # Left (-x) and right (+x)
            for x_sign in [1, -1]:
                for wy in [-0.25 * sy, 0.25 * sy]:
                    for wz in window_zs:
                        glColor3f(*window_color)
                        glBegin(GL_QUADS)
                        glVertex3f(x_sign*sx/2 + 0.01*x_sign, wy - window_width/2, wz - window_height/2)
                        glVertex3f(x_sign*sx/2 + 0.01*x_sign, wy + window_width/2, wz - window_height/2)
                        glVertex3f(x_sign*sx/2 + 0.01*x_sign, wy + window_width/2, wz + window_height/2)
                        glVertex3f(x_sign*sx/2 + 0.01*x_sign, wy - window_width/2, wz + window_height/2)
                        glEnd()


        elif shape == 'cylinder':
            glTranslatef(0, 0, h/5)
            glColor3f(0.8, 0.5, 0.2)
            glRotatef(-90, 1, 0, 0)
            gluCylinder(gluNewQuadric(), min(sx, sy)/2, min(sx, sy)/2, h, 12, 6)
            glPushMatrix()
            for bark in ob.get('bark_lines', []):
                glPushMatrix()
                glTranslatef(0, 0, bark['z'])
                glColor3f(*bark['color'])
                glBegin(GL_LINE_LOOP)
                segments = 16
                for j in range(segments):
                    angle = j * 2 * math.pi / segments
                    x = math.cos(angle) * bark['radius']
                    y = math.sin(angle) * bark['radius']
                    glVertex3f(x, y, 0)
                glEnd()
                glPopMatrix()
            glPopMatrix()


        elif shape == 'rock':
            glTranslatef(0, 0, h/3)
            glColor3f(*ob.get('rock_color', (0.4, 0.9, 0.6)))
            glScalef(sx*0.01, sy*0.01, h*0.01)
            glutSolidSphere(min(sx, sy)/2, 12, 12)
            glPopMatrix()  # Pop the main rock's transformation
            glPushMatrix()
            glTranslatef(center_x, center_y, 0)
            for gravel in ob.get('gravels', []):
                glPushMatrix()
                glTranslatef(gravel['x'], gravel['y'], gravel['size'] / 2)
                glColor3f(*gravel['color'])
                glutSolidSphere(gravel['size'], 8, 8)
                glPopMatrix()


        elif shape == 'tree':
            trunk_radius = min(sx, sy) * 0.2
            trunk_height = h * 0.6
            foliage_radius = min(sx, sy) * 0.6

            # Treat trunk and foliage as one entity
            glPushMatrix()
            glColor3f(0.4, 0.2, 0.1)
            gluCylinder(gluNewQuadric(), trunk_radius, trunk_radius, trunk_height, 8, 4)

            # Draw foliage at top of trunk
            glTranslatef(-7, -6, trunk_height)
            glColor3f(0.0, 0.6, 0.0)
            # glutSolidSphere(foliage_radius, 12, 12)
            glTranslatef(20, 20, 0)
            # glutSolidSphere(foliage_radius, 12, 12)
            glTranslatef(-20, -20, 0)
            # glutSolidSphere(foliage_radius, 12, 12)
            glTranslatef(20, 0, 0)
            # glutSolidSphere(foliage_radius, 12, 12)
            glColor3f(1, 0, 0.0) #red
            glutSolidCube(20.0)
            glTranslatef(0, 20, 0)
            # glutSolidSphere(foliage_radius, 12, 12)
            glColor3f(0.0, 1, 1) #cyan
            glutSolidCube(20.0)
            glTranslatef(-20, 0, 0)
            # glutSolidSphere(foliage_radius, 12, 12)
            glColor3f(0.5, 0.5, 0.0) #yellow
            glutSolidCube(20.0)
            glTranslatef(0, -20, 0)
            # glutSolidSphere(foliage_radius, 12, 12)
            glColor3f(0.5, 0, 0.5) #magenta
            glutSolidCube(20.0)
            glTranslatef(0, 0, 20)
            glColor3f(0.0, 1, 0.0) #green
            glutSolidCube(20.0)
            # glutSolidSphere(foliage_radius, 12, 12)


            glPopMatrix()

        glPopMatrix()

    # Draw powerups
    for p in powerups:
        glPushMatrix()
        glTranslatef(p['x'], p['y'], 6)
        if p['type'] == 'health': glColor3f(1,0,0)
        elif p['type'] == 'points': glColor3f(0,1,0)
        elif p['type'] == 'ammo': glColor3f(0,0,1)
        else: glColor3f(1,1,0)
        glutSolidSphere(6, 10, 10)
        glPopMatrix()

    # Draw troops
    for s in troops:
        if not s['alive']: continue
        glPushMatrix()
        glTranslatef(s['x'], s['y'], 0)
        glRotatef(s.get('rot',0),0,0,1)
        # Head
        glPushMatrix()
        glTranslatef(0,0,25)
        glColor3f(1,0.8,0.6)
        glutSolidSphere(8,16,16)
        glPopMatrix()
        # Body
        glPushMatrix()
        glTranslatef(0,0,10)
        glScalef(10,6,20)
        glColor3f(0.2,0.6,1.0) if s['side']=='A' else glColor3f(1.0,0.2,0.2)
        glutSolidCube(1.0)
        glPopMatrix()
        # Arms
        glColor3f(0.8,0.8,0.8)
        for side in [-1,1]:
            glPushMatrix()
            glTranslatef(side*8,0,15)
            glRotatef(90,0,1,0)
            gluCylinder(gluNewQuadric(),2,2,8,10,10)
            glPopMatrix()
        # Legs
        for side in [-1,1]:
            glPushMatrix()
            glTranslatef(side*4,0,0)
            glRotatef(-90,1,0,0)
            glutSolidCone(4,12,10,10)
            glPopMatrix()
        glPopMatrix()

    # Draw tanks
    for t in tanks:
        if not t['alive']: continue
        glPushMatrix()
        glTranslatef(t['x'], t['y'], 8)
        glRotatef(t.get('rot',0),0,0,1)

        # Tank base (wider, slightly sloped)
        glPushMatrix()
        glScalef(28, 40, 10)
        if t['side'] == 'A':
            glColor3f(0.1, 0.5, 0.1)
        else:
            glColor3f(0.4, 0.1, 0.4)
        glutSolidCube(1.0)
        glPopMatrix()
        # Tank tracks (left & right, with depth)
        glColor3f(0.1,0.1,0.1)
        for side in [-1,1]:
            glPushMatrix()
            glTranslatef(side*18, 0, 5)
            glScalef(6, 40, 8)  # slightly taller for realism
            glutSolidCube(1.0)
            glPopMatrix()

        # Turret (flattened, more rounded)
        glPushMatrix()
        glTranslatef(0,0,14)  # slightly higher
        glColor3f(0.2,0.2,0.2)
        glScalef(1.2, 1.2, 0.7)
        glutSolidSphere(10, 20, 20)
        glPopMatrix()

        # Gun barrel (tapered)
        glPushMatrix()
        glRotatef(t.get('rot',0),0,0,1)  # rotate with turret
        glTranslatef(0,15,14)  # start at turret front
        glRotatef(-90,1,0,0)
        glColor3f(0.2,0.2,0.2)
        # tapered barrel by using different top/bottom radius
        gluCylinder(gluNewQuadric(), 3, 2, 20, 12, 2)
        glPopMatrix()
        # Hatch
        glPushMatrix()
        glTranslatef(0,-3,18)
        glColor3f(0.3,0.3,0.3)
        glutSolidSphere(2.5, 12, 12)
        glPopMatrix()

        glPopMatrix()

    # Update and draw bullets
    if not game_over:
        new_bullets = []
        for b in bullets:
            prev_x, prev_y, prev_z = b['x'], b['y'], b.get('z', 6)
            step = 0.02
            if b['owner'] == player_side:
                step = 0.05
           # advance bullet
            b['x'] += b['dx'] * b['speed'] * step
            b['y'] += b['dy'] * b['speed'] * step
            b['ttl'] -= step

            # remove if time-to-live expired
            if b['ttl'] <= 0:
                continue

            # remove if outside grid bounds
            if not (-GRID_LENGTH <= b['x'] <= GRID_LENGTH and -GRID_LENGTH <= b['y'] <= GRID_LENGTH):
                continue

            # obstacle collision 
            hit_obstacle = False
            for obs in obstacles:
                # Check Z overlap
                bullet_z = b.get('z', 6)
                if not (0 <= bullet_z <= obs['height']):
                    continue
                if obs['shape'] in ['cube','cylinder']:
                    if (obs['x1']<=b['x']<=obs['x2'] and obs['y1']<=b['y']<=obs['y2'] and 0 <= b['z'] <= obs['height']): 
                        hit_obstacle=True; break
                elif obs['shape'] in ['rock','tree']:
                    cx, cy = (obs['x1']+obs['x2'])/2,(obs['y1']+obs['y2'])/2
                    r = max(obs['x2']-obs['x1'], obs['y2']-obs['y1'])/2
                    if (math.hypot(b['x']-cx,b['y']-cy)<=r and 0 <= b['z'] <= obs['height']): 
                        hit_obstacle=True; break
            if hit_obstacle: 
                continue

            # Draw bullet
            glPushMatrix()
            glTranslatef(b['x'],b['y'],6)
            glColor3f(1,1,0)
            glutSolidSphere(2.2,6,6)
            glPopMatrix()

            new_bullets.append(b)

        bullets = new_bullets

    # Bombs
    new_bombs = []
    for bm in bombs:
        if not bm['exploded']:
            # Move the bomb forward
            bm['x'] += bm.get('dx', 0) * 0.2
            bm['y'] += bm.get('dy', 0) * 0.2

            # Check for obstacle collision (similar to bullets, assume z=10, radius=3)
            hit_obstacle = False
            for obs in obstacles:
                # Z overlap check (bomb at height 10)
                if not (0 <= 10 <= obs['height']):
                    continue
                if obs['shape'] in ['cube', 'cylinder']:
                    if (obs['x1'] - 3 <= bm['x'] <= obs['x2'] + 3 and
                        obs['y1'] - 3 <= bm['y'] <= obs['y2'] + 3):
                        hit_obstacle = True
                        break
                elif obs['shape'] in ['rock', 'tree']:
                    cx, cy = (obs['x1'] + obs['x2']) / 2, (obs['y1'] + obs['y2']) / 2
                    r = max(obs['x2'] - obs['x1'], obs['y2'] - obs['y1']) / 2 + 3
                    if math.hypot(bm['x'] - cx, bm['y'] - cy) <= r:
                        hit_obstacle = True
                        break

            if hit_obstacle:
                bm['exploded'] = True
                # Explode immediately
                radius, ox, oy = bm['radius'], bm['x'], bm['y']
                for s in troops:
                    if s['alive'] and s['side'] != bm['owner']:
                        if math.hypot(s['x'] - ox, s['y'] - oy) <= radius:
                            s['hp'] = 0
                            s['alive'] = False
                            score[bm['owner']] += 1
                for t in tanks:
                    if t['alive'] and t['side'] != bm['owner']:
                        if math.hypot(t['x'] - ox, t['y'] - oy) <= radius:
                            t['hp'] = 0
                            t['alive'] = False
                            score[bm['owner']] += 2
                # Draw explosion this frame
                glPushMatrix()
                glTranslatef(bm['x'], bm['y'], 10)
                glColor3f(1.0, 0.4, 0.0)
                glutSolidSphere(bm['radius'], 20, 20)
                glPopMatrix()
                continue  # Remove by not appending
            else:
                bm['timer'] -= 0.02
                # Draw bomb
                glPushMatrix()
                glTranslatef(bm['x'], bm['y'], 10)
                glColor3f(0.2, 0.2, 0.8)
                glutSolidSphere(3, 8, 8)
                glPopMatrix()
                if bm['timer'] <= 0:
                    bm['exploded'] = True
                    radius, ox, oy = bm['radius'], bm['x'], bm['y']
                    for s in troops:
                        if s['alive'] and s['side'] != bm['owner']:
                            if math.hypot(s['x'] - ox, s['y'] - oy) <= radius:
                                s['hp'] = 0
                                s['alive'] = False
                                score[bm['owner']] += 1
                    for t in tanks:
                        if t['alive'] and t['side'] != bm['owner']:
                            if math.hypot(t['x'] - ox, t['y'] - oy) <= radius:
                                t['hp'] = 0
                                t['alive'] = False
                                score[bm['owner']] += 2
        else:
            # Draw explosion
            glPushMatrix()
            glTranslatef(bm['x'], bm['y'], 10)
            glColor3f(1.0, 0.4, 0.0)
            glutSolidSphere(bm['radius'], 20, 20)
            glPopMatrix()
            continue
        new_bombs.append(bm)
    bombs = new_bombs

    # Spawn powerups
    if time.time()-globals().get('last_power_spawn',0)>power_spawn_interval:
        globals()['last_power_spawn']=time.time()
        if random.random()<0.7:
            px,py = random.uniform(-GRID_LENGTH*0.8,GRID_LENGTH*0.8), random.uniform(-GRID_LENGTH*0.8,GRID_LENGTH*0.8)
            ptype=random.choice(['health','points','ammo','speed'])
            powerups.append({'x':px,'y':py,'z':6,'type':ptype,'spawn_time':time.time()})

    # Pickups
    for p in powerups[:]:
        for s in troops:
            if not s['alive']: continue
            if math.hypot(s['x']-p['x'],s['y']-p['y'])<12:
                if p['type']=='health': s['hp']=min(100,s['hp']+5)
                elif p['type']=='points': score[s['side']]+=2
                elif p['type']=='ammo': s['ammo']+=12
                else: s['x']+=random.uniform(-10,10); s['y']+=random.uniform(-10,10)
                try: powerups.remove(p)
                except ValueError: pass
        for t in tanks:
            if not t['alive']: continue
            if math.hypot(t['x']-p['x'],t['y']-p['y'])<18:
                if p['type']=='health': t['hp']=min(200,t['hp']+15)
                elif p['type']=='points': score[t['side']]+=2
                elif p['type']=='ammo': t['ammo']+=4
                else: t['x']+=random.uniform(-20,20); t['y']+=random.uniform(-20,20)
                try: powerups.remove(p)
                except ValueError: pass

    # Simple AI and firing
    frozen = time.time() < globals().get('cheat_freeze_until', 0.0)
    all_entities = troops + tanks  # include all troops and tanks

    for ent in all_entities:
        if not ent.get('alive'): 
            continue

        angle_rad = math.radians(ent.get('rot', 0))
        fire_offset = 20
        now = time.time()
        cooldown = 1.2 if ent in troops else 2.2

        # AI movement for non-player entities
        if ent['side'] != player_side and not frozen:
            target = find_nearest_enemy(ent['side'], ent['x'], ent['y'])
            if target:
                dx, dy = target['x'] - ent['x'], target['y'] - ent['y']
                dist = math.hypot(dx, dy) + 1e-6
                new_x = ent['x'] + (dx / dist) * ENTITY_SPEED
                new_y = ent['y'] + (dy / dist) * ENTITY_SPEED
                # Prevent AI from moving into obstacles
                entity_z = 0 if ent in troops else 8  # Match player movement: troops at 0, tanks at 8
                entity_radius = TROOP_RADIUS if ent in troops else TANK_RADIUS
                if not point_in_obstacle(new_x, new_y, entity_z, entity_radius):
                    ent['x'] = new_x
                    ent['y'] = new_y
                ent['rot'] = math.degrees(math.atan2(dy, dx))
                angle_rad = math.radians(ent['rot'])

        # Firing logic
        if ent['side'] != player_side and now - ent.get('last_fire', 0) > cooldown:
            spawn_x = ent['x'] + math.cos(angle_rad) * fire_offset
            spawn_y = ent['y'] + math.sin(angle_rad) * fire_offset

            if ent in troops:
                # Troops always fire bullets
                bullets.append({
                    'x': spawn_x,
                    'y': spawn_y,
                    'z': 8,
                    'dx': math.cos(angle_rad),
                    'dy': math.sin(angle_rad),
                    'dz': 0,
                    'speed': BULLET_SPEED * 5,
                    'owner': ent['side'],
                    'damage': 10,
                    'ttl': BULLET_TTL * 3
                })
            else:
                # Tanks fire bombs ONLY in Mode 2
                if GAME_MODE in (2,3):
                    BOMB_SPEED = 80
                    bombs.append({
                        'x': spawn_x,
                        'y': spawn_y,
                        'dx': math.cos(angle_rad) * BOMB_SPEED,
                        'dy': math.sin(angle_rad) * BOMB_SPEED,
                        'owner': ent['side'],
                        'radius': 60,
                        'timer': 0.7,
                        'exploded': False
                    })

            ent['last_fire'] = now
    # Bullet collisions with entities
    live_bullets=[]
    for b in bullets:
        hit=False
        for s in troops:
            if not s['alive'] or s['side']==b['owner']: continue
            if line_intersects_obstacle(b['x'],b['y'],s['x'],s['y']): continue
            if math.hypot(b['x']-s['x'],b['y']-s['y'])<10:
                s['hp']-=b['damage']
                if s['hp']<=0: s['alive']=False; score[b['owner']]+=1
                hit=True; break
        if hit: continue
        for t in tanks:
            if not t['alive'] or t['side']==b['owner']: continue
            if line_intersects_obstacle(b['x'],b['y'],t['x'],t['y']): continue
            if math.hypot(b['x']-t['x'],b['y']-t['y'])<18:
                t['hp']-=b['damage']
                if t['hp']<=0: t['alive']=False; score[b['owner']]+=2
                hit=True; break
        if hit: continue
        live_bullets.append(b)
    bullets=live_bullets
    # Win condition
    aliveA=sum(1 for e in (troops+tanks) if e.get('alive') and e.get('side')=='A')
    aliveB=sum(1 for e in (troops+tanks) if e.get('alive') and e.get('side')=='B')
    if not game_over and (aliveA==0 or aliveB==0):
        game_over=True
        winner='B' if aliveA==0 else 'A'

    # HUD
    draw_text(10,770,f"Mode: {'Gun Combat' if GAME_MODE==1 else 'Battle Drive' if GAME_MODE==2 else 'Survival'}")
    draw_text(10,745,f"Score A: {score['A']}    Score B: {score['B']}")
    draw_text(10,720,f"Enemies Alive A: {aliveA}   B: {aliveB}")
    draw_text(400,770,f"Cheats: U unlimited ammo [{'ON' if cheat_unlimited_ammo else 'OFF'}], F freeze (5s), T auto-target [{'ON' if cheat_autotarget else 'OFF'}]")
    draw_text(10,700,"Controls: Arrow keys move controlled unit. Left mouse to fire. R restart.")

    if game_over:
        draw_text(400,400,f"GAME OVER - Winner: Team {winner}")
        draw_text(400,380,"Press 'R' to restart.")

    glutSwapBuffers()

# Main - handles mode selection then starts GLUT loop


def main():
    global GAME_MODE
    # Ask for mode as requested (console)
    try:
        print("Select mode: Click '1' for Gun Combat, '2' for Battle Drive, '3' for Survival Mode.")
        sel = input("Enter mode number (1/2/3): ").strip()
        GAME_MODE = int(sel) if sel in ['1','2','3'] else 1
    except Exception:
        GAME_MODE = 1

    # prepare initial world
    reset_game()

    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(1000, 800)
    glutInitWindowPosition(0, 0)
    wind = glutCreateWindow(b"Uradhura Fight - Prototype")
    # glEnable(GL_DEPTH_TEST)
    # glClearColor(0.1, 0.1, 0.12, 1.0)

    glutDisplayFunc(showScreen)
    glutKeyboardFunc(keyboardListener)
    glutSpecialFunc(specialKeyListener)
    glutMouseFunc(mouseListener)
    glutIdleFunc(idle)

    glutMainLoop()

if __name__ == "__main__":
    main()