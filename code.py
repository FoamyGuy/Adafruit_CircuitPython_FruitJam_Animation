# SPDX-FileCopyrightText: 2025 Tim Cocks for Adafruit Industries
#
# SPDX-License-Identifier: MIT
import displayio
import supervisor
from displayio import OnDiskBitmap, TileGrid, Group
import adafruit_ticks
import adafruit_imageload
import time
import math

display = supervisor.runtime.display
display.auto_refresh = False

def make_alternate_platte(input_palette, target_color):
    new_palette = displayio.Palette(len(input_palette))

    for i in range(len(input_palette)):
        new_palette[i] = input_palette[i] & target_color
    new_palette.make_transparent(0)
    return new_palette


class OvershootAnimator:
    """
    A non-blocking animator that moves an element to a target with overshoot effect.

    Instead of blocking with sleep(), this class provides a tick() method that
    should be called repeatedly by an external loop (e.g., game loop, UI event loop).
    """

    def __init__(self, element):
        """
        Initialize the animator with an element to animate.

        Parameters:
        - element: An object with x and y properties that will be animated
        """
        self.element = element
        self.pos_animating = False
        self.start_time = 0
        self.start_x = 0
        self.start_y = 0
        self.target_x = 0
        self.target_y = 0
        self.overshoot_x = 0
        self.overshoot_y = 0
        self.duration = 0
        self.overshoot_pixels = 0
        self.eased_value = None

        self.cur_sprite_index = None
        self.last_sprite_frame_time = -1
        self.sprite_anim_start_time = -1
        self.sprite_anim_from_index = None
        self.sprite_anim_to_index = None
        self.sprite_anim_delay = None

    def animate_to(self, target_x, target_y, duration=1.0, overshoot_pixels=20,
                   start_sprite_anim_at=None, sprite_delay=1 / 60,
                   sprite_from_index=None, sprite_to_index=None, eased_value=None):

        """
        Start a new animation to the specified target.

        Parameters:
        - target_x, target_y: The final target coordinates
        - duration: Total animation time in seconds
        - overshoot_pixels: How many pixels to overshoot beyond the target
                            (use 0 for no overshoot)
        """
        _now = adafruit_ticks.ticks_ms() / 1000

        # Record starting position and time
        self.start_x = self.element.x
        self.start_y = self.element.y
        self.start_time = _now
        if start_sprite_anim_at is not None:
            self.sprite_anim_start_time = _now + start_sprite_anim_at
            self.sprite_anim_to_index = sprite_to_index
            self.sprite_anim_from_index = sprite_from_index
            self.cur_sprite_index = self.sprite_anim_from_index
            self.sprite_anim_delay = sprite_delay

        # Store target position and parameters
        self.target_x = target_x
        self.target_y = target_y
        self.duration = duration
        self.overshoot_pixels = overshoot_pixels

        # Calculate distance to target
        dx = target_x - self.start_x
        dy = target_y - self.start_y

        # Calculate the direction vector (normalized)
        distance = math.sqrt(dx * dx + dy * dy)
        if distance <= 0:
            # Already at target
            return False

        dir_x = dx / distance
        dir_y = dy / distance

        # Calculate overshoot position
        self.overshoot_x = target_x + dir_x * overshoot_pixels
        self.overshoot_y = target_y + dir_y * overshoot_pixels

        self.eased_value = eased_value

        # Start the animation
        self.pos_animating = True
        return True

    def sprite_anim_tick(self, cur_time):
        if cur_time >= self.last_sprite_frame_time + self.sprite_anim_delay:
            # print(f"cur idx: {self.cur_sprite_index}")
            self.element[0] = self.cur_sprite_index

            self.last_sprite_frame_time = cur_time
            # display.refresh()
            self.cur_sprite_index += 1
            # print(f"cur idx: {self.cur_sprite_index} > {self.sprite_anim_to_index}")
            if self.cur_sprite_index > self.sprite_anim_to_index:
                # print("returning false from sprite_anim_tick")
                self.cur_sprite_index = None
                self.sprite_anim_from_index = None
                self.sprite_anim_to_index = None
                self.sprite_anim_delay = None
                self.last_sprite_frame_time = -1
                self.sprite_anim_start_time = -1
                return False

        return True

    def tick(self):
        """
        Update the animation based on the current time.

        This method should be called repeatedly until it returns False.

        Returns:
        - True if the animation is still in progress
        - False if the animation has completed
        """
        still_sprite_animating = False
        _now = adafruit_ticks.ticks_ms() / 1000
        if self.cur_sprite_index is not None:
            if _now >= self.sprite_anim_start_time:

                still_sprite_animating = self.sprite_anim_tick(_now)
                # print("sprite_still_animating", still_sprite_animating)
                if not still_sprite_animating:
                    return False
        else:
            if not self.pos_animating:
                # print("returning false cur_sprite_index was None and pos_animating False")
                return False

        # Calculate elapsed time and progress
        elapsed = _now - self.start_time
        progress = elapsed / self.duration

        # Check if animation is complete
        if progress >= 1.0:
            # Ensure we end exactly at the target
            if self.element.x != self.target_x or self.element.y != self.target_y:
                self.element.x = self.target_x
                self.element.y = self.target_y
                # display.refresh()
            self.pos_animating = False
            if still_sprite_animating:
                return True
            else:
                return False

        # Calculate the current position based on progress
        if self.overshoot_pixels > 0:
            # Two-phase animation with overshoot
            if progress < 0.7:  # Move smoothly toward overshoot position
                # Use a single smooth curve to the overshoot point
                eased = progress / 0.7  # Linear acceleration toward overshoot
                # Apply slight ease-in to make it accelerate through the target point
                eased = eased ** 1.2
                current_x = self.start_x + (self.overshoot_x - self.start_x) * eased
                current_y = self.start_y + (self.overshoot_y - self.start_y) * eased
            else:  # Return from overshoot to target
                sub_progress = (progress - 0.7) / 0.3
                # Decelerate toward final target
                eased = 1 - (1 - sub_progress) ** 2  # ease-out quad
                current_x = self.overshoot_x + (self.target_x - self.overshoot_x) * eased
                current_y = self.overshoot_y + (self.target_y - self.overshoot_y) * eased
        else:
            # Simple ease-out when no overshoot is desired
            if self.eased_value is None:
                eased = 1 - (1 - progress) ** 4
            else:
                eased = progress / self.eased_value
            current_x = self.start_x + (self.target_x - self.start_x) * eased
            current_y = self.start_y + (self.target_y - self.start_y) * eased

        # Update element position
        self.element.x = int(current_x)
        self.element.y = int(current_y)
        # print(f"cur: {self.element.x}, {self.element.y}")
        # display.refresh(target_frames_per_second=30)

        return True

    def is_animating(self):
        """Check if an animation is currently in progress."""
        return self.pos_animating

    def cancel(self):
        """Cancel the current animation."""
        self.pos_animating = False

