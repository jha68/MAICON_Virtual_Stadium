import * as T from './vendor/three.module.min.js';

// Indexed geometry comes from core.robot_model, also used by TinyRenderer.
export function buildRobot(parent, manifest, slot) {
  const frames = new Map(), devices = new Map();
  for (const spec of manifest.models[slot.at(-1)]) {
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.Float32BufferAttribute(spec.vertices.flat(), 3));
    geometry.setIndex(spec.faces.flat());
    geometry.computeVertexNormals();
    const rgb = spec.color === 'camp' ? (slot[0] === 'B' ? [.08,.24,.78] : [.8,.035,.045]) : manifest.palette[spec.color];
    const material = new T.MeshStandardMaterial({color: new T.Color().setRGB(...rgb.slice(0,3), T.SRGBColorSpace),
      roughness: spec.color === 'glass' ? .18 : .72, metalness: ['metal','silver'].includes(spec.color) ? .5 : .08,
      flatShading: spec.name.startsWith('receiver')});
    const mesh = new T.Mesh(geometry, material);
    mesh.name = `${slot}/${spec.name}`;
    let frame = frames.get(spec.frame);
    if (!frame) { frame = new T.Group(); frames.set(spec.frame, frame); parent.add(frame); }
    if (spec.frame.startsWith('wheel')) {
      frame.position.fromArray(spec.origin);
    } else mesh.position.fromArray(spec.origin);
    frame.add(mesh); devices.set(spec.name, mesh);
  }
  return {frames, devices, manifest, angles: [0,0], previous: null};
}

export function updateRobot(model, r, g) {
  const {frames, devices, manifest} = model, p = r.pose;
  const head = frames.get('gimbal');
  head.position.fromArray(g.gimbal_pivot_m);
  head.quaternion.setFromEuler(new T.Euler(0, -r.tilt * .15 * Math.PI/180, -r.pan * .5 * Math.PI/180, 'ZYX'));
  if (model.previous) {
    const q = model.previous;
    const turn = Math.atan2(Math.sin(p.yaw_rad-q.yaw_rad), Math.cos(p.yaw_rad-q.yaw_rad));
    const distance = (p.x_m-q.x_m)*Math.cos(p.yaw_rad-turn/2)+(p.y_m-q.y_m)*Math.sin(p.yaw_rad-turn/2);
    model.angles[0] += (distance-turn*manifest.axle_width_m/2)/manifest.wheel_radius_m;
    model.angles[1] += (distance+turn*manifest.axle_width_m/2)/manifest.wheel_radius_m;
  }
  model.previous = {...p};
  for (const [name, frame] of frames) if (name.startsWith('wheel')) frame.rotation.y = model.angles[Number(name[5])];
  const hp = [0xff1010,0xff6b10,0xffe610,0x14ee20,0x1440ff][Math.max(0,Math.min(4,r.hp))];
  for (const [name, mesh] of devices) {
    if (name.startsWith('hp_led')) { mesh.material.color.setHex(hp); mesh.material.emissive.setHex(hp); mesh.material.emissiveIntensity=.35; }
    if (name.startsWith('ammo_led')) mesh.material.color.setHex(Number(name.slice(8)) < r.ammo ? 0x28d928 : 0x141a14);
  }
}
