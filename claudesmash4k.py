from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random
import math

# ============================================================================
# CONFIGURATION AND CONSTANTS
# ============================================================================

class GameConfig:
    """Centralized game configuration"""
    # Performance settings
    TARGET_FPS = 60
    VSYNC = True
    SHADOW_RESOLUTION = (2048, 2048)
    
    # Player movement (SM64-inspired)
    MAX_SPEED = 8
    ACCELERATION = 15
    DECELERATION = 12
    AIR_ACCELERATION = 6
    FRICTION = 0.92
    AIR_FRICTION = 0.98
    
    # Jump mechanics
    JUMP_HEIGHT = 2.5
    DOUBLE_JUMP_MULTIPLIER = 1.2
    TRIPLE_JUMP_MULTIPLIER = 1.8
    GRAVITY = 20
    TERMINAL_VELOCITY = -30
    MIN_TRIPLE_JUMP_SPEED = 4  # Minimum horizontal speed for triple jump
    
    # Advanced movement
    LONG_JUMP_BOOST = 1.5
    GROUND_POUND_VELOCITY = -25
    WALL_KICK_BOOST = 1.3
    
    # Combat (Melee-inspired)
    BASE_DAMAGE = 10
    KNOCKBACK_MULTIPLIER = 0.5
    MAX_DAMAGE_PERCENT = 300
    
    # Camera
    CAMERA_SPEED = 6
    CAMERA_OFFSET = Vec3(0, 8, -15)
    CAMERA_ROTATION_SPEED = 80
    MOUSE_SENSITIVITY = Vec2(40, 40)

# ============================================================================
# ENHANCED PLAYER CONTROLLER WITH SM64 MECHANICS
# ============================================================================