# apple_sprites, apple_sprites_palette = adafruit_imageload.load("apple_spritesheet.bmp")
# f_sprites, f_sprites_palette = adafruit_imageload.load("f_spritesheet_indexed.bmp")
# r_sprites, r_sprites_palette = adafruit_imageload.load("r_spritesheet.bmp")
# u_sprites, u_sprites_palette = adafruit_imageload.load("u_spritesheet.bmp")
# i_sprites, i_sprites_palette = adafruit_imageload.load("i_spritesheet.bmp")
# t_sprites, t_sprites_palette = adafruit_imageload.load("t_spritesheet.bmp")
# j_sprites, j_sprites_palette = adafruit_imageload.load("j_spritesheet_transparent.bmp")
# j_sprites_palette.make_transparent(0)
# a_sprites, a_sprites_palette = adafruit_imageload.load("a_spritesheet_transparent.bmp")
# a_sprites_palette.make_transparent(0)
# m_sprites, m_sprites_palette = adafruit_imageload.load("m_spritesheet_transparent.bmp")
# m_sprites_palette.make_transparent(0)

apple_sprites = OnDiskBitmap("apple_spritesheet.bmp")
apple_sprites_palette = apple_sprites.pixel_shader
apple_sprites_palette.make_transparent(0)

f_sprites = OnDiskBitmap("f_spritesheet.bmp")
f_sprites_palette = f_sprites.pixel_shader
f_sprites_palette.make_transparent(0)
r_sprites = OnDiskBitmap("r_spritesheet.bmp")
r_sprites_palette = r_sprites.pixel_shader
r_sprites_palette.make_transparent(0)
u_sprites = OnDiskBitmap("u_spritesheet.bmp")
u_sprites_palette = u_sprites.pixel_shader
u_sprites_palette.make_transparent(0)
i_sprites = OnDiskBitmap("i_spritesheet.bmp")
i_sprites_palette = i_sprites.pixel_shader
i_sprites_palette.make_transparent(0)
t_sprites = OnDiskBitmap("t_spritesheet.bmp")
t_sprites_palette = t_sprites.pixel_shader
t_sprites_palette.make_transparent(0)
j_sprites = OnDiskBitmap("j_spritesheet.bmp")
j_sprites_palette = j_sprites.pixel_shader
j_sprites_palette.make_transparent(0)
a_sprites = OnDiskBitmap("a_spritesheet.bmp")
a_sprites_palette = a_sprites.pixel_shader
a_sprites_palette.make_transparent(0)
m_sprites = OnDiskBitmap("m_spritesheet.bmp")
m_sprites_palette = m_sprites.pixel_shader
m_sprites_palette.make_transparent(0)

