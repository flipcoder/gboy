#!/usr/bin/env python2
import os
import sys
import pygame
import euclid
import pytmx
import copy
import random
import pytmx.util_pygame
import datetime

TITLE = 'GBOY'
COLORS = [
    (155, 188, 15),
    (139, 172, 15),
    (48, 98, 48),
    (15, 56, 15)
]
SCALE = 6
SCREEN_W = 160
SCREEN_H = 140
SCREEN_SZ = (SCREEN_W, SCREEN_H)
SCALED_SZ = (SCALE * SCREEN_W, SCALE * SCREEN_H)
FONT = './data/fonts/Early GameBoy.ttf'
TRANS = (255,0,255)
JOY_AXIS = 0

def sgn(a):
    return (a > 0) - (a < 0)

def load_image(fn):
    img = pygame.image.load(fn)
    img.set_colorkey(TRANS)
    return img

def tileset(fn, **kwargs):
    img = load_image(fn)
    w, h = img.get_size()
    tiles = []
    hflip = kwargs.get('hflip', False)
    vflip = kwargs.get('vflip', False)
    for i in xrange(0, w, h):
        tiles += [img.subsurface((i,0,h,h))]
        tiles[-1] = pygame.transform.flip(tiles[-1], hflip, vflip)
    return tiles

class Object(object):
    def __init__(self, **kwargs):
        self.game = kwargs.get('game', None)
        self.attached = False
        if self.game:
            self.game.world.attach(self)
        
        self.pos = euclid.Vector2(*kwargs.get('pos', (0.0, 0.0)))
        self.vel = euclid.Vector2(*kwargs.get('vel', (0.0, 0.0)))
        self.sz = euclid.Vector2(*kwargs.get('sz', (0.0, 0.0)))
        self.surface = kwargs.get('surface', None)
    
    def give(item):
        return False
    
    def rect(self):
        return pygame.Rect(self.pos.x, self.pos.y, self.sz.x, self.sz.y)
    
    def logic(self, t):
        self.pos += self.vel * t
        
        if self.pos.x < 0 or self.pos.x >= self.game.world.sz.x:
            self.attached = False
        elif self.pos.y < 0 or self.pos.y >= self.game.world.sz.y:
            self.attached = False
    
    def render(self, view):
        if self.attached and self.surface:
            self.game.screen.buf.blit(self.surface, self.pos - view)

class Screen(Object):
    def __init__(self,screen):
        self.pos = euclid.Vector2(0.0, 0.0)
        self.sz = euclid.Vector2(SCREEN_W, SCREEN_H)
        self.buf = pygame.Surface(SCREEN_SZ).convert()
        self.surface = pygame.Surface(SCALED_SZ).convert()
        self.screen = screen
    
    def render(self):
        pygame.transform.scale(self.buf, SCALED_SZ, self.surface)
        self.screen.blit(self.surface, (0,0))
        
class Bullet(Object):
    def __init__(self, **kwargs):
        super(self.__class__, self).__init__(**kwargs)
        self.surface = load_image('./data/gfx/bullet.png')
        w,h = self.surface.get_size()
        self.sz = euclid.Vector2(w*1.0, h*1.0)