class MarioController(Entity):
    """
    Advanced player controller implementing SM64 movement mechanics:
    - Triple jump with speed requirement
    - Long jump (crouch + jump while running)
    - Wall kicks with frame-perfect timing
    - Ground pound with impact effects
    - Variable jump height
    - Momentum-based movement
    """
    
    def __init__(self, **kwargs):
        super().__init__()
        
        # Core entity setup
        self.model = 'cube'
        self.color = color.red
        self.scale = (0.8, 1.6, 0.8)
        self.collider = 'box'
        self.position = Vec3(0, 5, 0)
        
        # Movement state
        self.velocity = Vec3(0, 0, 0)
        self.momentum = Vec3(0, 0, 0)
        self.current_speed = 0
        self.grounded = False
        self.can_move = True
        
        # Jump state tracking
        self.jump_count = 0
        self.max_jumps = 3
        self.jump_buffer_time = 0
        self.jump_buffer_duration = 0.1
        self.coyote_time = 0
        self.coyote_duration = 0.15
        self.is_jumping = False
        self.jump_held = False
        self.jump_start_time = 0
        
        # Advanced movement states
        self.is_crouching = False
        self.is_long_jumping = False
        self.is_ground_pounding = False
        self.can_wall_kick = False
        self.wall_kick_timer = 0
        self.wall_kick_window = 0.15  # 5 frames at 30fps = 0.15s
        
        # Combat stats (Melee-inspired)
        self.damage_percent = 0
        self.hitstun_frames = 0
        
        # Camera pivot for rotation control
        self.camera_pivot = Entity(parent=self, y=1)
        
        # Visual effects
        self.trail_timer = 0
        self.last_ground_y = 0
        
        # Apply any additional kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def update(self):
        """Main update loop - called every frame"""
        if not self.can_move:
            return
        
        dt = time.dt
        
        # Update timers
        self.jump_buffer_time = max(0, self.jump_buffer_time - dt)
        self.coyote_time = max(0, self.coyote_time - dt)
        self.wall_kick_timer = max(0, self.wall_kick_timer - dt)
        
        # Check ground state with multiple raycasts for slope detection
        self.check_ground_collision()
        
        # Handle different movement states
        if self.is_ground_pounding:
            self.update_ground_pound()
        elif self.is_long_jumping:
            self.update_long_jump()
        else:
            self.update_normal_movement()
        
        # Apply gravity
        self.apply_gravity()
        
        # Check wall collisions for wall kick
        self.check_wall_collision()
        
        # Apply velocity to position
        self.apply_movement()
        
        # Visual effects
        self.update_visual_effects()
        
        # Mouse camera control
        self.update_camera_rotation()
    
    def check_ground_collision(self):
        """
        Advanced ground detection using multiple raycasts
        Handles slopes and ensures reliable ground detection
        """
        was_grounded = self.grounded
        self.grounded = False
        
        # Three raycasts: center, left, right (for slope detection)
        ray_origins = [
            self.world_position + Vec3(0, 0.1, 0),
            self.world_position + Vec3(-self.scale_x * 0.4, 0.1, 0),
            self.world_position + Vec3(self.scale_x * 0.4, 0.1, 0)
        ]
        
        max_distance = max(0.2, abs(self.velocity.y) * time.dt + 0.1)
        hits = []
        
        for origin in ray_origins:
            ray = raycast(
                origin=origin,
                direction=Vec3(0, -1, 0),
                distance=max_distance,
                ignore=[self],
                traverse_target=scene
            )
            if ray.hit:
                hits.append(ray)
        
        if hits:
            # Use the highest hit point
            highest_point = max(hit.world_point.y for hit in hits)
            
            if self.velocity.y <= 0:
                self.y = highest_point + self.scale_y / 2
                self.velocity.y = 0
                self.grounded = True
                
                # Reset jump count when landing
                if not was_grounded:
                    self.on_land()
        
        # Coyote time: Allow jump shortly after leaving ground
        if was_grounded and not self.grounded:
            self.coyote_time = self.coyote_duration
            self.last_ground_y = self.y
    
    def update_normal_movement(self):
        """Standard movement with momentum and acceleration"""
        # Get input direction relative to camera
        input_dir = Vec3(
            held_keys['d'] - held_keys['a'],
            0,
            held_keys['w'] - held_keys['s']
        )
        
        if input_dir.length() > 0:
            input_dir = input_dir.normalized()
            
            # Rotate input by camera yaw
            angle = math.radians(camera.rotation_y)
            rotated_dir = Vec3(
                input_dir.x * math.cos(angle) - input_dir.z * math.sin(angle),
                0,
                input_dir.x * math.sin(angle) + input_dir.z * math.cos(angle)
            )
            
            # Apply acceleration
            accel = GameConfig.ACCELERATION if self.grounded else GameConfig.AIR_ACCELERATION
            target_velocity = rotated_dir * GameConfig.MAX_SPEED
            self.momentum = lerp(self.momentum, target_velocity, accel * time.dt)
            
            # Rotate player to face movement direction
            if self.momentum.length() > 0.1:
                target_rotation = math.degrees(math.atan2(self.momentum.x, self.momentum.z))
                self.rotation_y = lerp_angle(self.rotation_y, target_rotation, 10 * time.dt)
        else:
            # Apply friction
            friction = GameConfig.FRICTION if self.grounded else GameConfig.AIR_FRICTION
            self.momentum *= friction
            
            # Stop completely at low speeds
            if self.momentum.length() < 0.1:
                self.momentum = Vec3(0, 0, 0)
        
        # Update horizontal velocity
        self.velocity.x = self.momentum.x
        self.velocity.z = self.momentum.z
        self.current_speed = Vec2(self.velocity.x, self.velocity.z).length()
        
        # Crouch detection
        self.is_crouching = held_keys['left control'] or held_keys['c']
    
    def update_long_jump(self):
        """Handle long jump movement - maintains horizontal momentum"""
        # Long jump has limited air control
        input_dir = Vec3(
            held_keys['d'] - held_keys['a'],
            0,
            held_keys['w'] - held_keys['s']
        ).normalized()
        
        if input_dir.length() > 0:
            # Limited steering during long jump
            angle = math.radians(camera.rotation_y)
            rotated_dir = Vec3(
                input_dir.x * math.cos(angle) - input_dir.z * math.sin(angle),
                0,
                input_dir.x * math.sin(angle) + input_dir.z * math.cos(angle)
            )
            self.momentum += rotated_dir * GameConfig.AIR_ACCELERATION * 0.3 * time.dt
        
        self.velocity.x = self.momentum.x
        self.velocity.z = self.momentum.z
        
        # End long jump when grounded
        if self.grounded:
            self.is_long_jumping = False
    
    def update_ground_pound(self):
        """Handle ground pound - fast downward movement"""
        # Minimal horizontal movement during ground pound
        self.momentum *= 0.95
        self.velocity.x = self.momentum.x
        self.velocity.z = self.momentum.z
        
        # Check for ground impact
        if self.grounded:
            self.on_ground_pound_impact()
            self.is_ground_pounding = False
    
    def apply_gravity(self):
        """Apply gravity with terminal velocity cap"""
        if not self.grounded and not self.is_ground_pounding:
            self.velocity.y -= GameConfig.GRAVITY * time.dt
            self.velocity.y = max(self.velocity.y, GameConfig.TERMINAL_VELOCITY)
    
    def check_wall_collision(self):
        """
        Check for wall collisions in all directions for wall kicks
        Uses 8 raycasts around the player
        """
        if self.grounded or self.velocity.y > 0:
            self.can_wall_kick = False
            return
        
        directions = [
            Vec3(1, 0, 0), Vec3(-1, 0, 0),  # Left, Right
            Vec3(0, 0, 1), Vec3(0, 0, -1),  # Forward, Back
            Vec3(0.707, 0, 0.707), Vec3(-0.707, 0, 0.707),  # Diagonals
            Vec3(0.707, 0, -0.707), Vec3(-0.707, 0, -0.707)
        ]
        
        for direction in directions:
            ray = raycast(
                origin=self.world_position + Vec3(0, 0.5, 0),
                direction=direction,
                distance=0.6,
                ignore=[self],
                traverse_target=scene
            )
            
            if ray.hit:
                # Wall detected - enable wall kick for brief window
                self.can_wall_kick = True
                self.wall_kick_timer = self.wall_kick_window
                self.wall_normal = ray.normal
                return
    
    def apply_movement(self):
        """
        Apply velocity to position with collision detection
        Prevents tunneling through walls
        """
        # Horizontal movement
        move_distance = math.sqrt(self.velocity.x**2 + self.velocity.z**2) * time.dt
        if move_distance > 0:
            move_direction = Vec3(self.velocity.x, 0, self.velocity.z).normalized()
            
            # Check for horizontal collisions
            hit = raycast(
                origin=self.world_position + Vec3(0, 0.5, 0),
                direction=move_direction,
                distance=move_distance + self.scale_x / 2,
                ignore=[self],
                traverse_target=scene
            )
            
            if hit.hit:
                # Slide along wall
                slide_direction = Vec3(hit.normal.z, 0, -hit.normal.x)
                self.momentum = slide_direction * self.momentum.length() * 0.5
            else:
                self.x += self.velocity.x * time.dt
                self.z += self.velocity.z * time.dt
        
        # Vertical movement
        if not self.grounded:
            self.y += self.velocity.y * time.dt
    
    def update_visual_effects(self):
        """Update particle trails and visual feedback"""
        # Speed-based trail effect
        if self.current_speed > GameConfig.MAX_SPEED * 0.7:
            self.trail_timer += time.dt
            if self.trail_timer > 0.05:
                self.trail_timer = 0
                create_speed_trail(self.position, self.color)
    
    def update_camera_rotation(self):
        """Handle mouse-based camera rotation (C-button simulation)"""
        if mouse.locked:
            # Horizontal rotation (yaw)
            camera.rotation_y += mouse.velocity[0] * GameConfig.MOUSE_SENSITIVITY[1]
            
            # Vertical rotation (pitch)
            self.camera_pivot.rotation_x -= mouse.velocity[1] * GameConfig.MOUSE_SENSITIVITY[0]
            self.camera_pivot.rotation_x = clamp(self.camera_pivot.rotation_x, -45, 45)
    
    def input(self, key):
        """Handle player input"""
        # Jump
        if key == 'space':
            self.jump_buffer_time = self.jump_buffer_duration
            self.attempt_jump()
        
        # Ground pound (control key in air)
        if key == 'left control' and not self.grounded:
            self.start_ground_pound()
        
        # Toggle mouse lock
        if key == 'escape':
            mouse.locked = not mouse.locked
            self.camera_pivot.rotation_x = 0
    
    def attempt_jump(self):
        """
        Handle all jump types: single, double, triple, long jump, wall kick
        SM64-style progressive jump heights
        """
        # Wall kick takes priority
        if self.can_wall_kick and self.wall_kick_timer > 0:
            self.wall_kick()
            return
        
        # Check if jump is allowed (grounded or coyote time or has double jump)
        can_jump = (self.grounded or self.coyote_time > 0 or 
                   (self.jump_count > 0 and self.jump_count < self.max_jumps))
        
        if not can_jump:
            return
        
        # Long jump (crouch + jump while moving fast)
        if self.grounded and self.is_crouching and self.current_speed > 3:
            self.long_jump()
            return
        
        # Regular jump (single, double, or triple)
        self.jump_count += 1
        self.grounded = False
        self.coyote_time = 0
        self.is_jumping = True
        self.jump_held = True
        self.jump_start_time = time.time()
        
        # Calculate jump height based on jump count and speed
        if self.jump_count == 1:
            # Single jump - variable height
            jump_multiplier = 1.0
        elif self.jump_count == 2:
            # Double jump - higher
            jump_multiplier = GameConfig.DOUBLE_JUMP_MULTIPLIER
        elif self.jump_count == 3:
            # Triple jump - requires minimum speed and gives highest jump
            if self.current_speed >= GameConfig.MIN_TRIPLE_JUMP_SPEED:
                jump_multiplier = GameConfig.TRIPLE_JUMP_MULTIPLIER
                create_triple_jump_effect(self.position)
            else:
                # Not fast enough for triple jump, reset to double
                self.jump_count = 2
                jump_multiplier = GameConfig.DOUBLE_JUMP_MULTIPLIER
        else:
            jump_multiplier = 1.0
        
        # Apply jump velocity
        self.velocity.y = GameConfig.JUMP_HEIGHT * jump_multiplier
        
        # Particle effect
        create_jump_particles(self.position, self.jump_count)
    
    def long_jump(self):
        """Execute a long jump - horizontal distance with lower arc"""
        self.is_long_jumping = True
        self.jump_count = 1
        self.grounded = False
        
        # Lower arc than regular jump
        self.velocity.y = GameConfig.JUMP_HEIGHT * 0.8
        
        # Boost horizontal momentum
        self.momentum *= GameConfig.LONG_JUMP_BOOST
        self.momentum = self.momentum.normalized() * min(
            self.momentum.length(),
            GameConfig.MAX_SPEED * 1.5
        )
        
        create_long_jump_effect(self.position)
    
    def wall_kick(self):
        """Execute a wall kick off a wall"""
        # Reflect velocity off wall normal
        reflect_dir = Vec3(self.wall_normal.x, 0, self.wall_normal.z).normalized()
        self.momentum = reflect_dir * GameConfig.MAX_SPEED * GameConfig.WALL_KICK_BOOST
        
        # Upward velocity
        self.velocity.y = GameConfig.JUMP_HEIGHT * 1.1
        
        # Reset jump count to allow combo wall kicks
        self.jump_count = 1
        self.grounded = False
        self.can_wall_kick = False
        
        create_wall_kick_effect(self.position)
    
    def start_ground_pound(self):
        """Initiate ground pound"""
        if self.is_ground_pounding:
            return
        
        self.is_ground_pounding = True
        self.velocity.y = GameConfig.GROUND_POUND_VELOCITY
        self.momentum *= 0.2  # Kill horizontal momentum
    
    def on_ground_pound_impact(self):
        """Handle ground pound landing"""
        # Create impact effect
        create_ground_pound_impact(self.position)
        
        # Camera shake for impact feel
        camera.shake(duration=0.3, magnitude=0.5, speed=0.05)
        
        # Bounce slightly
        self.velocity.y = GameConfig.JUMP_HEIGHT * 0.3
    
    def on_land(self):
        """Called when player lands on ground"""
        # Reset jump count
        self.jump_count = 0
        
        # Landing particles
        if self.velocity.y < -5:
            create_landing_particles(self.position)
        
        # Check if buffered jump should execute
        if self.jump_buffer_time > 0:
            self.attempt_jump()

