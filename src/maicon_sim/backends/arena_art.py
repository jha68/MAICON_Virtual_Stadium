"""Public floor markings shared by the operator map, WebGL and robot RGB.

Only arena geometry goes here; object locations and scoring truth are never
printed on the floor seen by participant cameras.
"""
from PIL import Image, ImageDraw, ImageFont


SECTOR_NUMBERS = {'B-S1': '1', 'B-S2': '2', 'B-S3': '3',
                  'R-S1': '4', 'R-S2': '5', 'R-S3': '6', 'CM': '7'}


def base_panels(arena, assets):
    """Public M5 artwork on the inward-facing wall behind each entry zone.

    Mount size/height is a simulator fixture; it does not alter base sensors or
    collision geometry. The same placements feed Bullet and the operator view.
    """
    images = {a['label']: a['asset_id'] for a in assets['assets'] if a['kind'] == 'base'}
    width = arena['bounds']['width_m']
    height = min(.4, arena['bounds'].get('wall_height_m', .4))
    panels = []
    for base in arena['bases']:
        asset = images.get(base['code'].split('_', 1)[1])
        if asset is None:
            continue
        poly = base['polygon_xy_m']
        west = sum(p[0] for p in poly) / len(poly) < width / 2
        y = (min(p[1] for p in poly) + max(p[1] for p in poly)) / 2
        panels.append({'base_id': base['base_id'], 'asset_id': asset,
                       'center': [.002 if west else width-.002, y, height/2],
                       'right': [0, 1 if west else -1, 0], 'up': [0, 0, 1],
                       'normal': [1 if west else -1, 0, 0],
                       'width_m': 1.2, 'height_m': height})
    return panels


def arena_floor(arena, scale=256):
    bounds = arena['bounds']
    w, h = bounds['width_m'], bounds['height_m']
    image = Image.new('RGB', (round(w * scale), round(h * scale)), '#111518')
    draw = ImageDraw.Draw(image)

    def point(x, y):
        return (round(x * scale), round((h - y) * scale))

    def rectangle(x0, y0, x1, y1):
        return (*point(x0, y1), *point(x1, y0))

    def hazard(x0, y0, x1, y1):
        rect = rectangle(x0, y0, x1, y1)
        tile = Image.new('RGB', (max(1, rect[2]-rect[0]), max(1, rect[3]-rect[1])), '#292d2e')
        pen = ImageDraw.Draw(tile)
        step = max(4, round(.16 * scale))
        for x in range(-tile.height, tile.width, step):
            pen.line((x, tile.height, x+tile.height, 0), fill='#ae9333', width=max(1, scale//100))
        pen.rectangle((0, 0, tile.width-1, tile.height-1), outline='#55594c', width=2)
        image.paste(tile, rect[:2])

    for index in range(int(w / .2) + 1):
        draw.line((*point(index*.2, 0), *point(index*.2, h)), fill='#262b30', width=1)
    for index in range(int(h / .2) + 1):
        draw.line((*point(0, index*.2), *point(w, index*.2)), fill='#262b30', width=1)

    for x0 in (0, w-.4):
        hazard(x0, 0, x0+.4, .2)
        hazard(x0, h-.2, x0+.4, h)
        for y in (h/3, 2*h/3):
            hazard(x0, y-.2, x0+.4, y+.2)
    for y in (0, h-.4):
        hazard(w/2-.2, y, w/2+.2, y+.4)

    number_font = ImageFont.load_default(size=round(.23 * scale))
    base_font = ImageFont.load_default(size=round(.13 * scale))
    small_font = ImageFont.load_default(size=round(.09 * scale))
    for sector in arena['sectors']:
        polygon = sector['polygon_xy_m']
        points = [point(*p) for p in polygon]
        draw.line(points+[points[0]], fill='#626772', width=max(2, round(.018 * scale)))
        left, top = min(p[0] for p in polygon), max(p[1] for p in polygon)
        draw.text(point(left+.07, top-.07), SECTOR_NUMBERS[sector['sector_id']],
                  fill='#f5ce25', font=number_font)

    names = {'COMMAND_POST': 'COMMAND', 'MAINTENANCE': 'REPAIR', 'SUPPLY_DEPOT': 'SUPPLY'}
    for base in arena['bases']:
        blue = base['camp'] == 'BLUE'
        color = '#559cff' if blue else '#ff546c'
        poly = base['polygon_xy_m']
        x0, x1 = min(p[0] for p in poly), max(p[0] for p in poly)
        y0, y1 = min(p[1] for p in poly), max(p[1] for p in poly)
        draw.rectangle(rectangle(x0, y0, x1, y1), fill='#172533' if blue else '#311c24', outline=color, width=3)
        slot = ('B-' if blue else 'R-') + base['base_id'][-1]
        center = (x0+x1)/2
        draw.text(point(center, y1-.13), slot, fill=color, font=base_font, anchor='mm')
        draw.line([point(x0, (y0+y1)/2), point(x1, (y0+y1)/2)], fill=color, width=2)
        draw.line([point(*p) for p in base['trigger_segment_xy_m']], fill=color, width=5)
        label = Image.new('RGBA', (round(.7*scale), round(.13*scale)))
        ImageDraw.Draw(label).text((label.width/2, label.height/2), names[base['code'].split('_', 1)[1]],
                                  fill=color, font=small_font, anchor='mm')
        label = label.rotate(90 if blue else -90, expand=True)
        x, y = point(x1+.12 if blue else x0-.12, (y0+y1)/2)
        image.paste(label, (x-label.width//2, y-label.height//2), label)
    draw.rectangle((1, 1, image.width-2, image.height-2), outline='#747982', width=3)
    return image
