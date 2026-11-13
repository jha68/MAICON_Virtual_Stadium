import * as T from './vendor/three.module.min.js';
import {buildRobot, updateRobot} from './robot.js';

// Local axes match core.geometry3d.FACE_AXES (right, up, outward).
const faces = {
  east: {normal: [1, 0, 0], right: [0, 1, 0], axis: 0, sign: 1},
  west: {normal: [-1, 0, 0], right: [0, -1, 0], axis: 0, sign: -1},
  north: {normal: [0, 1, 0], right: [-1, 0, 0], axis: 1, sign: 1},
  south: {normal: [0, -1, 0], right: [1, 0, 0], axis: 1, sign: -1},
};

export class World {
  constructor(element) {
    this.element = element;
    this.renderer = new T.WebGLRenderer({antialias: true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0x101926);
    element.append(this.renderer.domElement);
    this.scene = new T.Scene();
    this.scene.add(new T.HemisphereLight(0xdce9ff, 0x51515a, 2.4));
    const sun = new T.DirectionalLight(0xffffff, 2.2);
    sun.position.set(-3, -2, 8);
    this.scene.add(sun);
    this.camera = new T.PerspectiveCamera(48, 1, .01, 100);
    this.camera.up.set(0, 0, 1);
    this.angle = -1.15;
    this.pitch = .97;
    this.distance = 9.2;
    this.robots = new Map();
    this.boxes = new Map();
    this.receivers = new Map();
    this.textures = new Map();
    this.group = new T.Group();
    this.scene.add(this.group);
    this.signature = null;
    this.lasers = new T.Group(); this.scene.add(this.lasers);
    this.focusSlot = null;
    let pointer = null;
    const canvas = this.renderer.domElement;
    canvas.title = '드래그: 회전 · 휠: 확대 · 더블클릭: 선택 UGV / 경기장 전환';
    canvas.addEventListener('dblclick', () => {
      this.focusSlot = this.focusSlot ? null : this.selected;
      this.distance = this.focusSlot ? .8 : 9.2;
      this.render();
    });
    canvas.style.touchAction = 'none';
    canvas.addEventListener('pointerdown', e => {
      pointer = [e.clientX, e.clientY];
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener('pointerup', () => pointer = null);
    canvas.addEventListener('pointercancel', () => pointer = null);
    canvas.addEventListener('pointermove', e => {
      if (!pointer) return;
      this.angle -= (e.clientX - pointer[0]) * .008;
      this.pitch = Math.max(.2, Math.min(1.5, this.pitch + (e.clientY - pointer[1]) * .006));
      pointer = [e.clientX, e.clientY];
      this.render();
    });
    canvas.addEventListener('wheel', e => {
      e.preventDefault();
      this.distance = Math.max(.45, Math.min(20, this.distance * Math.exp(e.deltaY * .001)));
      this.render();
    }, {passive: false});
  }

  box(w, d, h, color, x, y, z, parent = this.group) {
    const mesh = new T.Mesh(new T.BoxGeometry(w, d, h), new T.MeshStandardMaterial({color, roughness: .85}));
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  }

  sphere(radius, color, position, parent) {
    const mesh = new T.Mesh(new T.SphereGeometry(radius, 16, 12), new T.MeshStandardMaterial({color, roughness: .4}));
    mesh.position.fromArray(position);
    parent.add(mesh);
    return mesh;
  }

  texture(url) {
    if (!this.textures.has(url)) {
      const signature = this.signature;
      const texture = new T.TextureLoader().load(url, () => {
        if (signature === this.signature) this.render();
      }, undefined, () => this.element.dispatchEvent(new CustomEvent('textureerror')));
      texture.colorSpace = T.SRGBColorSpace;
      texture.anisotropy = Math.min(4, this.renderer.capabilities.getMaxAnisotropy());
      this.textures.set(url, texture);
    }
    return this.textures.get(url);
  }

  clear() {
    this.group.traverse(o => {
      o.geometry?.dispose();
      if (o.material) {
        if (o.isSprite) o.material.map?.dispose();
        o.material.dispose();
      }
    });
    for (const texture of this.textures.values()) texture.dispose();
    this.textures.clear();
    this.group.clear();
    this.robots.clear();
    this.boxes.clear();
    this.receivers.clear();
    this.focusSlot=null;
  }

  label(text, color) {
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 48;
    const c = canvas.getContext('2d');
    c.font = 'bold 26px sans-serif';
    c.textAlign = 'center';
    c.fillStyle = color;
    c.fillText(text, 64, 32);
    const sprite = new T.Sprite(new T.SpriteMaterial({map: new T.CanvasTexture(canvas), depthTest: false}));
    sprite.scale.set(.45, .17, 1);
    this.group.add(sprite);
    return sprite;
  }

  buildBox(box, state) {
    const group = new T.Group();
    group.name = box.box_id;
    this.group.add(group);
    this.boxes.set(box.box_id, group);
    const [sx, sy, sz] = box.size_m;
    this.box(sx, sy, sz, 0x656970, 0, 0, sz / 2, group);
    for (const face of box.faces) {
      const basis = faces[face.side], normal = new T.Vector3(...basis.normal);
      const center = [0, 0, sz / 2];
      center[basis.axis] = basis.sign * (box.size_m[basis.axis] / 2 + .001);
      const panel = new T.Mesh(new T.PlaneGeometry(box.size_m[1 - basis.axis] * .88, sz * .88),
        new T.MeshBasicMaterial({map: this.texture(state.visual_assets[face.asset_id].url)}));
      panel.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(
        new T.Vector3(...basis.right), new T.Vector3(0, 0, 1), normal));
      panel.position.fromArray(center);
      group.add(panel);
      if (face.kind === 'facility') {
        const g = state.render_geometry, r = g.facility_receiver_radius_m;
        center[2] = g.facility_receiver_z_m;
        center[basis.axis] = basis.sign * (box.size_m[basis.axis] / 2 + g.facility_receiver_offset_m);
        this.sphere(r * 1.4, 0xd1d6db, center.map((v, i) => v - basis.normal[i] * r * .6), group);
        const lens = this.sphere(r, 0x7b91a1, center, group);
        const ledPosition = [0, 0, sz + .018];
        ledPosition[basis.axis] = basis.sign * box.size_m[basis.axis] * .35;
        this.box(.11, .07, .016, 0x202428, ledPosition[0], ledPosition[1], sz + .008, group);
        const led = this.box(.08, .044, .024, 0x290f0d, ...ledPosition, group);
        this.receivers.set(face.facility_code, {lens, led});
      }
    }
  }

  build(state) {
    const b = state.arena.bounds, w = b.width_m, h = b.height_m;
    this.center = [w / 2, h / 2];
    this.box(w + .12, h + .12, .13, 0x30363d, ...this.center, -.08);
    const floor = new T.Mesh(new T.PlaneGeometry(w, h),
      new T.MeshBasicMaterial({map: this.texture(state.arena.floor_url)}));
    floor.position.set(...this.center, .001);
    this.group.add(floor);
    const wall = state.render_geometry.wall_thickness_m, wh = b.wall_height_m;
    this.box(w, wall, wh, 0x444b53, w / 2, -wall / 2, wh / 2);
    this.box(w, wall, wh, 0x444b53, w / 2, h + wall / 2, wh / 2);
    this.box(wall, h, wh, 0x444b53, -wall / 2, h / 2, wh / 2);
    this.box(wall, h, wh, 0x444b53, w + wall / 2, h / 2, wh / 2);
    for (const placement of state.arena.base_panels || []) {
      const panel = new T.Mesh(new T.PlaneGeometry(placement.width_m, placement.height_m),
        new T.MeshBasicMaterial({map: this.texture(state.visual_assets[placement.asset_id].url)}));
      panel.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(
        new T.Vector3(...placement.right), new T.Vector3(...placement.up), new T.Vector3(...placement.normal)));
      panel.position.fromArray(placement.center);
      panel.name = `base/${placement.base_id}`;
      this.group.add(panel);
    }
    for (const box of state.boxes) this.buildBox(box, state);
    for (const slot of Object.keys(state.robots)) {
      const color = slot[0] === 'B' ? 0x5089ef : 0xe7616d;
      const group = new T.Group();
      this.group.add(group);
      if (state.render_geometry.robot_model === 'wingbot_6wd_v1') {
        this.robots.set(slot, {group, label: this.label(slot, slot[0] === 'B' ? '#99c3ff' : '#ffb3b9'), color});
        continue;
      }
      const body = this.box(.23, .25, .12, color, 0, 0, .09, group);
      this.box(.055, .055, .18, color, 0, 0, .22, group);
      this.box(.055, .07, .04, 0xc4cbd1, .04, 0, .25, group);
      for (const x of [-.075, 0, .075]) {
        for (const y of [-.13, .13]) {
          const wheel = new T.Mesh(new T.CylinderGeometry(.045, .045, .035, 12),
            new T.MeshStandardMaterial({color: 0x101418, roughness: 1}));
          wheel.position.set(x, y, .045);
          group.add(wheel);
        }
      }
      this.robots.set(slot, {group, body, label: this.label(slot, slot[0] === 'B' ? '#99c3ff' : '#ffb3b9'), color});
    }
    if (state.render_geometry.robot_model === 'wingbot_6wd_v1') {
      const signature=this.signature;
      fetch(state.robot_model_url).then(r => { if (!r.ok) throw new Error('robot model'); return r.json(); }).then(manifest => {
        if (this.signature !== signature) return;
        for (const [slot, robot] of this.robots) robot.model = buildRobot(robot.group, manifest, slot);
        this.element.dataset.robotModel = manifest.model;
        this.update(this.lastState, this.selected);
      }).catch(() => this.element.dispatchEvent(new CustomEvent('modelerror')));
    }
  }

  update(state, selected) {
    this.lastState=state;this.selected=selected;
    if (state.match_id !== this.signature) {
      this.clear();
      this.signature = state.match_id;
      this.build(state);
    }
    for (const box of state.boxes) {
      const group = this.boxes.get(box.box_id);
      group.position.set(box.pose.x_m, box.pose.y_m, 0);
      group.rotation.z = box.pose.yaw_rad;
    }
    for (const [code, {lens, led}] of this.receivers) {
      const signal = state.facility_signals?.[code] || 'idle';
      const color = {idle: 0x290f0d, receiving: 0xff940d, hit: 0xff0508}[signal];
      led.material.color.setHex(color);
      led.material.emissive.setHex(signal === 'idle' ? 0 : color);
      lens.material.color.setHex(signal === 'idle' ? 0x7b91a1 : color);
    }
    for (const [slot, r] of Object.entries(state.robots)) {
      const {group, body, label, color, model} = this.robots.get(slot), p = r.pose;
      group.position.set(p.x_m, p.y_m, 0);
      group.rotation.z = p.yaw_rad;
      label.position.set(p.x_m, p.y_m, .45);
      if (body) { body.material.color.setHex(r.hp ? color : 0x606b7b); body.material.emissive.setHex(slot === selected ? 0x1e4940 : 0); }
      if (model) updateRobot(model,r,state.render_geometry);
    }
    for (const line of [...this.lasers.children]) { line.geometry.dispose(); line.material.dispose(); this.lasers.remove(line); }
    for (const ray of state.laser_segments || []) {
      const line=new T.Line(new T.BufferGeometry().setFromPoints([new T.Vector3(...ray.start),new T.Vector3(...ray.end)]),
        new T.LineBasicMaterial({color:0xff3030,transparent:true,opacity:.75}));
      line.name=`${ray.slot}/laser-guide`;this.lasers.add(line);
    }
    this.render();
  }

  render() {
    const w = this.element.clientWidth, h = this.element.clientHeight;
    if (!w || !h || !this.center) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    const focused=this.focusSlot && this.lastState?.robots[this.focusSlot]?.pose;
    const [x, y] = focused ? [focused.x_m,focused.y_m] : this.center, d = this.distance, z=focused ? .16 : 0;
    this.camera.position.set(x + d * Math.cos(this.angle) * Math.cos(this.pitch),
      y + d * Math.sin(this.angle) * Math.cos(this.pitch), z+d * Math.sin(this.pitch));
    this.camera.lookAt(x, y, z);
    this.renderer.render(this.scene, this.camera);
  }
}