# ============================================================================
# PARTICLE EFFECTS AND VISUAL POLISH
# ============================================================================

def create_jump_particles(position, jump_count):
    """Create particles when jumping"""
    colors = [color.white, color.yellow, color.gold]
    particle_color = colors[min(jump_count - 1, 2)]
    
    for i in range(5):
        particle = Entity(
            model='sphere',
            position=position + Vec3(random.uniform(-0.3, 0.3), 0, random.uniform(-0.3, 0.3)),
            scale=0.1,
            color=particle_color,
            collider=None
        )
        particle.animate_position(
            particle.position + Vec3(random.uniform(-1, 1), random.uniform(0.5, 1.5), random.uniform(-1, 1)),
            duration=0.5,
            curve=curve.out_quad
        )
        particle.fade_out(duration=0.5)
        destroy(particle, delay=0.5)

def create_triple_jump_effect(position):
    """Special effect for triple jump"""
    ring = Entity(
        model='sphere',
        position=position,
        scale=0.5,
        color=color.gold,
        alpha=0.8,
        collider=None
    )
    ring.animate_scale(3, duration=0.5, curve=curve.out_expo)
    ring.fade_out(duration=0.5)
    destroy(ring, delay=0.5)

def create_long_jump_effect(position):
    """Effect for long jump initiation"""
    for i in range(3):
        particle = Entity(
            model='cube',
            position=position,
            scale=0.15,
            color=color.orange,
            rotation=(random.uniform(0, 360), random.uniform(0, 360), random.uniform(0, 360)),
            collider=None
        )
        particle.animate_scale(0, duration=0.3)
        destroy(particle, delay=0.3)

