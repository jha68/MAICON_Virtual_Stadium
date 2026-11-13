export const assetNames = {
  COMMAND_POST: '작전지휘소', MAINTENANCE: '정비소', SUPPLY_DEPOT: '군수보급소',
  COMMS: '통신시설', OUTPOST: '감시초소', RADAR: '레이더시설',
  ammo_box: '탄약상자', drum: '위험물 · 드럼통', mortar: '박격포',
  military_truck: '군용차량 · 군용트럭', tank: '전차', missile: '미사일',
  urban_tree: '도시 나무', barrier: '차단벽', field_position: '야전진지',
  ruined_building: '파괴건물', wall: '방호벽',
};
const shortNames = {...assetNames, drum: '위험물', military_truck: '군용차량', RADAR: '레이더'};
const objectColors = {ammo_box: '#b99bea', drum: '#f1779b', mortar: '#e3c56c',
  military_truck: '#83d7b0', tank: '#d4dc80', missile: '#f7a776'};

export class ArenaMap {
  constructor(canvas) {
    this.canvas = canvas;
    this.floor = null;
    this.floorId = null;
    this.baseImages = new Map();
  }

  update(state, selected, trails) {
    this.state = state;
    this.selected = selected;
    this.trails = trails;
    const id = state.match_id;
    if (id !== this.floorId) {
      this.floorId = id;
      const floor = new Image();
      this.floor = floor;
      floor.onload = () => this.draw();
      floor.src = state.arena.floor_url;
      this.baseImages.clear();
      for (const panel of state.arena.base_panels || []) {
        if (this.baseImages.has(panel.asset_id)) continue;
        const image = new Image();
        this.baseImages.set(panel.asset_id, image);
        image.onload = () => this.draw();
        image.src = state.visual_assets[panel.asset_id].url;
      }
    }
    this.draw();
  }

  draw() {
    const canvas = this.canvas, state = this.state;
    const dpr = Math.min(devicePixelRatio || 1, 2), w = canvas.clientWidth, h = canvas.clientHeight;
    if (!state || !w || !h) return;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const c = canvas.getContext('2d');
    c.scale(dpr, dpr);
    const a = state.arena.bounds;
    const scale = Math.min((w - 44) / a.width_m, (h - 54) / a.height_m);
    const ox = (w - a.width_m * scale) / 2, oy = (h - a.height_m * scale) / 2;
    const P = (x, y) => [ox + x * scale, h - oy - y * scale];
    c.fillStyle = '#111518';
    c.fillRect(ox, oy, a.width_m * scale, a.height_m * scale);
    if (this.floor?.complete && this.floor.naturalWidth) {
      c.drawImage(this.floor, ox, oy, a.width_m * scale, a.height_m * scale);
    }
    // Overhead symbols for upright M5 wall panels, facing their entry zones.
    for (const panel of state.arena.base_panels || []) {
      const image = this.baseImages.get(panel.asset_id);
      if (!image?.complete || !image.naturalWidth) continue;
      c.save();
      c.translate(...P(panel.center[0], panel.center[1]));
      c.rotate(panel.normal[0] > 0 ? -Math.PI / 2 : Math.PI / 2);
      c.drawImage(image, -panel.width_m * scale / 2, 0, panel.width_m * scale, .18 * scale);
      c.restore();
    }
    for (const box of state.boxes) {
      const p = box.pose, sx = box.size_m[0] * scale, sy = box.size_m[1] * scale;
      const decoy = box.faces.length && box.faces.every(f => f.kind === 'decoy');
      c.save();
      c.translate(...P(p.x_m, p.y_m));
      c.rotate(-p.yaw_rad);
      c.fillStyle = decoy ? '#70766d' : '#969aa2';
      c.strokeStyle = '#c0c4cb';
      c.lineWidth = .8;
      c.fillRect(-sx / 2, -sy / 2, sx, sy);
      c.strokeRect(-sx / 2, -sy / 2, sx, sy);
      if (decoy) {
        c.fillStyle = '#f3f1dd';
        c.font = `500 ${Math.max(6, .072 * scale)}px system-ui`;
        c.textAlign = 'center';
        c.textBaseline = 'middle';
        c.fillText(shortNames[state.visual_assets[box.faces[0].asset_id].label] || '장애물', 0, 0, sx - 3);
      } else {
        for (const face of box.faces) this.face(c, face, box, scale);
      }
      c.restore();
    }
    for (const [slot, r] of Object.entries(state.robots)) {
      const p = r.pose, blue = slot[0] === 'B', color = blue ? '#589bff' : '#f4737b';
      const trail = this.trails.get(slot) || [];
      if (trail.length > 1) {
        c.beginPath();
        trail.forEach((q, i) => c[i ? 'lineTo' : 'moveTo'](...P(...q)));
        c.strokeStyle = blue ? '#376494' : '#854c57';
        c.stroke();
      }
      c.save();
      c.translate(...P(p.x_m, p.y_m));
      if (slot === this.selected) {
        c.beginPath();
        c.arc(0, 0, scale * .2, 0, Math.PI * 2);
        c.strokeStyle = '#67d9ac';
        c.stroke();
      }
      c.rotate(-p.yaw_rad);
      c.fillStyle = state.render_geometry.robot_model ? '#242a30' : (r.hp ? color : '#66707c');
      c.fillRect(-.1 * scale, -.12 * scale, .2 * scale, .24 * scale);
      if (state.render_geometry.robot_model) {
        for (const x of [-.075,0,.075]) for (const y of [-.1025,.1025]) {
          c.fillStyle='#101418';c.fillRect((x-.04)*scale,(y-.0225)*scale,.08*scale,.045*scale);
        }
        for (const receiver of state.render_geometry.receivers) {
          c.beginPath();c.arc(receiver.center_m[0]*scale,-receiver.center_m[1]*scale,receiver.radius_m*scale,0,Math.PI*2);
          c.fillStyle='#e4eaf3';c.fill();
        }
        for (const y of [-.083,.083]) {c.fillStyle=color;c.fillRect(-.08*scale,y*scale-.01*scale,.02*scale,.02*scale);}
      }
      c.strokeStyle = '#eaf4ff';
      c.beginPath();
      c.moveTo(0, 0);
      c.lineTo(.2 * scale*Math.cos(r.pan*.5*Math.PI/180), .2*scale*Math.sin(r.pan*.5*Math.PI/180));
      c.stroke();
      c.restore();
    }
    c.strokeStyle='#ff4d4d';
    for (const ray of state.laser_segments || []) {
      c.beginPath();c.moveTo(...P(...ray.start));c.lineTo(...P(...ray.end));c.stroke();
    }
  }