class Guy(Object):
    def __init__(self, **kwargs):
        super(self.__class__, self).__init__(**kwargs)
        
        self.speed = 100.0
        self.run_mult = 1.5
        self.sz = euclid.Vector2(10.0, 10.0)
        self.anim_speed = 8.0
        #self.jump_accel = 3000.0
        self.jump_vel = 220.0
        self.fall_accel = 1500.0
        self.fall_vel = 300.0
        self.move = euclid.Vector2(0.0, 0.0)
        self.surfaces = tileset('./data/gfx/guy2.png')
        self.surfaces += tileset('./data/gfx/guy2.png', hflip=True)
        self.frames = {
            "right": [0,1,0,2],
            "left": [3,4,3,5],
            "climb": [6,7]
        }
        self.keys = 0
        self.anim_point = 0.0
        self.direction = "right"
        self.surface = self.surfaces[self.frames[self.direction][0]]
        self.chan = pygame.mixer.Channel(0)
        self.jump_snd = pygame.mixer.Sound('./data/sfx/jump.wav')
        self.shoot_snd = pygame.mixer.Sound('./data/sfx/shoot.wav')
        self.item_snd = pygame.mixer.Sound('./data/sfx/key.wav')
        self.jump_time = 0.0
        self.max_jump_time = 0.2
        self.shoot_time = 0
        self.shoot_delay = 0.25
        
        self.strafe = False
        #self.running = False
        self.jumping = False
        self.by_ladder = False
        self.on_ladder = False
        self.items = []
        
    def give(self, item):
        if item == 'key':
            self.keys += 1
        self.chan.play(self.item_snd)
        return True
    
    def interface(self):
        self.move = euclid.Vector2(0.0, 0.0)
        for k in self.game.keys:
            if k == pygame.K_LEFT or k == pygame.K_j:
                self.move += euclid.Vector2(-1.0, 0.0)
            if k == pygame.K_RIGHT or k == pygame.K_l:
                self.move += euclid.Vector2(1.0, 0.0)
            if k == pygame.K_UP or k == pygame.K_i:
                if self.on_ladder:
                    self.move += euclid.Vector2(0.0, -1.0)
            if k == pygame.K_DOWN:
                if self.on_ladder:
                    self.move += euclid.Vector2(0.0, 1.0)
            if k == pygame.K_SPACE:
                self.shoot()

        for joy in self.game.joys:
            ax = JOY_AXIS
            if abs(joy.get_axis(ax)) > 0.2:
                if self.on_ladder:
                    self.move += euclid.Vector2(joy.get_axis(ax), joy.get_axis(ax+1))
                else:
                    ax = joy.get_axis(ax)
                    # snap close axis values to max value
                    if ax > 0.9:
                        ax = 1.0
                    elif ax < -0.9:
                        ax = -1.0
                    self.move += euclid.Vector2(ax, 0.0)
            elif joy.get_numhats() > 0 and joy.get_hat(0)[0] != 0:
                if self.on_ladder:
                    self.move += euclid.Vector2(joy.get_hat(0)[0], joy.get_hat(0)[1])
                else:
                    self.move += euclid.Vector2(joy.get_hat(0)[0], 0.0)
            if joy.get_button(3):
                self.shoot()
        
        self.move.x = max(-1.0, min(1.0, self.move.x))
        self.move.y = max(-1.0, min(1.0, self.move.y))
        
        joy_jump = False
        if len(self.game.joys) >= 1:
            joy_jump = self.game.joys[0].get_button(0)
        self.jump(pygame.K_i in self.game.keys or pygame.K_UP in self.game.keys or joy_jump)
        
    def logic(self, t):
        
        #speed = self.speed
        #if self.running:
        #    speed *= self.run_mult
        #self.vel.x = self.move.x * speed
        
        if self.by_ladder:
            self.vel = self.move * self.speed
        else:
            # preserve y vel
            self.vel.x = self.move.x * self.speed
        
        new_vel = copy.copy(self.vel)
        
        if not self.on_ladder:
            if self.jumping and self.jump_time < self.max_jump_time:
                #jt = min(self.max_jump_time - self.jump_time, t)
                #self.jump_time += jt
                #self.vel.y = -self.jump_speed * jt/t
                self.jump_time += t
                self.vel.y = -self.jump_vel
                #self.vel.y -= self.jump_accel/2.0 * t
                #new_vel.y -= t * self.jump_accel
                #self.vel.y = max(-self.jump_vel, self.vel.y)
                #new_vel.y = max(-self.jump_vel, self.vel.y)
            else:
                self.vel.y += t * self.fall_accel/2.0
                new_vel.y += t * self.fall_accel
                self.vel.y = min(self.fall_vel, self.vel.y)
                new_vel.y = min(self.fall_vel, self.vel.y)
        
        if not self.strafe:
            if self.vel.x < 0:
                self.direction = "left"
            if self.vel.x > 0:
                self.direction = "right"
        
        old_pos = copy.copy(self.pos)
        
        if self.vel.x != 0.0:
            self.pos.x += self.vel.x * t
            if self.game.world.collision(self):
                self.pos.x -= t*sgn(self.vel.x)
                while self.game.world.collision(self):
                    self.pos.x -= t*sgn(self.vel.x)
                self.vel.x = 0.0

        if self.vel.y != 0.0:
            self.pos.y += self.vel.y * t
            if self.game.world.collision(self):
                self.pos.y -= t*sgn(self.vel.y)
                while self.game.world.collision(self):
                    self.pos.y -= t*sgn(self.vel.y)
                self.vel.y = 0.0
                new_vel.y = 0.0
        
        if self.vel.y < 0.0:
            # moving up
            if self.jumping:
                self.anim_point = 0.0
        elif self.vel.y > 0.0 and not self.can_jump():
            # falling
            self.anim_point = 1.0
        elif self.vel.x != 0.0:
            if not self.jumping:
                self.anim_point += t * self.anim_speed
            if self.anim_point >= len(self.frames[self.direction])-1:
                self.anim_point = 0.0
        else:
            self.anim_point = 0.0
        
        self.vel = new_vel
        
        a = int(round(self.anim_point))
        self.surface = self.surfaces[self.frames[self.direction][a]]
        self.shoot_time -= t
    
    def shoot(self):
        if self.shoot_time <= 0:
            bullet_dir = -1.0 if self.direction=='left' else 1.0
            bullet_speed = 200.0
            self.shoot_time = self.shoot_delay
            b = Bullet(
                game=self.game,
                pos=(self.pos.x + self.sz.x/2.0, self.pos.y + self.sz.y/2.0),
                vel=(bullet_dir * bullet_speed, 0.0)
            )
            self.chan.play(self.shoot_snd)

    def render(self, view):
        self.game.screen.buf.blit(self.surface, self.pos - view)

    def jump(self, j=True):
        if self.jumping != j:
            if j:
                if self.can_jump():
                    self.jump_time = 0.0
                    self.jumping = True
                    #if not self.chan or not self.chan.get_busy():
                    self.chan.play(self.jump_snd)
                    self.by_ladder = False
            else:
                self.jumping = False
    
    def can_jump(self):
        return self.vel.y == 0.0
        #feet = Object(
        #    pos=(self.pos.x + 2.0, self.pos.y + self.sz.y / 2.0),
        #    sz=(self.sz.x-4.0, self.sz.y/2.0 + 1.0)
        #)
        #c = self.game.world.collision(feet)
        #return c
        #tb = self.game.world.tile_below(self)
        #r = copy.copy(self.rect())
        #r.centery -= 1.0
        #if tb:
        #    return r.colliderect(tb.rect())
        #return True