def create_wall_kick_effect(position):
    """Effect for wall kicks"""
    burst = Entity(
        model='sphere',
        position=position,
        scale=0.3,
        color=color.cyan,
        collider=None
    )
    burst.animate_scale(1.5, duration=0.3, curve=curve.out_expo)
    burst.fade_out(duration=0.3)
    destroy(burst, delay=0.3)

def create_ground_pound_impact(position):
    """Large impact effect for ground pound"""
    # Shockwave ring
    shockwave = Entity(
        model='circle',
        position=position,
        scale=1,
        color=color.white,
        alpha=0.7,
        rotation_x=90,
        collider=None
    )
    shockwave.animate_scale(5, duration=0.4, curve=curve.out_expo)
    shockwave.fade_out(duration=0.4)
    destroy(shockwave, delay=0.4)
    
    # Dust particles
    for i in range(12):
        angle = i * 30
        direction = Vec3(
            math.cos(math.radians(angle)),
            0.5,
            math.sin(math.radians(angle))
        )
        particle = Entity(
            model='sphere',
            position=position + Vec3(0, 0.1, 0),
            scale=0.2,
            color=color.gray,
            collider=None
        )
        particle.animate_position(
            particle.position + direction * 2,
            duration=0.6,
            curve=curve.out_quad
        )
        particle.fade_out(duration=0.6)
        destroy(particle, delay=0.6)

