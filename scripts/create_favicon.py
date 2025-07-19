#!/usr/bin/env python3
"""Create a pixel art favicon.ico with anime-style bot girl with twintails"""

from PIL import Image, ImageDraw

# Create a 32x32 image with transparent background
img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Define colors
skin = (255, 220, 200)
hair = (139, 69, 139)  # Purple for twintails
hair_shadow = (105, 50, 105)
eye_color = (70, 130, 180)  # Steel blue
white = (255, 255, 255)
black = (0, 0, 0)
blush = (255, 182, 193)
bot_accent = (192, 192, 192)  # Silver for bot elements

# Draw head (circle)
for y in range(10, 22):
    for x in range(11, 21):
        # Create circular head shape
        if ((x-16)**2 + (y-16)**2) <= 25:
            img.putpixel((x, y), skin)

# Draw face details
# Eyes
img.putpixel((13, 15), black)  # Left eye outline
img.putpixel((14, 15), eye_color)  # Left eye
img.putpixel((18, 15), black)  # Right eye outline
img.putpixel((17, 15), eye_color)  # Right eye

# Small highlights in eyes
img.putpixel((14, 14), white)
img.putpixel((17, 14), white)

# Blush
img.putpixel((12, 17), blush)
img.putpixel((19, 17), blush)

# Small mouth
img.putpixel((15, 18), black)
img.putpixel((16, 18), black)

# Draw twintails
# Left twintail
for y in range(8, 24):
    for x in range(5, 10):
        if y < 14:  # Upper part
            if x in [6, 7, 8]:
                img.putpixel((x, y), hair)
        elif y < 20:  # Middle part
            if x in [5, 6, 7]:
                img.putpixel((x, y), hair)
        else:  # Lower part
            if x in [5, 6]:
                img.putpixel((x, y), hair_shadow)

# Right twintail
for y in range(8, 24):
    for x in range(22, 27):
        if y < 14:  # Upper part
            if x in [23, 24, 25]:
                img.putpixel((x, y), hair)
        elif y < 20:  # Middle part
            if x in [24, 25, 26]:
                img.putpixel((x, y), hair)
        else:  # Lower part
            if x in [25, 26]:
                img.putpixel((x, y), hair_shadow)

# Hair on top of head
for x in range(11, 21):
    for y in range(8, 12):
        if ((x-16)**2 + (y-10)**2) <= 20:
            img.putpixel((x, y), hair)

# Bot antenna/accessories
# Left antenna
img.putpixel((12, 7), bot_accent)
img.putpixel((12, 6), bot_accent)
img.putpixel((11, 5), white)
img.putpixel((12, 5), white)

# Right antenna
img.putpixel((19, 7), bot_accent)
img.putpixel((19, 6), bot_accent)
img.putpixel((19, 5), white)
img.putpixel((20, 5), white)

# Small bot details on hair ties
img.putpixel((7, 13), bot_accent)
img.putpixel((24, 13), bot_accent)

# Create multiple sizes for the favicon
sizes = [(16, 16), (32, 32), (48, 48)]
images = []

for size in sizes:
    # Resize using nearest neighbor to maintain pixel art style
    resized = img.resize(size, Image.NEAREST)
    images.append(resized)

# Also keep the original 32x32
images.insert(1, img)

# Save as ICO with multiple sizes
images[0].save('./app/static/favicon.ico',
               format='ICO',
               sizes=[(16, 16), (32, 32), (48, 48)],
               append_images=images[1:])

print("Favicon created successfully!")