default_sprite_delay = 1/35

main_group = Group()

sliding_group = Group()
main_group.append(sliding_group)

letters_x_start = 83

coordinator = {
    "steps": [
        {
            "type": "animation_step",
            "tilegrid": TileGrid(apple_sprites, pixel_shader=apple_sprites_palette,
                                 tile_width=72, tile_height=107, width=1, height=1),
            "offscreen_loc": (0, -107),
            "onscreen_loc": (0, 21),
            "move_duration": 0.45,
            "overshoot_pixels": 1,
            "eased_value": None,
            "sprite_anim_range": (0, 11),
            "sprite_delay": 1/42,
            "start_time": 0.0,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        {
            "type": "animation_step",
            "tilegrid": TileGrid(f_sprites, pixel_shader=f_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start, 240),
            "onscreen_loc": (letters_x_start, 50),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 0.45,
            "sprite_anim_start": 0.347,
            "started": False,

        },
        {
            "type": "animation_step",
            "tilegrid": TileGrid(r_sprites, pixel_shader=r_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + 32 + 3, 240),
            "onscreen_loc": (letters_x_start + 32 + 3, 50),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 0.9,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        {
            "type": "animation_step",
            "tilegrid": sliding_group,
            "offscreen_loc": (100, 0),
            "onscreen_loc": (30, 0),
            "move_duration": 1.75,
            "overshoot_pixels": 0,

            "eased_value": 1,
            "sprite_anim_range": None,
            "sprite_delay": None,
            "start_time": 0.9,
            "sprite_anim_start": None,
            "started": False,
        },
        {
            "type": "animation_step",
            "tilegrid": TileGrid(u_sprites, pixel_shader=u_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + (32 + 3) * 2, 240),
            "onscreen_loc": (letters_x_start + (32 + 3) * 2, 50),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 1.35,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        {
            "type": "animation_step",
            "tilegrid": TileGrid(i_sprites, pixel_shader=i_sprites_palette,
                                 tile_width=16, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + (32 + 3) * 3, 240),
            "onscreen_loc": (letters_x_start + (32 + 3) * 3, 50),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 1.8,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        {
            "type": "animation_step",
            "tilegrid": TileGrid(t_sprites, pixel_shader=t_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + (32 + 3) * 3 + 16 + 3, 240),
            "onscreen_loc": (letters_x_start + (32 + 3) * 3 + 16 + 3, 50),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 2.25,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        {
            "type": "animation_step",
            "tilegrid": TileGrid(j_sprites, pixel_shader=j_sprites_palette,
                                 tile_width=32, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start, 240),
            "onscreen_loc": (letters_x_start, 50 + 39),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 2.7,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        {
            "type": "animation_step",
            "tilegrid": TileGrid(a_sprites, pixel_shader=a_sprites_palette,
                                 tile_width=33, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + 32 + 3, 240),
            "onscreen_loc": (letters_x_start + 32 + 3, 50 + 39),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 3.15,
            "sprite_anim_start": 0.347,
            "started": False,
        },
        {
            "type": "animation_step",
            "tilegrid": TileGrid(m_sprites, pixel_shader=m_sprites_palette,
                                 tile_width=44, tile_height=39, width=1, height=1),
            "offscreen_loc": (letters_x_start + 32 + 3 + 33 + 2, 240),
            "onscreen_loc": (letters_x_start + 32 + 3 + 33 + 2, 50 + 39),
            "move_duration": 0.45,
            "overshoot_pixels": 20,
            "eased_value": None,
            "sprite_anim_range": (0, 15),
            "sprite_delay": default_sprite_delay,
            "start_time": 3.6,
            "sprite_anim_start": 0.347,
            "started": False,
        }

    ]
}

for step in coordinator["steps"]:
    if isinstance(step["tilegrid"], TileGrid):
        sliding_group.append(step["tilegrid"])
        step["default_palette"] = step["tilegrid"].pixel_shader
        step["red_palette"] = make_alternate_platte(step["default_palette"], 0xff0000)
        step["yellow_palette"] = make_alternate_platte(step["default_palette"], 0xffff00)
        step["teal_palette"] = make_alternate_platte(step["default_palette"], 0x00ffff)
        step["pink_palette"] = make_alternate_platte(step["default_palette"], 0xff00ff)
        step["blue_palette"] = make_alternate_platte(step["default_palette"], 0x0000ff)
        step["green_palette"] = make_alternate_platte(step["default_palette"], 0x00ff00)
        #step["tilegrid"].pixel_shader = step["red_palette"]
    step["tilegrid"].x = step["offscreen_loc"][0]
    step["tilegrid"].y = step["offscreen_loc"][1]
    step["animator"] = OvershootAnimator(step["tilegrid"])


coordinator["steps"].insert(8,
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][1]["tilegrid"],
        "animator": coordinator["steps"][1]["animator"],
        "offscreen_loc": (letters_x_start, 240),
        "onscreen_loc": (letters_x_start, 50),
        "move_duration": 0.3,
        "overshoot_pixels": 10,
        "eased_value": None,
        "sprite_anim_range": (16, 27),
        "sprite_delay": 1/22,
        # "start_time": 4.08,
        "start_time": 3.047,
        "sprite_anim_start": 0.15,
        "started": False,
    },
)

coordinator["steps"].insert(10,
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][2]["tilegrid"],
        "animator": coordinator["steps"][2]["animator"],
        "offscreen_loc": (letters_x_start + 32 + 3, 240),
        "onscreen_loc": (letters_x_start + 32 + 3, 50),
        "move_duration": 0.3,
        "overshoot_pixels": 10,
        "eased_value": None,
        "sprite_anim_range": (16, 27),
        "sprite_delay": 1/22,
        #"start_time": 4.78,
        "start_time": 3.497,
        "sprite_anim_start": 0.15,
        "started": False,
    },
)

coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][4]["tilegrid"],
        "animator": coordinator["steps"][4]["animator"],
        "offscreen_loc": (letters_x_start + (32 + 3) * 2, 240),
        "onscreen_loc": (letters_x_start + (32 + 3) * 2, 50),
        "move_duration": 0.3,
        "overshoot_pixels": 10,
        "eased_value": None,
        "sprite_anim_range": (16, 27),
        "sprite_delay": 1/22,
        # "start_time": 5.48,
        "start_time": 3.947,
        "sprite_anim_start": 0.15,
        "started": False,
    },
)

coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][5]["tilegrid"],
        "animator": coordinator["steps"][5]["animator"],
        "offscreen_loc": (letters_x_start + (32 + 3) * 3 , 240),
        "onscreen_loc": (letters_x_start + (32 + 3) * 3, 50),
        "move_duration": 0.3,
        "overshoot_pixels": 10,
        "eased_value": None,
        "sprite_anim_range": (16, 27),
        "sprite_delay": 1/22,
        # "start_time": 5.58,
        "start_time": 4.047,
        "sprite_anim_start": 0.15,
        "started": False,
    },
)

coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][6]["tilegrid"],
        "animator": coordinator["steps"][6]["animator"],
        "offscreen_loc": (letters_x_start + (32 + 3) * 3 + 16 + 3, 240),
        "onscreen_loc": (letters_x_start + (32 + 3) * 3 + 16 + 3, 50),
        "move_duration": 0.3,
        "overshoot_pixels": 10,
        "eased_value": None,
        "sprite_anim_range": (16, 27),
        "sprite_delay": 1/22,
        # "start_time": 5.68,
        "start_time": 4.147,
        "sprite_anim_start": 0.15,
        "started": False,
    },
)

coordinator["steps"].append(
    {
        "start_time": 4.75,
        "type": "change_palette",
        "new_palette": "red_palette",
        "started": False,
    }
)
coordinator["steps"].append(
    {
        "start_time": 5,
        "type": "change_palette",
        "new_palette": "yellow_palette",
        "started": False,
    }
)
coordinator["steps"].append(
    {
        "start_time": 5.25,
        "type": "change_palette",
        "new_palette": "teal_palette",
        "started": False,
    }
)
coordinator["steps"].append(
    {
        "start_time": 5.5,
        "type": "change_palette",
        "new_palette": "pink_palette",
        "started": False,
    }
)
coordinator["steps"].append(
    {
        "start_time": 5.75,
        "type": "change_palette",
        "new_palette": "blue_palette",
        "started": False,
    }
)
coordinator["steps"].append(
    {
        "start_time": 6.00,
        "type": "change_palette",
        "new_palette": "green_palette",
        "started": False,
    }
)
coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][0]["tilegrid"],
        "animator": coordinator["steps"][0]["animator"],
        "offscreen_loc": (0, -107),
        "onscreen_loc": (0, 21),
        "move_duration": 0.01,
        "overshoot_pixels": 0,
        "eased_value": None,
        "sprite_anim_range": (12, 27),
        "sprite_delay": 1/32,
        # "start_time": 5.68,
        "start_time": 6.25,
        "sprite_anim_start": 0.0,
        "started": False,
    }
)
coordinator["steps"].append(
    {
        "type": "animation_step",
        "tilegrid": coordinator["steps"][0]["tilegrid"],
        "animator": coordinator["steps"][0]["animator"],
        "offscreen_loc": (0, -107),
        "onscreen_loc": (0, 21),
        "move_duration": 0.01,
        "overshoot_pixels": 0,
        "eased_value": None,
        "sprite_anim_range": (12, 27),
        "sprite_delay": 1/32,
        # "start_time": 5.68,
        "start_time": 8.55,
        "sprite_anim_start": 0.0,
        "started": False,
    }
)