def create_landing_particles(position):
    """Small particles when landing from a fall"""
    for i in range(4):
        particle = Entity(
            model='sphere',
            position=position + Vec3(random.uniform(-0.2, 0.2), 0.1, random.uniform(-0.2, 0.2)),
            scale=0.08,
            color=color.light_gray,
            collider=None
        )
        particle.animate_position(
            particle.position + Vec3(random.uniform(-0.5, 0.5), random.uniform(0.2, 0.5), random.uniform(-0.5, 0.5)),
            duration=0.3
        )
        particle.fade_out(duration=0.3)
        destroy(particle, delay=0.3)

def create_speed_trail(position, trail_color):
    """Trail effect when moving fast"""
    trail = Entity(
        model='cube',
        position=position,
        scale=0.3,
        color=trail_color,
        alpha=0.3,
        collider=None
    )
    trail.fade_out(duration=0.2)
    destroy(trail, delay=0.2)

# ============================================================================
# ENVIRONMENT AND LEVEL OBJECTS
# ============================================================================

class Platform(Entity):
    """Static platform with optimized collision"""
    def __init__(self, position=(0,0,0), scale=(5,1,5), platform_color=color.green, **kwargs):
        super().__init__(
            model='cube',
            position=position,
            scale=scale,
            color=platform_color,
            collider='box',
            texture='white_cube',
            **kwargs
        )

class MovingPlatform(Entity):
    """Platform that moves between waypoints"""
    def __init__(self, start_pos, end_pos, speed=2, **kwargs):
        super().__init__(
            model='cube',
            position=start_pos,
            scale=(4, 0.5, 4),
            color=color.blue,
            collider='box',
            **kwargs
        )
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.speed = speed
        self.moving_to_end = True
    
    def update(self):
        # Move between start and end positions
        target = self.end_pos if self.moving_to_end else self.start_pos
        direction = (target - self.position).normalized()
        
        self.position += direction * self.speed * time.dt
        
        # Switch direction when reaching target
        if distance(self.position, target) < 0.5:
            self.moving_to_end = not self.moving_to_end