  face(c, face, box, scale) {
    const label = this.state.visual_assets[face.asset_id].label;
    const sx = box.size_m[0] * scale, sy = box.size_m[1] * scale;
    const thickness = .075 * scale;
    const facility = face.kind === 'facility';
    const color = facility ? (face.facility_code.startsWith('BLUE') ? '#659ff4' : '#fa6d83') : objectColors[label] || '#9da986';
    const side = face.side;
    const x = side === 'east' ? sx / 2 : side === 'west' ? -sx / 2 : 0;
    const y = side === 'north' ? -sy / 2 : side === 'south' ? sy / 2 : 0;
    const angle = {north: 0, south: Math.PI, east: Math.PI / 2, west: -Math.PI / 2}[side];
    const width = side === 'east' || side === 'west' ? sy : sx;
    c.save();
    c.translate(x, y);
    c.rotate(angle);
    c.fillStyle = color;
    c.fillRect(-width / 2, 0, width, thickness);
    c.fillStyle = '#13202b';
    c.textBaseline = 'middle';
    c.textAlign = 'center';
    c.font = `600 ${Math.max(5, .061 * scale)}px system-ui`;
    c.fillText(shortNames[label] || label, 0, thickness / 2, width - 2);
    if (facility) {
      const signal = this.state.facility_signals?.[face.facility_code] || 'idle';
      c.fillStyle = {idle: '#edf4f8', receiving: '#ffb13e', hit: '#ff354e'}[signal];
      c.strokeStyle = '#414a57';
      c.beginPath();
      c.arc(0, -this.state.render_geometry.facility_receiver_offset_m * scale,
        Math.max(2, this.state.render_geometry.facility_receiver_radius_m * scale), 0, Math.PI * 2);
      c.fill();
      c.stroke();
    }
    c.restore();
  }
}

let catalogSignature = null;
export function updateCatalog(element, receivers, state) {
  if (catalogSignature !== state.match_id) {
    catalogSignature = state.match_id;
    const counts = new Map();
    for (const panel of state.arena.base_panels || []) counts.set(panel.asset_id, (counts.get(panel.asset_id) || 0) + 1);
    for (const box of state.boxes) {
      for (const id of new Set(box.faces.map(f => f.asset_id))) counts.set(id, (counts.get(id) || 0) + 1);
    }
    element.replaceChildren(...Object.entries(state.visual_assets).map(([id, asset]) => {
      const card = document.createElement('figure');
      card.className = 'asset-card';
      card.dataset.kind = asset.kind;
      const img = document.createElement('img');
      img.src = asset.url;
      img.alt = assetNames[asset.label] || asset.label;
      const caption = document.createElement('figcaption');
      caption.textContent = img.alt;
      const info = document.createElement('small');
      info.textContent = `${{facility: '표적 · 수광부', object: '인식 대상', decoy: '비인식 장애물', base: 'M5 목표거점'}[asset.kind] || asset.kind} · ${counts.get(id) || 0}${asset.kind === 'base' ? '곳' : '개 박스'}`;
      card.append(img, caption, info);
      return card;
    }));
    receivers.replaceChildren(...Object.keys(state.facility_signals).map(code => {
      const chip = document.createElement('span');
      chip.dataset.facility = code;
      return chip;
    }));
  }
  for (const chip of receivers.children) {
    const code = chip.dataset.facility, signal = state.facility_signals[code];
    chip.dataset.signal = signal;
    chip.textContent = `${code.startsWith('BLUE') ? 'B' : 'R'} ${assetNames[code.split('_')[1]]} · ${{idle: '대기', receiving: '수광 중', hit: '타격 완료'}[signal]}`;
  }
}