display.root_group = main_group

start_time = adafruit_ticks.ticks_ms() / 1000

while True:

    now = adafruit_ticks.ticks_ms() / 1000
    still_going = True

    for i, step in enumerate(coordinator["steps"]):
        if now - start_time >= step["start_time"]:
            if not step["started"]:
                step["started"] = True
                if step["type"] == "animation_step":
                    if step["sprite_anim_range"] is not None:
                        step["animator"].animate_to(
                            *step["onscreen_loc"],
                            duration=step["move_duration"], overshoot_pixels=step["overshoot_pixels"],
                            start_sprite_anim_at=step["sprite_anim_start"],
                            sprite_from_index=step["sprite_anim_range"][0], sprite_to_index=step["sprite_anim_range"][1],
                            sprite_delay=step["sprite_delay"], eased_value=step["eased_value"],
                        )
                    else:
                        step["animator"].animate_to(
                            *step["onscreen_loc"],
                            duration=step["move_duration"], overshoot_pixels=step["overshoot_pixels"],
                            eased_value=step["eased_value"]
                        )
                elif step["type"] == "change_palette":

                    for _cur_step in coordinator["steps"]:
                        if step["new_palette"] in _cur_step:
                            _cur_step["tilegrid"].pixel_shader = _cur_step[step["new_palette"]]

            if "animator" in step:
                if i == len(coordinator["steps"]) - 1:
                    still_going = step["animator"].tick()
                else:
                    step["animator"].tick()
            else:
                if i == len(coordinator["steps"]) - 1:
                    still_going = False

    display.refresh()

    if not still_going:
        for step in coordinator["steps"]:
            if step["type"] == "animation_step":
                step["tilegrid"].x = step["offscreen_loc"][0]
                step["tilegrid"].y = step["offscreen_loc"][1]
                if "default_palette" in step:
                    step["tilegrid"].pixel_shader = step["default_palette"]
            step["started"] = False

        # reset the apple to no eyes sprite
        coordinator["steps"][0]["tilegrid"][0] = 0

        time.sleep(1)
        display.refresh()
        start_time = adafruit_ticks.ticks_ms() / 1000