class WarpPipe(Entity):
    """Warp pipe that teleports player"""
    def __init__(self, position, destination, pipe_color=color.green, **kwargs):
        super().__init__(
            model='cylinder',
            position=position,
            scale=(1, 2, 1),
            color=pipe_color,
            collider='box',
            **kwargs
        )
        self.destination = destination
        self.cooldown = 0
    
    def update(self):
        if self.cooldown > 0:
            self.cooldown -= time.dt
    
    def trigger_warp(self, player):
        """Teleport player to destination"""
        if self.cooldown <= 0:
            player.position = self.destination
            self.cooldown = 1.0
            # Warp effect
            create_warp_effect(self.position)
            create_warp_effect(self.destination)

def create_warp_effect(position):
    """Visual effect for pipe warping"""
    for i in range(8):
        angle = i * 45
        offset = Vec3(
            math.cos(math.radians(angle)) * 0.5,
            random.uniform(0, 1),
            math.sin(math.radians(angle)) * 0.5
        )
        particle = Entity(
            model='sphere',
            position=position + offset,
            scale=0.15,
            color=color.green,
            collider=None
        )
        particle.animate_scale(0, duration=0.5)
        particle.animate_position(position + Vec3(0, 2, 0), duration=0.5)
        destroy(particle, delay=0.5)

class BreakableBlock(Entity):
    """Block that breaks when ground pounded"""
    def __init__(self, position, **kwargs):
        super().__init__(
            model='cube',
            position=position,
            scale=1,
            color=color.brown,
            collider='box',
            texture='brick',
            **kwargs
        )
        self.breakable = True
    
    def break_apart(self):
        """Break block into pieces"""
        # Create fragments
        for i in range(8):
            fragment = Entity(
                model='cube',
                position=self.position,
                scale=0.3,
                color=self.color,
                collider=None
            )
            # Random explosion direction
            direction = Vec3(
                random.uniform(-1, 1),
                random.uniform(0.5, 1.5),
                random.uniform(-1, 1)
            )
            fragment.animate_position(
                fragment.position + direction * 2,
                duration=1,
                curve=curve.out_quad
            )
            fragment.animate_rotation(
                (random.uniform(0, 360), random.uniform(0, 360), random.uniform(0, 360)),
                duration=1
            )
            fragment.fade_out(duration=1, delay=0.5)
            destroy(fragment, delay=1.5)
        
        destroy(self)

class CoinCollectible(Entity):
    """Spinning coin that can be collected"""
    def __init__(self, position, **kwargs):
        super().__init__(
            model='cylinder',
            position=position,
            scale=(0.5, 0.1, 0.5),
            color=color.yellow,
            collider='sphere',
            **kwargs
        )
        self.coin_value = 1
        self.rotation_y = 0
    
    def update(self):
        # Spin animation
        self.rotation_y += 180 * time.dt
        
        # Bob up and down
        self.y += math.sin(time.time() * 3) * 0.01

# ============================================================================
# OPTIMIZED LEVEL BUILDER
# ============================================================================