class Tile:
    def __init__(self, surface):
        self.surface = surface

class World:
    def __init__(self, fn, game):
        self.tmx = pytmx.util_pygame.load_pygame(fn)
        for img in self.tmx.images:
            if img:
                img.set_colorkey(TRANS)
        self.sz = euclid.Vector2(
            self.tmx.width * self.tmx.tilewidth,
            self.tmx.height * self.tmx.tileheight
        )
        
        line = []
        self.game = game
        self.objects = []
        
        self.spawns = []
        for layer in self.tmx.visible_layers:
            if isinstance(layer, pytmx.TiledObjectGroup):
                for obj in layer:
                    if obj.name == 'S':
                        self.spawns += [obj]
        
        self.keys = 0


        # get key count
        for row in self.tmx.layers[0].data:
            for gid in row:
                if gid not in self.tmx.tile_properties:
                    continue
                props  = self.tmx.tile_properties[gid]
                if 'key' in props:
                    self.keys += 1

        self.next_level = False
        self.time = 0
        
    def attach(self, obj):
        if not obj.attached:
            self.objects += [obj]
            obj.attached = True
    
    def tile_below(self, obj):
        center = obj.pos + obj.sz/2.0
        try:
            tx = int(round(center.x/self.tmx.tilewidth)) * self.tmx.tilewidth
            ty = int(round(center.x/self.tmx.tilewidth)) * self.tmx.tileheight
            t = self.tmx.get_tile_image(
                int(round(center.x/self.tmx.tilewidth)),
                int(round(center.y/self.tmx.tileheight)),
                0
            )
            if t:
                o = Object(
                    pos=(tx,ty),
                    sz=(self.tmx.tilewidth, self.tmx.tileheight)
                )
                o.tile = t
                return o
        except:
            pass
        return None
        
    def collision(self, obj):
        potentials = []
        obj_rect = pygame.Rect(obj.pos.x, obj.pos.y, obj.sz.x, obj.sz.y)
        tw = self.tmx.tilewidth
        th = self.tmx.tileheight
        f2i = lambda n: int(round(n))
        x_inc = min(tw, int(obj.sz.x))
        y_inc = min(th, int(obj.sz.y))
        obj.by_ladder = False
        
        for y in range(int(obj.pos.y), int(obj.pos.y + obj.sz.y), y_inc):
            for x in range(int(obj.pos.x), int(obj.pos.x + obj.sz.x), x_inc):
                if x < 0 or x >= self.sz.x or y < 0 or y >= self.sz.y:
                    continue
                #try:
                for i in self.tmx.visible_tile_layers:
                    t = self.tmx.get_tile_image(x/tw, y/th, i)
                    props = self.tmx.get_tile_properties(x/tw, y/th, i)
                    exit = True if props and 'exit' in props else False
                    ladder = True if props and 'ladder' in props else False
                    obj.by_ladder = ladder
                    kill = True if props and 'kill' in props else False
                    key = True if props and 'key' in props else False
                    if key:
                        if obj.give('key'):
                            self.tmx.layers[0].data[y/th][x/tw] = 0
                            self.keys -= 1
                    if kill:
                        obj.attached = False
                    if exit:
                        if self.keys == 0:
                            self.next_level = True
                        else:
                            obj.attached = False
                    if t and not ladder:
                        return True
                        #print t
                        #potentials += [pygame.Rect(x/tw*tw, y/th*th, tw, th)]
                #except:
                #    pass
        
        #return potentials
        #b = obj_rect.collidelist(potentials)
        #print b
        #return b != -1
        
        #print 'none'
        #return False
        
    def logic(self, t):
        if self.next_level:
            self.game.level += 1
            self.next_level = False
            print self.time # temp
            self.game.reset()
        self.time += t
        
    def render(self, view):
        tw = self.tmx.tilewidth
        th = self.tmx.tileheight
        for layer in self.tmx.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer):
                for x, y, img in layer.tiles():
                    self.game.screen.buf.blit(img, (x*tw-view.x, y*th-view.y))

        for obj in self.objects:
            obj.render(view)
        