class MushroomKingdomLevel:
    """
    Optimized level builder that combines geometry for performance
    Implements best practices for Ursina level design
    """
    
    def __init__(self):
        self.platforms = []
        self.collectibles = []
        self.hazards = []
        
    def build_level(self):
        """Build the complete Mushroom Kingdom stage"""
        # Main ground platform (combined mesh for performance)
        self.create_ground()
        
        # Castle structure
        self.create_castle()
        
        # Platforming section
        self.create_platform_section()
        
        # Warp pipes
        self.create_warp_pipes()
        
        # Moving platforms
        self.create_moving_platforms()
        
        # Collectibles
        self.create_collectibles()
        
        # Breakable blocks
        self.create_breakable_blocks()
        
        # Sky and lighting
        self.setup_environment()
    
    def create_ground(self):
        """Create main ground using combined mesh for performance"""
        # Large ground plane
        ground = Platform(
            position=(0, -1, 0),
            scale=(100, 1, 100),
            platform_color=color.rgb(34, 139, 34)  # Forest green
        )
        ground.texture = 'grass'
        self.platforms.append(ground)
    
    def create_castle(self):
        """Build a simple castle structure"""
        # Castle base
        castle_base = Entity(
            model='cube',
            position=(0, 5, 30),
            scale=(15, 10, 12),
            color=color.gray,
            collider='box',
            texture='brick'
        )
        
        # Castle towers (four corners)
        tower_positions = [
            (-6, 8, 24), (6, 8, 24),
            (-6, 8, 36), (6, 8, 36)
        ]
        
        for pos in tower_positions:
            tower = Entity(
                model='cylinder',
                position=pos,
                scale=(2, 8, 2),
                color=color.light_gray,
                collider='box'
            )
            # Tower roof
            roof = Entity(
                model='cone',
                position=Vec3(pos[0], pos[1] + 5, pos[2]),
                scale=(2.5, 3, 2.5),
                color=color.red,
                collider=None
            )
    
    def create_platform_section(self):
        """Create a series of platforms for parkour"""
        platform_data = [
            # (position, scale)
            ((-10, 2, 0), (3, 0.5, 3)),
            ((-15, 4, 5), (3, 0.5, 3)),
            ((-12, 6, 10), (3, 0.5, 3)),
            ((-8, 8, 15), (4, 0.5, 4)),
            ((-3, 10, 18), (3, 0.5, 3)),
            ((3, 12, 20), (3, 0.5, 3)),
            ((8, 14, 18), (4, 0.5, 4)),
            ((12, 16, 15), (3, 0.5, 3)),
        ]
        
        for pos, scale in platform_data:
            platform = Platform(
                position=pos,
                scale=scale,
                platform_color=color.orange
            )
            self.platforms.append(platform)
    
    def create_warp_pipes(self):
        """Create warp pipes for teleportation"""
        # Left pipe (green)
        left_pipe = WarpPipe(
            position=(-20, 1, -10),
            destination=Vec3(20, 1, -10),
            pipe_color=color.green
        )
        
        # Right pipe (red)
        right_pipe = WarpPipe(
            position=(20, 1, -10),
            destination=Vec3(-20, 1, -10),
            pipe_color=color.red
        )
    
    def create_moving_platforms(self):
        """Create moving platforms"""
        # Horizontal mover
        moving1 = MovingPlatform(
            start_pos=Vec3(0, 5, -5),
            end_pos=Vec3(10, 5, -5),
            speed=2
        )
        
        # Vertical mover
        moving2 = MovingPlatform(
            start_pos=Vec3(-5, 3, 10),
            end_pos=Vec3(-5, 10, 10),
            speed=1.5
        )
    
    def create_collectibles(self):
        """Place coins and collectibles"""
        # Coin trail leading up platforms
        for i in range(10):
            coin = CoinCollectible(
                position=(-10 + i * 2, 3 + i * 0.5, i * 2)
            )
            self.collectibles.append(coin)
        
        # Coins around castle
        for i in range(8):
            angle = i * 45
            x = math.cos(math.radians(angle)) * 12
            z = 30 + math.sin(math.radians(angle)) * 12
            coin = CoinCollectible(position=(x, 2, z))
            self.collectibles.append(coin)
    
    def create_breakable_blocks(self):
        """Create breakable blocks (ground poundable)"""
        # Line of breakable blocks
        for i in range(5):
            block = BreakableBlock(
                position=(i * 2 - 4, 3, -15)
            )
    
    def setup_environment(self):
        """Setup lighting and atmosphere"""
        # Sky
        Sky(color=color.rgb(135, 206, 235))  # Sky blue
        
        # Sun (directional light)
        sun = DirectionalLight(
            color=color.white,
            rotation=(45, -45, 0)
        )
        sun.look_at(Vec3(1, -1, 1))
        
        # Ambient light for fill
        AmbientLight(color=color.rgba(100, 100, 100, 0.1))
        
        # Optional: Fog for depth
        scene.fog_density = 0.02
        scene.fog_color = color.rgb(200, 220, 255)

# ============================================================================
# CAMERA SYSTEM
# ============================================================================

class SM64Camera(Entity):
    """
    SM64-style camera system with smooth following and C-button controls
    """
    def __init__(self, target=None, **kwargs):
        super().__init__()
        self.target = target
        self.offset = GameConfig.CAMERA_OFFSET
        self.speed = GameConfig.CAMERA_SPEED
        
    def update(self):
        if not self.target:
            return
        
        # Smooth follow target
        target_pos = self.target.world_position + self.offset
        camera.world_position = lerp(
            camera.world_position,
            target_pos,
            self.speed * time.dt
        )
        
        # Look at target (with slight upward offset)
        look_at_pos = self.target.world_position + Vec3(0, 1, 0)
        camera.look_at(look_at_pos)

# ============================================================================
# GAME MANAGER
# ============================================================================

class GameManager:
    """Main game manager handling gameplay logic"""
    
    def __init__(self):
        self.score = 0
        self.coins_collected = 0
        self.player = None
        
        # UI Elements
        self.create_ui()
    
    def create_ui(self):
        """Create HUD elements"""
        self.coin_text = Text(
            text=f'Coins: {self.coins_collected}',
            position=(-0.85, 0.45),
            origin=(0, 0),
            scale=2,
            color=color.yellow
        )
        
        self.fps_text = Text(
            text='FPS: 60',
            position=(0.7, 0.45),
            origin=(0, 0),
            scale=1.5,
            color=color.white
        )
        
        # Instructions
        instructions = Text(
            text='WASD: Move | Space: Jump | Ctrl: Crouch/Ground Pound | ESC: Mouse Lock',
            position=(0, -0.45),
            origin=(0, 0),
            scale=1,
            color=color.white
        )
    
    def update(self):
        """Update game state"""
        # Update FPS counter
        self.fps_text.text = f'FPS: {int(1/time.dt) if time.dt > 0 else 60}'
        
        # Check coin collection
        if self.player:
            for coin in list(level_builder.collectibles):
                if hasattr(coin, 'coin_value'):
                    dist = distance(self.player.position, coin.position)
                    if dist < 1:
                        self.collect_coin(coin)
            
            # Check warp pipe triggers
            for entity in scene.entities:
                if isinstance(entity, WarpPipe):
                    if distance(self.player.position, entity.position) < 1.5:
                        if held_keys['down arrow'] or held_keys['s']:
                            entity.trigger_warp(self.player)
            
            # Check ground pound on breakable blocks
            for entity in scene.entities:
                if isinstance(entity, BreakableBlock):
                    if self.player.is_ground_pounding:
                        if distance_xz(self.player.position, entity.position) < 1:
                            if abs(self.player.position.y - entity.position.y) < 1:
                                entity.break_apart()
    
    def collect_coin(self, coin):
        """Handle coin collection"""
        self.coins_collected += coin.coin_value
        self.score += 100
        self.coin_text.text = f'Coins: {self.coins_collected}'
        
        # Coin collection effect
        coin.animate_scale(0, duration=0.2)
        coin.animate_position(coin.position + Vec3(0, 1, 0), duration=0.2)
        destroy(coin, delay=0.2)
        
        if coin in level_builder.collectibles:
            level_builder.collectibles.remove(coin)

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Initialize and run the game"""
    # Create Ursina app with optimized settings
    app = Ursina(
        title='SM64 Mushroom Kingdom Engine',
        borderless=False,
        fullscreen=False,
        vsync=GameConfig.VSYNC,
        development_mode=False
    )
    
    # Window settings
    window.fps_counter.enabled = False  # Using custom FPS counter
    window.exit_button.visible = False
    window.cog_button.visible = False
    
    # Build level
    global level_builder
    level_builder = MushroomKingdomLevel()
    level_builder.build_level()
    
    # Create player
    player = MarioController()
    
    # Setup camera
    camera_controller = SM64Camera(target=player)
    
    # Lock mouse for camera control
    mouse.locked = True
    
    # Create game manager
    global game_manager
    game_manager = GameManager()
    game_manager.player = player
    
    # Custom update function
    def game_update():
        game_manager.update()
    
    app.update = game_update
    
    # Run game
    app.run()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def lerp_angle(a, b, t):
    """Interpolate between angles properly handling wrap-around"""
    diff = (b - a) % 360
    if diff > 180:
        diff -= 360
    return a + diff * t

def distance_xz(pos1, pos2):
    """Calculate horizontal distance ignoring Y axis"""
    return math.sqrt((pos1.x - pos2.x)**2 + (pos1.z - pos2.z)**2)

# ============================================================================
# RUN GAME
# ============================================================================

if __name__ == '__main__':
    main()