def snap(pos):
    return (int(round(pos[0])), int(round(pos[1])))

class Game:
    def __init__(self):

        pygame.init()
        pygame.mixer.init(channels=8)
        #pygame.mixer.music.load(os.path.join(os.path.expanduser("~"), "mus2.mp3"))
        
        pygame.joystick.init()
        self.joys = []
        idx = 0
        while True:
            idx+=1
            joy = None
            try:
                joy = pygame.joystick.Joystick(idx)
            except:
                pass
            if not joy:
                break
            joy.init()
            self.joys += [joy]

        self.TITLE = 0
        self.GAME = 1
        self.mode = self.TITLE
        
        pygame.display.set_caption(TITLE)
        self.screen = Screen(pygame.display.set_mode(SCALED_SZ))
        self.font = pygame.font.Font(FONT, 8)
        self.clock = pygame.time.Clock()
        self.keys = []
        if len(sys.argv) >= 2:
            self.level = sys.argv[1]
        else:
            self.level = 1
        #self.reset_snd = pygame.mixer.Sound('./data/sfx/hurt.wav')
        self.chan = pygame.mixer.Channel(1)
        
        self.guy = None
        self.world = None
        self.reset()

    def reset(self):
        
        #pygame.mixer.music.play()
        
        #if self.world:
        #    self.chan.play(self.reset_snd)
        
        self.world = World('./data/maps/%s.tmx' % self.level, self)
        if self.guy:
            self.guy.attached = False
            self.clean()
        s = self.world.spawns[random.randint(0,len(self.world.spawns)-1)]
        self.guy = Guy(game=self, pos=(s.x, s.y))

    def __call__(self):
        
        self.done = False
        while True:
            t = self.clock.tick(60)*0.001
            self.logic(t)
            if self.done:
                break
            self.render()
            self.draw()
        
        return 0
       
    def clean(self):
        
        self.world.objects = filter(lambda obj: obj.attached, self.world.objects)
        
    def logic(self, t):
        
        if self.mode == self.GAME:
        
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.done = True
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_q:
                        self.done = True
                    if ev.key == pygame.K_r:
                        self.reset()
                        #self.world = World('./data/maps/%s.tmx' % self.level, self)
                        #self.world.attach(self.guy)
                    self.keys += [ev.key]
                    if ev.key == pygame.K_PAGEUP:
                        self.world.next_level = True
                elif ev.type == pygame.KEYUP:
                    if ev.key in self.keys:
                        self.keys.remove(ev.key)
                #elif ev.type == pygame.JOYBUTTONDOWN:
                #    pass
                #    #if ev.button == 3:
                #    #    #self.guy.running = True
                #    #    self.guy.shoot()
                #    #elif ev.button == 1:
                #    #    self.guy.shoot()
                #elif ev.type == pygame.JOYBUTTONUP:
                #    pass
                #    #if ev.button == 3:
                #    #    self.guy.running = False

            self.guy.interface()

            #self.guy.strafe = pygame.K_LSHIFT in self.keys
            
            self.world.logic(t)

            if not self.guy.attached:
                self.reset()
            
            self.clean()
            for obj in self.world.objects:
                obj.logic(t)

            #if self.guy.pos.y < 0.0: # allow jumping above
                #self.reset()
            if self.guy.pos.x < -self.guy.sz.x:
                self.reset()
            elif self.guy.pos.x >= self.world.sz.x:
                self.reset()
            elif self.guy.pos.y >= self.world.sz.y:
                self.reset()
        
        elif self.mode == self.TITLE:
            
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.done = True
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_q:
                        self.done = True
                    if ev.key == pygame.K_SPACE or ev.key == pygame.K_RETURN:
                        self.mode = self.GAME
                        #pygame.mixer.music.play()

            for joy in self.joys:
                if joy.get_button(0):
                        self.mode = self.GAME
    
    def render(self):
        
        self.screen.buf.fill(COLORS[0])
        
        if self.mode == self.GAME:
            view = euclid.Vector2(
                self.guy.pos.x + self.guy.sz.x/2.0 - SCREEN_W/2.0,
                self.guy.pos.y + self.guy.sz.x/2.0 - 2.0*SCREEN_H/3.0
            )
            view.x = max(0, min(view.x, self.world.sz.x - SCREEN_W))
            view.y = max(0, min(view.y, self.world.sz.y - SCREEN_H))
            self.world.render(view)
            
            
            if self.guy.pos.y >= self.guy.sz.y:
                pygame.draw.rect(self.screen.buf, COLORS[0], [0, 0, SCREEN_W, 10])
                tim = str(datetime.timedelta(seconds=self.world.time))
                tim = str(tim)
                try:
                    tim = tim[:tim.index('.')+3]
                except ValueError:
                    pass
                tx = "lev %s . %s" % (self.level,tim)
                self.screen.buf.blit(self.font.render(tx, 1, COLORS[3]), (0,0))
        
        elif self.mode == self.TITLE:
            
            idx = 0
            text = [
                'warning',
                'extremely difficult',
                '',
                'gamepad recommended',
                '',
                'avoid traps',
                'find the right door',
                '',
                'Good Luck'
            ]
            for line in text:
                self.screen.buf.blit(self.font.render(line, 1, COLORS[3]), ((10- len(line)/2)*7,idx))
                idx += 10
        
    def draw(self):
        
        self.screen.render()
        pygame.display.flip()

def main():
    return Game()()

if __name__=='__main__':
    sys.exit(main())

